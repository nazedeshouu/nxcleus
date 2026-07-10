"""Seat: `certifier` — plan completion, rehydration & certification (stage 2, refine).

Runs on `local:B/glm-46` (RAW clearance, D9): it reads the customer's original request
verbatim, the raw code map, real DB schemas, and the boundary vault — everything the frontier
planner could not see. Its job is to find and fix everything that information gap caused, then
restore production specificity, pin the goal, and emit the tests that guard its own amendments.

This is the product's originality claim in prompt form: a strong local model completes what a
stronger frontier model necessarily left incomplete.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.seats._common import (
    ENGLISH_ONLY,
    GENESIS_HASH,
    STRUCTURED_ONLY,
    amendment_hash,
    apply_rfc6902,
    as_json,
    convo,
    normalize_regions,
    parsed_or_raise,
    region_ids,
    rehydrate_tokens,
)
from app.seats.base import CompleteFn, EmitFn

# The certifier holds each certification round to a soft consult budget (03 §4): amend-first,
# consult sparingly. Overflow consults are deferred (system.notice + `deferred_consults`) rather
# than fired — a simple KYC plan does not need eight frontier round-trips. The backend keeps its
# own hard round cap on top of this.
SOFT_CONSULT_CAP = 2

# The 7 checks fan out concurrently; on the hosted-AMD fallback a single instance served all 7 at
# once and single-call latency (19-42s observed) blew past the 120s seat timeout, failing the stage.
# ponytail: fixed cap of 3; make it per-backend only if seats ever fan out much wider than this.
_CHECK_CONCURRENCY = 3

# Harnesses return plain, schema-validated dicts; backend adapts into db/models (CertifyResult,
# Finding, IntegrationTestSpec, OracleVector) at the call site. No backend model imports (team ruling).

DATA_CLASS = "RAW"

_FRAMING = """\
A STRONGER model authored the plan you are reviewing — but it did so WITHOUT seeing the real \
context. It planned against a sanitized brief: real names, tables, files, and values were \
replaced by typed placeholders, and it had to ASSUME the shapes behind them. You are local, \
you have the FULL raw context, and your job is to find and fix everything that information gap \
caused. Verify each assumption the planner marked; correct details the sanitization blurred; \
restore production specificity. Trust the plan's STRUCTURE (the frontier is good at that); \
distrust its GUESSES about the concrete."""

# The 7-check suite (03 §4). Each runs as a separate focused pass (parallelizable).
CHECKS: dict[str, str] = {
    "interface-compat": (
        "Verify every module's `consumes` is matched by some module's `provides`, and that "
        "the producing and consuming interface schemas are compatible (types, required fields). "
        "Flag any dangling consume, type mismatch, or missing interface."
    ),
    "data-completeness": (
        "Verify every field any module or step READS is PRODUCED somewhere upstream — by an "
        "interface, a data schema, or the input. Flag any field that is consumed but never "
        "produced, and any output nothing consumes if the goal needs it."
    ),
    "error-coverage": (
        "Verify every external call, every parse, and every division has a specified failure "
        "branch. Flag any happy-path-only step where a realistic failure (timeout, malformed "
        "input, empty result, zero denominator) is unhandled."
    ),
    "pattern-consistency": (
        "Verify conventions are uniform across modules: authentication, state handling, money "
        "rounding, date/locale formatting, identifier casing. Flag any module that diverges "
        "from the pattern the others establish."
    ),
    "ac-coverage": (
        "Verify every acceptance criterion in the brief maps to at least one planned test, "
        "inspector probe, or oracle vector. Flag any criterion with no coverage."
    ),
    "bom-sanity": (
        "Verify every judgment step names a seat; the fleet width in the BoM is at least the "
        "DAG's maximum parallelism; and every module/step carries SANE task_flags — a module "
        "that edits existing code must carry refactor-edit, a schema/query module must carry "
        "sql-data, a prose task must carry docs-writing. Flag missing or nonsensical flags. "
        "Every kind:\"analysis\" step must carry a CONCRETE, testable `purpose` — naming its "
        "inputs, its logic, and what a finding row contains; amend vague purposes into "
        "concrete ones."
    ),
    "production-fit": (
        "This is the pass only you can do (D9). Check every planner assumption against the RAW "
        "context: real module paths, real table and field names and types, actual framework "
        "conventions, actual data shapes and cardinalities. Where the plan's placeholder-era "
        "guess is wrong, amend it to the real value/shape. Where it is right, confirm it."
    ),
}


