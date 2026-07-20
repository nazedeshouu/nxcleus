"""Stage 2 — Plan completion, rehydration & certification (03 §4). Seat: certifier (RAW, D9), with
sanitized planner consults. Emits findings/amendments/consults, the goal (D10), then the certified
plan + IntegrationTestSpec[] + OracleVector[]. Ends by issuing the quote (stage 3) and parking at
`quoted`.
"""
from __future__ import annotations

import json

from app.boundary import vault
from app.events import E, now_iso
from app.ids import deterministic
from app.orchestrator.seatlib import seat
from app.quote import stage3
from app.seats._common import normalize_regions, region_ids

_CHECKS = ["interface-compat", "data-completeness", "error-coverage", "pattern-consistency",
           "ac-coverage", "bom-sanity", "production-fit"]
_CONSULT_CAP = 3


async def run(ctx) -> None:
    job = await ctx.refresh()
    # Planning upserts this deterministic draft on correction. Prefer it explicitly: the old
    # certified v2 remains in the audit trail and would otherwise win current_plan's version sort.
    draft = await ctx.dao.get_plan(deterministic("plan", ctx.job_id, "v1"))
    if draft is None:
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
    # B1 goal anchor: intake overwrites job.spec with the sanitized brief, so spec.request is empty
    # here — the certifier's RAW original request lives on the jobs.request column (dao.create_job)
    messages = await ctx.dao.list_messages(ctx.job_id)
    raw_context = {
        "request": job.get("request") or (job.get("spec") or {}).get("request", ""),
        "messages": [{"role": row["role"], "content": row["content"]} for row in messages],
        "vault": vault_map,
    }

    certifier = seat("certifier")
    for check in _CHECKS:
        await ctx.emit(E.CERTIFY_CHECK_STARTED, {"check": check})

    result = await certifier.certify(ctx.complete, ctx.emit, plan=plan, raw_context=raw_context, policy=policy)

    consult_rounds = 0
    replans: list[tuple[dict, dict]] = []            # (scope_lock, replanned plan) to fold in
    cap_skipped_structural: list[str] = []           # consult findings dropped past the cap
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
        elif finding.get("triage") == "consult":
            if consult_rounds >= _CONSULT_CAP:
                if finding.get("severity") == "structural":
                    cap_skipped_structural.append(finding.get("finding_id", ""))
                continue
            consult_rounds += 1
            # A consult is a best-effort escalation to the planner, not a hard gate: the certifier's
            # local amendments are already applied, and stage-4's conductor follows the same
            # proceed-without-review policy (07 §3.1). A failed consult (scope-lock violation from a
            # replan, timeout, planner refusal) must degrade gracefully, not block the whole build.
            try:
                folded = await _run_consult(ctx, plan, plan_id, finding, vault_map, consult_rounds)
                if folded:
                    replans.append(folded)
            except Exception as exc:  # noqa: BLE001
                await ctx.emit(E.SYSTEM_NOTICE, {
                    "text": f"consult {finding.get('finding_id')} skipped: {type(exc).__name__}: "
                            f"{str(exc)[:160]}", "level": "warn", "scope": "certify"})
                if finding.get("severity") == "structural":
                    cap_skipped_structural.append(finding.get("finding_id", ""))

    # consult cap spillover (03 §5): remaining STRUCTURAL findings pause the job for human review
    structural_deferred = [f.get("finding_id") for f in (result.get("deferred_consults") or [])
                           if f.get("severity") == "structural"] + cap_skipped_structural
    if structural_deferred:
        await ctx.emit(E.CERTIFY_BLOCKED, {
            "findings": structural_deferred,
            "reason": "structural findings deferred past the consult cap need human review"})
        await ctx.dao.update_job(ctx.job_id, status="blocked")
        return

    # rehydration (D9) — placeholders -> real values inside the LOCAL zone
    rehydrated = result.get("identifiers_rehydrated", await vault.count(ctx.job_id))

    # goal statement (D10)
    goal = result.get("goal", "")
    await ctx.dao.update_job(ctx.job_id, goal=goal)
    await ctx.emit(E.CERTIFY_GOAL_SET, {"goal": goal})

    # certified plan version (v2) — the certifier's amended + rehydrated artifact (03 §4.1, D9),
    # NOT the frontier draft: without this every amendment is logged but absent from the plan
    certified_id = deterministic("plan", ctx.job_id, "certified")
    plan_c = dict(result.get("certified_plan") or plan)
    # fold each consult's scope-locked re-plan into the artifact (03 §4.2) — the paid frontier
    # answer must land in the plan, not just the consult log — then re-rehydrate merged regions
    for scope_lock, replanned in replans:
        ids, _unres = normalize_regions(scope_lock.get("only_regions", []),
                                        region_ids(plan_c) | region_ids(replanned))
        if ids:
            plan_c = _merge_regions(plan_c, replanned, set(ids))
    if replans:
        from app.seats._common import rehydrate_tokens
        plan_c, _n = rehydrate_tokens(plan_c, vault_map)

    # production-fit for sql candidate steps (hardening 2026-07-10): every kind=="sql" step is
    # EXECUTED read-only against the bound corpus; a failing query gets one certifier repair
    # round (router schema-repair pattern); still failing -> the sql is dropped so the run
    # degrades to per-unit judgment instead of sweeping over an empty candidate set.
    await _validate_sql_steps(ctx, certifier, plan_c, (job.get("spec") or {}).get("company"))

    plan_c["version"] = 2
    plan_c["plan_id"] = certified_id
    plan_c["job_id"] = ctx.job_id
    await ctx.dao.create_plan(job_id=ctx.job_id, version=2, status="certified", body=plan_c,
                              plan_id=certified_id)
    await ctx.dao.update_plan(certified_id, status="certified", certified_at=now_iso())

    # T9: publish the certified interfaces read-only for the folder-isolated build agents
    from app.runtime import workspace
    workspace.write_shared_interfaces(ctx.job_id, plan_c.get("interfaces", []))

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


