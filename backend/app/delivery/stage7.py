"""Stage 7 — Delivery -> operations registry (03 §10, 04 §2). Seat: trust (docs). Assembles the
immutable process package, computes the final metered invoice, registers processes + process_versions
v1, and emits deliver.registered. Job closes; everything after is the operate phase.
"""
from __future__ import annotations

import re

from app.events import E
from app.metering import invoice as invoice_mod
from app.orchestrator import codeexec
from app.orchestrator.seatlib import seat
from app.runtime import workspace
from app.safe_paths import UnsafePathError, resolve_within


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "process").lower()).strip("-")
    return slug or "process"


async def _unique_slug(dao, base: str) -> str:
    slug, n = base, 1
    while await dao.get_process_by_slug(slug) is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


def _validate_outcome_section(
    qa_result: dict, name: str, outcome_field: str, categories: tuple[str, ...],
) -> dict:
    section = qa_result.get(name)
    if not isinstance(section, dict):
        raise RuntimeError(f"delivery gate has invalid QA {name} evidence")
    outcomes = section.get("outcomes")
    if not isinstance(outcomes, list) or any(not isinstance(item, dict) for item in outcomes):
        raise RuntimeError(f"delivery gate has invalid QA {name} outcomes")
    count_names = ("total", *categories)
    if any(type(section.get(key)) is not int or section[key] < 0 for key in count_names):
        raise RuntimeError(f"delivery gate has invalid QA {name} counts")
    actual = {
        category: sum(1 for item in outcomes if item.get(outcome_field) == category)
        for category in categories
    }
    if any(item.get(outcome_field) not in categories for item in outcomes):
        raise RuntimeError(f"delivery gate has unknown QA {name} outcome")
    if section["total"] != len(outcomes) or any(
        section[category] != actual[category] for category in categories
    ):
        raise RuntimeError(f"delivery gate has inconsistent QA {name} counts")
    return section


def _validate_qa_evidence(integration: dict, qa_result: dict, goal_check: dict) -> dict:
    required = {
        "verification", "integration", "probes", "oracles", "tickets",
        "goal_verdict", "reasons", "demo_override",
    }
    if not required.issubset(qa_result):
        raise RuntimeError("delivery gate missing stable QA evidence")

    qa_integration = qa_result.get("integration")
    if not isinstance(qa_integration, dict):
        raise RuntimeError("delivery gate has invalid QA integration evidence")
    integration_keys = ("verification", "total", "passed", "failed")
    if any(qa_integration.get(key) != integration.get(key) for key in integration_keys):
        raise RuntimeError("delivery gate QA integration evidence does not match integration_result")
    if qa_result.get("goal_verdict") != goal_check.get("verdict"):
        raise RuntimeError("delivery gate QA goal verdict does not match goal_check")

    probes = _validate_outcome_section(
        qa_result, "probes", "outcome", ("clear", "finding", "inconclusive"))
    oracles = _validate_outcome_section(
        qa_result, "oracles", "verdict",
        ("match", "mismatch", "no_actual", "oracle_uncertain"))
    tickets = qa_result.get("tickets")
    if not isinstance(tickets, dict):
        raise RuntimeError("delivery gate has invalid QA ticket evidence")
    ticket_outcomes = tickets.get("outcomes")
    if not isinstance(ticket_outcomes, list) or any(
        not isinstance(item, dict) for item in ticket_outcomes
    ):
        raise RuntimeError("delivery gate has invalid QA ticket outcomes")
    if any(type(tickets.get(key)) is not int or tickets[key] < 0
           for key in ("opened", "human_review")):
        raise RuntimeError("delivery gate has invalid QA ticket counts")
    human_review = sum(
        1 for item in ticket_outcomes if item.get("status") == "human_review")
    if tickets["opened"] != len(ticket_outcomes) or tickets["human_review"] != human_review:
        raise RuntimeError("delivery gate has inconsistent QA ticket counts")

    demo_override = qa_result.get("demo_override")
    if type(demo_override) is not bool:
        raise RuntimeError("delivery gate has invalid QA demo override")
    qa_state = qa_result["verification"]
    qa_reasons = qa_result["reasons"]
    if qa_state == "passed":
        false_green = (
            bool(qa_reasons)
            or demo_override
            or probes["total"] == 0
            or probes["finding"] > 0
            or probes["inconclusive"] > 0
            or oracles["mismatch"] > 0
            or oracles["no_actual"] > 0
            or oracles["oracle_uncertain"] > 0
            or tickets["opened"] > 0
        )
        if false_green:
            raise RuntimeError("delivery gate rejected inconsistent passed QA evidence")
    elif qa_state == "unverified" and not qa_reasons:
        raise RuntimeError("delivery gate rejected unverified QA without reasons")
    return {"probes": probes, "oracles": oracles, "tickets": tickets}