def check_system(check: str) -> str:
    return f"""\
{_FRAMING}

FOCUSED CHECK — {check}: {CHECKS[check]}

Return findings ONLY for this check. Bias HARD toward amend: the local completion pass exists \
precisely to fix things WITHOUT a frontier round-trip, and you have the full raw context to do \
it. A consult is the rare, expensive exception. For each finding, TRIAGE it:
  - amend (DEFAULT): fix it locally with a precise RFC-6902 patch to the plan. Give the patch \
(op/path/value over the plan JSON), a one-line rationale, and the spec/AC reference it \
satisfies. Any wrong VALUE, name, type, threshold, flag, missing field, missing failure branch, \
or added test is an amend — not a consult.
  - consult: choose this ONLY when the fix is genuinely STRUCTURAL and no local patch can express \
it — the topology itself is wrong: a module that must be added or removed, an interface that \
must be redesigned, a data flow that must be re-routed. If you can describe the fix as a patch, \
it is an amend, not a consult. Each consult costs the customer a frontier call, so at most about \
TWO consults are warranted for an entire plan; beyond that you are almost certainly under-using \
amend. Give a precise question and a scope lock whose `only_regions` quotes the plan's region \
ids VERBATIM — the exact `id` strings of the modules, interfaces, or topology steps involved \
(e.g. "mod_risk", "if_sanctions_result", "s_extract"). NEVER a JSONPath, a dotted path, or a \
field name (not "$.model_bom.seats", not "modules.mod_risk.algorithm" — just "mod_risk"). A \
scope lock that names no real region id will be discarded.

Severity is gap (something missing), inconsistency (something contradictory), or structural \
(a design-level problem). If the plan passes this check, return an empty findings list. \
{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""


SYSTEM_GOAL = f"""\
You emit the GOAL for this job (D10): a semi-detailed, plain-language statement of what must \
EXIST when the work is finished. Derive it from the customer's ORIGINAL raw request (not the \
sanitized brief) plus the certified plan. It is the fixed star the whole job is judged \
against — the conductor checks every wave against it, and a dedicated check verifies the \
deliverable against it at the end.

