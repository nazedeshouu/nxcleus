"""Stage 0 — Intake, policy, mode classification & data boundary (03 §2). Seat: trust. Zone: LOCAL.

Wave-1 depth: single-shot auto-confirm (the multi-turn clarification dialogue + human confirm-spec
gate is Wave 2). The mechanical boundary (baseline PII mask -> boundary_vault -> sanitized brief) is
real now; the trust-model-driven, policy-aware extraction plugs in via app/seats/trust.py.
"""
from __future__ import annotations

from app.boundary import sanitize, vault
from app.events import E
from app.orchestrator.seatlib import seat


def resolve_policy_sources(job: dict) -> list[dict]:
    """Stage-0 policy-source resolution (D11). An explicitly provided policy always wins; otherwise a
    job bound to a sandbox company defaults to that company's Terms of Sensitive Data Use file so
    distill_policy sees real obligations, not just the PII baseline. Company lives in spec["company"]
    (dao.create_job). Pure — no model call — so it's directly testable."""
    from app.sandbox import seeds

    policy = job.get("policy")
    sources = (policy or {}).get("sources", []) if isinstance(policy, dict) else []
    if sources:
        return sources
    spec = job.get("spec") or {}
    company = spec.get("company") if isinstance(spec, dict) else None
    terms = seeds.company_terms(company)
    if terms:
        return [{"kind": "doc", "ref": f"terms/{company}_terms.md", "text": terms}]
    return sources


async def run(ctx) -> None:
    job = await ctx.refresh()
    spec = job.get("spec") or {}
    # jobs.request survives the spec overwrite below — on re-entry (clarification answers) the
    # spec no longer carries the raw request
    request = job.get("request") or (spec.get("request", "") if isinstance(spec, dict) else "")
    trust = seat("trust")

    # customer turn in the intake dialogue
    await ctx.dao.add_message(ctx.job_id, "customer", request)
    await ctx.emit(E.INTAKE_MESSAGE, {"role": "customer", "content": request[:500]})

    # 1) confidentiality policy (D11) — baseline always on; distilled policy on top. With no explicit
    #    policy, a sandbox company job defaults its sources to that company's Terms of Sensitive Data Use.
    sources = resolve_policy_sources(job)
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

    # 3) context intake (code map / db schema) — counts render in the UI. Sandbox jobs inject the
    #    selected company's schema so the planner scopes topologies to real tables (09 §2);
    #    synthetic demo data = SANITIZED by construction.
    ctx_pack = spec.get("context_pack", {}) if isinstance(spec, dict) else {}
    db_schemas = list(ctx_pack.get("db_schemas", []))
    company = spec.get("company") if isinstance(spec, dict) else None
    if company:
        from app.sandbox import seeds
        db_schemas += seeds.company_schema(company)
    await ctx.emit(E.INTAKE_CONTEXT_MAPPED, {
        "files": ctx_pack.get("code_map", {}).get("files", 0),
        "symbols": len(ctx_pack.get("code_map", {}).get("modules", [])),
        "tables": len(db_schemas),
        "masked_identifiers": len(entries),
    })

    # 4) compose the sanitized planner brief (trust seat). Clarification answers (a resumed
    #    intake) are appended to the request context so the brief treats them as binding facts.
    answers = (spec.get("clarification_answers") if isinstance(spec, dict) else None) or []
    brief_request = masked_request
    if answers:
        brief_request += "\n\nClarification answers (binding):\n" + "\n".join(
            f"- {a.get('id', '')}: {a.get('answer', '')}" for a in answers)
    sanitized_spec = await trust.build_spec(
        ctx.complete, ctx.emit,
        request=brief_request, files=[], code_map=ctx_pack.get("code_map", {}),
        db_schema=db_schemas, policy=distilled, messages=[],
    )
    if company:
        sanitized_spec["company"] = company     # survives the spec overwrite; fan-out needs it
    if answers:
        sanitized_spec["clarification_answers"] = answers
    deliverable = spec.get("deliverable") if isinstance(spec, dict) else None
    if deliverable and not sanitized_spec.get("deliverable"):
        sanitized_spec["deliverable"] = deliverable   # set by /answers (delivery-kind answer)
    await ctx.dao.update_job(ctx.job_id, spec=sanitized_spec)
    await ctx.emit(E.INTAKE_SPEC_UPDATED, {"title": sanitized_spec.get("title", ""),
                                           "entities": len(sanitized_spec.get("entities", []))})

    # 4b) clarifying intake (hardening 2026-07-10): materially-ambiguous requests park for the
    #     customer's answers; sandbox/reinstantiate jobs auto-answer so the demo never stalls.
    clars = [q for q in (sanitized_spec.get("clarifications") or []) if q.get("question")][:3]
    if clars and not answers:
        if job.get("origin") in ("sandbox", "reinstantiate"):
            auto = [{"id": q.get("id", f"q{i}"), "answer": (q.get("options") or ["use sensible defaults"])[0]}
                    for i, q in enumerate(clars)]
            sanitized_spec["clarification_answers"] = auto
            await ctx.dao.update_job(ctx.job_id, spec=sanitized_spec)
            await ctx.emit(E.INTAKE_CLARIFICATION_ANSWERED, {"auto": True, "answers": auto})
        else:
            await ctx.checkpoint("clarifications", clars)
            await ctx.dao.update_job(ctx.job_id, status="awaiting_input", current_stage=0)
            await ctx.emit(E.INTAKE_CLARIFICATION_REQUESTED, {"questions": clars})
            await ctx.dao.add_message(
                ctx.job_id, "trust",
                "Before planning, please answer: " + " ".join(q.get("question", "") for q in clars))
            return

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

    # 6) boundary gate — the "what the frontier will never see" moment (payload per 06 §3 ruling:
    #    findings[{rule_id,label,count,action}] + never_leaves[] + brief_tokens)
    sr = sanitized_spec.get("sensitivity_report", {})
    kind_counts: dict[str, int] = {}
    for _, _, kind in entries:
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    findings = [{"rule_id": r.get("id", ""), "label": r.get("description", ""),
                 "count": kind_counts.get(r.get("kind", ""), 0), "action": r.get("kind", "mask")}
                for r in rules] or [
        {"rule_id": "PII-BASE", "label": "PII baseline", "count": len(entries), "action": "never_leak"}]
    never_leaves = [r.get("description", "") for r in rules if r.get("kind") == "never_leak"] \
        or ["names, accounts, contacts, government IDs, credentials"]
    brief_tokens = max(1, len(str(sanitized_spec)) // 4)
    await ctx.emit(E.BOUNDARY_SANITIZED, {
        "findings": findings,
        "never_leaves": never_leaves,
        "brief_tokens": brief_tokens,
        # retained for the sensitivity story (additive)
        "pii_fields_masked": max(sr.get("pii_fields_masked", 0), len(entries)),
        "documents_ocred": sr.get("documents_ocred", 0),
        "identifiers_generalized": sr.get("identifiers_generalized", len(entries)),
        "vault_size": await vault.count(ctx.job_id),
    })

    await ctx.dao.add_message(ctx.job_id, "trust", f"Spec confirmed as {mode} mode. Boundary sanitized.")

    # Wave-1: auto-confirm spec + mode -> planning (interactive confirm-spec gate is Wave 2)
    await ctx.advance("planning")
