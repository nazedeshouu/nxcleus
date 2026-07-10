"""Nxcleus control plane — FastAPI app factory + lifespan (01 §5). The orchestrator engine runs as
asyncio tasks inside this single API process (07 §1): one writer to SQLite, no IPC.
"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    admin,
    connections,
    economics,
    fleet,
    jobs,
    processes,
    proxy,
    runs,
    sandbox,
    traces,
)
from app.boundary import egress
from app.boundary.errors import BoundaryViolation, BudgetExceeded, SovereignViolation
from app.config import settings
from app.db.engine import db
from app.events import replay
from app.fleet.manager import poll_loop
from app.orchestrator.engine import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.admin_token and settings.model_mode != "mock":
        import sys
        print("[auth] WARNING: ADMIN_TOKEN is empty in non-mock mode — every demo/admin write "
              "endpoint is OPEN. Set a real token before judging.", file=sys.stderr)
    await db.connect()
    await db.apply_schema()
    await engine.start()
    poll_task = asyncio.create_task(poll_loop())
    try:
        yield
    finally:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task
        await engine.stop()
        await egress.aclose()
        await db.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(title="Nxcleus — adaptive sovereign process platform",
                  description="Control plane API + event catalog (specs 06). Every token is generated "
                              "on AMD silicon; only the sanitized planner brief ever leaves the boundary.",
                  version="0.1.0", lifespan=lifespan)

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["*"])

    for r in (jobs.router, processes.router, runs.router, fleet.router, sandbox.router,
              admin.router, economics.router, connections.router, proxy.router, traces.router):
        app.include_router(r, prefix="/api")

    @app.exception_handler(StarletteHTTPException)
    async def _http_err(_: Request, exc: StarletteHTTPException):
        # spec 06 §1 envelope is top-level {"error": {...}} — FastAPI's default wraps detail as
        # {"detail": ...}, which every client error path would misparse
        detail = exc.detail
        content = detail if isinstance(detail, dict) and "error" in detail \
            else {"error": {"code": exc.status_code, "message": str(detail)}}
        return JSONResponse(status_code=exc.status_code, content=content,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(BoundaryViolation)
    async def _boundary(_: Request, exc: BoundaryViolation):
        return JSONResponse(status_code=422, content={"error": {"code": "boundary_violation",
                                                                 "message": str(exc)}})

    @app.exception_handler(SovereignViolation)
    async def _sovereign(_: Request, exc: SovereignViolation):
        return JSONResponse(status_code=422, content={"error": {"code": "sovereign_violation",
                                                                 "message": str(exc)}})

    @app.exception_handler(BudgetExceeded)
    async def _budget(_: Request, exc: BudgetExceeded):
        return JSONResponse(status_code=429, content={"error": {"code": "budget_exceeded",
                                                                "message": str(exc)}})

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name, "model_mode": settings.model_mode}

    @app.get("/api/config/public")
    async def config_public() -> dict:
        from app.fleet import health

        ready = health.ready_node_names()
        # fleet profile inference (02 §5): no nodes -> P0 fallback; else P2 demo standard
        profile = "P0" if not ready else "P2"
        fallback_serving = (not ready) and settings.model_mode != "mock"
        # frontend contract (06 §3 ruling) + retained safe_summary fields (additive)
        return {
            "sovereign": settings.sovereign_default,
            "fallback_serving": fallback_serving,
            "profile": profile,
            "demo": not bool(settings.admin_token),   # presenter controls open when no token set
            **settings.safe_summary(),
        }

    @app.get("/api/replay/{scope:path}")
    async def replay_scope(scope: str, from_seq: int = 0) -> dict:
        return {"scope": scope, "events": await replay(scope, from_seq)}

    return app


app = create_app()
