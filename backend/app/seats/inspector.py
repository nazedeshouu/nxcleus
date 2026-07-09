"""Seat: `inspector` — agentic QA probes + goal-fulfillment check (stages 6, operate).

Runs on `local:A/qwen36-35b-a3b` (SANITIZED) — swapped from Gemma on a measured ~2x tool-use
gap (MCPMark 37.0 vs 18.1). A swarm of agents each runs a BOUNDED tool loop against the
deployed-to-staging process: they cannot see the code, only its HTTP surface, and they try to
BREAK the claim. Every finding needs a reproducible request/response pair.

Scenarios come from three generators (AC-derived, a static generic suite, plan-aware from the
certifier), merged and deduped. The goal-fulfillment check (08 §1.5) is one elevated scenario:
judge the deliverable against the goal in the customer's own terms.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.seats._common import ENGLISH_ONLY, STRUCTURED_ONLY, as_json, convo, parsed_or_raise
from app.seats.base import CompleteFn, EmitFn

# Harnesses return schema-validated dicts (a Ticket-shaped dict or None from probe; a GoalCheck-
# shaped dict from the goal check); backend adapts into db/models at the call site (team ruling).

DATA_CLASS = "SANITIZED"

SYSTEM_PROBE = f"""\
You are a QA inspector probing a DEPLOYED business process over HTTP. You cannot see its code \
— only its behavior. Your job is to BREAK THE CLAIM the process makes, not to fix it or to \
confirm it works. Assume it is wrong until you fail to break it.

Each turn you take exactly ONE action:
  - read_manifest: fetch the process's manifest and input/output schemas (do this first if you \
have not).
  - http_request: send a request to the process (method + path + optional headers/body). Only \
the process's staging URL is reachable — any other host is blocked.
  - submit_finding: end the scenario. Set defect=true with a REPRODUCIBLE request/response \
pair, suspected modules, and a severity if you broke it; set defect=false if, after genuinely \
trying, the claim holds.

