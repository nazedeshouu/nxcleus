"""Stage-4 wave review — the conductor (D8, 03 §6, 07 §3.1). Between waves the conductor reviews the
wave's outputs against the plan + goal and may amend ONLY not-yet-built regions (scope-locked, same
hash-chain mechanics as certification). Proceed-without-review: a failing/timed-out conductor never
dead-ends a build.
"""
from __future__ import annotations

import re

from app.events import E
from app.orchestrator.seatlib import seat
from app.seats._common import apply_rfc6902


def _ref_matches(ref: str, module_ids: set[str]) -> bool:
    """Exact region-id token match (B3): 'modules.mod_ocr' unlocks mod_ocr, never mod_ocr2."""
    return bool(set(re.split(r"[^A-Za-z0-9_-]+", ref or "")) & module_ids)


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

    applied_any = False
    for amend in review.get("amendments", []):
        ref = amend.get("plan_ref", "")
        # scope-lock: conductor may touch only not-yet-built regions (03 §6)
        if _ref_matches(ref, unbuilt_module_ids):
            # APPLY the patch to the live plan dict (stage 4 holds this reference across waves) —
            # an amendment that is only logged never reaches the next wave's coders (07 §3.1)
            try:
                patched = apply_rfc6902(plan, amend.get("patch", {}))
            except Exception as exc:  # noqa: BLE001 — malformed patch: skip, don't corrupt the plan
                await ctx.emit(E.SYSTEM_NOTICE, {"text": f"conductor amendment on {ref!r} skipped "
                                                 f"(malformed patch: {type(exc).__name__})",
                                                 "level": "warn"})
                continue
            plan.clear()
            plan.update(patched)
            applied_any = True
            row = await ctx.dao.append_amendment(plan_id=plan_id, origin="conductor",
                                                 patch=amend.get("patch", {}),
                                                 rationale=amend.get("rationale", ""), plan_ref=ref)
            await ctx.emit(E.CONDUCTOR_AMENDMENT, {"wave": wave_idx + 1, "seq": row["seq"],
                                                   "origin": "conductor", "plan_ref": ref,
                                                   "hash": row["hash"], "prev_hash": row["prev_hash"],
                                                   "rationale": row["rationale"]})
        else:
            await ctx.emit(E.SYSTEM_NOTICE, {"text": f"conductor amendment on built region {ref!r} "
                                             "rejected (scope-lock)", "level": "warn"})

    if applied_any:
        # B2: persist the patched body — resume/retry reloads the plan from the DB, and a
        # hash-chained amendment log must never point at changes that vanished
        await ctx.dao.update_plan(plan_id, body=plan)

    for rework in review.get("rework", []):
        await ctx.emit(E.SYSTEM_NOTICE, {"text": f"conductor rework: {rework.get('module_id')} — "
                                         f"{rework.get('instruction', '')[:120]}", "level": "info"})

    await ctx.emit(E.CONDUCTOR_GREEN_FLAG, {"wave": wave_idx + 1, "of": total_waves, "reviewed": True})
