"""Stage 0 — Intake, policy, mode classification & data boundary (03 §2). Seat: trust. Zone: LOCAL.

Wave-1 depth: single-shot auto-confirm (the multi-turn clarification dialogue + human confirm-spec
gate is Wave 2). The mechanical boundary (baseline PII mask -> boundary_vault -> sanitized brief) is
real now; the trust-model-driven, policy-aware extraction plugs in via app/seats/trust.py.
"""
from __future__ import annotations

from app.boundary import sanitize, vault
from app.events import E
from app.orchestrator.seatlib import seat


async def run(ctx) -> None:
    job = await ctx.refresh()
    spec = job.get("spec") or {}
    request = spec.get("request", "") if isinstance(spec, dict) else ""
    trust = seat("trust")

    # customer turn in the intake dialogue
    await ctx.dao.add_message(ctx.job_id, "customer", request)
    await ctx.emit(E.INTAKE_MESSAGE, {"role": "customer", "content": request[:500]})

    # 1) confidentiality policy (D11) — baseline always on; distilled policy on top
    policy = job.get("policy")
    sources = (policy or {}).get("sources", []) if isinstance(policy, dict) else []
    distilled = await trust.distill_policy(ctx.complete, ctx.emit, sources=sources)
    await ctx.dao.update_job(ctx.job_id, policy=distilled)
    rules = distilled.get("rules", [])
    baseline = [r for r in rules if r.get("origin") == "pii_baseline"]
    await ctx.emit(E.INTAKE_POLICY_REGISTERED, {
        "sources": [s.get("kind") for s in distilled.get("sources", [])],
        "rule_count": len(rules), "baseline_rules": len(baseline),
        "policy_rules": len(rules) - len(baseline),
    })

    # 2) mechanical PII mask of the raw request -> boundary_vault (never serialized outward)
    masked_request, entries = sanitize.baseline_mask(request)
    if entries:
        await vault.store(ctx.job_id, entries)

    # 3) context intake (code map / db schema) — counts render in the UI
    ctx_pack = spec.get("context_pack", {}) if isinstance(spec, dict) else {}
    await ctx.emit(E.INTAKE_CONTEXT_MAPPED, {
        "files": ctx_pack.get("code_map", {}).get("files", 0),
        "symbols": len(ctx_pack.get("code_map", {}).get("modules", [])),
        "tables": len(ctx_pack.get("db_schemas", [])),
        "masked_identifiers": len(entries),
    })

    # 4) compose the sanitized planner brief (trust seat)
    sanitized_spec = await trust.build_spec(
        ctx.complete, ctx.emit,
        request=masked_request, files=[], code_map=ctx_pack.get("code_map", {}),
        db_schema=ctx_pack.get("db_schemas", []), policy=distilled, messages=[],
    )
    await ctx.dao.update_job(ctx.job_id, spec=sanitized_spec)
    await ctx.emit(E.INTAKE_SPEC_UPDATED, {"title": sanitized_spec.get("title", ""),
                                           "entities": len(sanitized_spec.get("entities", []))})

    # 5) mode classification. Sandbox/reinstantiate jobs come with a pre-set mode (single-shot intake).
    if job.get("origin") in ("sandbox", "reinstantiate") and job.get("mode"):
        mode = job["mode"]
        sanitized_spec.setdefault("mode", {})
        sanitized_spec["mode"]["recommended"] = mode
        sanitized_spec["mode"]["confirmed"] = mode
        await ctx.dao.update_job(ctx.job_id, spec=sanitized_spec)
    else:
        mode = (sanitized_spec.get("mode") or {}).get("confirmed") \
            or (sanitized_spec.get("mode") or {}).get("recommended") or job.get("mode") or "build"
    await ctx.dao.update_job(ctx.job_id, mode=mode)
    await ctx.emit(E.INTAKE_CLASSIFIED, {"mode": mode,
                                         "rationale": (sanitized_spec.get("mode") or {}).get("rationale", "")})

    # 6) boundary gate — the "what the frontier will never see" moment, citing policy rule IDs
    sr = sanitized_spec.get("sensitivity_report", {})
    await ctx.emit(E.BOUNDARY_SANITIZED, {
        "pii_fields_masked": max(sr.get("pii_fields_masked", 0), len(entries)),
        "documents_ocred": sr.get("documents_ocred", 0),
        "policy_rules_applied": sr.get("policy_rules_applied", [r.get("id") for r in rules[:3]]),
        "identifiers_generalized": sr.get("identifiers_generalized", len(entries)),
        "vault_size": await vault.count(ctx.job_id),
    })

    await ctx.dao.add_message(ctx.job_id, "trust", f"Spec confirmed as {mode} mode. Boundary sanitized.")

    # Wave-1: auto-confirm spec + mode -> planning (interactive confirm-spec gate is Wave 2)
    await ctx.advance("planning")
