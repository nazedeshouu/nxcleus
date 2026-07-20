"""Seat: `planner` — the frontier topology + BoM author (stage 1, refine consults).

The ONE designed-in non-local seat (D7). Default binding `anthropic:claude-fable-5`;
sovereign binding `local:B/glm-46`. Data class is a HARD SANITIZED ceiling — this seat can
never see RAW; it plans against the sanitized brief alone. The whole product claim rests on
that: everything the frontier ever sees is the sanitized planner brief.

The system prompt tells the planner EXACTLY what execution fabric will run its plan, so it
designs an executable work order, not generic advice (03 §3).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.seats._common import (
    ENGLISH_ONLY,
    STRUCTURED_ONLY,
    as_json,
    convo,
    msg,
    parsed_or_raise,
    region_ids,
)
from app.seats.base import CompleteFn, EmitFn

# Harnesses return plain, schema-validated dicts; backend adapts into db/models.Plan at the call
# site. Seat modules never import backend model classes (team ruling).

DATA_CLASS = "SANITIZED"

_FABRIC = """\
Your plan is executed by a specific fabric — design FOR it:
  - A fleet of parallel sub-agents (specialist coder models, or per-unit workers) builds the \
work concurrently. Agents that never see each other's output must not diverge at the seams, \
so every shared boundary must be a declared, typed interface.
  - A CONDUCTOR reviews the outputs between topological waves and may amend not-yet-built \
regions before green-flagging the next wave — so structure your DAG into meaningful waves.
  - A CONSOLIDATOR merges the modules into one coherent codebase against your interfaces.
  - An adversarial QA gate then attacks the result: an inspector swarm probes the deployed \
process and a numeric ORACLE independently recomputes every numeric rule. Anything you leave \
underspecified becomes a defect ticket here.
  - A local model with the FULL production context you never saw will complete and correct \
your plan first (it restores real names, schemas, and values). Your plan is a strong first \
draft that a smarter, better-informed pass will finish — so mark clearly what you had to \
assume."""

_ARCHETYPES = """\
Choose ONE topology archetype, or hybridize deliberately:
  - INDEPENDENT parallelism (process mode): the work shards into disjoint units with no \
cross-dependencies — one applicant, one contract, one transaction per worker. Emit `topology` \
with the unit definition and the per-unit + aggregate steps. `modules`, `interfaces`, `dag` \
stay empty. Each worker needs only its own shard spec.
  - INTERDEPENDENT parallelism (build mode): the units are code modules that depend on each \
other. Emit `modules`, typed `interfaces`, and a `dag`. Every module declares its TOUCH \
POINTS — the exact interface ids it `consumes` and `provides` — so parallel agents cannot \
drift apart. The `dag` deps must let the engine partition tasks into topological waves."""

_SQL_STEPS = """\
MATCH THE STEP KIND TO THE DETECTION SHAPE (process mode) — three kinds, each irreplaceable:
  - kind:"sql" — joins, aggregates, and window patterns over STRUCTURED columns: matched \
pairs, duplicate clusters, sums vs limits, grouped balances, time-window bursts. Emit \
{id, kind:"sql", per_unit:false, sql:"SELECT ...", label} against the provided db schema — a \
single read-only SELECT (CTEs allowed; no writes, no PRAGMA). Its result rows REPLACE the \
unit set: each row becomes one candidate for the steps that follow; select every column the \
downstream judge needs (both sides of a pair, the sum and the limit, the burst window). \
PRECISION: the candidate SQL must approximate the request's OWN phenomenon, not a loose \
numeric proxy for it. Two things: \
(a) BIND to the request's named entities and their state using the schema's own columns. If the \
request scopes to a described subset (a "dormant" account, a "closed" ticket, an "external" \
counterparty), filter the column that records that state; if it names a DIRECTION or TYPE of \
event ("reactivation / inflow / deposit" vs "payout / withdrawal / transfer out"), filter \
direction/kind. Do NOT substitute a computed proxy (a LAG time-gap between rows) for a status the \
schema already stores — a "dormant-account reactivation" is an INFLOW that wakes a status=dormant \
account, not any large row that happens to follow a quiet spell on an active account. \
(b) encode the request's quantitative qualifiers directly in WHERE/HAVING — a magnitude it calls \
"large/material/unusual", a minimum count or run-length, a time gap, a threshold vs a limit — \
derived from the request's language and the data's scale. Do NOT emit an "any activity / any \
match" net that defers all discrimination to the judge; an over-broad or off-target candidate set \
floods the reviewer with false positives.
  - per-unit JUDGMENT steps — wherever the signal is SEMANTIC, in free-text fields (columns \
like *_narrative, notes, memo, description): meaning must be read, not keyword-matched — a \
paraphrase carries the same signal as the phrasing you would grep for, so SQL LIKE-patterns \
are blind here by construction. Route each row/candidate through a judgment step whose \
prompt_spec names the MEANING to look for. When a judgment step CONFIRMS candidates from a \
sql/analysis step, its prompt_spec must confirm against the detection's STRUCTURAL definition \
(the matched keys/sums/identifiers/window), NOT demand that the rows share identical free-text \
or describe the same underlying story — a genuine duplicate or ring member is routinely re-filed \
with fresh wording, so requiring matching prose silently drops true findings.
  - kind:"analysis" — multi-hop or statistical logic no single query expresses: chain/layer \