Write it concrete enough to verify against ("applicants are screened against OFAC and EU \
sanctions lists, risk-scored, and routed to review above threshold; a reviewer can see why \
each was flagged") yet short enough to hold in one prompt — a few sentences, in the \
customer's own terms, not the plan's vocabulary. Do not restate the plan; state the outcome. \
{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_TESTS = f"""\
You emit the deterministic test artifacts that will guard this plan — including your own \
amendments (a bad local patch must die at the same QA gate as bad code).

  - IntegrationTestSpec[]: given concrete inputs at named interfaces, assert concrete outputs \
(path/op/value). Cover the main path, each acceptance criterion, and each amendment you made.
  - OracleVector[]: for every numeric rule, the INPUTS only — never the expected output (the \
oracle computes that blind at stage 6). Give each a tolerance: "exact" for money after \
rounding, "epsilon:<n>" for scores. Each vector MUST carry `rule_text`: the full rule stated \
in words (formula, thresholds, rounding), self-contained — the blind oracle recomputes from \
that text alone and never sees the plan.

Use the plan's real (rehydrated) interface ids and rule ids. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_SCENARIOS = f"""\
You emit 3 to 5 PLAN-AWARE adversarial scenarios for the inspector swarm — specific ways this \
particular process could fail that a generic probe suite would miss. Ground each in the plan's \
actual logic: a sanctions hit under a transliterated-name variant, a renewal clause whose \
notice window straddles the threshold, a duplicate submission that must be idempotent. Each \
scenario is one sentence describing the probe and what a correct process must do. \
{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_REFINE_TRIAGE = f"""\
{_FRAMING}

A customer wants to REFINE an already-certified process. Triage their request as a delta \
against the certified plan:
  - amend: mechanical — a new field, a threshold change, an added schema data point, an extra \
output. Give the RFC-6902 patch, rationale, and the regions it touches so only those modules \
rebuild.
  - consult: structural — the change alters the topology or adds a capability the plan cannot \
express by patching. Give a scope lock and a question for the planner.

Refine stays local whenever it can — a consult that fires costs the customer a frontier call, \
so reach for amend first. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

_AMENDMENT = {
    "type": "object",
    "properties": {
        "plan_ref": {"type": "string"},
        "patch": {"type": "array", "items": {
            "type": "object",
            "properties": {"op": {"enum": ["add", "replace", "remove"]},
                           "path": {"type": "string"}, "value": {}},
            "required": ["op", "path"]}},
        "rationale": {"type": "string"},
        "spec_ref": {"type": "string"},
    },
    "required": ["plan_ref", "patch", "rationale"],
}
_CONSULT = {
    "type": "object",
    "properties": {
        "scope": {"type": "object", "properties": {
            "only_regions": {"type": "array", "items": {"type": "string"}}},
            "required": ["only_regions"]},
        "question": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scope", "question"],
}
_FINDING = {
    "type": "object",
    "properties": {
        "finding_id": {"type": "string"},
        "check": {"type": "string"},
        "plan_ref": {"type": "string"},
        "severity": {"enum": ["gap", "inconsistency", "structural"]},
        "triage": {"enum": ["amend", "consult"]},
        "amendment": _AMENDMENT,
        "consult_request": _CONSULT,
    },
    "required": ["finding_id", "check", "severity", "triage"],
}
FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"findings": {"type": "array", "items": _FINDING}},
    "required": ["findings"],
}
GOAL_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"goal": {"type": "string"}}, "required": ["goal"],
}
_TEST_SPEC = {"type": "object", "additionalProperties": True, "properties": {
    "id": {"type": "string"}, "module": {"type": "string"},
    "kind": {"enum": ["integration", "unit"]}, "given": {"type": "object"},
    "expect": {"type": "array", "items": {"type": "object", "properties": {
        "path": {"type": "string"}, "op": {"type": "string"}, "value": {}}, "required": ["path"]}}},
    "required": ["id"]}
_ORACLE_VECTOR = {"type": "object", "additionalProperties": True, "properties": {
    "id": {"type": "string"}, "rule": {"type": "string"},
    "rule_text": {"type": "string"},   # full rule in words — the oracle's ONLY view of the rule (S4)
    "inputs": {"type": "object"},
    "tolerance": {"type": ["string", "null"]}}, "required": ["id"]}
TESTS_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"tests": {"type": "array", "items": _TEST_SPEC},
                   "vectors": {"type": "array", "items": _ORACLE_VECTOR}},
    # LIVE FIX (backend-w2): only `tests` is required. Real GLM output intermittently omits
    # `vectors`, which failed validation even after the router's repair round and forced a costly
    # full-stage retry; the harness already defaults `vectors` to []. A process with no numeric
    # rules legitimately has no oracle vectors, so this is also more correct.
    "required": ["tests"],
}
SCENARIOS_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    # LIVE FIX (backend-w2): dropped minItems/maxItems. A real model returning 2 or 6 scenarios is
    # fine; strict cardinality only bought spurious validation failures. Prompt still asks for 3-5.
    "properties": {"scenarios": {"type": "array", "items": {"type": "string"}}},
    "required": ["scenarios"],
}
REFINE_TRIAGE_SCHEMA = _FINDING

