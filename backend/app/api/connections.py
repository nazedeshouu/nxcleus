"""BYOK connections, custom models, seat rebinding, and the merged model registry (06 §2, 02 §8).
Keys are write-only: stored encrypted, surfaced masked, never serialized into events/logs/packages.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_demo_token
from app.boundary import secrets
from app.boundary.egress import host_of
from app.db import dao
from app.events import E, emit
from app.models.registry import registry

router = APIRouter(tags=["config"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.get("/models")
async def list_models() -> dict:
    """Merged registry: builtin models.yaml entries + runtime custom models, with capability flags."""
    builtin = [{"key": k, "source": "builtin", **v} for k, v in registry.merged_models().items()]
    custom = [{"key": m["id"], "source": "custom", "connection_id": m["connection_id"],
               "display_name": m["display_name"], "provider_model_id": m["provider_model_id"],
               "flags": m.get("flags", []), "context_len": m.get("context_len")}
              for m in await dao.list_custom_models()]
    seats = {name: {"data_class_max": sd.data_class_max,
                    "default": sd.default.model if sd.default else None,
                    "pool": [b.model for b in sd.pool]}
             for name, sd in registry.seats.items()}
    return {"models": builtin + custom, "seats": seats, "overrides": await dao.list_seat_overrides()}


@router.post("/connections", dependencies=[Depends(require_demo_token)])
async def create_connection(body: dict) -> dict:
    name = body.get("name", "")
    base_url = body.get("base_url", "")
    api_key = body.get("api_key", "")
    if not (name and base_url and api_key):
        raise _err(400, "name, base_url, api_key required")
    key_ref = await secrets.store_secret(api_key)
    cid = await dao.create_connection(name=name, base_url=base_url, api_key_ref=key_ref,
                                      data_class_ceiling=body.get("data_class_ceiling", "SANITIZED"),
                                      counts_as_local=bool(body.get("counts_as_local")))
    await emit("system", E.CONFIG_CONNECTION_ADDED, {"name": name, "host": host_of(base_url),
                                                     "ceiling": body.get("data_class_ceiling", "SANITIZED")})
    return {"connection": {"id": cid, "name": name, "base_url": base_url,
                           "api_key": secrets.mask(api_key)}}


@router.get("/connections")
async def list_connections() -> dict:
    rows = await dao.list_connections()
    return {"connections": [{"id": r["id"], "name": r["name"], "base_url": r["base_url"],
                             "zone": r["zone"], "data_class_ceiling": r["data_class_ceiling"],
                             "counts_as_local": bool(r["counts_as_local"]), "api_key": "••••"}
                            for r in rows]}


@router.delete("/connections/{connection_id}", dependencies=[Depends(require_demo_token)])
async def delete_connection(connection_id: str) -> dict:
    await dao.delete_connection(connection_id)
    return {"ok": True}


@router.post("/connections/{connection_id}/models", dependencies=[Depends(require_demo_token)])
async def add_model(connection_id: str, body: dict) -> dict:
    if not await dao.get_connection(connection_id):
        raise _err(404, "connection not found")
    mid = await dao.add_custom_model(connection_id=connection_id,
                                     provider_model_id=body.get("provider_model_id", ""),
                                     display_name=body.get("display_name", ""),
                                     flags=body.get("flags", []),
                                     context_len=body.get("context_len", 0))
    await emit("system", E.CONFIG_MODEL_REGISTERED, {"model": body.get("display_name", ""),
                                                     "flags": body.get("flags", [])})
    return {"model_id": mid}


@router.put("/seats/{seat}/binding", dependencies=[Depends(require_demo_token)])
async def bind_seat(seat: str, body: dict) -> dict:
    if seat not in registry.seats:
        raise _err(404, "unknown seat")
    model_key = body.get("model_key", "")
    scope = body.get("scope", "global")
    sd = registry.seats[seat]

    # eligibility (02 §8.2): a RAW seat needs a LOCAL or RAW-attested connection
    custom = next((m for m in await dao.list_custom_models() if m["id"] == model_key), None)
    if custom:
        conn = await dao.get_connection(custom["connection_id"])
        if sd.data_class_max == "RAW" and conn and conn["data_class_ceiling"] != "RAW":
            raise _err(409, f"seat {seat} needs RAW clearance; connection ceiling is "
                            f"{conn['data_class_ceiling']} (attest the boundary to raise it)")
    await dao.set_seat_override(seat=seat, model_key=model_key, scope=scope)
    await emit("system", E.CONFIG_SEAT_BOUND, {"seat": seat, "model_key": model_key, "scope": scope})
    return {"seat": seat, "model_key": model_key, "scope": scope}
