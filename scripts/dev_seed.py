#!/usr/bin/env python
"""Dev demo feed (brief item 13) — boots the app in mock mode, runs a KYC/AML job 0->7, registers a
process + a batch run, and exercises refine / BYOK / sandbox / fleet / sovereign-enforcement paths so
that every 06 §3 event the pipeline can emit appears at least once. Idempotent + re-runnable.

Run:  uv run --project backend python scripts/dev_seed.py
      (or:  cd backend && uv run python ../scripts/dev_seed.py)
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("MODEL_MODE", "mock")

from app.boundary.errors import SovereignViolation  # noqa: E402
from app.db import dao  # noqa: E402
from app.db.engine import db  # noqa: E402
from app.events import ALL_EVENT_TYPES  # noqa: E402
from app.fleet import manager  # noqa: E402
from app.models.router import router  # noqa: E402
from app.orchestrator.engine import engine  # noqa: E402
from app.runtime.operate import drive_run  # noqa: E402
from app.sandbox.queue import sandbox_queue  # noqa: E402
from app.seats.base import Message  # noqa: E402

KYC_REQUEST = (
    "We onboard new banking customers and must run KYC/AML checks: read their uploaded ID documents, "
    "screen each applicant against sanctions and PEP lists, compute a weighted risk score, and decide "
    "approve / review / reject. Applicant John Smith, account 4111 1111 1111 1111, email j.smith@acme.co. "
    "Never leak client names or document numbers — see our data-handling policy."
)


async def wait_status(job_id: str, targets: set[str], timeout: float = 60.0) -> str:
    for _ in range(int(timeout * 10)):
        job = await dao.get_job(job_id)
        if job and job["status"] in targets:
            return job["status"]
        await asyncio.sleep(0.1)
    job = await dao.get_job(job_id)
    return job["status"] if job else "missing"


async def run_build_job() -> str:
    job_id = await dao.create_job(title="KYC/AML customer onboarding", request=KYC_REQUEST,
                                  policy={"sources": [{"kind": "doc", "ref": "policy.pdf"}]})
    engine.submit_job(job_id)
    status = await wait_status(job_id, {"quoted", "blocked", "done", "aborted"})
    if status == "quoted":
        await dao.approve_quote(job_id)
        await engine.set_stage(job_id, "building")
        engine.submit_job(job_id)
        status = await wait_status(job_id, {"done", "blocked", "aborted"}, timeout=90)
    print(f"  build job {job_id} -> {status}")
    return job_id


async def fleet_beat() -> None:
    gpus = [{"index": i, "vram_used_gb": 84 + i, "vram_total_gb": 192, "util": 71 + i, "power_w": 540}
            for i in range(8)]
    node_id = await manager.register(name="A", ip="127.0.0.1", gpus=gpus,
                                     seats=["trust", "oracle", "inspector"])
    await manager._emit_telemetry("A", {"gpus": gpus, "tokens_per_s": 1830})
    await manager.drain(node_id)


async def byok_and_sovereign(process_id: str) -> None:
    # BYOK: connection + model + seat binding (config.* events)
    from app.boundary import secrets

    key_ref = await secrets.store_secret("sk-demo-not-a-real-key")
    conn_id = await dao.create_connection(name="Team GLM (Z.ai)", base_url="https://api.z.ai/v1",
                                          api_key_ref=key_ref, data_class_ceiling="SANITIZED",
                                          counts_as_local=False)
    from app.events import E, emit
    await emit("system", E.CONFIG_CONNECTION_ADDED, {"name": "Team GLM (Z.ai)", "host": "api.z.ai"})
    model_id = await dao.add_custom_model(connection_id=conn_id, provider_model_id="glm-5p2",
                                          display_name="GLM-5.2 (BYOK)", flags=["long-context", "sql-data"])
    await emit("system", E.CONFIG_MODEL_REGISTERED, {"model": "GLM-5.2 (BYOK)", "flags": ["long-context"]})
    # bind a SANITIZED seat to the custom model, scoped to a throwaway sovereign job
    await dao.set_seat_override(seat="oracle", model_key=model_id, scope="job:demo-sovereign")
    await emit("system", E.CONFIG_SEAT_BOUND, {"seat": "oracle", "model_key": model_id,
                                               "scope": "job:demo-sovereign"})
    # sovereign enforcement: a CUSTOM (non-attested) dispatch under sovereign fails closed -> egress.violation
    try:
        await router.complete("oracle", [Message(role="user", content="probe")],
                              scope="job:demo-sovereign", data_class="SANITIZED", sovereign=True)
        print("  WARNING: sovereign violation was NOT raised")
    except SovereignViolation:
        print("  sovereign enforcement fired (egress.violation logged)")


async def coverage_report() -> None:
    rows = await db.fetchall("SELECT DISTINCT type FROM events ORDER BY type")
    seen = {r["type"] for r in rows}
    missing = [t for t in ALL_EVENT_TYPES if t not in seen]
    print(f"\n  event catalog: {len(seen)}/{len(ALL_EVENT_TYPES)} types emitted")
    if missing:
        print("  not emitted this run:")
        for t in missing:
            print(f"    - {t}")


async def main() -> None:
    await db.connect()
    await db.apply_schema()
    print("Nxcleus dev seed (mock mode)")

    await fleet_beat()
    job_id = await run_build_job()

    process = None
    for p in await dao.list_processes():
        if p["created_from_job"] == job_id:
            process = p
            break
    if process is None:
        print("  no process registered — aborting downstream seed")
        await coverage_report()
        await db.disconnect()
        return

    # operate: one batch run (run.* + warranty + spotcheck)
    run_id = await dao.create_run(process_id=process["id"], version=1, kind="batch", input_ref="8")
    await drive_run(run_id)
    print(f"  batch run {run_id} complete")

    # review one needs_review unit (review.decided)
    review_units = await dao.list_run_units(run_id, status="needs_review")
    if review_units:
        from app.db import dao as _dao
        from app.events import E, emit
        await _dao.review_unit(review_units[0]["id"], "approve", "looks fine")
        await emit("system", E.REVIEW_DECIDED, {"unit": review_units[0]["id"], "verdict": "approve"})

    # refine (refine.*)
    from app.refine.refine import run_refine
    await run_refine(process["id"], "Also flag adverse media mentions in Spanish")
    print("  refine complete")

    await byok_and_sovereign(process["id"])

    # sandbox run (sandbox.* + a process-mode job)
    sjob, pos = await sandbox_queue.enqueue(company="lawfirm",
                                            prompt="Extract renewal dates and auto-renew clauses; flag "
                                                   "notice windows under 60 days", session_id=None)
    await wait_status(sjob, {"done", "blocked", "aborted"}, timeout=90)
    print(f"  sandbox job {sjob} complete")

    # abort path (job.aborted)
    from app.events import E, emit
    abort_job = await dao.create_job(title="Aborted demo", request="cancel me")
    await dao.update_job(abort_job, status="aborted")
    await emit(f"job:{abort_job}", E.JOB_ABORTED, {"reason": "presenter aborted"})

    await coverage_report()
    await engine.stop()
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