# Repair reprompt for a consult whose `only_regions` named no real plan region (the JSONPath-ish
# failure mode). One shot: re-express the scope lock using verbatim plan region ids, or empty.
REPAIR_REGIONS_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"only_regions": {"type": "array", "items": {"type": "string"}}},
    "required": ["only_regions"],
}


REPAIR_SQL_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"sql": {"type": "string"}}, "required": ["sql"],
}


def _repair_sql_system(schema_tables: list[dict]) -> str:
    return f"""\
A topology step's sql query FAILED when executed read-only against the customer's real corpus. \
Fix it. Constraints: a single read-only SELECT (a WITH/CTE is fine); no INSERT/UPDATE/DELETE/\
PRAGMA/ATTACH; reference only the tables and columns below; keep the step's detection intent \
(the same pairs/clusters/aggregates/windows), and keep every column a downstream judge needs \
in the result rows.

The corpus schema (the only tables/columns that exist):
{as_json(schema_tables)}

Return the corrected query only. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""


async def repair_sql(
    complete: CompleteFn, emit: EmitFn, *, step: dict[str, Any], error: str,
    schema_tables: list[dict], temperature: float | None = None,
) -> str:
    """One repair round for a sql topology step that failed against the real corpus (stage 2
    production-fit). Returns the corrected sql, or "" when the repair itself fails."""
    body = {"step_id": step.get("id"), "label": step.get("label", ""),
            "failed_sql": step.get("sql", ""), "error": error}
    try:
        c = await complete("certifier", convo(_repair_sql_system(schema_tables), as_json(body)),
                           data_class=DATA_CLASS, schema=REPAIR_SQL_SCHEMA, temperature=temperature)
        out = parsed_or_raise(c, "certifier.repair_sql")
    except Exception:  # noqa: BLE001 — a failed repair drops the step, it must not crash the stage
        return ""
    return out.get("sql", "")


def _repair_regions_system(valid_ids: list[str]) -> str:
    return f"""\
Your previous consult named plan regions that DO NOT EXIST — its `only_regions` was not a list of \
real region ids. A scope lock's `only_regions` MUST quote plan region ids VERBATIM: the exact \
`id` strings of modules, interfaces, or topology steps in the plan (e.g. "mod_risk", \
"if_sanctions_result", "s_extract"). Not a JSONPath, not a dotted path, not a field or seat name.

The ONLY valid region ids for this plan are:
{as_json(valid_ids)}

Re-express the scope lock for your consult using ONLY ids from that list — pick the smallest set \
of regions that contains the fix. If NONE of them apply, return an empty list. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""


# ─────────────────────────────────────────────────────────────────────────────
# Harnesses
# ─────────────────────────────────────────────────────────────────────────────


async def run_check(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], raw_context: dict[str, Any],
    check: str, temperature: float | None = None,
) -> list[dict[str, Any]]:
    """One focused certification pass. production-fit gets the raw context; others get the plan."""
    body: dict[str, Any] = {"plan": plan}
    if check == "production-fit":
        body["raw_context"] = raw_context
    c = await complete("certifier", convo(check_system(check), as_json(body)),
                       data_class=DATA_CLASS, schema=FINDINGS_SCHEMA, temperature=temperature)
    findings = parsed_or_raise(c, f"certifier.run_check[{check}]").get("findings", [])
    for f in findings:
        f.setdefault("check", check)
    await emit("certify.check_completed", {"check": check, "findings": len(findings)})
    return findings


def _is_timeout(exc: BaseException) -> bool:
    """A timeout-class failure worth one retry (asyncio/builtin TimeoutError, httpx ReadTimeout, etc.)."""
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in type(exc).__name__.lower()


