"""Judge sandbox FIFO queue (07 §6, 09 §3–4). SANDBOX_MAX_CONCURRENT jobs at a time; a sandbox job is
a normal job (origin=sandbox, auto-confirmed spec, auto-approved capped quote, process mode) — the
guards, not the pipeline, are what's special. The per-run budget cap is registered on the router.
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app.db import dao
from app.events import E, emit
from app.models.router import clear_scope_cap, set_scope_cap


class SandboxQueue:
    def __init__(self) -> None:
        self._q: asyncio.Queue[str] = asyncio.Queue()
        self._pending: list[str] = []
        self._worker: asyncio.Task | None = None

    async def enqueue(self, *, company: str, prompt: str, session_id: str | None) -> tuple[str, int]:
        job_id = await dao.create_job(title=f"Sandbox: {company}", request=prompt, origin="sandbox",
                                      mode="process", sandbox_session_id=session_id)
        scope = f"job:{job_id}"
        set_scope_cap(scope, settings.sandbox_run_budget_usd)
        await emit(scope, E.JOB_CREATED, {"origin": "sandbox", "company": company})
        self._pending.append(job_id)
        position = len(self._pending)
        await emit(scope, E.SANDBOX_QUEUED, {"position": position, "company": company})
        await self._q.put(job_id)
        self._ensure_worker()
        return job_id, position

    def queue_state(self) -> dict:
        return {"pending": list(self._pending), "max_concurrent": settings.sandbox_max_concurrent}

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def _run(self) -> None:
        from app.orchestrator.engine import engine

        while not self._q.empty():
            job_id = await self._q.get()
            if job_id in self._pending:
                self._pending.remove(job_id)
            scope = f"job:{job_id}"
            await emit(scope, E.SANDBOX_STARTED, {"job_id": job_id})
            engine.submit_job(job_id)
            # wait for the job to reach a terminal/parked state (bounded)
            for _ in range(600):
                job = await dao.get_job(job_id)
                if job and job["status"] in ("done", "aborted", "blocked"):
                    break
                await asyncio.sleep(1.0)
            clear_scope_cap(scope)
            self._q.task_done()


sandbox_queue = SandboxQueue()
