"""Seat: `conductor` — between-wave review (stage 4, D8).

Same served instance as the certifier (`local:B/glm-46`, RAW), different prompt. Between
topological waves it reviews the wave's outputs against the certified plan + goal and may
amend NOT-YET-BUILT regions, or order bounded rework of an already-built module. It never
dead-ends a build: if it is unavailable the engine proceeds without review (07 §3.1).
"""
from __future__ import annotations

from typing import Any

from app.seats.base import CompleteFn, EmitFn
from app.seats._common import ENGLISH_ONLY, STRUCTURED_ONLY, as_json, convo, parsed_or_raise

# Returns a schema-validated dict; backend adapts into db/models.ConductorReview (team ruling).

DATA_CLASS = "RAW"

SYSTEM_REVIEW = f"""\
You are the conductor of a wave-based build. A wave of parallel agents just finished part of \
the plan; you review their work before the next wave starts. You see the certified plan, the \
GOAL (the fixed star — what must exist when the job is done), this wave's outputs (files, test \
results, worker notes), and the remaining DAG (what is not yet built).

Judge two things:
  1. GOAL DRIFT — is the work still converging on the goal, in the customer's terms? If it is \
drifting, describe how (this surfaces to the operator); do not silently correct course.
  2. Whether the remaining plan needs adjustment given what this wave revealed.

You have exactly two levers, and strict limits on each:
  - amendments: precise RFC-6902 patches to plan regions that are NOT YET BUILT (only ids in \
the remaining DAG). You may not edit finished work by patching the plan under it — that is \
forbidden and will be rejected. Same scope-lock discipline as certification.
  - rework: at most ONE rework order per module per wave, for a problem in an ALREADY-BUILT \
module. Give the module id and a precise instruction; it reruns as a scoped micro-loop.

If the wave is sound and the plan needs no change, return verdict "proceed" with empty \
amendments and rework. Prefer proceeding — you improve quality, you do not gate availability. \
{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["proceed", "amend"]},
        "wave_assessment": {"type": "string"},
        "goal_drift": {"type": ["string", "null"]},
        "amendments": {"type": "array", "items": {
            "type": "object",
            "properties": {"plan_ref": {"type": "string"},
                           "patch": {"type": "array", "items": {
                               "type": "object",
                               "properties": {"op": {"enum": ["add", "replace", "remove"]},
                                              "path": {"type": "string"}, "value": {}},
                               "required": ["op", "path"]}},
                           "rationale": {"type": "string"}},
            "required": ["plan_ref", "patch", "rationale"]}},
        "rework": {"type": "array", "items": {
            "type": "object",
            "properties": {"module_id": {"type": "string"}, "instruction": {"type": "string"}},
            "required": ["module_id", "instruction"]}},
    },
    "required": ["verdict", "wave_assessment"],
}


async def review(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    plan: dict[str, Any],
    goal: str,
    wave_outputs: list[dict[str, Any]] | dict[str, Any],
    remaining: list[Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Review one wave (returns a ConductorReview-shaped dict). Enforces (in-harness, not just prompt):
      - amendments may touch only ids in `remaining` (unbuilt regions) — out-of-scope dropped;
      - at most one rework order per module.
    `remaining` items may be region-id strings or dag-task dicts ({id|task|module}); both accepted.
    A rejected-scope amendment is logged, not applied (07 §3.1)."""
    remaining_ids = {r if isinstance(r, str) else (r.get("id") or r.get("task") or r.get("module"))
                     for r in (remaining or [])}
    remaining_ids.discard(None)
    await emit("conductor.wave_started", {"remaining": len(remaining_ids)})
    payload = as_json({"plan": plan, "goal": goal, "wave_outputs": wave_outputs,
                       "remaining_dag": list(remaining_ids)})
    c = await complete("conductor", convo(SYSTEM_REVIEW, payload),
                       data_class=DATA_CLASS, schema=REVIEW_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "conductor.review")

    allowed = remaining_ids
    kept_amendments: list[dict[str, Any]] = []
    for a in out.get("amendments", []) or []:
        if a.get("plan_ref") in allowed:
            kept_amendments.append(a)
            await emit("conductor.amendment", {"plan_ref": a.get("plan_ref"),
                       "rationale": a.get("rationale")})
        else:
            await emit("plan.scope_violation", {"origin": "conductor",
                       "plan_ref": a.get("plan_ref"), "allowed": sorted(allowed)})

    # ≤1 rework per module per wave.
    seen: set[str] = set()
    kept_rework: list[dict[str, Any]] = []
    for r in out.get("rework", []) or []:
        mid = r.get("module_id")
        if mid and mid not in seen:
            seen.add(mid)
            kept_rework.append(r)

    out["amendments"], out["rework"] = kept_amendments, kept_rework
    if out.get("goal_drift"):
        await emit("conductor.goal_drift", {"description": out["goal_drift"]})
    await emit("conductor.green_flag", {"verdict": out.get("verdict"),
               "amendments": len(kept_amendments), "rework": len(kept_rework)})
    return out