def _build_delivery_gate(integration: object, qa_result: object, goal_check: object) -> dict:
    """Validate all build-mode evidence before package generation or registry writes."""
    checkpoints = {
        "integration_result": integration,
        "qa_result": qa_result,
        "goal_check": goal_check,
    }
    missing = [name for name, value in checkpoints.items() if not isinstance(value, dict)]
    if missing:
        raise RuntimeError("delivery gate missing required checkpoint(s): " + ", ".join(missing))

    integration_state = integration.get("verification")
    qa_state = qa_result.get("verification")
    goal_verdict = goal_check.get("verdict")
    if integration_state not in {"passed", "failed", "unverified"}:
        raise RuntimeError("delivery gate has invalid integration verification")
    if qa_state not in {"passed", "failed", "unverified"}:
        raise RuntimeError("delivery gate has invalid QA verification")
    if goal_verdict not in {"fulfilled", "partial", "unfulfilled"}:
        raise RuntimeError("delivery gate has invalid goal verdict")
    goal_gaps = goal_check.get("gaps")
    if not isinstance(goal_gaps, list) or any(not isinstance(gap, dict) for gap in goal_gaps):
        raise RuntimeError("delivery gate has invalid goal evidence")
    qa_reasons = qa_result.get("reasons")
    if not isinstance(qa_reasons, list) or any(not isinstance(reason, str) for reason in qa_reasons):
        raise RuntimeError("delivery gate has invalid QA reasons")
    integration_counts = {
        name: integration.get(name) for name in ("total", "passed", "failed")
    }
    if any(type(value) is not int or value < 0 for value in integration_counts.values()):
        raise RuntimeError("delivery gate has invalid integration counts")
    total = integration_counts["total"]
    passed = integration_counts["passed"]
    failed_count = integration_counts["failed"]
    counts_consistent = passed + failed_count == total
    qa_evidence = _validate_qa_evidence(integration, qa_result, goal_check)

    failed: list[str] = []
    unverified: list[str] = []
    if integration_state == "failed":
        failed.append("integration verification failed")
    elif integration_state == "unverified":
        unverified.append("integration verification is unverified")
    if failed_count:
        failed.append("integration checkpoint contains failed tests")
    if not counts_consistent:
        failed.append("integration checkpoint has inconsistent counts")
    if integration_state == "passed" and (total == 0 or passed != total):
        failed.append("passed integration checkpoint lacks a fully passing executed suite")
    if qa_state == "failed":
        failed.append("QA verification failed")
    elif qa_state == "unverified":
        unverified.append("QA verification is unverified")
    if qa_evidence["probes"]["finding"] > 0:
        failed.append("QA evidence contains a known inspector defect")
    if qa_evidence["oracles"]["mismatch"] > 0:
        failed.append("QA evidence contains a known oracle mismatch")
    if goal_verdict == "unfulfilled":
        failed.append("goal is unfulfilled")
    elif goal_verdict == "partial":
        unverified.append("goal check is partial")
    if any(gap.get("severity") == "blocker" for gap in goal_gaps):
        failed.append("goal check contains a blocker")

    reasons = list(dict.fromkeys([*qa_reasons, *failed, *unverified]))
    if failed:
        raise RuntimeError("delivery gate failed: " + "; ".join(reasons))
    if unverified:
        override = (
            qa_result.get("demo_override") is True
            and codeexec.unverified_demo_delivery_allowed()
        )
        if not override:
            raise RuntimeError("delivery gate unverified: " + "; ".join(reasons))
        return {
            "verification": "unverified",
            "reasons": reasons,
            "demo_override": True,
            "label": "UNVERIFIED DEMO",
        }
    return {
        "verification": "passed",
        "reasons": [],
        "demo_override": False,
        "label": "VERIFIED",
    }


