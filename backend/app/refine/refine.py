"""Refine phase (04 §5) — triage a change request as amend (mechanical) or consult (structural),
bump the process version, and emit the refine beats. Old versions stay runnable (packages are
immutable). Refine invoices show 'frontier consult: $0.00' when triage stayed local.
"""
from __future__ import annotations

from app.db import dao
from app.events import E, emit
from app.metering import invoice as invoice_mod
from app.orchestrator.engine import StageContext
from app.orchestrator.seatlib import seat


async def run_refine(process_id: str, request: str) -> str:
    process = await dao.get_process(process_id)
    if process is None:
        raise KeyError("process not found")
    job_id = await dao.create_job(title=f"Refine: {process['name']}", request=request,
                                  origin="refine", parent_process_id=process_id)
    job = await dao.get_job(job_id)
    scope = f"job:{job_id}"
    await emit(scope, E.JOB_CREATED, {"origin": "refine", "parent_process": process_id})
    ctx = StageContext(job)

    latest_v = process["current_version"]
    version = await dao.get_version(process_id, latest_v)
    plan = await dao.get_plan(version["plan_id"]) if version else None

    certifier = seat("certifier")
    triage = await certifier.triage_refine(ctx.complete, ctx.emit,
                                           plan=(plan or {}).get("body", {}), request=request)
    verdict = triage.get("triage", "amend")
    await emit(scope, E.REFINE_TRIAGED, {"verdict": verdict, "regions": triage.get("regions", []),
                                         "rationale": triage.get("rationale", "")})

    # bump version (amend path: scoped rebuild; here a compact diff record)
    new_version = latest_v + 1
    diff = {"triage": verdict, "regions": triage.get("regions", []),
            "modules_rebuilt": triage.get("regions", []), "tests_added": 0,
            "frontier_consult": verdict == "consult"}
    await dao.create_version(process_id=process_id, version=new_version,
                             plan_id=version["plan_id"] if version else "",
                             package_path=version["package_path"] if version else "",
                             image_tag=version.get("image_tag") if version else None, diff=diff)
    await dao.update_process(process_id, current_version=new_version)

    invoice = await invoice_mod.build_invoice(scope)
    invoice["frontier_consult_usd"] = 0.0 if verdict == "amend" else invoice.get("total_usd", 0.0)
    await emit(scope, E.REFINE_VERSION_CREATED, {"version": new_version, "diff": diff,
                                                 "invoice": invoice})
    await dao.update_job(job_id, status="done", current_stage=7, goal=process.get("goal"))
    await emit(scope, E.JOB_DONE, {"status": "done"})
    return job_id
