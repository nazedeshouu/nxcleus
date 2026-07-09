"""Invoice aggregation (10 §5). Aggregate `meter_events` by scope into the same line structure as the
quote, with actuals: real token counts per seat/backend/zone + estimated GPU-seconds (footnoted).
The quote is a range; the invoice is exact — reconciled side-by-side at delivery.
"""
from __future__ import annotations

from app.db.engine import db
from app.models.registry import ZONE

_ZONE_LABEL = {"EXTERNAL": "Frontier planning (sanitized brief only)",
               "LOCAL": "Local GPU (certify / build / conductor / consolidate / QA)",
               "AMD_HOSTED": "Fallback serving (Fireworks, AMD-hosted)",
               "CUSTOM": "Customer-connected endpoint"}


async def build_invoice(scope: str, quote_body: dict | None = None) -> dict:
    # meter_events records `backend` (05); zone is derived from it (01 §3 map)
    rows = await db.fetchall(
        "SELECT backend, COALESCE(SUM(tokens_in),0) ti, COALESCE(SUM(tokens_out),0) to_, "
        "COALESCE(SUM(cost_usd),0) cost, COUNT(*) calls FROM meter_events "
        "WHERE scope = :scope AND kind = 'llm_call' GROUP BY backend",
        {"scope": scope},
    )
    lines = []
    total = 0.0
    frontier_calls = 0
    for r in rows:
        cost = round(float(r["cost"]), 6)
        total += cost
        zone = ZONE.get(r["backend"], "LOCAL")
        if zone == "EXTERNAL":
            frontier_calls += int(r["calls"])
        lines.append({
            "item": _ZONE_LABEL.get(zone, zone),
            "qty": f"{int(r['ti'])+int(r['to_'])} tokens, {int(r['calls'])} calls",
            "actual_usd": cost,
            "tokens_in": int(r["ti"]),
            "tokens_out": int(r["to_"]),
            "zone": zone,
            "backend": r["backend"],
        })
    invoice = {
        "lines": lines,
        "total_usd": round(total, 6),
        "footnote": "GPU-seconds are an estimate (10 §2); token counts are exact.",
        "frontier_calls": frontier_calls,
    }
    if quote_body:
        invoice["quote_total_est_usd"] = quote_body.get("total_est_usd")
        invoice["delta_vs_quote"] = round(total - (quote_body.get("total_est_usd", [0, 0])[0]), 6)
    return invoice
