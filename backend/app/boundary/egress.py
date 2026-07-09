"""Egress ledger + the single wrapped outbound HTTP client (01 §3).

All outbound HTTP from the control plane goes through `http_client`; every model dispatch (real or
mock) records an `egress_log` row via `record()` — the network monitor is a query, not a screenshot.
`record()` is called by the router (02 §4), which is the one place that knows a call's zone/seat/scope.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.db.engine import db
from app.events import E, emit
from app.ids import new_id

# shared outbound client for the real backend adapters (vLLM / Fireworks). Anthropic SDK is handed
# this same client so every byte still leaves through one place.
http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))


async def aclose() -> None:
    await http_client.aclose()


def host_of(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


async def record(
    *,
    scope: str,
    host: str,
    zone: str,
    seat: str,
    bytes_out: int,
    bytes_in: int,
    sovereign_violation: bool = False,
) -> None:
    """Write one egress ledger row and emit the network-monitor event."""
    await db.execute(
        "INSERT INTO egress_log (id, ts, scope, host, zone, seat, bytes_out, bytes_in, "
        "sovereign_violation) VALUES (:id, datetime('now'), :scope, :host, :zone, :seat, :bo, :bi, :sv)",
        {
            "id": new_id("egress"), "scope": scope, "host": host, "zone": zone, "seat": seat,
            "bo": bytes_out, "bi": bytes_in, "sv": 1 if sovereign_violation else 0,
        },
    )
    payload = {"host": host, "zone": zone, "seat": seat, "bytes_out": bytes_out, "bytes_in": bytes_in}
    if sovereign_violation:
        await emit(scope, E.EGRESS_VIOLATION, {**payload, "detail": "EXTERNAL egress in Sovereign Mode"})
    else:
        await emit(scope, E.EGRESS_REQUEST, payload)
