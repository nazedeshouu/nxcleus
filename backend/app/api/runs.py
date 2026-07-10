"""Runs / units / tickets router (06 §2) + run deliverables (hardening 2026-07-10)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import require_demo_token
from app.api.sse import sse_response
from app.db import dao
from app.events import E, emit
from app.runtime import deliverables

router = APIRouter(tags=["runs"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = await dao.get_run(run_id)
    if not run:
        raise _err(404, "run not found")
    # contract: the RUN payload gains artifacts — readers use run.artifacts; the top-level
    # sibling is kept for anything already reading it
    run["artifacts"] = deliverables.existing_artifacts(run_id)
    return {"run": run, "artifacts": run["artifacts"]}


@router.get("/runs/{run_id}/report")
async def run_report(run_id: str):
    f = deliverables.run_dir(run_id) / "report.html"
    if not f.exists():
        raise _err(404, "no report for this run yet")
    return FileResponse(str(f), media_type="text/html")


@router.get("/runs/{run_id}/export.csv")
async def run_export_csv(run_id: str):
    f = deliverables.run_dir(run_id) / "findings.csv"
    if not f.exists():
        raise _err(404, "no findings export for this run yet")
    return FileResponse(str(f), media_type="text/csv", filename=f"findings-{run_id}.csv")


@router.get("/runs/{run_id}/units")
async def get_units(run_id: str, status: str | None = None, page: int = 0, page_size: int = 100) -> dict:
    return {"units": await dao.list_run_units(run_id, status=status, limit=page_size,
                                              offset=page * page_size)}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, from_seq: int = 0):
    return await sse_response(request, scope=f"run:{run_id}", from_seq=from_seq)


@router.post("/units/{unit_id}/review", dependencies=[Depends(require_demo_token)])
async def review_unit(unit_id: str, body: dict) -> dict:
    unit = await dao.get_run_unit(unit_id)
    if not unit:
        raise _err(404, "unit not found")
    verdict = body.get("verdict", "approve")
    await dao.review_unit(unit_id, verdict, body.get("note", ""))
    # the review queue listens on the run's stream — a system-scope emit never reaches it
    await emit(f"run:{unit['run_id']}", E.REVIEW_DECIDED, {"unit": unit_id, "verdict": verdict})
    return {"ok": True, "unit_id": unit_id, "verdict": verdict}


@router.get("/tickets")
async def list_tickets(scope: str | None = None, status: str | None = None,
                       source: str | None = None) -> dict:
    return {"tickets": await dao.list_tickets(scope=scope, status=status, source=source)}


# ---------------------------------------------------------------- next steps (hardening, M6)
@router.post("/runs/{run_id}/next-steps", dependencies=[Depends(require_demo_token)])
async def make_next_steps(run_id: str) -> dict:
    """One trust-seat call over the run's outcome; idempotent — cached on the run row."""
    run = await dao.get_run(run_id)
    if not run:
        raise _err(404, "run not found")
    if run.get("next_steps"):
        return {"next_steps": run["next_steps"], "cached": True}
    from app.models.router import router as model_router
    from app.orchestrator.seatlib import seat

    process = await dao.get_process(run.get("process_id") or "") or {}
    open_tickets = await dao.list_tickets(scope=f"process:{run.get('process_id')}", status="open")
    context = {
        "goal": process.get("goal", ""),
        "stats": run.get("stats") or {},
        "flagged": (run.get("stats") or {}).get("needs_review", 0),
        "open_tickets": len(open_tickets),
        "deliverable": (run.get("params") or {}).get("deliverable"),
    }

    async def _complete(seat_name, messages, **kw):
        return await model_router.complete(seat_name, messages, scope=f"run:{run_id}",
                                           data_class=kw.get("data_class", "RAW"),
                                           schema=kw.get("schema"))

    async def _emit(type_, payload):
        await emit(f"run:{run_id}", type_, payload)

    out = await seat("trust").suggest_next_steps(_complete, _emit, context=context)
    steps = out.get("next_steps", [])
    await dao.update_run(run_id, next_steps=steps)
    return {"next_steps": steps, "cached": False}


@router.get("/runs/{run_id}/next-steps")
async def get_next_steps(run_id: str) -> dict:
    run = await dao.get_run(run_id)
    if not run:
        raise _err(404, "run not found")
    return {"next_steps": run.get("next_steps") or []}