async def _validate_sql_steps(ctx, certifier, plan_c: dict, company: str | None) -> None:
    import asyncio as _asyncio

    from app.sandbox import seeds

    steps = ((plan_c.get("topology") or {}).get("steps")) or []
    sql_steps = [s for s in steps if s.get("kind") == "sql" and s.get("sql")]
    if not sql_steps:
        return
    schema_tables = seeds.company_schema(company)

    async def _try(sql: str) -> tuple[str | None, int]:
        try:
            rows = await _asyncio.to_thread(seeds.run_select, company, sql, cap=5, timeout_s=10.0)
            return None, len(rows)
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {str(exc)[:300]}", 0

    for s in sql_steps:
        err, n = await _try(s["sql"])
        if err is not None:
            repaired = await certifier.repair_sql(ctx.complete, ctx.emit, step=s, error=err,
                                                  schema_tables=schema_tables)
            if repaired and repaired != s["sql"]:
                err2, n = await _try(repaired)
                if err2 is None:
                    s["sql"] = repaired
                    err = None
        if err is not None:
            s["sql_invalid"] = err
            s.pop("sql", None)   # execute_topology skips it; per-unit judgment still runs
            await ctx.emit(E.SYSTEM_NOTICE, {"text": f"sql step {s.get('id')} dropped after failed "
                                             f"repair: {err[:160]}", "level": "warn", "scope": "certify"})
        await ctx.emit(E.CERTIFY_CHECK_COMPLETED, {"check": "sql-step", "step": s.get("id"),
                                                   "ok": err is None, "sample_rows": n})


async def _run_consult(ctx, plan, plan_id, finding, vault_map, round_n) -> tuple[dict, dict] | None:
    """One sanitized consult round. EVERYTHING planner-bound passes the egress gate (03 §4.2) —
    the question AND the findings text; the ledger receipt describes exactly what crossed.
    Returns (scope_lock, replanned_plan) for the stage to fold into the certified artifact."""
    req = finding.get("consult_request") or {}
    scope = req.get("scope", {})
    trust = seat("trust")
    payload = str(req.get("question", ""))
    sanitized, receipt = await trust.sanitize_consult(ctx.complete, ctx.emit, payload=payload,
                                                      vault_map=vault_map)
    sanitized_findings: list[str] = []
    for raw in req.get("findings", []) or []:
        sf, _r = await trust.sanitize_consult(ctx.complete, ctx.emit, payload=str(raw),
                                              vault_map=vault_map)
        sanitized_findings.append(sf)
    consult_id = await ctx.dao.create_consult(plan_id=plan_id, round=round_n, scope=scope,
                                              request={"question": sanitized,
                                                       "findings": sanitized_findings})
    await ctx.emit(E.CERTIFY_CONSULT_OPENED, {"consult_id": consult_id, "round": round_n,
                                              "scope": scope, "sanitization_receipt": receipt})
    # constrained re-plan back to the planner (EXTERNAL / SANITIZED — auditable in the egress ledger)
    planner = seat("planner")
    replanned = await planner.replan(ctx.complete, ctx.emit, plan=plan,
                                     findings=sanitized_findings or [sanitized], scope_lock=scope)
    await ctx.dao.resolve_consult(consult_id, "resolved via constrained re-plan")
    await ctx.emit(E.CERTIFY_CONSULT_RESOLVED, {"consult_id": consult_id, "round": round_n})
    return (scope, replanned) if isinstance(replanned, dict) and replanned else None


def _merge_regions(target: dict, source: dict, ids: set[str]) -> dict:
    """Replace the named regions (module / interface / dag-task / topology-step ids — the canonical
    scope-lock vocabulary) in `target` with their `source` versions. Non-named regions untouched."""
    out = json.loads(json.dumps(target))
    for coll, key in (("modules", "id"), ("interfaces", "id"), ("dag", "task")):
        src = {e.get(key): e for e in source.get(coll) or []}
        items = out.get(coll) or []
        for n, e in enumerate(items):
            rid = e.get(key)
            if rid in ids and rid in src:
                items[n] = src[rid]
    src_steps = {s.get("id"): s for s in ((source.get("topology") or {}).get("steps")) or []}
    for n, s in enumerate(((out.get("topology") or {}).get("steps")) or []):
        rid = s.get("id")
        if rid in ids and rid in src_steps:
            out["topology"]["steps"][n] = src_steps[rid]
    return out
