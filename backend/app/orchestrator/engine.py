"""Event-sourced asyncio engine (07 §1). One engine inside the API process; stages are asyncio
tasks; SQLite has one writer and the fan-out is network-bound LLM calls (07 §1). The engine is
deterministic — it dispatches, retries, resumes; it never decides (D3). Deciding happens in the
certified plan and the conductor's bounded wave reviews.
"""
from __future__ import annotations

import asyncio

from app.boundary.errors import BudgetExceeded
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
_STOP = {"quoted", "blocked", "done", "aborted", "awaiting_input"}
# terminal statuses a forward transition must never overwrite (an abort landing mid-stage must stick)
_TERMINAL = {"aborted", "done", "blocked"}

# whole-stage watchdog seconds (07 §3)
_WATCHDOG = {
    "planning": 600, "certifying": 900, "building": 1800, "consolidating": 480,
    "qa": 1200, "intake": 300, "delivering": 120,
}
_MAX_STAGE_ATTEMPTS = 2

# stage number for the UI (03 §1)
_STAGE_NUM = {"intake": 0, "awaiting_input": 0, "planning": 1, "certifying": 2, "quoted": 3,
              "building": 4, "consolidating": 5, "qa": 6, "delivering": 7, "done": 7}
_STATUS_BY_STAGE = {number: status for status, number in _STAGE_NUM.items()
                    if status in _STAGE_MODULES}

_CORRECTION_CHECKPOINTS = (
    "clarifications", "tests", "vectors", "adversarial_scenarios", "certified_plan_id",
    "fanout_result", "fanout_run_id", "consolidation_assembled", "consolidation_fix_state",
    "integration_result", "qa_result", "goal_check",
)
_RETRY_CHECKPOINTS = {
    "building": ("fanout_result", "fanout_run_id"),
    "consolidating": ("integration_result", "consolidation_fix_state"),
    "qa": ("qa_result", "goal_check"),
}


async def _persist_status(job_id: str, status: str) -> bool:
    """Write jobs.status + emit job.stage_changed together (07 §2 — state can't diverge). A forward
    transition first RE-READS the row: if a terminal status (e.g. an abort) landed concurrently mid-
    stage, the write is suppressed so the abort sticks instead of being clobbered. Returns False when
    suppressed."""
    if status not in _TERMINAL:
        cur = await dao.get_job(job_id)
        if cur and cur["status"] in _TERMINAL:
            return False
    await dao.update_job(job_id, status=status, current_stage=_STAGE_NUM.get(status, 0))
    await emit(f"job:{job_id}", E.JOB_STAGE_CHANGED, {"status": status, "stage": _STAGE_NUM.get(status, 0)})
    return True