async def _run_check_guarded(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], raw_context: dict[str, Any],
    check: str, sem: asyncio.Semaphore, temperature: float | None = None,
) -> list[dict[str, Any]]:
    """Resilient wrapper around run_check (live-fix, backend-w3): cap concurrency via `sem`, retry
    ONCE on a timeout-class failure, then DEGRADE the check (record inconclusive, contribute no
    findings) rather than fail the whole stage. No certify check is treated as mandatory today — an
    empty findings list already means "this check found nothing" — so a degraded check reads as a
    conservative pass with an explicit inconclusive marker for the honesty trail."""
    async with sem:
        for attempt in (1, 2):
            try:
                return await run_check(complete, emit, plan=plan, raw_context=raw_context,
                                       check=check, temperature=temperature)
            except Exception as exc:  # noqa: BLE001
                if attempt == 1 and _is_timeout(exc):
                    await emit("system.notice", {"scope": "certify", "level": "warn",
                               "message": f"check {check} timed out; retrying once"})
                    continue
                await emit("system.notice", {"scope": "certify", "level": "warn",
                           "message": f"check {check} inconclusive after {attempt} attempt(s): "
                                      f"{type(exc).__name__}: {str(exc)[:160]}"})
                await emit("certify.check_completed", {"check": check, "findings": 0, "inconclusive": True})
                return []
        return []  # unreachable


async def _repair_consult_regions(
    complete: CompleteFn, emit: EmitFn, *, consult: dict[str, Any], valid_ids: set[str],
    bad: list[str], temperature: float | None = None,
) -> list[str]:
    """One repair reprompt for a consult whose scope lock named no real region: ask the certifier
    to restate `only_regions` with verbatim plan ids. Returns the resolved ids (possibly empty). A
    failed repair NEVER raises out — a consult it can't fix is simply deferred."""
    body = {"question": consult.get("question", ""), "rejected_only_regions": list(bad),
            "valid_region_ids": sorted(valid_ids)}
    try:
        c = await complete("certifier", convo(_repair_regions_system(sorted(valid_ids)), as_json(body)),
                           data_class=DATA_CLASS, schema=REPAIR_REGIONS_SCHEMA, temperature=temperature)
        out = parsed_or_raise(c, "certifier.repair_consult_regions")
    except Exception:  # noqa: BLE001 — a failed repair defers the consult, it must not crash the stage
        return []
    resolved, _ = normalize_regions(out.get("only_regions", []), valid_ids)
    await emit("certify.consult_repaired", {"regions": resolved})
    return resolved


