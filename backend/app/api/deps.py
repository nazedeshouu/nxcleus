"""API auth dependencies (06 §1). Deliberate hackathon-grade model:
- public read: all GETs + SSE unauthenticated;
- demo writes: X-Demo-Token == ADMIN_TOKEN (presenter-only). Empty ADMIN_TOKEN => open (dev);
- admin/node: X-Admin-Token == ADMIN_TOKEN;
- sandbox writes: anonymous sandbox_session cookie.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request, Response

from app.config import settings
from app.ids import new_id


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


async def require_demo_token(x_demo_token: str | None = Header(default=None)) -> None:
    if settings.admin_token and x_demo_token != settings.admin_token:
        raise _err(401, "demo token required (X-Demo-Token)")


async def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise _err(401, "admin token required (X-Admin-Token)")


async def sandbox_session(request: Request, response: Response) -> str:
    sid = request.cookies.get("sandbox_session")
    if not sid:
        sid = new_id("sandbox_session")
        response.set_cookie("sandbox_session", sid, httponly=True, samesite="lax", max_age=86400)
    return sid


def client_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}"
