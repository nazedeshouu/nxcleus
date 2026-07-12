"""Real login for the public showcase (06 §1 extension). Cookie-session auth, custom + stdlib-only.

Design (deliberate hackathon scope):
- env users only — `admin` (role admin) and `judge` (role judge), passwords from settings.
  # ponytail: env users, real user store when multi-tenant.
- session = an httpOnly signed cookie `nx_session` carrying `username|role|expiry`, HMAC-SHA256 signed.
  itsdangerous isn't installed here, so we sign with stdlib hmac — same guarantee (tamper-evident,
  not encrypted; the payload is non-secret).
- BOTH passwords unset => auth DISABLED: /auth/me reports a synthetic dev session and the write gates
  keep their legacy X-Demo-Token behavior (see deps.py). Setting either password turns the wall on.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import _err
from app.config import settings

router = APIRouter(tags=["auth"])

COOKIE = "nx_session"
_MAX_AGE = 7 * 86400  # 7-day session
# random-at-boot fallback signing key: used only when neither AUTH_SECRET nor ADMIN_TOKEN is set.
# Consequence: restarting the process invalidates existing sessions (users re-login). Acceptable.
_BOOT_SECRET = secrets.token_hex(32)


def _secret() -> bytes:
    return (settings.auth_secret or settings.admin_token or _BOOT_SECRET).encode()


def _sign(payload: str) -> str:
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify(token: str) -> dict | None:
    payload, _, sig = token.rpartition(".")
    if not sig:
        return None
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        username, role, exp = payload.split("|")
    except ValueError:
        return None
    if int(exp) < int(time.time()):
        return None
    return {"username": username, "role": role}


def read_session(request: Request) -> dict | None:
    """Verified {username, role} from the cookie, or None. Imported by deps.py's write gates."""
    tok = request.cookies.get(COOKIE)
    return _verify(tok) if tok else None


def _users() -> dict[str, tuple[str, str]]:
    """username -> (role, password), only for configured passwords."""
    u: dict[str, tuple[str, str]] = {}
    if settings.auth_admin_password:
        u["admin"] = ("admin", settings.auth_admin_password)
    if settings.auth_judge_password:
        u["judge"] = ("judge", settings.auth_judge_password)
    return u


def _authenticate(username: str, password: str) -> str | None:
    """Return the role on success, else None. Constant-time compare; runs even when the user is
    unknown so login timing doesn't leak which usernames exist."""
    entry = _users().get(username)
    role, expected = entry if entry else ("", "\x00nope")
    ok = hmac.compare_digest(password, expected)
    return role if (entry and ok) else None


def _is_https(request: Request) -> bool:
    # Caddy terminates TLS and forwards; trust the scheme or the forwarded-proto it sets.
    return request.url.scheme == "https" or \
        request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    role = _authenticate(body.username, body.password)
    if not role:
        raise _err(401, "invalid username or password")
    exp = int(time.time()) + _MAX_AGE
    token = _sign(f"{body.username}|{role}|{exp}")
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                        secure=_is_https(request), max_age=_MAX_AGE, path="/")
    return {"username": body.username, "role": role, "auth_enabled": True}


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request) -> dict:
    # auth off => synthetic dev session so the SPA never shows a login wall in dev/mock.
    if not settings.auth_enabled:
        return {"username": "dev", "role": "admin", "auth_enabled": False}
    sess = read_session(request)
    if not sess:
        raise _err(401, "not authenticated")
    return {**sess, "auth_enabled": True}


if __name__ == "__main__":  # ponytail: smallest runnable check for the signing/session logic
    object.__setattr__(settings, "auth_secret", "k1")
    good = _sign("judge|judge|9999999999")
    assert _verify(good) == {"username": "judge", "role": "judge"}
    assert _verify(good + "x") is None, "tamper must fail"
    assert _verify(_sign("admin|admin|1")) is None, "expired must fail"
    object.__setattr__(settings, "auth_secret", "k2")
    assert _verify(good) is None, "wrong key must fail"
    object.__setattr__(settings, "auth_secret", "k1")
    object.__setattr__(settings, "auth_admin_password", "pw")
    object.__setattr__(settings, "auth_judge_password", "")
    assert _authenticate("admin", "pw") == "admin"
    assert _authenticate("admin", "bad") is None
    assert _authenticate("judge", "pw") is None, "unset user must fail"
    print("auth self-check ok")
