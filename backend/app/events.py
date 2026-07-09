"""Event envelope, typed catalog (06 §3), and the in-process SSE bus.

`emit(scope, type, payload)` writes one append-only `events` row and fans out to every live SSE
subscriber. UI state for a job is a fold of its events; the DB rows are the materialized current
state (05 §1). Token-level deltas are coalesced to <=10 events/s per scope (06 §3 rule); every SSE
stream also sends `: heartbeat` comments every 10 s (implemented in the SSE responder, api/sse.py).
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from app.config import settings
from app.db.engine import db


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- catalog (06 §3)
class E:
    # job lifecycle
    JOB_CREATED = "job.created"
    JOB_STAGE_CHANGED = "job.stage_changed"
    JOB_BLOCKED = "job.blocked"
    JOB_DONE = "job.done"
    JOB_ABORTED = "job.aborted"
    # stage 0 — intake / policy / boundary
    INTAKE_MESSAGE = "intake.message"
    INTAKE_SPEC_UPDATED = "intake.spec_updated"
    INTAKE_CLASSIFIED = "intake.classified"
    INTAKE_POLICY_REGISTERED = "intake.policy_registered"
    INTAKE_CONTEXT_MAPPED = "intake.context_mapped"
    BOUNDARY_SANITIZED = "boundary.sanitized"
    # stage 1 — planning
    PLAN_STARTED = "plan.started"
    PLAN_DELTA = "plan.delta"
    PLAN_COMPLETED = "plan.completed"
    # stage 2 — certification
    CERTIFY_CHECK_STARTED = "certify.check_started"
    CERTIFY_FINDING = "certify.finding"
    CERTIFY_AMENDMENT = "certify.amendment"
    CERTIFY_CONSULT_OPENED = "certify.consult_opened"
    CERTIFY_CONSULT_RESOLVED = "certify.consult_resolved"
    CERTIFY_GOAL_SET = "certify.goal_set"
    CERTIFY_CERTIFIED = "certify.certified"
    CERTIFY_BLOCKED = "certify.blocked"
    # stage 3 — quote
    QUOTE_ISSUED = "quote.issued"
    QUOTE_APPROVED = "quote.approved"
    # fleet / provisioning
    FLEET_PROFILE_REQUESTED = "fleet.profile_requested"
    FLEET_NODE_READY = "fleet.node_ready"
    FLEET_NODE_DOWN = "fleet.node_down"
    # stage 4 — build tasks
    TASK_STARTED = "task.started"
    TASK_OUTPUT_DELTA = "task.output_delta"
    TASK_TESTS = "task.tests"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    # stage 4 — conductor waves
    CONDUCTOR_WAVE_STARTED = "conductor.wave_started"
    CONDUCTOR_REVIEW = "conductor.review"
    CONDUCTOR_AMENDMENT = "conductor.amendment"
    CONDUCTOR_GREEN_FLAG = "conductor.green_flag"
    # stage 5 — consolidation
    CONSOLIDATE_STARTED = "consolidate.started"
    CONSOLIDATE_TEST_RUN = "consolidate.test_run"
    CONSOLIDATE_COMPLETED = "consolidate.completed"
    # stage 6 — QA
    QA_INSPECTOR_STARTED = "qa.inspector_started"
    QA_PROBE = "qa.probe"
    QA_FINDING = "qa.finding"
    QA_GOAL_CHECK = "qa.goal_check"
    QA_ORACLE_CHECK = "qa.oracle_check"
    QA_PASSED = "qa.passed"
    # tickets
    TICKET_OPENED = "ticket.opened"
    TICKET_IN_FIX = "ticket.in_fix"
    TICKET_VERIFIED = "ticket.verified"
    TICKET_HUMAN_REVIEW = "ticket.human_review"
    # stage 7 — delivery
    DELIVER_REGISTERED = "deliver.registered"
    # operate phase
    RUN_STARTED = "run.started"
    RUN_UNIT_COMPLETED = "run.unit_completed"
    RUN_PROGRESS = "run.progress"
    RUN_SPOTCHECK = "run.spotcheck"
    RUN_COMPLETED = "run.completed"
    WARRANTY_TICKET = "warranty.ticket"
    REFINE_TRIAGED = "refine.triaged"
    REFINE_VERSION_CREATED = "refine.version_created"
    REVIEW_DECIDED = "review.decided"
    # router / metering / boundary
    MODEL_CALL = "model.call"
    METER_TICK = "meter.tick"
    EGRESS_REQUEST = "egress.request"
    EGRESS_VIOLATION = "egress.violation"
    # fleet telemetry
    TELEMETRY_GPU = "telemetry.gpu"
    # sandbox
    SANDBOX_QUEUED = "sandbox.queued"
    SANDBOX_STARTED = "sandbox.started"
    # config / BYOK
    CONFIG_CONNECTION_ADDED = "config.connection_added"
    CONFIG_MODEL_REGISTERED = "config.model_registered"
    CONFIG_SEAT_BOUND = "config.seat_bound"
    # system
    SYSTEM_NOTICE = "system.notice"


# every catalog type, for the DoD coverage check in dev_seed
ALL_EVENT_TYPES: list[str] = sorted(
    v for k, v in vars(E).items() if not k.startswith("_") and isinstance(v, str)
)

# token-level deltas are coalesced (06 §3)
_DELTA_TYPES = {E.PLAN_DELTA, E.TASK_OUTPUT_DELTA}


# --------------------------------------------------------------------------- SSE bus
class Subscriber:
    def __init__(self, scope: str | None, type_prefix: str | None) -> None:
        self.scope = scope
        self.type_prefix = type_prefix
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

    def matches(self, event: dict) -> bool:
        if self.scope is not None and event["scope"] != self.scope:
            return False
        if self.type_prefix is not None and not event["type"].startswith(self.type_prefix):
            return False
        return True


class EventBus:
    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()
        # per-(scope, type, key) delta coalescing buffers + their scheduled flush tasks
        self._delta_buffers: dict[tuple, str] = {}
        self._delta_payloads: dict[tuple, dict] = {}
        self._flush_tasks: dict[tuple, asyncio.Task] = {}

    def subscribe(self, scope: str | None = None, type_prefix: str | None = None) -> Subscriber:
        sub = Subscriber(scope, type_prefix)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    def publish(self, event: dict) -> None:
        for sub in list(self._subs):
            if sub.matches(event):
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    # slow client — drop; it can reconnect with from_seq to catch up
                    pass

    async def write(self, scope: str, type_: str, payload: dict) -> dict:
        ts = now_iso()
        seq = await db.execute_returning(
            "INSERT INTO events (ts, scope, type, payload) VALUES (:ts, :scope, :type, :payload) "
            "RETURNING seq",
            {"ts": ts, "scope": scope, "type": type_, "payload": json.dumps(payload)},
        )
        event = {"seq": int(seq), "ts": ts, "scope": scope, "type": type_, "payload": payload}
        self.publish(event)
        return event

    def coalesce_delta(self, scope: str, type_: str, payload: dict) -> None:
        """Accumulate a token delta; schedule a single flush per throttle window (06 §3)."""
        key = (scope, type_, payload.get("task") or payload.get("module") or "")
        text = payload.get("delta") or payload.get("text") or ""
        self._delta_buffers[key] = self._delta_buffers.get(key, "") + text
        self._delta_payloads[key] = {**payload, "delta": self._delta_buffers[key]}
        if key not in self._flush_tasks:
            self._flush_tasks[key] = asyncio.create_task(self._flush_after(key, scope, type_))

    async def _flush_after(self, key: tuple, scope: str, type_: str) -> None:
        await asyncio.sleep(1.0 / max(1, settings.sse_throttle_per_s))
        self._flush_tasks.pop(key, None)
        self._delta_buffers.pop(key, None)
        payload = self._delta_payloads.pop(key, None)
        if payload is not None:
            await self.write(scope, type_, payload)


bus = EventBus()


async def emit(scope: str, type_: str, payload: dict | None = None) -> dict:
    """Persist + fan out one event. Delta types are coalesced (<=throttle/s per scope)."""
    payload = payload or {}
    if type_ in _DELTA_TYPES:
        bus.coalesce_delta(scope, type_, payload)
        # provisional envelope (seq assigned at flush) so callers don't await a row per token
        return {"seq": -1, "ts": now_iso(), "scope": scope, "type": type_, "payload": payload}
    return await bus.write(scope, type_, payload)


async def replay(scope: str, from_seq: int = 0) -> list[dict]:
    rows = await db.fetchall(
        "SELECT seq, ts, scope, type, payload FROM events WHERE scope = :scope AND seq >= :from_seq "
        "ORDER BY seq",
        {"scope": scope, "from_seq": from_seq},
    )
    return [
        {"seq": r["seq"], "ts": r["ts"], "scope": r["scope"], "type": r["type"],
         "payload": json.loads(r["payload"])}
        for r in rows
    ]


async def replay_prefix(type_prefix: str, from_seq: int = 0) -> list[dict]:
    rows = await db.fetchall(
        "SELECT seq, ts, scope, type, payload FROM events WHERE type LIKE :pfx AND seq >= :from_seq "
        "ORDER BY seq",
        {"pfx": f"{type_prefix}%", "from_seq": from_seq},
    )
    return [
        {"seq": r["seq"], "ts": r["ts"], "scope": r["scope"], "type": r["type"],
         "payload": json.loads(r["payload"])}
        for r in rows
    ]
