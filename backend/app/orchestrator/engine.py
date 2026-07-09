"""Event-sourced asyncio engine (07 §1). One engine inside the API process; stages are asyncio
tasks; SQLite has one writer and the fan-out is network-bound LLM calls (07 §1). The engine is
deterministic — it dispatches, retries, resumes; it never decides (D3). Deciding happens in the
certified plan and the conductor's bounded wave reviews.
"""
from __future__ import annotations

import asyncio

from app.db import dao
from app.events import E, emit
from app.metering import meter
from app.models.router import router
from app.seats.base import CompleteFn  # noqa: F401  (documents the curried type)

# status -> stage module path + entry fn; imported lazily to avoid import cycles at load
_STAGE_MODULES: dict[str, tuple[str, str]] = {
    "intake": ("app.boundary.intake", "run"),
    "planning": ("app.planning.stage1", "run"),
    "certifying": ("app.certify.stage2", "run"),
    "building": ("app.fleet.stage4", "run"),
    "consolidating": ("app.consolidate.stage5", "run"),
    "qa": ("app.qa.stage6", "run"),
    "delivering": ("app.delivery.stage7", "run"),
}

# statuses the driver stops on (parked or terminal)
_STOP = {"quoted", "blocked", "done", "aborted"}

# whole-stage watchdog seconds (07 §3)
_WATCHDOG = {
    "planning": 600, "certifying": 900, "building": 1800, "consolidating": 480,
    "qa": 1200, "intake": 300, "delivering": 120,
}
_MAX_STAGE_ATTEMPTS = 2

# stage number for the UI (03 §1)
_STAGE_NUM = {"intake": 0, "planning": 1, "certifying": 2, "quoted": 3, "building": 4,
              "consolidating": 5, "qa": 6, "delivering": 7, "done": 7}


class StageContext:
    """The five capabilities every stage gets (07 §1): emit, complete (curried router), dao, meter,
    checkpoint. `complete` is the CompleteFn the seat layer receives (base.py) — scope + sovereign
    are bound; the seat passes its seat name and data_class at call time."""

    def __init__(self, job: dict) -> None:
        self.job = job
        self.job_id = job["id"]
        self.scope = f"job:{job['id']}"
        self.sovereign = bool(job.get("sovereign"))
        self.dao = dao
        self.meter = meter

    async def emit(self, type_: str, payload: dict | None = None) -> None:
        await emit(self.scope, type_, payload or {})

    async def complete(self, seat: str, messages, *, data_class: str, schema: dict | None = None,
                       stream=None, temperature: float | None = None, max_tokens: int | None = None):
        return await router.complete(
            seat, messages, scope=self.scope, data_class=data_class, sovereign=self.sovereign,
            schema=schema, stream=stream, temperature=temperature, max_tokens=max_tokens,
        )

    async def checkpoint(self, key: str, value) -> None:
        await dao.set_checkpoint(self.scope, key, value)

    async def get_checkpoint(self, key: str):
        return await dao.get_checkpoint(self.scope, key)

    async def advance(self, status: str) -> None:
        """Write jobs.status + emit job.stage_changed together (07 §2 — state can't diverge)."""
        await dao.update_job(self.job_id, status=status, current_stage=_STAGE_NUM.get(status, 0))
        await emit(self.scope, E.JOB_STAGE_CHANGED,
                   {"status": status, "stage": _STAGE_NUM.get(status, 0)})

    async def refresh(self) -> dict:
        self.job = await dao.get_job(self.job_id) or self.job
        return self.job


class Engine:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    # -------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Resume unfinished jobs/runs on startup (07 §4)."""
        for job in await dao.resume_candidates():
            await emit(f"job:{job['id']}", E.SYSTEM_NOTICE,
                       {"text": f"resuming job at stage {job.get('status')}", "level": "info"})
            self.submit_job(job["id"])
        for run in await dao.resume_runs():
            self.submit_run(run["id"])

    async def stop(self) -> None:
        for t in list(self._tasks.values()):
            t.cancel()
        self._tasks.clear()

    # -------------------------------------------------------------- submit
    def submit_job(self, job_id: str) -> None:
        if job_id in self._tasks and not self._tasks[job_id].done():
            return
        self._tasks[job_id] = asyncio.create_task(self._drive_job(job_id))

    def submit_run(self, run_id: str) -> None:
        key = f"run:{run_id}"
        if key in self._tasks and not self._tasks[key].done():
            return
        from app.runtime.operate import drive_run

        self._tasks[key] = asyncio.create_task(drive_run(run_id))

    # -------------------------------------------------------------- transitions
    async def set_stage(self, job_id: str, status: str) -> None:
        """Write jobs.status + emit job.stage_changed together (07 §2 — state can't diverge)."""
        await dao.update_job(job_id, status=status, current_stage=_STAGE_NUM.get(status, 0))
        await emit(f"job:{job_id}", E.JOB_STAGE_CHANGED,
                   {"status": status, "stage": _STAGE_NUM.get(status, 0)})

    # -------------------------------------------------------------- driver
    async def _drive_job(self, job_id: str) -> None:
        while True:
            job = await dao.get_job(job_id)
            if job is None:
                return
            status = job["status"]
            # sandbox jobs auto-approve the capped quote and continue (09 §3)
            if status == "quoted" and job.get("origin") == "sandbox":
                await dao.approve_quote(job_id)
                await emit(f"job:{job_id}", E.QUOTE_APPROVED, {"auto": True})
                await self.set_stage(job_id, "building")
                continue
            if status in _STOP:
                if status == "done":
                    await emit(f"job:{job_id}", E.JOB_DONE, {"status": "done"})
                return
            if status not in _STAGE_MODULES:
                return
            ok = await self._run_stage(job, status)
            if not ok:
                return  # blocked/parked by failure policy

    async def _run_stage(self, job: dict, status: str) -> bool:
        mod_path, fn_name = _STAGE_MODULES[status]
        import importlib

        stage_fn = getattr(importlib.import_module(mod_path), fn_name)
        ctx = StageContext(job)
        watchdog = _WATCHDOG.get(status, 600)
        for attempt in range(1, _MAX_STAGE_ATTEMPTS + 1):
            try:
                await asyncio.wait_for(stage_fn(ctx), timeout=watchdog)
                return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — uniform failure policy (07 §3)
                await emit(ctx.scope, E.SYSTEM_NOTICE,
                           {"text": f"stage {status} attempt {attempt} failed: {type(exc).__name__}: "
                            f"{str(exc)[:200]}", "level": "warn"})
                if attempt >= _MAX_STAGE_ATTEMPTS:
                    await dao.update_job(job["id"], status="blocked")
                    await emit(ctx.scope, E.JOB_BLOCKED,
                               {"stage": status, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
                    return False
        return False


engine = Engine()
