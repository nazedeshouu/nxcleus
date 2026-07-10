"""Stage 5 — Consolidation (03 §7, build mode). Seat: consolidator (local, node B). Merges module
files into a coherent package (process.py entrypoint), then runs the full stage-2 integration suite in
the code-exec sandbox — objective pass/fail. Failures -> tickets -> coder fixes (<=3 rounds). The
Demo-3 'validation wall' (partial -> N/N green) is this gate rendered live.
"""
from __future__ import annotations

from app.events import E
from app.orchestrator import codeexec
from app.orchestrator.seatlib import seat
from app.runtime import workspace

_FIX_CAP = 3


async def run(ctx) -> None:
    await ctx.refresh()
    plan_id = await ctx.get_checkpoint("certified_plan_id")
    plan_row = await ctx.dao.get_plan(plan_id) if plan_id else await ctx.dao.current_plan(ctx.job_id)
    plan = plan_row["body"]
    modules = plan.get("modules", [])
    interfaces = plan.get("interfaces", [])
    tests = await ctx.get_checkpoint("tests") or []

    await ctx.emit(E.CONSOLIDATE_STARTED, {"modules": len(modules)})

    # T9: the consolidator is the single cross-folder reader — merge agents/*/ into the
    # job-level src/ tree before assembling (its own suite run mounts the WHOLE job dir)
    merged = workspace.merge_agent_src(ctx.job_id)
    if merged:
        await ctx.emit(E.SYSTEM_NOTICE, {"text": f"merged {len(merged)} files from agent folders",
                                         "level": "info", "scope": "consolidate"})

    consolidator = seat("consolidator")
    package = await consolidator.consolidate(ctx.complete, ctx.emit, modules=modules,
                                             interfaces=interfaces, plan=plan)
    workspace.write_files(ctx.job_id, package.get("files", []))

    # full integration suite against the assembled package (the validation wall)
    attempt = 0
    fix_tickets: list[str] = []
    while True:
        attempt += 1
        result = await codeexec.run_tests(workspace=str(workspace.job_dir(ctx.job_id)), tests=tests)
        await ctx.emit(E.CONSOLIDATE_TEST_RUN, {"passed": result["passed"], "total": result["total"],
                                                "failed": result["failed"], "attempt": attempt})
        # S5: a ticket is `verified` only when the suite RE-RUN after its fix passes
        if result["failed"] == 0:
            for tid in fix_tickets:
                await ctx.dao.update_ticket(tid, status="verified")
                await ctx.emit(E.TICKET_VERIFIED, {"ticket_id": tid, "retested": True})
            break
        if attempt >= _FIX_CAP:
            for tid in fix_tickets:
                await ctx.dao.update_ticket(tid, status="human_review")
                await ctx.emit(E.TICKET_HUMAN_REVIEW, {"ticket_id": tid,
                               "reason": "suite still failing after fix cap"})
            break
        tid = await ctx.dao.create_ticket(scope=ctx.scope, source="consolidation", severity="major",
                                          title="integration suite failure",
                                          body={"instrument": "consolidation", "suspected_modules": []})
        await ctx.emit(E.TICKET_OPENED, {"ticket_id": tid, "source": "consolidation"})
        coder = seat("coder")
        await coder.fix(ctx.complete, ctx.emit, ticket={"title": "integration suite failure"},
                        module_src="", tests=tests)
        await ctx.dao.update_ticket(tid, status="fix_applied")
        await ctx.emit(E.TICKET_FIX_APPLIED, {"ticket_id": tid, "retested": False})
        fix_tickets.append(tid)

    await ctx.checkpoint("integration_result", result)   # stage 6's goal manifest reads this
    await ctx.emit(E.CONSOLIDATE_COMPLETED, {"passed": result["passed"], "total": result["total"]})
    await ctx.advance("qa")
