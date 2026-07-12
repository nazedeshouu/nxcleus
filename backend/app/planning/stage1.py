"""Stage 1 — Planning: topology + BoM authoring (03 §3). Seat: planner. Zone: EXTERNAL (default) /
LOCAL (sovereign). The planner receives ONLY the SanitizedSpec (planner brief) and streams reasoning
(plan.delta) before emitting Plan v1.
"""
from __future__ import annotations

import asyncio

from app.events import E
from app.ids import deterministic
from app.orchestrator.seatlib import seat

# A corpus-bound detection plan that ships NO candidate step judges raw sampled rows and silently
# misses the pattern (the lawfirm/exchange 0-flag failure). The guard below replans once with this
# directive, then blocks loudly rather than delivering a false "0 findings". Generic — no per-company
# knowledge; it only asserts that a data-analysis plan must narrow the corpus before it judges.
_TOPOLOGY_REQUIRED = (
    "REQUIRED FIX: your previous plan had NO candidate step, so it would scan raw rows and surface "
    "nothing. This request targets a pattern in the corpus — you MUST include at least one candidate "
    'step (kind:"sql" for structured joins/aggregates/windows, or kind:"analysis" for multi-hop/'
    "statistical logic) that narrows the whole corpus to the rows that structurally match, BEFORE any "
    "per-unit judgment. Only omit it if the request is genuinely impossible from this company's schema, "
    "in which case say so in risks."
)


# A candidate query whose SHAPE is right but whose filter LITERAL doesn't match the corpus's encoding
# ('direction'='inflow' vs the seed's 'credit'/'debit') runs clean and returns ZERO rows — a silent
# 0-findings "done". The guard dry-runs the sql candidate step(s) read-only; if the final set is empty
# it replans ONCE to re-derive literals from the schema's stated values (Fix A surfaces them), then
# blocks loudly rather than shipping the false clean. Generic — no per-company knowledge.
_CANDIDATE_ZERO_ROWS = (
    "REQUIRED FIX: your previous candidate query ran against the real corpus and returned ZERO rows, "
    "so the run would report no findings. The query SHAPE is right but a filter LITERAL does not match "
    "how the data encodes that value — re-derive every WHERE/HAVING literal from the values stated in "
    "the schema brief (low-cardinality columns list their actual values, e.g. `direction (values: "
    "credit, debit)`), not from the request's wording. Filter a direction/type/status column using one "
    "of its listed values verbatim, never a synonym. Keep the same detection shape; only fix the literals."
)


def _sql_candidate_steps(plan: dict) -> list[dict]:
    return [s for s in ((plan.get("topology") or {}).get("steps") or [])
            if s.get("kind") == "sql" and s.get("sql")]


def _has_analysis_candidate(plan: dict) -> bool:
    return any(s.get("kind") == "analysis" and (s.get("purpose") or s.get("prompt_spec"))
              for s in ((plan.get("topology") or {}).get("steps") or []))


def _has_candidate_step(plan: dict) -> bool:
    """A candidate step (sql with a query, or analysis with a purpose) narrows the corpus. Its
    presence is the difference between 'detected the pattern' and 'sampled raw rows and missed it'."""
    for s in ((plan.get("topology") or {}).get("steps") or []):
        if s.get("kind") == "sql" and s.get("sql"):
            return True
        if s.get("kind") == "analysis" and (s.get("purpose") or s.get("prompt_spec")):
            return True
    return False


def _is_refusal(plan: dict) -> bool:
    """A deliberate out-of-scope refusal: empty topology + a stated risk. Honest 0-findings, not the
    silent-miss failure — the guard must let it through, not force a topology onto it."""
    steps = (plan.get("topology") or {}).get("steps") or []
    return not steps and bool(plan.get("risks"))


def _is_detection_plan(plan: dict) -> bool:
    return plan.get("mode") == "process" or bool(plan.get("topology"))