async def _triage_consults(
    complete: CompleteFn, emit: EmitFn, *, findings: list[dict[str, Any]], valid_ids: set[str],
    temperature: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Consult discipline (03 §4). For every finding triaged `consult`:
      1. normalize its `only_regions` onto the canonical vocabulary (`normalize_regions`);
      2. if it resolves to no real region, run ONE repair reprompt; still nothing -> defer it;
      3. enforce the soft per-round cap (`SOFT_CONSULT_CAP`) — overflow consults are deferred.
    Kept consults carry verbatim region ids in `consult_request.scope.only_regions`, so the stage
    passes a clean scope lock straight into `planner.replan`. Amend findings pass through
    untouched and in place. Returns `(kept_findings, deferred)` where deferred is a list of
    `{finding_id, reason, only_regions}` and each deferral also emits a `system.notice`."""
    kept: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    accepted = 0
    for f in findings:
        if f.get("triage") != "consult":
            kept.append(f)
            continue
        req = f.get("consult_request") or {}
        scope = req.get("scope") or {}
        raw_regions = scope.get("only_regions", []) or []
        resolved, unresolved = normalize_regions(raw_regions, valid_ids)
        if not resolved:
            resolved = await _repair_consult_regions(
                complete, emit, consult=req, valid_ids=valid_ids,
                bad=unresolved or [str(r) for r in raw_regions], temperature=temperature)
        fid = f.get("finding_id")
        if not resolved:
            deferred.append({"finding_id": fid, "reason": "no_valid_region",
                             "only_regions": [str(r) for r in raw_regions]})
            await emit("system.notice", {"scope": "certify", "level": "warn",
                       "message": f"consult {fid} dropped: only_regions named no plan region "
                                  f"({[str(r) for r in raw_regions]})"})
            continue
        if accepted >= SOFT_CONSULT_CAP:
            deferred.append({"finding_id": fid, "reason": "consult_cap", "only_regions": resolved})
            await emit("system.notice", {"scope": "certify", "level": "warn",
                       "message": f"consult {fid} deferred: >{SOFT_CONSULT_CAP} consults this "
                                  f"round — amend-first, escalate only the most structural"})
            continue
        scope["only_regions"] = resolved
        req["scope"] = scope
        f["consult_request"] = req
        kept.append(f)
        accepted += 1
    return kept, deferred


async def certify(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    plan: dict[str, Any],
    raw_context: dict[str, Any],
    policy: dict[str, Any] | None = None,
    prev_hash: str = GENESIS_HASH,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Full stage-2 certification: run the 7 checks (parallel), apply amendments, collect
    consults, rehydrate, emit goal + tests + vectors + scenarios. Returns a CertifyResult-shaped
    dict PLUS `certified_plan` (the amended + rehydrated, version-bumped plan — stage 2's headline
    output; backend's CertifyResult adds this field or reads it alongside).

    `raw_context` carries the full raw context the certifier reads (D9); the original request and
    the boundary vault ride on it as `raw_context["request"]` and `raw_context["vault"]`.
    Consults are returned in `findings` (triage=='consult') for the stage to batch into a
    scope-locked re-plan; this harness does the local, deterministic part end-to-end."""
    raw_request = raw_context.get("request", "")
    vault = raw_context.get("vault", {})
    sem = asyncio.Semaphore(_CHECK_CONCURRENCY)
    results = await asyncio.gather(
        *[_run_check_guarded(complete, emit, plan=plan, raw_context=raw_context, check=chk,
                             sem=sem, temperature=temperature) for chk in CHECKS]
    )
    findings: list[dict[str, Any]] = [f for group in results for f in group]

    # Consult discipline (03 §4): normalize each consult's scope lock to the canonical region-id
    # vocabulary (repairing JSONPath-style output once, dropping locks that name no real region)
    # and hold the round to the soft consult cap. Validated against `plan`'s region ids — the same
    # plan the stage hands to `planner.replan` — so a kept consult's `only_regions` is guaranteed
    # to be a lock replan will accept, not reject. Overflow/untranslatable consults are deferred.
    findings, deferred_consults = await _triage_consults(
        complete, emit, findings=findings, valid_ids=region_ids(plan), temperature=temperature)

    # Apply every amendment immediately (03 §4); collect consults for the stage's re-plan loop.
    # Each applied amendment is hash-chained (origin: certifier) so the log is tamper-evident.
    working = plan
    applied, consults = 0, 0
    chain = prev_hash
    for f in findings:
        if f.get("triage") == "amend" and f.get("amendment", {}).get("patch"):
            try:
                working = apply_rfc6902(working, f["amendment"]["patch"])
                applied += 1
                amd = f["amendment"]
                amd["origin"] = amd.get("origin", "certifier")
                amd["prev_hash"] = chain
                amd["hash"] = amendment_hash(chain, amd.get("patch"), amd.get("rationale", ""))
                chain = amd["hash"]
                await emit("certify.amendment", {"finding_id": f.get("finding_id"),
                           "plan_ref": f.get("plan_ref"), "rationale": amd.get("rationale"),
                           "hash": amd["hash"]})
            except Exception as exc:  # noqa: BLE001 — skip a malformed patch, don't corrupt the plan
                await emit("system.notice", {"scope": "certify",
                           "message": f"skipped malformed amendment {f.get('finding_id')}: {exc}"})
        elif f.get("triage") == "consult":
            consults += 1
            await emit("certify.consult_requested", {"finding_id": f.get("finding_id"),
                       "only_regions": (f.get("consult_request") or {}).get("scope", {}).get("only_regions", [])})

    # Rehydration (D9) — deterministic vault substitution; the certified plan is now RAW.
    working, rehydrated = rehydrate_tokens(working, vault)
    working["version"] = int(working.get("version", 1)) + 1
    await emit("certify.rehydrated", {"identifiers_rehydrated": rehydrated})

    # Goal, tests+vectors, adversarial scenarios (goal derives from the RAW request, D10).
    goal = await emit_goal(complete, emit, raw_request=raw_request, certified_plan=working,
                           temperature=temperature)
    tests, vectors = await emit_tests(complete, emit, plan=working, temperature=temperature)
    scenarios = await emit_scenarios(complete, emit, plan=working, temperature=temperature)

    await emit("certify.certified", {"amendments": applied, "consults": consults,
               "deferred_consults": len(deferred_consults),
               "tests": len(tests), "vectors": len(vectors), "version": working["version"]})
    return {
        "findings": findings,
        "goal": goal,
        "tests": tests,
        "vectors": vectors,
        "adversarial_scenarios": scenarios,
        "identifiers_rehydrated": rehydrated,
        "certified_plan": working,
        "deferred_consults": deferred_consults,   # amend-first overflow / untranslatable locks
        "amendment_chain_head": chain,   # thread into the conductor's prev_hash next stage
    }


async def emit_goal(
    complete: CompleteFn, emit: EmitFn, *, raw_request: str, certified_plan: dict[str, Any],
    temperature: float | None = None,
) -> str:
    c = await complete("certifier", convo(SYSTEM_GOAL,
                       as_json({"original_request": raw_request, "certified_plan": certified_plan})),
                       data_class=DATA_CLASS, schema=GOAL_SCHEMA, temperature=temperature)
    goal = parsed_or_raise(c, "certifier.emit_goal").get("goal", "")
    await emit("certify.goal_set", {"goal": goal})
    return goal


async def emit_tests(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], temperature: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    c = await complete("certifier", convo(SYSTEM_TESTS, as_json(plan)),
                       data_class=DATA_CLASS, schema=TESTS_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "certifier.emit_tests")
    return out.get("tests", []), out.get("vectors", [])


async def emit_scenarios(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], temperature: float | None = None,
) -> list[str]:
    c = await complete("certifier", convo(SYSTEM_SCENARIOS, as_json(plan)),
                       data_class=DATA_CLASS, schema=SCENARIOS_SCHEMA, temperature=temperature)
    scenarios = parsed_or_raise(c, "certifier.emit_scenarios").get("scenarios", [])
    await emit("certify.scenarios_emitted", {"count": len(scenarios)})
    return scenarios