tracing, circular-flow detection, concert-party accumulation, fuzzy matching, cross-record \
consistency, distribution outliers. Emit {id, kind:"analysis", per_unit:false, purpose, \
label}: the platform commissions a small deterministic tool from your `purpose` (it receives \
{"rows": [...]} and returns {"findings": [...]}); findings replace the unit set like sql rows \
do. The `purpose` must be CONCRETE and testable — name the inputs, the logic, and what a \
finding row contains.
A topology may end on a candidate step when the query/tool itself is the finding; include a \
`flagged` column (0/1) when only some rows are findings. Most real detections COMPOSE kinds: \
sql or analysis finds candidates, then judgment reads each candidate's narrative evidence."""

_WORKSPACE = """\
Your build workers are FOLDER-ISOLATED: each module's agent writes only its own workspace \
folder and cannot see a sibling's files; the certified interface specs are the one shared, \
read-only surface. Any file two modules both need MUST therefore be a declared interface, \
never shared scratch. Workers may also commission small deterministic tools (createTool) \
when a step needs computed evidence — in process mode express that as an `analysis` step."""

_DISCIPLINE = f"""\
Non-negotiable requirements for every plan:
  - ASSUMPTIONS: sanitization blurred real values behind placeholders (like «TABLE_A»). For \
every place you had to assume a shape, name, type, or convention, record it in that module's \
or step's `assumptions` so the certifier can verify it cheaply against the real context.
  - TASK FLAGS: tag every module and every topology step with `task_flags` drawn ONLY from \
this vocabulary — greenfield-codegen, refactor-edit, sql-data, test-writing, docs-writing, \
extraction, math, agentic-tool-use, long-context, merge-review. What kind of work each unit \
is is a planning fact; the scheduler routes each task to the pool member best at that kind. \
A module that edits existing code MUST carry refactor-edit; a schema/query module MUST carry \
sql-data; a prose/docs task MUST carry docs-writing.
  - BILL OF MATERIALS (mandatory): `model_bom` names the seats and counts the fan-out width \
your topology needs — it drives GPU provisioning and the customer's quote. State it for every \
plan; a plan without a BoM is incomplete.
  - INTERFACES carry real JSON Schemas; ACCEPTANCE CRITERIA from the brief must each be \
covered by something the plan produces.
  - Design for verification: prefer explicit failure branches for every external call, parse, \
and division; keep rounding/locale/auth conventions uniform across modules.

{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_PLAN = f"""\
You are the planning intelligence for Nxcleus. You receive a SANITIZED brief — a structured \
description of a business process with all confidential values replaced by typed \
placeholders. You never see the customer's real data; you design the work topology from the \
brief's STRUCTURE, which is complete and faithful.

{_FABRIC}

{_ARCHETYPES}

{_SQL_STEPS}

{_WORKSPACE}

{_DISCIPLINE}"""


def sandbox_system(company: str, company_schema: dict[str, Any]) -> str:
    """Sandbox planner variant (09 §2): scoped to one synthetic company's schema; politely
    refuses out-of-scope requests."""
    return f"""\
You are the planning intelligence for the Nxcleus judge sandbox, scoped to a single \
synthetic company: "{company}". You may design PROCESS-MODE work only, and ONLY against this \
company's schema — no other data source exists in the sandbox.

Company schema (the only tables/fields available):
{as_json(company_schema)}

{_FABRIC}

