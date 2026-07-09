# 07 — Orchestrator Engine & Fleet Manager

Locked 2026-07-07 (decision D3: custom event-sourced asyncio engine); revised 2026-07-08 (v2.1 — D8 conductor waves). Siblings: 03 (the stages it runs), 05 (event log), 02 (seats it dispatches to).

**Division of labor (D3 + D8):** the engine stays deterministic — it dispatches, retries, and resumes; it never decides. The *deciding* happens in artifacts and bounded review points: the certified plan says what to build, and between stage-4 waves the `conductor` seat reviews and may amend what hasn't been built yet (§3.1). In deck language: the certified plan is the orchestrator's mind; the engine is its hands; the conductor is its eyes between waves.

## 1. Engine shape

One asyncio engine inside the API process (`app/orchestrator/engine.py`). No queues, no workers-as-processes, no IPC — SQLite has one writer and the fan-out is network-bound LLM calls, which asyncio handles at any concurrency we'll reach this week.

```python
class Engine:
    async def start(self):            # lifespan hook: resume unfinished jobs/runs (§4)
    async def submit_job(self, job_id)      # spawns _drive_job task
    async def submit_run(self, run_id)      # spawns _drive_run task (04 §4)
    async def _drive_job(self, job_id):
        while stage := next_stage(job):
            await self.stages[stage].run(StageContext(job, emit, router, db, meter))
```

`StageContext` gives every stage the same five capabilities: `emit(type, payload)` (writes `events` + fans out to SSE subscribers in-process), `router.complete(...)` (02 §2), DAO access, `meter`, and `checkpoint(key, value)` (job-scoped scratch, backs resumability).

## 2. Stage state machine

```
intake → planning → certifying → quoted ⏸ → building → consolidating → qa → delivering → done
   (process mode skips building/consolidating: quoted ⏸ → qa? → running fan-out → delivering)
any-stage → blocked ⏸ (human input needed) / aborted
```

- `⏸` = engine parks the job (no task running); an API call (`approve-quote`, `confirm-spec`, ticket resolution) re-submits it.
- Transitions are written to `jobs.status` **and** emitted as `job.stage_changed` in the same DB transaction — the event log and materialized state can't diverge.
- Refine and re-instantiation jobs run the same machine with a stage subset (04 §5).

## 3. Failure policy (uniform across stages)

| Failure | Handling |
|---|---|
| LLM call transient (429/5xx/timeout) | router retries ×2; then stage-level retry |
| Structured-output invalid after repair round | counts as stage attempt failure |
| Stage attempt failure | retry stage from top, max 2 attempts (stages are idempotent: they re-emit, UI dedupes by seq) |
| Stage exhausted / non-retryable | `job.blocked` + `system.notice`; job parked, presenter decides (retry button = re-submit) |
| Certify consult cap (3 rounds) / QA fix cap (3 rounds) | remaining findings → `ticket.human_review`; job proceeds only if no blockers, else parked |
| Fleet node dies mid-stage | router fails over to `fallback` binding (badge on), stage continues; `fleet.node_down` |
| Engine crash / deploy restart | §4 resume |

Timeouts per seat (02 §2.2); whole-stage watchdogs: planning 10 min, certification 15 min, building 30 min (incl. conductor reviews), QA 20 min → treat as attempt failure.

### 3.1 Stage-4 wave loop (D8)

```
partition DAG into topological waves
for wave in waves:
    emit conductor.wave_started
    dispatch wave tasks to coder pool (§6); await settle
    review = conductor.review(plan, goal, wave outputs, remaining DAG)   # ≤2 rounds
    if review.amendments: validate scope-lock (unbuilt regions only) → apply + hash-chain (origin: conductor)
    if review.rework: run module micro-loops (≤1 per module per wave)
    emit conductor.green_flag → next wave
```

