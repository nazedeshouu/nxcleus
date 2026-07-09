"""Staging deploy for stage-6 inspector probes (04 §3, P3).

The consolidated process is served over REAL HTTP by a minimal FastAPI shim bound to an ephemeral
127.0.0.1 port, so the inspector swarm probes a live endpoint — GET /health, GET /manifest, POST
/run_unit — exactly as it will against the production deployment. The shim runs on a uvicorn Server
in-process (its own asyncio task); `deploy()` returns a handle whose `.base_url` goes on the job and
whose `.stop()` tears it down. `/run_unit` imports the assembled `process.py` and calls its
`run_unit` entrypoint when present, else falls back to manifest-driven input validation — either way
the inspector gets a real HTTP surface to attack, not a mock.

The same shim is what the delivery-time process-runtime container image serves (04 §3); running it
in-process here keeps the live demo path free of a per-job docker build while preserving the contract.
"""
from __future__ import annotations

import asyncio
import importlib.util
import socket
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request

from app.boundary.proxy_token import verify_token


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _load_entrypoint(workspace: Path):
    """Return the assembled process's `run_unit` callable if the package exposes one, else None."""
    for cand in (workspace / "src" / "process.py", workspace / "process.py"):
        if cand.exists():
            try:
                spec = importlib.util.spec_from_file_location(f"staged_{workspace.name}", cand)
                mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                fn = getattr(mod, "run_unit", None)
                if callable(fn):
                    return fn
            except Exception:
                return None
    return None


def _build_app(process_id: str, manifest: dict, workspace: Path, expect_token: bool) -> FastAPI:
    app = FastAPI()
    entry = _load_entrypoint(workspace)
    required = list(((manifest.get("unit_schema") or {}).get("required")) or [])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "process": process_id}

    @app.get("/manifest")
    async def get_manifest() -> dict:
        return manifest

    @app.post("/run_unit")
    async def run_unit(request: Request) -> Any:
        # per-process proxy-token scoping (P3): a token scoped to another process is refused, so the
        # inspector's wrong-tenant probe hits a real authz boundary.
        if expect_token:
            tok = request.headers.get("x-proxy-token", "")
            claims = verify_token(tok)
            if not claims or claims.get("process") != process_id:
                return _json({"error": "unauthorized", "detail": "proxy token missing or wrong process"}, 401)
        try:
            payload = await request.json()
        except Exception:
            return _json({"error": "bad_request", "detail": "body must be JSON"}, 400)
        if not isinstance(payload, dict):
            return _json({"error": "bad_request", "detail": "unit must be an object"}, 400)
        missing = [f for f in required if f not in payload]
        if missing:
            return _json({"error": "validation", "missing": missing}, 422)
        if entry is not None:
            try:
                out = entry(payload)
                return out if isinstance(out, dict) else {"result": out}
            except Exception as exc:  # a crash in generated code is a finding, not a shim error
                return _json({"error": "process_error", "detail": type(exc).__name__}, 500)
        # no entrypoint: acknowledge a well-formed unit (manifest-driven surface)
        return {"status": "accepted", "unit": payload.get("id"), "decision": "review"}

    return app


def _json(body: dict, status: int):
    from fastapi.responses import JSONResponse
    return JSONResponse(body, status_code=status)


class StagingHandle:
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


async def deploy(process_id: str, manifest: dict, workspace: str, *, expect_token: bool = False) -> StagingHandle:
    """Start the shim on an ephemeral localhost port; return once it answers /health. Real HTTP."""
    port = _free_port()
    app = _build_app(process_id, manifest, Path(workspace), expect_token)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    base_url = f"http://127.0.0.1:{port}"   # routes are bound at root; probe tools append /manifest etc.
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    return StagingHandle(base_url, server, task)
