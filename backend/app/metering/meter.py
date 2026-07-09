"""Meter — writes a `meter_events` row on every dispatch (10 §1) and emits the cost events.

Real numbers from real calls: token counts from the provider/vLLM `usage`, cost from the rates
table (10 §3). Local backends price on estimated GPU-seconds (10 §2). `tick()` emits a throttled
`meter.tick` (<=1/s per scope) with running scope totals for the cost meter.
"""
from __future__ import annotations

import time

from app.config import settings
from app.db.engine import db
from app.events import E, emit
from app.ids import new_id
from app.metering.rates import gpu_hour_usd, load_rates, token_rate

_last_tick: dict[str, float] = {}


def cost_for(backend: str, model: str, tokens_in: int, tokens_out: int, gpu_seconds: float) -> float:
    in_rate, out_rate = token_rate(backend, model)
    token_cost = (tokens_in / 1_000_000) * in_rate + (tokens_out / 1_000_000) * out_rate
    gpu_cost = gpu_seconds * gpu_hour_usd() / 3600.0
    margin = load_rates().get("margin", 0.0)
    return round((token_cost + gpu_cost) * (1 + margin), 6)


def estimate_gpu_seconds(backend: str, tokens_out: int) -> float:
    """Honest approximation for local/mock calls when we lack a wall-clock concurrency snapshot
    (10 §2). Real local dispatch overrides this with the measured value."""
    if backend in ("local", "mock"):
        return round(max(0.1, tokens_out / 40.0), 3)
    return 0.0


async def record(
    *, scope: str, seat: str, backend: str, model: str, zone: str,
    tokens_in: int, tokens_out: int, gpu_seconds: float | None = None,
) -> float:
    gpu_s = estimate_gpu_seconds(backend, tokens_out) if gpu_seconds is None else gpu_seconds
    cost = cost_for(backend, model, tokens_in, tokens_out, gpu_s)
    await db.execute(
        "INSERT INTO meter_events (id, ts, scope, seat, backend, model_id, kind, tokens_in, "
        "tokens_out, gpu_seconds, cost_usd) VALUES (:id, datetime('now'), :scope, :seat, :backend, "
        ":model, 'llm_call', :ti, :to, :gs, :cost)",
        {"id": new_id("meter"), "scope": scope, "seat": seat, "backend": backend, "model": model,
         "ti": tokens_in, "to": tokens_out, "gs": gpu_s, "cost": cost},
    )
    return cost


async def record_gpu_sample(*, scope: str, node: str, gpu_seconds: float, cost_usd: float) -> None:
    await db.execute(
        "INSERT INTO meter_events (id, ts, scope, seat, backend, model_id, kind, tokens_in, "
        "tokens_out, gpu_seconds, cost_usd) VALUES (:id, datetime('now'), :scope, 'fleet', :node, "
        "'', 'gpu_sample', 0, 0, :gs, :cost)",
        {"id": new_id("meter"), "scope": scope, "node": node, "gs": gpu_seconds, "cost": cost_usd},
    )


async def scope_totals(scope: str) -> dict:
    row = await db.fetchone(
        "SELECT COALESCE(SUM(tokens_in),0) ti, COALESCE(SUM(tokens_out),0) to_, "
        "COALESCE(SUM(cost_usd),0) cost, COUNT(*) calls FROM meter_events "
        "WHERE scope = :scope AND kind = 'llm_call'",
        {"scope": scope},
    )
    return {"tokens_in": int(row["ti"]), "tokens_out": int(row["to_"]),
            "cost_usd": round(float(row["cost"]), 6), "calls": int(row["calls"])}


async def tick(scope: str) -> None:
    """Throttled scope-total broadcast (<=1/s per scope) for the live cost meter (06 §3)."""
    now = time.monotonic()
    if now - _last_tick.get(scope, 0.0) < 1.0:
        return
    _last_tick[scope] = now
    await emit(scope, E.METER_TICK, await scope_totals(scope))


# --- budget guards (07 §5.4, 10 §7) ---------------------------------------------------------------
async def fireworks_spend_today() -> float:
    row = await db.fetchone(
        "SELECT COALESCE(SUM(cost_usd),0) c FROM meter_events "
        "WHERE backend = 'fireworks' AND ts >= datetime('now','start of day')"
    )
    return float(row["c"])


async def scope_spend(scope: str) -> float:
    row = await db.fetchone(
        "SELECT COALESCE(SUM(cost_usd),0) c FROM meter_events WHERE scope = :scope", {"scope": scope}
    )
    return float(row["c"])


def fireworks_budget() -> float:
    return settings.fireworks_daily_budget_usd
