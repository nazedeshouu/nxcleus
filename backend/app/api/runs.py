"""Runs / units / tickets router (06 §2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_demo_token
from app.api.sse import sse_response
from app.db import dao
from app.events import E, emit

router = APIRouter(tags=["runs"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = await dao.get_run(run_id)
    if not run:
        raise _err(404, "run not found")
    return {"run": run}


@router.get("/runs/{run_id}/units")
async def get_units(run_id: str, status: str | None = None, page: int = 0, page_size: int = 100) -> dict:
    return {"units": await dao.list_run_units(run_id, status=status, limit=page_size,
                                              offset=page * page_size)}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, from_seq: int = 0):
    return await sse_response(request, scope=f"run:{run_id}", from_seq=from_seq)


@router.post("/units/{unit_id}/review", dependencies=[Depends(require_demo_token)])
async def review_unit(unit_id: str, body: dict) -> dict:
    verdict = body.get("verdict", "approve")
    await dao.review_unit(unit_id, verdict, body.get("note", ""))
    await emit("system", E.REVIEW_DECIDED, {"unit": unit_id, "verdict": verdict})
    return {"ok": True, "unit_id": unit_id, "verdict": verdict}


@router.get("/tickets")
async def list_tickets(scope: str | None = None, status: str | None = None,
                       source: str | None = None) -> dict:
    return {"tickets": await dao.list_tickets(scope=scope, status=status, source=source)}