Design a process-mode topology (independent parallelism) that DETECTS the requested pattern. \
A detection request is ALWAYS built as: (1) a candidate step — kind:"sql" or kind:"analysis" — \
that narrows the whole corpus to the rows that STRUCTURALLY match the request (matched pairs, \
clusters, sums vs limits, time-window bursts, chains), then optionally (2) a per-unit judgment \
step that confirms each candidate against free-text evidence. A bare per-unit scan over raw \
rows with NO candidate step is almost always wrong: it samples the corpus and never surfaces \
the pattern, so the run reports zero findings. Emit a candidate step unless the request is \
genuinely out of scope for this company's data. Reference only tables and fields present in the \
schema above; end with an aggregate step producing a dashboard payload.

{_SQL_STEPS}

If the request cannot be satisfied from this company's data — it asks for a data source that \
is not here, or falls outside process-mode analysis — do NOT invent data. Return a minimal \
plan whose single risk explains, in one polite sentence, that the request is out of scope for \
this company, and set mode to "process" with an empty topology. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""


REPLAN_GUIDANCE = f"""\
This is a CONSTRAINED re-plan. You receive the current plan, the certifier's findings, and a \
SCOPE LOCK: a list of plan region ids you are permitted to change (`only_regions`). Return a \
full plan object, but every edit you make MUST fall inside the locked regions — do not touch \
any module, interface, topology step, or dag task whose id is not in `only_regions`. Edits \
outside the lock will be rejected and the re-plan will fail. Address the findings precisely \
and change nothing else. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

# The Plan artifact schema is the structured-output contract (03 §3). Hand-written to mirror
# db/models.Plan without importing it (team ruling).
_TASK_FLAGS = ["greenfield-codegen", "refactor-edit", "sql-data", "test-writing", "docs-writing",
               "extraction", "math", "agentic-tool-use", "long-context", "merge-review"]
_MODULE_ID_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": True,
    "properties": {
        "plan_id": {"type": "string"}, "job_id": {"type": "string"}, "version": {"type": "integer"},
        "mode": {"enum": ["build", "process", "semi"]},
        "modules": {"type": "array", "items": {"type": "object", "additionalProperties": True,
            "properties": {
                "id": {"type": "string", "pattern": _MODULE_ID_PATTERN},
                "name": {"type": "string"}, "purpose": {"type": "string"},
                "consumes": {"type": "array", "items": {"type": "string"}},
                "provides": {"type": "array", "items": {"type": "string"}},
                "algorithm": {"type": "string"}, "complexity": {"enum": ["S", "M", "L"]},
                "task_flags": {"type": "array", "items": {"enum": _TASK_FLAGS}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "model": {"type": ["string", "null"]}},
            "required": ["id"]}},
        "interfaces": {"type": "array", "items": {"type": "object", "additionalProperties": True,
            "properties": {"id": {"type": "string"}, "producer": {"type": "string"},
                           "consumers": {"type": "array", "items": {"type": "string"}},
                           "schema": {"type": "object"}}, "required": ["id"]}},
        "dag": {"type": "array", "items": {"type": "object", "properties": {
            "task": {"type": "string"},
            "module": {"type": "string", "pattern": _MODULE_ID_PATTERN},
            "deps": {"type": "array", "items": {"type": "string"}}},
            "required": ["task", "module"]}},
        "topology": {"type": ["object", "null"], "additionalProperties": True, "properties": {
            "unit": {"type": "object", "additionalProperties": True, "properties": {
                "noun": {"type": "string"}, "source": {"type": "string"}, "schema": {"type": "object"}}},
            "steps": {"type": "array", "items": {"type": "object", "additionalProperties": True,
                "properties": {"id": {"type": "string"}, "seat": {"type": ["string", "null"]},
                               "per_unit": {"type": "boolean"}, "kind": {"type": ["string", "null"]},
                               "sql": {"type": ["string", "null"]}, "label": {"type": "string"},
                               "purpose": {"type": ["string", "null"]},
                               "prompt_spec": {"type": "string"}, "output_schema": {"type": "object"},
                               "task_flags": {"type": "array", "items": {"type": "string"}}},
                "required": ["id"]}}}},
        "data_schemas": {"type": "object"},
        "model_bom": {"type": "object", "additionalProperties": True, "properties": {
            "seats": {"type": "array", "items": {"type": "object", "additionalProperties": True,
                "properties": {"seat": {"type": "string"}, "count": {"type": "integer"},
                               "why": {"type": "string"}, "sampling": {"type": ["number", "null"]}},
                "required": ["seat"]}},
            "fleet": {"type": "object", "additionalProperties": True, "properties": {
                "profile": {"type": "string"}, "nodes": {"type": "integer"},
                "parallel_width": {"type": "integer"}}},
            "conductor": {"type": ["object", "null"]}}},
        "estimates": {"type": "object", "additionalProperties": True, "properties": {
            "frontier_tokens": {"type": "integer"}, "local_tokens": {"type": "number"},
            "gpu_hours": {"type": "number"}}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plan_id", "job_id", "mode", "model_bom"],
}


async def _stream_cb(emit: EmitFn, event: str) -> Callable[[str], Awaitable[None]]:
    async def cb(chunk: str) -> None:
        await emit(event, {"text": chunk})
    return cb


async def plan(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    brief: dict[str, Any],
    temperature: float | None = None,
    stream: bool = True,
) -> dict[str, Any]:
    """Author Plan v1 (dict) from the sanitized brief (stage 1). Streams reasoning as plan.delta."""
    cb = await _stream_cb(emit, "plan.delta") if stream else None
    c = await complete("planner", convo(SYSTEM_PLAN, as_json(brief)),
                       data_class=DATA_CLASS, schema=PLAN_SCHEMA, temperature=temperature, stream=cb)
    out = parsed_or_raise(c, "planner.plan")
    await emit("plan.completed", {"mode": out.get("mode"), "modules": len(out.get("modules", [])),
               "width": (out.get("model_bom", {}).get("fleet", {}) or {}).get("parallel_width")})
    return out


async def replan(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    plan: dict[str, Any],
    findings: list[str],
    scope_lock: dict[str, Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Constrained re-plan (03 §3): scope-locked to `scope_lock["only_regions"]`. Returns the full
    re-planned plan dict; rejects out-of-scope edits.

    Enforcement is in-harness (not just prompt): any region that CHANGED but is not inside the
    lock -> plan.scope_violation event + ValueError. Certifier/refine batch consults here."""
    only_regions = scope_lock.get("only_regions", [])
    lock = set(only_regions)
    current_plan = plan
    before = region_ids(current_plan)
    payload = as_json({"current_plan": current_plan, "findings": findings,
                       "scope_lock": {"only_regions": only_regions}})
    c = await complete("planner", convo(SYSTEM_PLAN + "\n\n" + REPLAN_GUIDANCE, payload),
                       data_class=DATA_CLASS, schema=PLAN_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "planner.replan")

    # Scope-lock enforcement: compare each region's content; anything altered outside the lock
    # is a violation. New/removed ids outside the lock are violations too.
    touched = _changed_regions(current_plan, out)
    illegal = {r for r in touched if r not in lock}
    if illegal:
        await emit("plan.scope_violation", {"illegal_regions": sorted(illegal),
                                            "allowed": sorted(lock)})
        raise ValueError(f"planner.replan touched regions outside the scope lock: {sorted(illegal)}")

    await emit("plan.replanned", {"only_regions": only_regions,
               "added_regions": sorted(region_ids(out) - before)})
    return out


