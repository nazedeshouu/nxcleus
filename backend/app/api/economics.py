"""Economics router — the money-slide data (06 §2, 10 §6)."""
from __future__ import annotations

from fastapi import APIRouter

from app.db import dao
from app.metering.invoice import build_invoice

router = APIRouter(tags=["economics"])


@router.get("/economics/summary")
async def economics_summary() -> dict:
    """Per process: build cost vs per-run trend (10 §6)."""
    out = []
    for process in await dao.list_processes():
        job_scope = f"job:{process['created_from_job']}"
        build_invoice_data = await build_invoice(job_scope)
        runs = await dao.list_runs(process["id"])
        run_lines = []
        for r in runs:
            cost = r.get("cost") if isinstance(r.get("cost"), dict) else {}
            stats = r.get("stats") if isinstance(r.get("stats"), dict) else {}
            units_value = stats.get("units")
            units = (units_value if isinstance(units_value, int)
                     and not isinstance(units_value, bool) and units_value >= 0 else None)
            cost_verification = cost.get("verification")
            if cost_verification not in {"passed", "unverified"}:
                cost_verification = "unverified"
            reason = cost.get("reason")
            if cost_verification == "unverified" and not isinstance(reason, str):
                reason = "cost verification metadata is unavailable"

            status_value = r.get("status")
            status = (status_value.strip() if isinstance(status_value, str)
                      and status_value.strip() else "unknown")
            run_verification = stats.get("verification")
            if run_verification not in {"passed", "failed", "unverified"}:
                run_verification = "unverified"
            reasons_value = stats.get("verification_reasons")
            verification_reasons = (
                [item for item in reasons_value if isinstance(item, str)]
                if isinstance(reasons_value, list) else []
            )
            corpus = stats.get("corpus")
            if not isinstance(corpus, dict):
                corpus = r.get("corpus") if isinstance(r.get("corpus"), dict) else {}
            demo = (r.get("demo") is True or stats.get("demo") is True
                    or corpus.get("kind") == "synthetic")
            run_lines.append({"run_id": r["id"], "ts": r.get("started_at"), "units": units,
                              "cost_usd": cost.get("total_usd"),
                              "cost_per_unit": cost.get("cost_per_unit"),
                              "model_calls": cost.get("model_calls"),
                              "frontier_calls": cost.get("frontier_calls"),
                              "cost_verification": cost_verification,
                              "cost_reason": reason,
                              "status": status,
                              "verification": run_verification,
                              "verification_reasons": verification_reasons,
                              "demo": demo,
                              "mock_dispatches": stats.get("mock_dispatches", 0)})
        out.append({
            "process_id": process["id"], "slug": process["slug"],
            "build_cost_usd": build_invoice_data["total_usd"],
            "build_frontier_calls": build_invoice_data["frontier_calls"],
            "runs": run_lines,
            "trend": "capex once, flat opex per run",
        })
    return {"processes": out}
