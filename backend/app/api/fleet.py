"""Fleet + egress router — the AMD-usage demo surfaces (06 §2)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.sse import sse_response
from app.db import dao

router = APIRouter(tags=["fleet"])


@router.get("/fleet")
async def get_fleet() -> dict:
    return {"nodes": await dao.list_nodes()}


@router.get("/fleet/telemetry")
async def fleet_telemetry(request: Request, from_seq: int = 0):
    return await sse_response(request, scope="fleet", from_seq=from_seq)


@router.get("/egress")
async def egress(scope: str | None = None, zone: str | None = None) -> dict:
    return {"egress": await dao.list_egress(scope=scope, zone=zone)}


@router.get("/egress/stream")
async def egress_stream(request: Request, from_seq: int = 0):
    return await sse_response(request, type_prefix="egress.", from_seq=from_seq)