def _changed_regions(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """Ids of scope-lockable regions whose content differs (added, removed, or edited).

    Scope-lock regions are modules, interfaces, and topology steps (the ids `only_regions`
    references, per 03 §3). The `dag` is derived structure and is deliberately excluded — a
    dag task can share a string id with a module, and indexing both would let an unchanged
    task mask a changed module."""
    def index(plan: dict[str, Any]) -> dict[str, Any]:
        idx: dict[str, Any] = {}
        for m in plan.get("modules", []) or []:
            idx[m.get("id", "")] = m
        for i in plan.get("interfaces", []) or []:
            idx[i.get("id", "")] = i
        for s in ((plan.get("topology") or {}).get("steps") or []):
            idx[s.get("id", "")] = s
        idx.pop("", None)
        return idx

    a, b = index(before), index(after)
    changed = set()
    for rid in set(a) | set(b):
        if a.get(rid) != b.get(rid):
            changed.add(rid)
    return changed


async def sandbox_plan(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    prompt: str,
    company: str,
    company_schema: dict[str, Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Sandbox planning (09 §2): company-schema-scoped process-mode plan; polite out-of-scope refusal."""
    messages = [msg("system", sandbox_system(company, company_schema)), msg("user", prompt)]
    c = await complete("planner", messages, data_class=DATA_CLASS, schema=PLAN_SCHEMA,
                       temperature=temperature)
    out = parsed_or_raise(c, "planner.sandbox_plan")
    steps = len((out.get("topology") or {}).get("steps") or [])
    risks = out.get("risks", [])
    if steps == 0:
        await emit("system.notice", {"scope": "sandbox",
                   "message": risks[0] if risks else "request out of scope for this company"})
    else:
        await emit("plan.completed", {"mode": out.get("mode"), "company": company, "steps": steps})
    return out
