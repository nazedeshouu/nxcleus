"""Sandbox enqueue must deliver its explicitly-unverified mock run with an FK-valid parent.

The Wave-2 blocker was an IntegrityError on exactly this path (run_units inserted under the job
id, FK pragma only set on one pooled connection).
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import dao
from app.sandbox.queue import sandbox_queue


@pytest.mark.asyncio
async def test_sandbox_api_path_completes_with_fk_parent():
    job_id, _pos = await sandbox_queue.enqueue(
        company="lawfirm",
        prompt="Extract renewal dates and auto-renew clauses; flag notice windows under 60 days",
        session_id=None)

    job = None
    for _ in range(1200):
        job = await dao.get_job(job_id)
        if job and job["status"] in ("done", "blocked", "aborted"):
            break
        await asyncio.sleep(0.05)
    assert job and job["status"] == "done", f"sandbox job ended {job and job['status']}"

    # the fan-out created a real parent run
    run_id = await dao.get_checkpoint(f"job:{job_id}", "fanout_run_id")
    assert run_id, "fan-out did not checkpoint its run id"
    run = await dao.get_run(run_id)
    assert run and run["status"] == "unverified"
    stats = run.get("stats") or {}
    assert stats.get("units", 0) > 0
    assert stats.get("verification") == "unverified"
    assert any("mock model backend" in reason
               for reason in stats.get("verification_reasons", []))

    units = await dao.list_run_units(run_id, limit=500)
    assert units, "no run_units under the fan-out run"
    assert all(u["run_id"] == run_id for u in units)

    # stage 7 linked the run to the registered process (registry dashboard fills)
    assert run["process_id"], "fan-out run not linked to the registered process"

    # FK enforcement holds on whatever pooled connection serves the write
    with pytest.raises(IntegrityError):
        await dao.add_run_unit(run_id="job_no_such_run", unit_ref="x", status="ok",
                               result={}, trace=[])


@pytest.mark.asyncio
async def test_foreign_keys_on_across_pooled_connections():
    from app.db.engine import db
    vals = await asyncio.gather(*[db.scalar("PRAGMA foreign_keys") for _ in range(8)])
    assert all(v == 1 for v in vals), f"foreign_keys off on some pooled connection: {vals}"
