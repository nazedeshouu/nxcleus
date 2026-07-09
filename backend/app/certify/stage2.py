"""Stage 2 — Plan completion, rehydration & certification (03 §4). Seat: certifier (RAW, D9), with
sanitized planner consults. Emits findings/amendments/consults, the goal (D10), then the certified
plan + IntegrationTestSpec[] + OracleVector[]. Ends by issuing the quote (stage 3) and parking at
`quoted`.
"""
from __future__ import annotations

from app.boundary import vault
from app.events import E, now_iso
from app.ids import deterministic
from app.orchestrator.seatlib import seat
from app.quote import stage3

_CHECKS = ["interface-compat", "data-completeness", "error-coverage", "pattern-consistency",
           "ac-coverage", "bom-sanity", "production-fit"]
_CONSULT_CAP = 3


async def run(ctx) -> None:
    job = await ctx.refresh()
    draft = await ctx.dao.current_plan(ctx.job_id)
    if draft is None:
        raise RuntimeError("no plan to certify")
    plan = draft["body"]
    plan_id = draft["id"]
    policy = job.get("policy") or {}
    vault_map = await vault.get_map(ctx.job_id)
    # The certifier reads RAW (D9) and rehydrates placeholders from the vault; it needs the full
    # placeholder->raw MAP, not just the key list. (`list(vault_map)` broke rehydrate_tokens with
    # "'list' object has no attribute 'items'"; only surfaced live, since mock uses the placeholder
    # certifier.) Certifier's RAW clearance is enforced by the router boundary check.
    raw_context = {"request": (job.get("spec") or {}).get("request", ""), "vault": vault_map}

    certifier = seat("certifier")
    for check in _CHECKS:
        await ctx.emit(E.CERTIFY_CHECK_STARTED, {"check": check})

    result = await certifier.certify(ctx.complete, ctx.emit, plan=plan, raw_context=raw_context, policy=policy)

    consult_rounds = 0
    for finding in result.get("findings", []):
        await ctx.emit(E.CERTIFY_FINDING, {"finding_id": finding.get("finding_id"),
                                           "check": finding.get("check"), "severity": finding.get("severity"),
                                           "triage": finding.get("triage")})
        if finding.get("triage") == "amend" and finding.get("amendment"):
            amend = finding["amendment"]
            row = await ctx.dao.append_amendment(
                plan_id=plan_id, origin="certifier", patch=amend.get("patch", {}),
                rationale=amend.get("rationale", ""), finding_id=finding.get("finding_id", ""),
                check_name=finding.get("check", ""), plan_ref=amend.get("plan_ref", ""),
                spec_ref=amend.get("spec_ref", ""),
            )
            await ctx.emit(E.CERTIFY_AMENDMENT, {"seq": row["seq"], "origin": "certifier",
                                                 "plan_ref": row["plan_ref"], "hash": row["hash"],
                                                 "rationale": row["rationale"]})
        elif finding.get("triage") == "consult" and consult_rounds < _CONSULT_CAP:
            consult_rounds += 1
            # A consult is a best-effort escalation to the planner, not a hard gate: the certifier's
            # local amendments are already applied, and stage-4's conductor follows the same
            # proceed-without-review policy (07 §3.1). A failed consult (scope-lock violation from a
            # replan, timeout, planner refusal) must degrade gracefully, not block the whole build.
            try:
                await _run_consult(ctx, plan, plan_id, finding, vault_map, consult_rounds)
            except Exception as exc:  # noqa: BLE001
                await ctx.emit(E.SYSTEM_NOTICE, {
                    "text": f"consult {finding.get('finding_id')} skipped: {type(exc).__name__}: "
                            f"{str(exc)[:160]}", "level": "warn", "scope": "certify"})

    # rehydration (D9) — placeholders -> real values inside the LOCAL zone
    rehydrated = result.get("identifiers_rehydrated", await vault.count(ctx.job_id))

    # goal statement (D10)
    goal = result.get("goal", "")
    await ctx.dao.update_job(ctx.job_id, goal=goal)
    await ctx.emit(E.CERTIFY_GOAL_SET, {"goal": goal})

    # certified plan version (v2), rehydrated -> data-class RAW
    certified_id = deterministic("plan", ctx.job_id, "certified")
    plan_c = dict(plan)
    plan_c["version"] = 2
    plan_c["plan_id"] = certified_id
    plan_c["job_id"] = ctx.job_id
    await ctx.dao.create_plan(job_id=ctx.job_id, version=2, status="certified", body=plan_c,
                              plan_id=certified_id)
    await ctx.dao.update_plan(certified_id, status="certified", certified_at=now_iso())

    tests = result.get("tests", [])
    vectors = result.get("vectors", [])
    scenarios = result.get("adversarial_scenarios", [])
    await ctx.checkpoint("tests", tests)
    await ctx.checkpoint("vectors", vectors)
    await ctx.checkpoint("adversarial_scenarios", scenarios)
    await ctx.checkpoint("certified_plan_id", certified_id)

    await ctx.emit(E.CERTIFY_CERTIFIED, {"tests": len(tests), "vectors": len(vectors),
                                         "identifiers_rehydrated": rehydrated,
                                         "amendments": len(await ctx.dao.list_amendments(plan_id))
                                         + len(await ctx.dao.list_amendments(certified_id))})

    # stage 3 — quote, then park
    await stage3.issue(ctx, plan_c, certified_id)
    await ctx.advance("quoted")


async def _run_consult(ctx, plan, plan_id, finding, vault_map, round_n) -> None:
    req = finding.get("consult_request") or {}
    scope = req.get("scope", {})
    trust = seat("trust")
    payload = str(req.get("question", ""))
    sanitized, receipt = await trust.sanitize_consult(ctx.complete, ctx.emit, payload=payload,
                                                      vault_map=vault_map)
    consult_id = await ctx.dao.create_consult(plan_id=plan_id, round=round_n, scope=scope,
                                              request={"question": sanitized})
    await ctx.emit(E.CERTIFY_CONSULT_OPENED, {"consult_id": consult_id, "round": round_n,
                                              "scope": scope, "sanitization_receipt": receipt})
    # constrained re-plan back to the planner (EXTERNAL / SANITIZED — auditable in the egress ledger)
    planner = seat("planner")
    await planner.replan(ctx.complete, ctx.emit, plan=plan, findings=req.get("findings", []),
                         scope_lock=scope)
    await ctx.dao.resolve_consult(consult_id, "resolved via constrained re-plan")
    await ctx.emit(E.CERTIFY_CONSULT_RESOLVED, {"consult_id": consult_id, "round": round_n})
