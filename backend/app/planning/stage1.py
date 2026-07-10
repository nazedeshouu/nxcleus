"""Stage 1 — Planning: topology + BoM authoring (03 §3). Seat: planner. Zone: EXTERNAL (default) /
LOCAL (sovereign). The planner receives ONLY the SanitizedSpec (planner brief) and streams reasoning
(plan.delta) before emitting Plan v1.
"""
from __future__ import annotations

from app.events import E
from app.ids import deterministic
from app.orchestrator.seatlib import seat


async def run(ctx) -> None:
    job = await ctx.refresh()
    brief = job.get("spec") or {}
    await ctx.emit(E.PLAN_STARTED, {"title": brief.get("title", ""), "sovereign": ctx.sovereign})

    planner = seat("planner")
    company = brief.get("company") if isinstance(brief, dict) else None
    sandbox_fn = getattr(planner, "sandbox_plan", None) \
        if job.get("origin") == "sandbox" and company else None
    if sandbox_fn:
        # sandbox planning is company-schema-scoped with polite out-of-scope refusal (09 §2)
        from app.sandbox import seeds
        plan = await sandbox_fn(ctx.complete, ctx.emit,
                                prompt=brief.get("request") or brief.get("summary") or brief.get("title", ""),
                                company=company,
                                company_schema={"tables": seeds.company_schema(company)})
    else:
        plan = await planner.plan(ctx.complete, ctx.emit, brief=brief)

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
