"""Model-proxy (06 §4) — the only network egress a process-runtime container has. Body
{seat, messages, schema?}, header X-Process-Token (claims: process id + allowed seats from the
manifest BoM). The router enforces the seat allowlist + data class + budgets exactly as internal
calls; meter scope = the process.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

from app.boundary.proxy_token import verify_token
from app.db import dao
from app.models.router import router as model_router
from app.seats.base import Message

router = APIRouter(tags=["proxy"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


async def _allowed_seats(process_id: str) -> list[str]:
    process = await dao.get_process(process_id)
    if not process:
        return []
    version = await dao.get_version(process_id, process["current_version"])
    if not version or not version.get("package_path"):
        return []
    manifest_path = Path(version["package_path"]) / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        return json.loads(manifest_path.read_text()).get("seats", [])
    except (json.JSONDecodeError, OSError):
        return []


@router.post("/proxy/complete")
async def proxy_complete(body: dict, x_process_token: str | None = Header(default=None)) -> dict:
    if not x_process_token:
        raise _err(401, "X-Process-Token required")
    claims = verify_token(x_process_token)
    if not claims:
        raise _err(401, "invalid or expired process token")
    process_id = claims.get("process", "")
    process = await dao.get_process(process_id)
    if not process:
        raise _err(401, "unknown process")
    seat = body.get("seat", "")
    if not seat:
        raise _err(400, "seat is required")
    if seat not in (claims.get("seats") or []):
        raise _err(403, f"seat {seat!r} not in this token's allowlist")
    allowed = await _allowed_seats(process_id)
    if allowed and seat not in allowed:   # manifest BoM allowlist — defense in depth
        raise _err(403, f"seat {seat!r} not in this process's BoM allowlist {allowed}")
    messages = [Message(role=m.get("role", "user"), content=m.get("content", ""))
                for m in body.get("messages", [])]
    comp = await model_router.complete(seat, messages, scope=f"process:{process_id}",
                                       data_class="RAW", schema=body.get("schema"))
    return {"text": comp.text, "parsed": comp.parsed, "usage": comp.usage}
