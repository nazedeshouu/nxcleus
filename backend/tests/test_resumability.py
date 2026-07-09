"""Resumability & idempotency (07 §4) — a crash mid-stage-4 resumes at the top of the stage and
completes without duplicate side effects (deterministic IDs upsert; done build_tasks are skipped)."""
from __future__ import annotations

import asyncio

from app.db import dao
from app.orchestrator.engine import engine


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


async def test_resume_after_stage4_crash_no_duplicate_side_effects():
    job_id = await dao.create_job(title="KYC resume", request="run kyc/aml onboarding checks")
    assert await _drive_to_done(job_id) == "done"

    plan = await dao.current_plan(job_id)
    n_modules = len(plan["body"]["modules"])
    tasks_before = await dao.list_build_tasks(job_id)
    assert len(tasks_before) == n_modules            # one build_task per module, no dupes
    procs_before = [p for p in await dao.list_processes() if p["created_from_job"] == job_id]
    assert len(procs_before) == 1

    # simulate a crash-and-restart at stage 4: rewind to 'building', drop the delivered process,
    # keep the certified plan + completed build_tasks + checkpoints
    for p in procs_before:
        await dao.db.execute("DELETE FROM process_versions WHERE process_id=:p", {"p": p["id"]})  # type: ignore[attr-defined]
        await dao.db.execute("DELETE FROM processes WHERE id=:p", {"p": p["id"]})  # type: ignore[attr-defined]
    await dao.update_job(job_id, status="building")

    # engine.start() scans for non-terminal jobs and re-submits them
    await engine.start()
    for _ in range(1200):
        if (await dao.get_job(job_id))["status"] in ("done", "blocked"):
            break
        await asyncio.sleep(0.05)

    assert (await dao.get_job(job_id))["status"] == "done"
    tasks_after = await dao.list_build_tasks(job_id)
    assert len(tasks_after) == n_modules             # upsert by deterministic id — no duplicates
    procs_after = [p for p in await dao.list_processes() if p["created_from_job"] == job_id]
    assert len(procs_after) == 1                      # re-registered exactly once
