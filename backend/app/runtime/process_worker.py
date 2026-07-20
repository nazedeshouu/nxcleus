"""Trusted protocol worker for the explicitly unsafe demo generated-process runtime.

This child process prevents generated module imports and globals from executing in the FastAPI
interpreter. It is deliberately *not* a production security boundary: generated code still has the
host user's filesystem and network privileges. Production must replace it with a low-privilege,
network-restricted container or equivalent isolation.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_ALLOWED_STATUSES = {"ok", "needs_review", "error"}


class ProcessContext:
    """Minimal demo context. Only local trace logging is available in this executor."""

    def __init__(self) -> None:
        self.trace: list[dict] = []

    def log(self, event: str, **fields: Any) -> None:
        self.trace.append({"event": str(event), **fields})

    async def model(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("ctx.model is unavailable in the unsafe demo subprocess runtime")

    def connector(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("ctx.connector is unavailable in the unsafe demo subprocess runtime")


def _load_module(entrypoint: Path, workspace: Path) -> ModuleType:
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location("_generated_process", entrypoint)
    if spec is None or spec.loader is None:
        raise RuntimeError("generated entrypoint could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _invoke(module: ModuleType, unit: dict, ctx: ProcessContext) -> dict:
    process_class = getattr(module, "Process", None)
    if isinstance(process_class, type):
        target = process_class().run_unit
        raw = target(unit, ctx)
    else:
        target = getattr(module, "run_unit", None)
        if not callable(target):
            raise RuntimeError("generated entrypoint has no callable run_unit")
        raw = target(unit)
    if inspect.isawaitable(raw):
        raw = await raw
    return _normalize_result(raw, ctx)


def _normalize_result(raw: Any, ctx: ProcessContext) -> dict:
    if not isinstance(raw, dict):
        raise TypeError("run_unit must return a dict UnitResult")

    status = raw.get("status", "ok")
    if status not in _ALLOWED_STATUSES:
        raise ValueError("UnitResult.status must be ok, needs_review, or error")

    generated_trace = raw.get("trace", [])
    if not isinstance(generated_trace, list):
        raise TypeError("UnitResult.trace must be a list when provided")
    if "output" in raw:
        output = raw["output"]
    elif "status" in raw or "trace" in raw:
        output = {k: v for k, v in raw.items() if k not in {"status", "trace"}}
    else:
        output = raw  # legacy top-level run_unit(unit) compatibility
    return {"status": status, "output": output, "trace": [*generated_trace, *ctx.trace]}


async def _run(entrypoint: Path, workspace: Path, unit: dict) -> dict:
    ctx = ProcessContext()
    # Keep ordinary generated print() calls out of the JSON protocol. Direct fd writes remain one
    # reason this demo subprocess must not be represented as a sandbox.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        module = _load_module(entrypoint, workspace)
        return await _invoke(module, unit, ctx)


def _error(exc: BaseException) -> dict:
    detail = f"{type(exc).__name__}: {str(exc)[:240]}"
    return {"status": "error", "output": {"error": "process_exception", "detail": detail},
            "trace": []}


def main() -> int:
    try:
        if len(sys.argv) != 3:
            raise ValueError("worker requires entrypoint and workspace arguments")
        request = json.loads(sys.stdin.read())
        unit = request.get("unit") if isinstance(request, dict) else None
        if not isinstance(unit, dict):
            raise ValueError("worker request unit must be an object")
        result = asyncio.run(_run(Path(sys.argv[1]), Path(sys.argv[2]), unit))
        encoded = json.dumps(result, ensure_ascii=False)
    except BaseException as exc:  # generated SystemExit/KeyboardInterrupt must stay in the child
        encoded = json.dumps(_error(exc), ensure_ascii=False)
    sys.stdout.write(encoded + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