Work within a tight step budget — be economical, each request should test a specific \
hypothesis. A finding without a concrete request and the response it produced is worthless. \
{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_GOAL_CHECK = f"""\
You perform the final goal-fulfillment check. The other instruments verified the process was \
BUILT RIGHT; you verify we BUILT THE RIGHT THING. Judge the deliverable against the GOAL \
statement — in the customer's own terms — NOT against the plan (the plan may have drifted \
through amendments; the goal is the fixed star).

You are given the goal, the process manifest, the acceptance-criteria outcomes, and 2-3 live \
probe results of the main path. Return:
  - verdict: fulfilled (does what was asked), partial (does most, with caveats), or unfulfilled \
(a core promise is missing).
  - gaps: each unmet goal clause with the evidence and a severity — blocker (a core promise \
unmet) or caveat (a minor shortfall). A blocker parks the job for human review; caveats ship \
with a note. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

ACTION_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "thought": {"type": "string"},
        "tool": {"enum": ["read_manifest", "http_request", "submit_finding"]},
        "http_request": {
            "type": "object",
            "properties": {"method": {"type": "string"}, "path": {"type": "string"},
                           "headers": {"type": "object"}, "body": {}},
            "required": ["method", "path"]},
        "submit_finding": {
            "type": "object",
            "properties": {
                "defect": {"type": "boolean"},
                "title": {"type": "string"},
                "request": {"type": "object"},
                "response": {"type": "object"},
                "suspected_modules": {"type": "array", "items": {"type": "string"}},
                "severity": {"enum": ["blocker", "major", "minor", "disagreement"]},
            },
            "required": ["defect"]},
    },
    "required": ["tool"],
}

GOAL_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["fulfilled", "partial", "unfulfilled"]},
        "gaps": {"type": "array", "items": {
            "type": "object",
            "properties": {"goal_clause": {"type": "string"}, "evidence": {"type": "string"},
                           "severity": {"enum": ["blocker", "caveat"]}},
            "required": ["goal_clause", "evidence", "severity"]}},
    },
    "required": ["verdict", "gaps"],
}

# Tool implementations are injected by the backend (real HTTP client scoped to staging).
Tools = dict[str, Callable[..., Awaitable[Any]]]


async def probe(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    scenario: dict[str, Any],
    tools: Tools,
    step_budget: int = 15,
    scenario_deadline_s: float = 60.0,
    temperature: float | None = 0.7,
) -> dict[str, Any] | None:
    """Run one scenario as a bounded tool loop (<=step_budget steps, <=deadline seconds).

    Returns a Ticket-shaped dict if the inspector found a defect, else None (claim held / budget
    spent). The step cap and deadline are enforced HERE — a probe can never run away."""
    await emit("qa.probe_started", {"scenario": scenario.get("id"), "source": scenario.get("source")})
    transcript: list[dict[str, Any]] = []
    started = time.monotonic()

    for step in range(step_budget):
        if time.monotonic() - started > scenario_deadline_s:
            await emit("qa.probe_timeout", {"scenario": scenario.get("id"), "steps": step})
            return None
        payload = as_json({"scenario": scenario, "transcript": transcript,
                           "steps_used": step, "steps_left": step_budget - step})
        c = await complete("inspector", convo(SYSTEM_PROBE, payload),
                           data_class=DATA_CLASS, schema=ACTION_SCHEMA, temperature=temperature)
        action = parsed_or_raise(c, "inspector.probe")
        tool = action.get("tool")

        if tool == "submit_finding":
            sf = action.get("submit_finding", {}) or {}
            if not sf.get("defect"):
                await emit("qa.probe_passed", {"scenario": scenario.get("id"), "steps": step + 1})
                return None
            ticket = {
                "title": sf.get("title", scenario.get("title", "inspector finding")),
                "instrument": "inspector",
                "repro": {"request": sf.get("request"), "response": sf.get("response")},
                "suspected_modules": sf.get("suspected_modules", []),
                "severity": sf.get("severity", "major"),
            }
            await emit("qa.finding", {"scenario": scenario.get("id"),
                       "title": ticket["title"], "severity": ticket["severity"]})
            return ticket

        if tool == "read_manifest":
            result = await tools["read_manifest"]()
            transcript.append({"step": step, "action": "read_manifest", "result": result})
        elif tool == "http_request":
            req = action.get("http_request", {}) or {}
            result = await tools["http_request"](
                method=req.get("method", "GET"), path=req.get("path", "/"),
                headers=req.get("headers"), body=req.get("body"))
            transcript.append({"step": step, "action": "http_request", "request": req, "result": result})
        else:  # unknown tool — record and continue (defensive)
            transcript.append({"step": step, "action": "unknown", "raw": action})

    await emit("qa.probe_exhausted", {"scenario": scenario.get("id"), "steps": step_budget})
    return None


async def goal_fulfillment_check(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    goal: str,
    manifest: dict[str, Any],
    ac_outcomes: list[dict[str, Any]],
    probe_results: list[dict[str, Any]],
    temperature: float | None = None,
) -> dict[str, Any]:
    """The elevated scenario (08 §1.5): deliverable vs goal, in the customer's terms.
    Returns a GoalCheck-shaped dict: {verdict, gaps: [{goal_clause, evidence, severity}]}."""
    payload = as_json({"goal": goal, "manifest": manifest,
                       "acceptance_criteria_outcomes": ac_outcomes, "main_path_probes": probe_results})
    c = await complete("inspector", convo(SYSTEM_GOAL_CHECK, payload),
                       data_class=DATA_CLASS, schema=GOAL_CHECK_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "inspector.goal_fulfillment_check")
    await emit("qa.goal_check", {"verdict": out.get("verdict"),
               "blockers": sum(1 for g in out.get("gaps", []) if g.get("severity") == "blocker")})
    return out


# ── Engine entrypoint (canonical name; app/seats/_placeholder.py) ─────────────
async def goal_check(
    complete: CompleteFn, emit: EmitFn, *, goal: str, manifest: dict[str, Any],
    ac_outcomes: list[dict[str, Any]], probe_results: list[dict[str, Any]],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Canonical alias for goal_fulfillment_check (08 §1.5)."""
    return await goal_fulfillment_check(complete, emit, goal=goal, manifest=manifest,
                                        ac_outcomes=ac_outcomes, probe_results=probe_results,
                                        temperature=temperature)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario generators (08 §3) — merged and deduped by the stage.
# ─────────────────────────────────────────────────────────────────────────────


def generic_probe_suite() -> list[dict[str, Any]]:
    """Static library that applies to ANY process (08 §3). Deterministic, no model."""
    return [
        {"id": "gen-malformed", "source": "generic", "title": "malformed unit rejected",
         "probe": "Submit a unit missing required fields and with wrong types; expect a clean "
                  "validation error, never a 500 or a silent wrong answer."},
        {"id": "gen-missing-required", "source": "generic", "title": "missing required field",
         "probe": "Omit each required input field in turn; expect a specific, actionable error."},
        {"id": "gen-boundary", "source": "generic", "title": "boundary values",
         "probe": "Send 0, negative, and maximum values for every numeric field; expect correct "
                  "handling at the edges (no overflow, no off-by-one in thresholds)."},
        {"id": "gen-idempotency", "source": "generic", "title": "duplicate submission idempotent",
         "probe": "Submit the same unit twice; expect the same result and no duplicate side effects."},
        {"id": "gen-oversized", "source": "generic", "title": "oversized payload",
         "probe": "Send an oversized payload; expect a bounded rejection, not a hang or crash."},
        {"id": "gen-authz", "source": "generic", "title": "wrong-tenant / token misuse",
         "probe": "Call with a token scoped to a different process; expect a refusal (the "
                  "model-proxy seat scoping must hold)."},
        {"id": "gen-needs-review", "source": "generic", "title": "needs_review pathway",
         "probe": "Drive an ambiguous unit that should route to human review; expect status "
                  "needs_review, not a forced ok."},
    ]


def ac_derived_scenarios(acceptance_criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One scenario per acceptance criterion with verify == 'inspector' (08 §3)."""
    out = []
    for ac in acceptance_criteria:
        if ac.get("verify") == "inspector":
            out.append({"id": f"ac-{ac.get('id')}", "source": "ac",
                        "title": f"acceptance {ac.get('id')}", "probe": ac.get("text", "")})
    return out


def plan_aware_scenarios(adversarial: list[str]) -> list[dict[str, Any]]:
    """Wrap the certifier's plan-aware adversarial scenarios (03 §4.3 / 08 §3)."""
    return [{"id": f"plan-{i+1}", "source": "plan", "title": f"plan-aware {i+1}", "probe": s}
            for i, s in enumerate(adversarial)]


def merge_scenarios(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge and dedupe by title (03 §3 generators are merged and deduped)."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for s in group:
            key = s.get("title", s.get("id", ""))
            if key not in seen:
                seen.add(key)
                merged.append(s)
    return merged
