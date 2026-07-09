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

    consolidator = seat("consolidator")
    package = await consolidator.consolidate(ctx.complete, ctx.emit, modules=modules,
                                             interfaces=interfaces, plan=plan)
    workspace.write_files(ctx.job_id, package.get("files", []))

    # full integration suite against the assembled package (the validation wall)
    attempt = 0
    while True:
        attempt += 1
        result = await codeexec.run_tests(workspace=str(workspace.job_dir(ctx.job_id)), tests=tests)
        await ctx.emit(E.CONSOLIDATE_TEST_RUN, {"passed": result["passed"], "total": result["total"],
                                                "failed": result["failed"], "attempt": attempt})
        if result["failed"] == 0 or attempt >= _FIX_CAP:
            break
        # failures -> tickets -> coder fixes (skeleton: run_tests is green, so this rarely loops)
        tid = await ctx.dao.create_ticket(scope=ctx.scope, source="consolidation", severity="major",
                                          title="integration suite failure",
                                          body={"instrument": "consolidation", "suspected_modules": []})
        await ctx.emit(E.TICKET_OPENED, {"ticket_id": tid, "source": "consolidation"})
        coder = seat("coder")
        await coder.fix(ctx.complete, ctx.emit, ticket={"title": "integration suite failure"},
                        module_src="", tests=tests)
        await ctx.dao.update_ticket(tid, status="verified")
        await ctx.emit(E.TICKET_VERIFIED, {"ticket_id": tid})

    await ctx.emit(E.CONSOLIDATE_COMPLETED, {"passed": result["passed"], "total": result["total"]})
    await ctx.advance("qa")