def _process_delivery_gate(fanout_result: object) -> dict:
    """Validate persisted process fan-out evidence before any package or registry write."""
    from app.runtime.operate import _classify_process_fanout

    if not isinstance(fanout_result, dict):
        raise RuntimeError("process delivery gate missing fanout_result")
    required = {
        "run_id", "status", "verification", "reasons", "demo_override",
        "execution", "artifact",
    }
    missing = sorted(required - fanout_result.keys())
    if missing:
        raise RuntimeError(
            "process delivery gate missing fan-out evidence: " + ", ".join(missing))
    if not isinstance(fanout_result.get("run_id"), str) or not fanout_result["run_id"]:
        raise RuntimeError("process delivery gate has invalid run id")
    if fanout_result.get("status") not in {"done", "failed", "partial", "unverified"}:
        raise RuntimeError("process delivery gate has invalid run status")
    if fanout_result.get("verification") not in {"passed", "failed", "unverified"}:
        raise RuntimeError("process delivery gate has invalid verification")
    reasons = fanout_result.get("reasons")
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or not reason for reason in reasons
    ):
        raise RuntimeError("process delivery gate has invalid verification reasons")
    if type(fanout_result.get("demo_override")) is not bool:
        raise RuntimeError("process delivery gate has invalid demo override")

    execution = fanout_result.get("execution")
    artifact = fanout_result.get("artifact")
    if not isinstance(execution, dict) or not isinstance(artifact, dict):
        raise RuntimeError("process delivery gate has invalid execution or artifact evidence")
    execution_required = {
        "counts", "done", "total", "partial", "zero_candidate",
        "actual_units", "mock_dispatches", "artifact",
    }
    if not execution_required.issubset(execution):
        raise RuntimeError("process delivery gate has incomplete execution evidence")
    if execution.get("artifact") != artifact:
        raise RuntimeError("process delivery gate artifact evidence is inconsistent")
    artifact_required = {"verification", "degraded", "reason", "artifacts"}
    if not artifact_required.issubset(artifact):
        raise RuntimeError("process delivery gate has incomplete artifact evidence")
    if artifact.get("verification") not in {"passed", "failed", "unverified"}:
        raise RuntimeError("process delivery gate has invalid artifact verification")
    if type(artifact.get("degraded")) is not bool:
        raise RuntimeError("process delivery gate has invalid artifact degradation evidence")
    if artifact.get("reason") is not None and not isinstance(artifact.get("reason"), str):
        raise RuntimeError("process delivery gate has invalid artifact reason")
    descriptors = artifact.get("artifacts")
    if not isinstance(descriptors, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("kind"), str)
        or not isinstance(item.get("url"), str)
        for item in descriptors
    ):
        raise RuntimeError("process delivery gate has invalid artifact descriptors")

    derived = _classify_process_fanout(execution, artifact)
    if any(fanout_result.get(key) != derived[key]
           for key in ("status", "verification", "reasons")):
        raise RuntimeError("process delivery gate rejected contradictory fan-out evidence")
    if derived["verification"] == "failed":
        raise RuntimeError("process delivery gate failed: " + "; ".join(derived["reasons"]))
    if derived["verification"] == "unverified":
        override = (
            fanout_result.get("demo_override") is True
            and codeexec.unverified_demo_delivery_allowed()
        )
        if not override:
            raise RuntimeError(
                "process delivery gate unverified: " + "; ".join(derived["reasons"]))
        return {
            "verification": "unverified", "reasons": derived["reasons"],
            "demo_override": True, "label": "UNVERIFIED DEMO",
            "fanout": fanout_result,
        }
    if fanout_result.get("demo_override") is True:
        raise RuntimeError("process delivery gate rejected override on passed evidence")
    return {
        "verification": "passed", "reasons": [], "demo_override": False,
        "label": "VERIFIED", "fanout": fanout_result,
    }