async def refine_triage(
    complete: CompleteFn, emit: EmitFn, *, certified_plan: dict[str, Any], refine_request: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Refine-phase triage (04 §5): amend vs consult on a delta against the certified plan.
    Returns a Finding-shaped dict."""
    c = await complete("certifier", convo(SYSTEM_REFINE_TRIAGE,
                       as_json({"certified_plan": certified_plan, "refine_request": refine_request})),
                       data_class=DATA_CLASS, schema=REFINE_TRIAGE_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "certifier.refine_triage")
    await emit("refine.triaged", {"triage": out.get("triage")})
    return out


# ── Engine entrypoint (canonical name; app/seats/_placeholder.py) ─────────────
async def triage_refine(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], request: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Refine triage in the stage's expected shape {triage, regions, rationale}. Delegates to
    refine_triage (which returns a full Finding)."""
    finding = await refine_triage(complete, emit, certified_plan=plan, refine_request=request,
                                  temperature=temperature)
    amendment = finding.get("amendment") or {}
    consult = finding.get("consult_request") or {}
    if finding.get("triage") == "consult":
        regions = (consult.get("scope") or {}).get("only_regions", [])
        rationale = consult.get("question", "")
    else:
        regions = [amendment.get("plan_ref", "")]
        rationale = amendment.get("rationale", "")
    return {"triage": finding.get("triage", "amend"),
            "regions": [r for r in regions if r], "rationale": rationale}
