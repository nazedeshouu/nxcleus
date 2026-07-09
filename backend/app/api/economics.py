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
            cost = (r.get("cost") or {}).get("total_usd", 0.0)
            units = (r.get("stats") or {}).get("units", 0)
            run_lines.append({"run_id": r["id"], "ts": r.get("started_at"), "units": units,
                              "cost_usd": cost,
                              "cost_per_unit": round(cost / units, 6) if units else 0.0,
                              "frontier_calls": 0})
        out.append({
            "process_id": process["id"], "slug": process["slug"],
            "build_cost_usd": build_invoice_data["total_usd"],
            "build_frontier_calls": build_invoice_data["frontier_calls"],
            "runs": run_lines,
            "trend": "capex once, flat opex per run",
        })
    return {"processes": out}
