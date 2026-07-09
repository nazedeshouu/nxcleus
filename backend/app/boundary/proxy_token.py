"""Per-process signed proxy token (P3, 01 §5 / 04 §3).

Generated code never holds a model key; it calls the control-plane model-proxy, which dispatches to
the process's ALLOWED seats on its behalf. That call is gated by a compact HMAC token scoped to one
`process` id + a seat allowlist, so a token minted for process A cannot drive seats for process B
(the inspector's wrong-tenant probe, 08 §3, exercises exactly this boundary). The signing key is
derived from `ADMIN_TOKEN`; absent one, a stable dev key keeps local runs working.

Format: `<b64url(claims)>.<b64url(hmac_sha256)>` — self-contained, no server-side store.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.config import settings


def _key() -> bytes:
    seed = (settings.admin_token or "nxcleus-dev-proxy-key").encode()
    return hashlib.sha256(b"nxcleus:proxy-token:v1:" + seed).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_token(process_id: str, allowed_seats: list[str], *, ttl_s: int = 3600) -> str:
    claims = {"process": process_id, "seats": list(allowed_seats), "exp": int(time.time()) + ttl_s}
    body = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    mac = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def verify_token(token: str) -> dict | None:
    """Return the claims dict if the token is authentic and unexpired, else None. Never raises."""
    try:
        body, mac = token.split(".", 1)
        expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(mac, expected):
            return None
        claims = json.loads(_unb64(body))
        if int(claims.get("exp", 0)) < int(time.time()):
            return None
        return claims
    except Exception:
        return None


def seat_allowed(claims: dict | None, process_id: str, seat: str) -> bool:
    """The full gate: authentic token, right process, seat in the allowlist."""
    return bool(claims) and claims.get("process") == process_id and seat in (claims.get("seats") or [])