async def _block_job(job_id: str, stage: str, reason: str) -> None:
    """Persist the exact restart point before parking the job."""
    await dao.set_checkpoint(f"job:{job_id}", "failed_stage", {"stage": stage, "reason": reason})
    await dao.update_job(job_id, status="blocked", current_stage=_STAGE_NUM.get(stage, 0))
    await emit(f"job:{job_id}", E.JOB_BLOCKED, {"stage": stage, "reason": reason})


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
        """Write jobs.status + emit job.stage_changed together (07 §2 — state can't diverge). Guarded:
        a stage that finishes just after an abort landed must not overwrite the terminal status."""
        await _persist_status(self.job_id, status)

    async def block(self, stage: str, reason: str) -> None:
        await _block_job(self.job_id, stage, reason)

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
        current = self._tasks.get(job_id)
        if current is not None and not current.done():
            return
        if current is not None:
            self._tasks.pop(job_id, None)
        self._tasks[job_id] = asyncio.create_task(self._drive_job(job_id))

    def wake_job(self, job_id: str) -> None:
        """Resume after the current driver exits, avoiding the parked-task race."""
        current = self._tasks.get(job_id)
        if current is None or current.done():
            self.submit_job(job_id)
            return

        def resume(done: asyncio.Task) -> None:
            if self._tasks.get(job_id) is done:
                self._tasks.pop(job_id, None)
                self.submit_job(job_id)

        current.add_done_callback(resume)

    async def retry_job(self, job_id: str, correction: str = "") -> tuple[dict, bool, str]:
        """Retry the failed stage, or re-run intake when the customer corrects the request."""
        job = await dao.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        failed = await dao.get_checkpoint(f"job:{job_id}", "failed_stage") or {}
        failed_stage = failed.get("stage") or _STATUS_BY_STAGE.get(job.get("current_stage"))
        if failed_stage not in _STAGE_MODULES:
            raise ValueError("blocked job has no retryable failed-stage checkpoint")

        correction = correction.strip()
        target = "intake" if correction else failed_stage
        claimed = await dao.retry_blocked_job(
            job_id, status=target, current_stage=_STAGE_NUM[target])
        if not claimed:
            return (await dao.get_job(job_id)) or job, False, target

        scope = f"job:{job_id}"
        checkpoint_keys = (
            _CORRECTION_CHECKPOINTS if correction
            else _RETRY_CHECKPOINTS.get(failed_stage, ())
        )
        await dao.delete_checkpoints(scope, checkpoint_keys)

        if correction:
            # A correction changes the plan, so old generated code cannot remain authoritative.
            # Conversation, event history, and the original request remain as the audit trail.
            from app.runtime import workspace

            await dao.delete_build_tasks(job_id)
            workspace.reset_job(job_id)

        if correction:
            if not await dao.list_messages(job_id):
                await dao.add_message(job_id, "customer", job.get("request", ""))
            await dao.add_message(job_id, "customer", correction)
            await emit(f"job:{job_id}", E.INTAKE_MESSAGE,
                       {"role": "customer", "content": correction})
        await dao.set_checkpoint(f"job:{job_id}", "retry_context", {
            "failed_stage": failed_stage,
            "target_stage": target,
            "correction": correction,
        })
        await emit(f"job:{job_id}", E.JOB_STAGE_CHANGED,
                   {"status": target, "stage": _STAGE_NUM[target]})
        self.wake_job(job_id)
        return (await dao.get_job(job_id)) or job, True, target

    def submit_run(self, run_id: str) -> None:
        key = f"run:{run_id}"
        if key in self._tasks and not self._tasks[key].done():
            return
        from app.runtime.operate import drive_run

        self._tasks[key] = asyncio.create_task(drive_run(run_id))

    # -------------------------------------------------------------- transitions
    async def set_stage(self, job_id: str, status: str) -> None:
        """Write jobs.status + emit job.stage_changed together (07 §2 — state can't diverge). Guarded
        so a forward transition (e.g. quote-approve -> building) can't un-stick a terminal abort."""
        await _persist_status(job_id, status)

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
            # B6: a stage that returns ok without advancing would hot-loop forever — park it
            after = await dao.get_job(job_id)
            if after and after["status"] == status:
                reason = f"stage {status} returned without advancing"
                await _block_job(job_id, status, reason)
                await emit(f"job:{job_id}", E.SYSTEM_NOTICE,
                           {"text": f"{reason} — job parked", "level": "error"})
                return

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
            except BudgetExceeded as exc:
                # deterministic guard, not a fault: no retry; the run aborts gracefully (09 §4)
                await dao.update_job(job["id"], status="aborted")
                await emit(ctx.scope, E.JOB_ABORTED,
                           {"reason": f"budget cap reached during {status}: {exc}"})
                return False
            except Exception as exc:  # noqa: BLE001 — uniform failure policy (07 §3)
                await emit(ctx.scope, E.SYSTEM_NOTICE,
                           {"text": f"stage {status} attempt {attempt} failed: {type(exc).__name__}: "
                            f"{str(exc)[:200]}", "level": "warn"})
                if attempt >= _MAX_STAGE_ATTEMPTS:
                    await ctx.block(status, f"{type(exc).__name__}: {str(exc)[:200]}")
                    return False
        return False


engine = Engine()