async def run(ctx) -> None:
    job = await ctx.refresh()
    brief = job.get("spec") or {}
    await ctx.emit(E.PLAN_STARTED, {"title": brief.get("title", ""), "sovereign": ctx.sovereign})

    planner = seat("planner")
    company = brief.get("company") if isinstance(brief, dict) else None
    sandbox_fn = getattr(planner, "sandbox_plan", None) \
        if job.get("origin") == "sandbox" and company else None

    async def _author(extra_directive: str = ""):
        if sandbox_fn:
            # sandbox planning is company-schema-scoped with polite out-of-scope refusal (09 §2)
            from app.sandbox import seeds
            prompt = brief.get("request") or brief.get("summary") or brief.get("title", "")
            if extra_directive:
                prompt = f"{prompt}\n\n{extra_directive}"
            return await sandbox_fn(ctx.complete, ctx.emit, prompt=prompt, company=company,
                                    company_schema={"tables": seeds.company_schema(company, values=True)})
        b = {**brief, "topology_requirement": extra_directive} if extra_directive else brief
        return await planner.plan(ctx.complete, ctx.emit, brief=b)

    plan = await _author()

    # Topology guard (reliability): a corpus-bound detection plan MUST narrow the corpus with a
    # candidate step or it silently reports 0 findings. Replan ONCE with an explicit requirement;
    # if it still lacks one (and isn't a genuine out-of-scope refusal), block loudly — never deliver
    # a silent 0-flag "done".
    def _missing_topology(p: dict) -> bool:
        # mock mode synthesizes plans from the schema — no real planner to hold accountable, and the
        # mock corpus fan-out is understood to be synthetic; only enforce on non-mock (live) runs.
        from app.config import settings
        if settings.model_mode == "mock":
            return False
        return bool(company) and _is_detection_plan(p) and not _has_candidate_step(p) and not _is_refusal(p)

    if _missing_topology(plan):
        await ctx.emit(E.SYSTEM_NOTICE, {
            "text": "plan has no corpus-narrowing (sql/analysis) step — replanning with a "
                    "topology requirement so the run can't silently report 0 findings",
            "level": "warn"})
        plan = await _author(_TOPOLOGY_REQUIRED)
        if _missing_topology(plan):
            await ctx.emit(E.SYSTEM_NOTICE, {
                "text": "planner produced no corpus-narrowing topology after a replan — blocking "
                        "the job rather than delivering a false 0-findings result",
                "level": "error"})
            await ctx.dao.update_job(ctx.job_id, status="blocked")
            await ctx.emit(E.JOB_BLOCKED, {"stage": "planning",
                           "reason": "no candidate topology for a corpus-bound detection request"})
            return

    # Zero-candidate guard (deterministic): a candidate step whose literal doesn't match the corpus's
    # encoding returns 0 rows and ships a silent clean "done". Dry-run the sql candidate step(s)
    # read-only; only the row COUNT is used locally (no row values cross to the planner), so this stays
    # boundary-safe. Replan once, then block loudly if it still returns nothing.
    async def _zero_candidates(p: dict) -> bool:
        from app.config import settings
        if settings.model_mode == "mock" or not company:
            return False   # mock synthesizes plans; mirror the topology guard's live-only skip
        steps = _sql_candidate_steps(p)
        if not steps or _has_analysis_candidate(p):
            return False   # nothing to dry-run, or an analysis step we can't evaluate at plan time
        from app.sandbox import seeds
        for s in steps:    # operate replaces units per step — the last step's rows are the candidates
            try:
                rows = await asyncio.to_thread(seeds.run_select, company, s["sql"], cap=1,
                                               timeout_s=settings.sql_step_timeout_s)
            except Exception:  # a broken query is the certifier's repair job, not this guard's
                return False
        return not rows

    if await _zero_candidates(plan):
        await ctx.emit(E.SYSTEM_NOTICE, {
            "text": "candidate query returned zero rows against the corpus — a filter literal doesn't "
                    "match the data's encoding; replanning to re-derive literals from the schema values",
            "level": "warn"})
        plan = await _author(_CANDIDATE_ZERO_ROWS)
        if _missing_topology(plan) or await _zero_candidates(plan):
            await ctx.emit(E.SYSTEM_NOTICE, {
                "text": "candidate query still returns zero rows after a replan — blocking the job "
                        "rather than delivering a false 0-findings result",
                "level": "error"})
            await ctx.dao.update_job(ctx.job_id, status="blocked")
            await ctx.emit(E.JOB_BLOCKED, {"stage": "planning",
                           "reason": "candidate topology returns zero rows (literals don't match corpus)"})
            return

    # deterministic plan id so a resumed stage upserts the same row (07 §4)
    plan_id = deterministic("plan", ctx.job_id, "v1")
    plan["plan_id"] = plan_id
    plan["job_id"] = ctx.job_id
    plan["version"] = 1
    await ctx.dao.create_plan(job_id=ctx.job_id, version=1, status="draft", body=plan, plan_id=plan_id)

    bom = plan.get("model_bom", {})
    topology = "independent" if plan.get("topology") else "interdependent"
    await ctx.emit(E.PLAN_COMPLETED, {
        "plan_id": plan_id,
        "mode": plan.get("mode", "build"),
        "modules": len(plan.get("modules", [])),
        "topology_archetype": topology,
        "bom": bom,
    })
    await ctx.advance("certifying")
