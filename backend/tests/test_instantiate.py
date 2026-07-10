"""Re-instantiation (04 §5): enters the pipeline at stage 4 with the certified plan as-is —
no stage-1 planner call, no external egress, new process entry with lineage."""
from __future__ import annotations

import asyncio

import pytest

from app.api.processes import instantiate
from app.db import dao
from app.db.engine import db
from app.sandbox.queue import sandbox_queue


async def _wait(job_id: str, timeout_ticks: int = 1200) -> dict:
    job = None
    for _ in range(timeout_ticks):
        job = await dao.get_job(job_id)
        if job and job["status"] in ("done", "blocked", "aborted"):
            return job
        await asyncio.sleep(0.05)
    return job or {}


@pytest.mark.asyncio
async def test_instantiate_skips_planning_and_stays_local():
    # build a registered process the normal way (mock sandbox job 0->7)
    src_job, _ = await sandbox_queue.enqueue(company="bank", prompt="Screen customers", session_id=None)
    assert (await _wait(src_job))["status"] == "done"
    procs = await dao.list_processes()
    process = next(p for p in procs if p["created_from_job"] == src_job)

    out = await instantiate(process["id"], {"connectors": [{"kind": "sqlite", "ref": "new.db"}]})
    new_job = out["job_id"]
    job = await _wait(new_job)
    assert job["status"] == "done", f"instantiate job ended {job['status']}"

    rows = await db.fetchall("SELECT type FROM events WHERE scope = :s", {"s": f"job:{new_job}"})
    types = {r["type"] for r in rows}
    assert not any(t.startswith("plan.") for t in types), "stage-1 planner ran on instantiate"
    assert not any(t.startswith("intake.") for t in types), "intake ran on instantiate"

    ext = await db.fetchall(
        "SELECT * FROM egress_log WHERE scope = :s AND zone = 'EXTERNAL'", {"s": f"job:{new_job}"})
    assert ext == [], "instantiate crossed the boundary"

    # a new process entry exists with lineage to the instantiate job
    twins = [p for p in await dao.list_processes() if p["created_from_job"] == new_job]
    assert twins and twins[0]["created_from"] == "reinstantiate"
