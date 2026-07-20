"""Honest demo staging HTTP surface for generated processes.

Generated ``process.py`` is statically preflighted in the control plane and executed only by a
trusted JSON-protocol subprocess worker. It is never imported or executed in the FastAPI process.

This is intentionally named ``unsafe-demo-subprocess``: process separation protects control-plane
Python state, but the child still has the host user's filesystem and network privileges. Production
must use a low-privilege, network-restricted container or an equivalent isolation boundary.
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, Request

from app.boundary.proxy_token import verify_token
from app.config import settings
from app.safe_paths import UnsafePathError, resolve_within

EXECUTION_MODE = "unsafe-demo-subprocess"
_ALLOWED_STATUSES = {"ok", "needs_review", "error"}
_WORKER_TIMEOUT_S = 5.0
_WORKER_SCRIPT = Path(__file__).with_name("process_worker.py").resolve()


class StagingDeployError(RuntimeError):
    """The generated package cannot honestly be deployed to the demo runtime."""


@dataclass(frozen=True)
class Entrypoint:
    path: Path
    workspace: Path
    contract: Literal["process-class-async", "legacy-function"]


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _positional_count(arguments: ast.arguments) -> int:
    return len(arguments.posonlyargs) + len(arguments.args)


def _matches_call_shape(arguments: ast.arguments, positional: int) -> bool:
    required_keyword_only = any(default is None for default in arguments.kw_defaults)
    return _positional_count(arguments) == positional and not required_keyword_only


def _preflight_entrypoint(workspace: Path) -> Entrypoint:
    """UTF-8/AST-only contract validation. Never imports generated code."""
    root = workspace.resolve(strict=False)
    selected: tuple[str, Path] | None = None
    for relative in ("src/process.py", "process.py"):
        raw = root / relative
        if raw.exists() or raw.is_symlink():
            try:
                selected = (relative, resolve_within(root, relative))
            except UnsafePathError as exc:
                raise StagingDeployError(f"entrypoint path rejected: {exc}") from None
            break
    if selected is None:
        raise StagingDeployError("generated package has no src/process.py or process.py entrypoint")

    relative, path = selected
    if not path.is_file():
        raise StagingDeployError(f"generated entrypoint {relative} is not a regular file")
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StagingDeployError(
            f"generated entrypoint {relative} is not readable UTF-8: {type(exc).__name__}") from None
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        raise StagingDeployError(
            f"generated entrypoint {relative} has invalid Python syntax at line {exc.lineno}") from None

    process_class = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Process"),
        None,
    )
    if process_class is not None:
        method = next(
            (node for node in process_class.body
             if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_unit"),
            None,
        )
        if method is None or not _matches_call_shape(method.args, 3):
            raise StagingDeployError(
                "Process contract requires async run_unit(self, unit, ctx)")
        return Entrypoint(path=path, workspace=root, contract="process-class-async")

    legacy = next(
        (node for node in tree.body
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run_unit"),
        None,
    )
    if legacy is None or not _matches_call_shape(legacy.args, 1):
        raise StagingDeployError("entrypoint requires class Process or top-level run_unit(unit)")
    return Entrypoint(path=path, workspace=root, contract="legacy-function")


def _worker_environment() -> dict[str, str]:
    # Keep only OS bootstrap/temp values; provider tokens, admin tokens, database URLs, and user
    # environment do not cross the protocol boundary.
    allowed = ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "TEMP", "TMP", "TMPDIR")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return env


def _runtime_error(code: str, detail: str) -> dict:
    return {"status": "error", "output": {"error": code, "detail": detail}, "trace": []}


async def _terminate_worker(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
    except TimeoutError:
        pass


async def _run_worker(entrypoint: Entrypoint, unit: dict) -> tuple[dict, int]:
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(_WORKER_SCRIPT),
            str(entrypoint.path),
            str(entrypoint.workspace),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(entrypoint.workspace),
            env=_worker_environment(),
            **kwargs,
        )
    except (OSError, ValueError) as exc:
        return _runtime_error("worker_start_failed", type(exc).__name__), 500

    request = json.dumps({"unit": unit}, ensure_ascii=False).encode("utf-8")
    try:
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(request), timeout=_WORKER_TIMEOUT_S)
    except TimeoutError:
        await _terminate_worker(process)
        return _runtime_error(
            "worker_timeout", f"run_unit exceeded {_WORKER_TIMEOUT_S:g}s"), 504
    except asyncio.CancelledError:
        await _terminate_worker(process)
        raise

    if process.returncode != 0:
        return _runtime_error("worker_crash", f"worker exited with code {process.returncode}"), 500
    try:
        lines = stdout.decode("utf-8").splitlines()
        result = json.loads(lines[-1]) if lines else None
    except (UnicodeError, json.JSONDecodeError):
        result = None
    if not isinstance(result, dict):
        return _runtime_error("worker_protocol", "worker returned invalid JSON"), 500
    if result.get("status") not in _ALLOWED_STATUSES or not isinstance(result.get("trace"), list):
        return _runtime_error("worker_protocol", "worker returned an invalid UnitResult"), 500
    return result, 500 if result["status"] == "error" else 200


def _with_mode(body: dict) -> dict:
    return {**body, "execution_mode": EXECUTION_MODE}


def _build_app(process_id: str, manifest: dict, entrypoint: Entrypoint,
               expect_token: bool) -> FastAPI:
    app = FastAPI()
    required = list(((manifest.get("unit_schema") or {}).get("required")) or [])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "process": process_id, "execution_mode": EXECUTION_MODE}

    @app.get("/manifest")
    async def get_manifest() -> dict:
        return {**manifest, "execution_mode": EXECUTION_MODE,
                "entrypoint_contract": entrypoint.contract}

    @app.post("/run_unit")
    async def run_unit(request: Request) -> Any:
        if expect_token:
            token = request.headers.get("x-proxy-token", "")
            claims = verify_token(token)
            if not claims or claims.get("process") != process_id:
                return _json(_with_mode({
                    "error": "unauthorized", "detail": "proxy token missing or wrong process",
                }), 401)
        try:
            payload = await request.json()
        except Exception:
            return _json(_with_mode({"error": "bad_request", "detail": "body must be JSON"}), 400)
        if not isinstance(payload, dict):
            return _json(_with_mode({"error": "bad_request", "detail": "unit must be an object"}),
                         400)
        missing = [field for field in required if field not in payload]
        if missing:
            return _json(_with_mode({"error": "validation", "missing": missing}), 422)

        result, status_code = await _run_worker(entrypoint, payload)
        body = _with_mode(result)
        return body if status_code == 200 else _json(body, status_code)

    return app


def _json(body: dict, status: int):
    from fastapi.responses import JSONResponse

    return JSONResponse(body, status_code=status)


class StagingHandle:
    execution_mode = EXECUTION_MODE

    def __init__(self, base_url: str, server: uvicorn.Server, task: asyncio.Task) -> None:
        self.base_url = base_url
        self._server = server
        self._task = task

    async def stop(self) -> None:
        self._server.should_exit = True
        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except (TimeoutError, asyncio.CancelledError):
            self._task.cancel()


async def deploy(process_id: str, manifest: dict, workspace: str, *,
                 expect_token: bool = False) -> StagingHandle:
    """Start the unsafe demo subprocess-backed HTTP shim after a fail-closed preflight."""
    if not settings.unsafe_demo_runtime or settings.model_mode != "mock":
        raise StagingDeployError(
            "generated execution is disabled; unsafe_demo_runtime requires MODEL_MODE=mock")
    entrypoint = _preflight_entrypoint(Path(workspace))
    port = _free_port()
    app = _build_app(process_id, manifest, entrypoint, expect_token)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                            loop="asyncio", access_log=False)
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        if task.done():
            try:
                await task
            except Exception as exc:
                raise StagingDeployError(f"staging server failed to start: {type(exc).__name__}") from exc
            raise StagingDeployError("staging server stopped before startup")
        await asyncio.sleep(0.05)
    if not server.started:
        server.should_exit = True
        task.cancel()
        raise StagingDeployError("staging server did not start within 5 seconds")
    return StagingHandle(f"http://127.0.0.1:{port}", server, task)