- Wave membership persists on `build_tasks.wave`; resume (§4) re-enters at the first wave with incomplete tasks and **skips the conductor review for waves already green-flagged** (the flag is an event, so replay knows).
- **Proceed-without-review rule:** conductor call fails (2 router retries + 1 stage retry) or exceeds its 90 s timeout → engine emits `system.notice` ("wave N unreviewed") and proceeds. A missing reviewer degrades quality, never availability. Scope-lock violations in a conductor amendment are rejected (logged, not applied) — same as constrained re-plans.
- Single-wave DAGs (independent parallelism) skip conductor review entirely unless the plan's BoM requests it (`"conductor": {"always": true}`).

## 4. Resumability & idempotency

On startup the engine scans for `jobs.status NOT IN (done, aborted, quoted, blocked)` and re-submits each — the stage restarts *from the top of the stage*, not mid-stage. Cheap idempotency rules that make this safe:

- Stages write their outputs (plan, amendments, quote, tasks) keyed by deterministic IDs — re-running upserts.
- `checkpoint()` stores per-stage progress worth keeping (e.g. completed build tasks); stage 4 skips `build_tasks.status = done` on re-entry, so a crash mid-build loses only in-flight modules.
- Run fan-out resumes the same way: `run_units` already written are skipped.

This is the whole durability story — deliberately Temporal-free. A restart during a live demo costs seconds, not the job.

## 5. Fleet manager (`app/fleet/manager.py`)

### 5.1 Node lifecycle
AMD Dev Cloud provisioning is assumed **manual via portal** until O5 confirms an API: we boot droplets from `infra/droplet/bootstrap.sh` (pulls ROCm vLLM docker image, starts vLLM instances per assigned profile role, starts node agent). The node agent then **self-registers**: `POST /api/admin/nodes/register {name, ip, gpus}`. The control plane treats nodes as cattle-by-registration: whatever registers and heartbeats is schedulable.

- Heartbeat: control plane polls `node:/telemetry` every 2 s → `telemetry.gpu` events; 3 misses → `status=down` → `fleet.node_down` → seats fail over per 02 §3 bindings.
- `POST /admin/nodes/{id}/drain` for clean teardown before destroying a droplet.

### 5.2 Seat placement
`infra/fleet.yaml` maps profile → node roles → vLLM launch specs (model, port, max-model-len, gpu-mem-fraction). The router resolves `local:A/...` bindings against currently-`ready` nodes. If the BoM requests profile P3 but only P1 is registered, the engine emits `fleet.profile_requested` (renders as "plan requests 3 nodes — provision or continue with fallback") and proceeds with fallback bindings unless the presenter pauses — demos never dead-end on missing GPUs.

### 5.3 Worker pool (stage 4 + fan-out)
```python
class SeatPool:                     # per seat, built from bindings + node registry + models.yaml flags
    slots: dict[backend, int]      # concurrency per backend (config; default 4/vLLM instance)
    async def submit(self, coro_factory, task_flags: list[str] = ()) -> result
        # bounded by total slots; member = capability-score argmax over healthy members
        # (02 §7.4, D12); ties → least-loaded → round-robin; no flags → round-robin
```
Stage 4 submits DAG-ready tasks (with their plan `task_flags`) to the `coder` pool; process-mode fan-out submits per-unit steps to their seats' pools the same way. Routing decision lands in the `task.started` payload. Backpressure is just the semaphore; queue depth renders from `meter.tick`.

### 5.4 Budget guards & idle watchdog
- Router pre-check per dispatch: Fireworks daily spend < `FIREWORKS_DAILY_BUDGET_USD`; sandbox run spend < `SANDBOX_RUN_BUDGET_USD`; over → `429`-style refusal upward (`system.notice`, sandbox run marked `aborted (budget)`).
- Idle watchdog: nodes registered + no active job/run for 30 min → Discord webhook "fleet idle, $/hr burning" (auto-destroy only if O5 yields an API).

## 6. Sandbox queue

`SANDBOX_MAX_CONCURRENT=1`: sandbox jobs enter a FIFO (`sandbox.queued` with live position). A sandbox job is a normal job (origin `sandbox`, auto-approved quote, budget-capped, seats prefer local-if-warm else Fireworks) — the guards, not the pipeline, are what's special (09 §4).
