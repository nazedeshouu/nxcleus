"""Stage-4 wave review — the conductor (D8, 03 §6, 07 §3.1). Between waves the conductor reviews the
wave's outputs against the plan + goal and may amend ONLY not-yet-built regions (scope-locked, same
hash-chain mechanics as certification). Proceed-without-review: a failing/timed-out conductor never
dead-ends a build.
"""
from __future__ import annotations

from app.events import E
from app.orchestrator.seatlib import seat


async def review_wave(ctx, *, plan: dict, plan_id: str, goal: str, wave_idx: int, total_waves: int,
                      wave_outputs: list, unbuilt_module_ids: set[str], remaining_modules: list) -> None:
    conductor = seat("conductor")
    try:
        review = await conductor.review(ctx.complete, ctx.emit, plan=plan, goal=goal,
                                        wave_outputs=wave_outputs, remaining=remaining_modules)
    except Exception as exc:  # noqa: BLE001 — proceed-without-review (07 §3.1)
        await ctx.emit(E.SYSTEM_NOTICE, {"text": f"wave {wave_idx + 1} unreviewed "
                                         f"({type(exc).__name__}); proceeding", "level": "warn"})
        await ctx.emit(E.CONDUCTOR_GREEN_FLAG, {"wave": wave_idx + 1, "of": total_waves,
                                                "reviewed": False})
        return

    await ctx.emit(E.CONDUCTOR_REVIEW, {"wave": wave_idx + 1, "of": total_waves,
                                        "verdict": review.get("verdict", "proceed"),
                                        "goal_drift": review.get("goal_drift"),
                                        "assessment": review.get("wave_assessment", "")})

    for amend in review.get("amendments", []):
        ref = amend.get("plan_ref", "")
        # scope-lock: conductor may touch only not-yet-built regions (03 §6)
        if any(mid in ref for mid in unbuilt_module_ids):
            row = await ctx.dao.append_amendment(plan_id=plan_id, origin="conductor",
                                                 patch=amend.get("patch", {}),
                                                 rationale=amend.get("rationale", ""), plan_ref=ref)
            await ctx.emit(E.CONDUCTOR_AMENDMENT, {"wave": wave_idx + 1, "seq": row["seq"],
                                                   "origin": "conductor", "plan_ref": ref,
                                                   "hash": row["hash"], "rationale": row["rationale"]})
        else:
            await ctx.emit(E.SYSTEM_NOTICE, {"text": f"conductor amendment on built region {ref!r} "
                                             "rejected (scope-lock)", "level": "warn"})

    for rework in review.get("rework", []):
        await ctx.emit(E.SYSTEM_NOTICE, {"text": f"conductor rework: {rework.get('module_id')} — "
                                         f"{rework.get('instruction', '')[:120]}", "level": "info"})

    await ctx.emit(E.CONDUCTOR_GREEN_FLAG, {"wave": wave_idx + 1, "of": total_waves, "reviewed": True})
