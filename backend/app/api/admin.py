"""Admin router — sovereign toggle + node self-registration (06 §2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_admin_token
from app.config import settings
from app.events import E, emit
from app.fleet import manager

router = APIRouter(tags=["admin"])


@router.post("/admin/sovereign", dependencies=[Depends(require_admin_token)])
async def set_sovereign(body: dict) -> dict:
    enabled = bool(body.get("enabled"))
    object.__setattr__(settings, "sovereign_default", enabled)
    await emit("system", E.SYSTEM_NOTICE,
               {"text": f"Sovereign Mode {'ON' if enabled else 'OFF'} (global)", "level": "info",
                "sovereign": enabled})
    return {"sovereign_default": enabled}


@router.post("/admin/nodes/register", dependencies=[Depends(require_admin_token)])
async def register_node(body: dict) -> dict:
    node_id = await manager.register(name=body.get("name", "A"), ip=body.get("ip", "127.0.0.1"),
                                     gpus=body.get("gpus", []), seats=body.get("seats"))
    return {"node_id": node_id}


@router.post("/admin/nodes/{node_id}/drain", dependencies=[Depends(require_admin_token)])
async def drain_node(node_id: str) -> dict:
    await manager.drain(node_id)
    return {"ok": True}
