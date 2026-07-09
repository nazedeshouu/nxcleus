"""Stage state machine (07 §2) — a build job travels intake->…->done, transitions written to
jobs.status AND emitted as job.stage_changed (state can't diverge)."""
from __future__ import annotations

import asyncio

from app.db import dao
from app.db.engine import db
from app.orchestrator.engine import engine

_STAGES = ["planning", "certifying", "quoted", "building", "consolidating", "qa", "delivering"]


async def _drive_to_done(job_id: str, timeout: float = 60.0) -> str:
    engine.submit_job(job_id)
    for _ in range(int(timeout * 20)):
        job = await dao.get_job(job_id)
        if job["status"] == "quoted":
            await dao.approve_quote(job_id)
            await engine.set_stage(job_id, "building")
            engine.submit_job(job_id)
        if job["status"] in ("done", "aborted", "blocked"):
            return job["status"]
        await asyncio.sleep(0.05)
    return (await dao.get_job(job_id))["status"]


async def test_build_job_reaches_done_and_registers_process():
    job_id = await dao.create_job(title="KYC test", request="run kyc/aml onboarding checks")
    status = await _drive_to_done(job_id)
    assert status == "done"
    # a process was registered from this job (stage 7)
    processes = [p for p in await dao.list_processes() if p["created_from_job"] == job_id]
    assert len(processes) == 1


async def test_stage_changed_events_match_status_progression():
    job_id = await dao.create_job(title="KYC test", request="run kyc/aml onboarding checks")
    await _drive_to_done(job_id)
    rows = await db.fetchall(
        "SELECT payload FROM events WHERE scope=:s AND type='job.stage_changed' ORDER BY seq",
        {"s": f"job:{job_id}"})
    import json
    statuses = [json.loads(r["payload"])["status"] for r in rows]
    # every declared stage appears, in order
    for stage in _STAGES:
        assert stage in statuses, f"missing stage transition: {stage}"
    assert statuses.index("planning") < statuses.index("building") < statuses.index("delivering")
