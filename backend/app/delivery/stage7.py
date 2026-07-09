"""Stage 7 — Delivery -> operations registry (03 §10, 04 §2). Seat: trust (docs). Assembles the
immutable process package, computes the final metered invoice, registers processes + process_versions
v1, and emits deliver.registered. Job closes; everything after is the operate phase.
"""
from __future__ import annotations

import re

from app.events import E
from app.metering import invoice as invoice_mod
from app.orchestrator.seatlib import seat
from app.runtime import workspace


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "process").lower()).strip("-")
    return slug or "process"


async def _unique_slug(dao, base: str) -> str:
    slug, n = base, 1
    while await dao.get_process_by_slug(slug) is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


async def run(ctx) -> None:
    job = await ctx.refresh()
    plan_id = await ctx.get_checkpoint("certified_plan_id")
    plan_row = await ctx.dao.get_plan(plan_id) if plan_id else await ctx.dao.current_plan(ctx.job_id)
    plan = plan_row["body"]
    plan_id = plan_row["id"]
    goal = job.get("goal", "")
    mode = job.get("mode", "build")

    tests = await ctx.get_checkpoint("tests") or []
    vectors = await ctx.get_checkpoint("vectors") or []
    goal_check = await ctx.get_checkpoint("goal_check") or {"verdict": "fulfilled", "gaps": []}
    amendments = await ctx.dao.list_amendments(plan_id)
    consults = await ctx.dao.list_consults(plan_id)

    # generated docs (trust seat)
    trust = seat("trust")
    docs = await trust.write_docs(ctx.complete, ctx.emit, plan=plan, goal=goal)

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
        "image_tag": f"nxcleus/proc-{slug}:v{version}" if mode == "build" else None,
        "sampling": 0.05, "seats": seats_used,
        "goal_verdict": goal_check.get("verdict", "fulfilled"),
    }
    src_files = workspace.read_src(ctx.job_id)
    if mode == "build":
        entry = workspace.job_dir(ctx.job_id) / "process.py"
        if entry.exists():
            src_files.append({"path": "process.py", "content": entry.read_text()})
    goal_doc = {"text": goal, "verdict": goal_check.get("verdict", "fulfilled"),
                "gaps": goal_check.get("gaps", [])}

    package_path = workspace.assemble_package(
        slug=slug, version=version, manifest=manifest, plan=plan, amendments=amendments,
        consults=consults, goal=goal_doc, src_files=src_files, tests=tests, vectors=vectors,
        docs=docs, invoice=invoice, topology=plan.get("topology") if mode != "build" else None,
    )

    # register in the operations registry
    process_id = await ctx.dao.create_process(slug=slug, name=job.get("title", slug), mode=mode,
                                              goal=goal, created_from_job=ctx.job_id,
                                              created_from=job.get("origin", "build"))
    await ctx.dao.create_version(process_id=process_id, version=version, plan_id=plan_id,
                                 package_path=package_path, image_tag=manifest["image_tag"])

    await ctx.emit(E.DELIVER_REGISTERED, {
        "process_id": process_id, "slug": slug, "version": version, "mode": mode,
        "package_path": package_path, "goal_verdict": goal_check.get("verdict", "fulfilled"),
        "invoice_total_usd": invoice["total_usd"], "frontier_calls": invoice["frontier_calls"],
    })
    await ctx.advance("done")
