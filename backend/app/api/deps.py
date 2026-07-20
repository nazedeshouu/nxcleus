"""API auth dependencies (06 §1). Deliberate hackathon-grade model:
- public read: all GETs + SSE unauthenticated;
- demo writes: a valid login session (any role) OR X-Demo-Token == ADMIN_TOKEN;
- admin/node: a login session with role==admin OR X-Admin-Token == ADMIN_TOKEN;
- sandbox writes: anonymous sandbox_session cookie.
When auth is OFF (no login password set) the token behavior is legacy: empty ADMIN_TOKEN => open (dev).
When auth is ON a session is required for writes unless a matching token header is presented.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request, Response

from app.config import settings
from app.ids import new_id


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


async def require_demo_token(request: Request, x_demo_token: str | None = Header(default=None)) -> None:
    # Lazy import avoids a cycle: auth imports _err from this module.
    from app.api.auth import read_session

    if read_session(request):
        return  # any authenticated user may perform demo-level writes
    if settings.admin_token and x_demo_token == settings.admin_token:
        return  # legacy presenter token (unchanged; keeps BYOK's token path working)
    if settings.auth_enabled or settings.admin_token:
        raise _err(401, "login required (session cookie or X-Demo-Token)")
    # dev default: no auth, no token configured => writes open


async def require_admin_token(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    from app.api.auth import read_session

    sess = read_session(request)
    if sess:
        if sess.get("role") == "admin":
            return
        raise _err(403, "admin privileges required")  # e.g. a judge session on an admin-only op
    if settings.admin_token and x_admin_token == settings.admin_token:
        return
    if settings.auth_enabled or settings.admin_token:
        raise _err(401, "admin login required (session cookie or X-Admin-Token)")
    # dev default: open


async def sandbox_session(request: Request, response: Response) -> str:
    sid = request.cookies.get("sandbox_session")
    if not sid:
        sid = new_id("sandbox_session")
        response.set_cookie("sandbox_session", sid, httponly=True, samesite="lax", max_age=86400)
    return sid


def client_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}"