async def run(ctx) -> None:
    job = await ctx.refresh()
    mode = job.get("mode", "build")
    delivery_gate = None
    if mode == "build":
        integration = await ctx.get_checkpoint("integration_result")
        qa_result = await ctx.get_checkpoint("qa_result")
        goal_check = await ctx.get_checkpoint("goal_check")
        delivery_gate = _build_delivery_gate(integration, qa_result, goal_check)
        job_root = workspace.job_dir(ctx.job_id)
        try:
            entrypoint = resolve_within(job_root, "process.py")
        except UnsafePathError as exc:
            raise RuntimeError("delivery gate rejected unsafe process.py path") from exc
        if not entrypoint.is_file():
            raise RuntimeError("delivery gate missing required build entrypoint process.py")
        try:
            entrypoint_source = entrypoint.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("delivery gate cannot read process.py as UTF-8") from exc

    plan_id = await ctx.get_checkpoint("certified_plan_id")
    plan_row = await ctx.dao.get_plan(plan_id) if plan_id else await ctx.dao.current_plan(ctx.job_id)
    plan = plan_row["body"]
    plan_id = plan_row["id"]
    goal = job.get("goal", "")

    if mode != "build":
        fanout_result = await ctx.get_checkpoint("fanout_result")
        delivery_gate = _process_delivery_gate(fanout_result)
        fanout_run_id = await ctx.get_checkpoint("fanout_run_id")
        if fanout_run_id != delivery_gate["fanout"]["run_id"]:
            raise RuntimeError("process delivery gate run checkpoints do not match")

    tests = await ctx.get_checkpoint("tests") or []
    vectors = await ctx.get_checkpoint("vectors") or []
    if mode != "build":
        goal_check = await ctx.get_checkpoint("goal_check") or {"verdict": "fulfilled", "gaps": []}
    amendments = await ctx.dao.list_amendments(plan_id)
    consults = await ctx.dao.list_consults(plan_id)

    # generated docs (trust seat). A budget-capped run (09 §4) must still deliver its partial
    # dashboard — docs degrade to deterministic content rather than blocking the job.
    trust = seat("trust")
    try:
        docs = await trust.write_docs(ctx.complete, ctx.emit, plan=plan, goal=goal)
    except Exception as exc:
        await ctx.emit(E.SYSTEM_NOTICE, {"text": f"docs generation skipped: {type(exc).__name__}",
                                         "level": "warn", "scope": "delivery"})
        docs = {"readme": f"# {job.get('title', 'Process')}\n\nGoal: {goal}\n",
                "runbook": "## Runbook\n1. Provide a batch of units.\n2. Run the process.\n"
                           "3. Review any needs_review units in the queue.\n",
                "qa_report": "## QA report\nSee tickets and oracle checks in the package.\n",
                "entry_module": "process"}

    # final invoice reconciled against the quote
    quote = await ctx.dao.get_quote(ctx.job_id)
    invoice = await invoice_mod.build_invoice(ctx.scope, (quote or {}).get("body"))

    # package layout (04 §2)
    slug = await _unique_slug(ctx.dao, _slugify(job.get("title", "") or plan.get("mode", "process")))
    version = 1
    seats_used = sorted({s.get("seat") for s in plan.get("model_bom", {}).get("seats", []) if s.get("seat")})
    manifest = {
        "name": job.get("title", slug), "slug": slug, "version": version, "mode": mode, "goal": goal,
        "model_bom": plan.get("model_bom", {}), "connectors": (job.get("spec") or {}).get("connectors", []),
        "entrypoint": "process.py" if mode == "build" else "topology.json",
        # No image build occurs in this stage; claiming a tag would be a false deliverable.
        "image_tag": None,
        "sampling": 0.05, "seats": seats_used,
        "goal_verdict": goal_check.get("verdict") if mode == "build"
        else goal_check.get("verdict", "fulfilled"),
    }
    src_files = workspace.read_src(ctx.job_id)
    if mode == "build":
        src_files.append({"path": "process.py", "content": entrypoint_source})
        package_summary = {
            "source_files": len(src_files),
            "test_specs": len(tests),
            "oracle_vectors": len(vectors),
            "runtime_image_built": False,
            "image_tag": None,
        }
        manifest.update({
            "verification": delivery_gate["verification"],
            "verification_reasons": delivery_gate["reasons"],
            "demo_override": delivery_gate["demo_override"],
            "delivery_label": delivery_gate["label"],
            "package_summary": package_summary,
        })
        goal_doc = {
            "text": goal,
            "verdict": goal_check.get("verdict"),
            "gaps": goal_check.get("gaps", []),
            "verification": delivery_gate["verification"],
            "reasons": delivery_gate["reasons"],
            "demo_override": delivery_gate["demo_override"],
        }
        reason_lines = "\n".join(f"- {reason}" for reason in delivery_gate["reasons"])
        docs["qa_report"] = (
            f"## Verification\n\nStatus: {delivery_gate['label']}\n\n"
            + (f"Reasons:\n{reason_lines}\n\n" if reason_lines else "")
            + docs.get("qa_report", "")
        )
    else:
        fanout = delivery_gate["fanout"]
        execution = fanout["execution"]
        package_summary = {
            "topology_steps": len((plan.get("topology") or {}).get("steps") or []),
            "fanout_run_id": fanout["run_id"],
            "input_total": execution["total"],
            "processed_total": execution["done"],
            "actual_units": execution["actual_units"],
            "synthetic_units": execution.get("synthetic_units") is True,
            "artifact_verification": fanout["artifact"]["verification"],
            "image_tag": None,
        }
        manifest.update({
            "verification": delivery_gate["verification"],
            "verification_reasons": delivery_gate["reasons"],
            "demo_override": delivery_gate["demo_override"],
            "delivery_label": delivery_gate["label"],
            "package_summary": package_summary,
            "run_evidence": {
                "run_id": fanout["run_id"], "status": fanout["status"],
                "verification": fanout["verification"],
                "partial": execution["partial"],
                "zero_candidate": execution["zero_candidate"],
                "actual_units": execution["actual_units"],
            },
        })
        goal_doc = {
            "text": goal, "verdict": goal_check.get("verdict", "fulfilled"),
            "gaps": goal_check.get("gaps", []),
            "verification": delivery_gate["verification"],
            "reasons": delivery_gate["reasons"],
            "demo_override": delivery_gate["demo_override"],
        }
        reason_lines = "\n".join(f"- {reason}" for reason in delivery_gate["reasons"])
        docs["qa_report"] = (
            f"## Verification\n\nStatus: {delivery_gate['label']}\n\n"
            + (f"Reasons:\n{reason_lines}\n\n" if reason_lines else "")
            + docs.get("qa_report", "")
        )

    package_path = workspace.assemble_package(
        slug=slug, version=version, manifest=manifest, plan=plan, amendments=amendments,
        consults=consults, goal=goal_doc, src_files=src_files, tests=tests, vectors=vectors,
        docs=docs, invoice=invoice, topology=plan.get("topology") if mode != "build" else None,
    )

    # register in the operations registry
    process_id = await ctx.dao.create_process(slug=slug, name=job.get("title", slug), mode=mode,
                                              goal=goal, created_from_job=ctx.job_id,
                                              created_from=job.get("origin", "build"))
    # corpus binding (hardening): registered-process runs default to the build-time corpus
    company = (job.get("spec") or {}).get("company")
    if company:
        await ctx.dao.update_process(process_id, corpus_company=company)
    await ctx.dao.create_version(process_id=process_id, version=version, plan_id=plan_id,
                                 package_path=package_path, image_tag=manifest["image_tag"])

    # link the build-time corpus run (process mode) to the registered process so the registry
    # shows it as the process's first run with a filled dashboard
    fanout_run_id = await ctx.get_checkpoint("fanout_run_id")
    if fanout_run_id:
        await ctx.dao.update_run(fanout_run_id, process_id=process_id, version=version)

    await ctx.emit(E.DELIVER_REGISTERED, {
        "process_id": process_id, "slug": slug, "version": version, "mode": mode,
        "package_path": package_path, "goal_verdict": goal_check.get("verdict", "fulfilled"),
        "invoice_total_usd": invoice["total_usd"], "frontier_calls": invoice["frontier_calls"],
        "verification": delivery_gate["verification"],
        "verification_reasons": delivery_gate["reasons"],
        "demo_override": delivery_gate["demo_override"],
        "delivery_label": delivery_gate["label"],
        "image_tag": None,
        "package_summary": package_summary,
    })
    await ctx.advance("done")
