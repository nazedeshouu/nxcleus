"""Stage 3 — Quote (10 §4). Deterministic function of BoM + estimates + rates; no LLM. Emits an
itemized quote; the job parks at `quoted` until POST /approve-quote. Quote is a range; the invoice
is exact (10 §5) — reconciled side-by-side at delivery.
"""
from __future__ import annotations

from app.events import E
from app.metering.rates import gpu_hour_usd, token_rate


def build_quote_body(plan: dict) -> dict:
    est = plan.get("estimates", {})
    bom = plan.get("model_bom", {})
    fleet = bom.get("fleet", {})

    frontier_tokens = est.get("frontier_tokens", 0)
    gpu_hours = est.get("gpu_hours", 0.0)
    width = fleet.get("parallel_width", 1)

    in_rate, out_rate = token_rate("anthropic", "claude-fable-5")
    frontier_low = (frontier_tokens / 1_000_000) * in_rate
    frontier_high = frontier_low + (frontier_tokens / 1_000_000) * out_rate
    gpu_rate = gpu_hour_usd()

    build_gpu = gpu_hours * 0.7
    consolidate_gpu = gpu_hours * 0.1
    qa_gpu = gpu_hours * 0.2

    def rng(base: float, spread: float) -> list[float]:
        return [round(base * (1 - spread), 2), round(base * (1 + spread), 2)]

    lines = [
        {"item": "Frontier planning & consults (sanitized brief only)",
         "qty": f"≈{frontier_tokens // 1000}k tokens",
         "est_usd": [round(frontier_low, 2), round(max(frontier_high, frontier_low * 1.5), 2)]},
        {"item": "Local certification, build waves & conductor review (GPU)",
         "qty": f"≈{round(build_gpu, 1)} GPU-h on {fleet.get('nodes', 1)}× MI300X",
         "est_usd": rng(build_gpu * gpu_rate, 0.3)},
        {"item": "Local consolidation (GPU)", "qty": f"≈{round(consolidate_gpu, 1)} GPU-h",
         "est_usd": rng(consolidate_gpu * gpu_rate, 0.3)},
        {"item": "Adversarial QA incl. Numeric Oracle & goal check",
         "qty": f"≈{round(qa_gpu, 1)} GPU-h", "est_usd": rng(qa_gpu * gpu_rate, 0.3)},
        {"item": "Projected per-run operating cost", "qty": "per 100 units", "est_usd": [0.06, 0.12]},
    ]
    total_low = round(sum(line_low for line in lines[:-1] for line_low in [line["est_usd"][0]]), 2)
    total_high = round(sum(line["est_usd"][1] for line in lines[:-1]), 2)
    return {
        "lines": lines,
        "total_est_usd": [total_low, total_high],
        "basis": f"model BoM v1 (width {width}); ranges = ±50% on token estimates, ±30% on GPU time",
    }


async def issue(ctx, plan: dict, plan_id: str) -> str:
    body = build_quote_body(plan)
    quote_id = await ctx.dao.create_quote(job_id=ctx.job_id, plan_id=plan_id, body=body)
    await ctx.emit(E.QUOTE_ISSUED, {"quote_id": quote_id, "lines": body["lines"],
                                    "total_est_usd": body["total_est_usd"]})
    return quote_id
