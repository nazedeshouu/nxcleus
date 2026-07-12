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
import re
import secrets
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import _err
from app.config import settings
from app.db import dao

router = APIRouter(tags=["auth"])

COOKIE = "nx_session"
_MAX_AGE = 7 * 86400  # 7-day session
# random-at-boot fallback signing key: used only when neither AUTH_SECRET nor ADMIN_TOKEN is set.
# Consequence: restarting the process invalidates existing sessions (users re-login). Acceptable.
_BOOT_SECRET = secrets.token_hex(32)

# self-serve accounts ---------------------------------------------------------------------------
_RESERVED = {"admin", "judge"}                 # env-user names; a db signup may never shadow them
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")  # 3–32 chars, lowercased before match
_PW_MIN, _PW_MAX = 8, 1024                     # max caps scrypt cost against a giant-password DoS
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}         # ~16MB work factor, under OpenSSL's 32MB maxmem
# in-memory per-IP signup limiter — ponytail: in-memory limiter, move to redis if multi-process
_RATE_MAX, _RATE_WINDOW = 5, 3600.0            # 5 signups / hour / IP
_signup_hits: dict[str, list[float]] = {}


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT).hex()


def _verify_password(password: str, salt: bytes, expected_hex: str) -> bool:
    return hmac.compare_digest(_hash_password(password, salt), expected_hex)


def _client_ip(request: Request) -> str:
    # Caddy fronts the app and appends the real client to X-Forwarded-For; trust the first hop only.
    xff = request.headers.get("x-forwarded-for", "")
    if xff.strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_ok(ip: str) -> bool:
    """Record one signup attempt for ip; False once it exceeds the window budget."""
    now = time.time()
    hits = [t for t in _signup_hits.get(ip, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _signup_hits[ip] = hits
        return False
    hits.append(now)
    _signup_hits[ip] = hits
    return True


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


def _issue_session(response: Response, request: Request, username: str, role: str) -> None:
    exp = int(time.time()) + _MAX_AGE
    token = _sign(f"{username}|{role}|{exp}")
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                        secure=_is_https(request), max_age=_MAX_AGE, path="/")


class LoginBody(BaseModel):
    username: str
    password: str


class SignupBody(BaseModel):
    username: str
    password: str
    invite_code: str | None = None


@router.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    # env users first (exact 'admin'/'judge'), then the db users table (case-insensitive).
    role, username = _authenticate(body.username, body.password), body.username
    if not role:
        user = await dao.get_user(body.username)
        if user and _verify_password(body.password, bytes.fromhex(user["salt"]), user["password_hash"]):
            role, username = user["role"], user["username"]
    if not role:
        raise _err(401, "invalid username or password")
    _issue_session(response, request, username, role)
    return {"username": username, "role": role, "auth_enabled": True}


@router.post("/auth/signup")
async def signup(body: SignupBody, request: Request, response: Response) -> dict:
    if not settings.auth_enabled:
        # dev/mock deployments have no user store wall — /auth/me already reports a synthetic admin.
        raise _err(409, "self-serve signup is disabled on this deployment (auth is off)")
    if not _rate_ok(_client_ip(request)):
        raise _err(429, "too many signups from this address; try again later")
    if settings.auth_signup_code and not hmac.compare_digest(
            body.invite_code or "", settings.auth_signup_code):
        raise _err(403, "invalid invite code")
    username = body.username.strip().lower()
    if not _USERNAME_RE.match(username):
        raise _err(400, "username must be 3–32 chars: a–z, 0–9, '-', '_' (start alphanumeric)")
    if not (_PW_MIN <= len(body.password) <= _PW_MAX):
        raise _err(400, f"password must be {_PW_MIN}–{_PW_MAX} characters")
    if username in _RESERVED or await dao.get_user(username):
        raise _err(409, "username is taken")  # ponytail: UNIQUE index is the backstop for the TOCTOU race
    salt = secrets.token_bytes(16)
    await dao.create_user(username=username, password_hash=_hash_password(body.password, salt),
                          salt=salt.hex(), role="judge")
    _issue_session(response, request, username, "judge")
    return {"username": username, "role": "judge", "auth_enabled": True}


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
    salt = secrets.token_bytes(16)
    h = _hash_password("correct horse battery", salt)
    assert _verify_password("correct horse battery", salt, h), "round-trip must verify"
    assert not _verify_password("wrong", salt, h), "wrong password must fail"
    assert _USERNAME_RE.match("judge_01") and not _USERNAME_RE.match("ab"), "username rule"
    ip = "203.0.113.7"
    assert all(_rate_ok(ip) for _ in range(_RATE_MAX)) and not _rate_ok(ip), "limiter trips at cap"
    print("auth self-check ok")
