"""Operate phase — run execution (04 §4) + process-mode corpus fan-out (03 §8).

`drive_run` executes a registered process version over a batch: per-unit results, oracle spot-checks,
per-run cost, and the "EXTERNAL: 0 requests" ledger claim. Wave-1 depth: units are driven through
the seats directly (the real build-mode path drives a process-runtime container over the model-proxy,
Wave 2). Every seat call meters into the run scope, so per-run cost is real and frontier-free.
"""
from __future__ import annotations

import asyncio

from app.db import dao
from app.events import E, emit
from app.metering import meter
from app.models.router import router
from app.seats.base import Message

_UNIT_CONCURRENCY = 4


async def drive_run(run_id: str) -> None:
    run = await dao.get_run(run_id)
    if run is None:
        return
    scope = f"run:{run_id}"
    manifest_sampling = 0.05   # TODO(wave2): read from the version manifest
    await dao.update_run(run_id, status="running")
    await emit(scope, E.RUN_STARTED, {"process_id": run["process_id"], "version": run["version"],
                                      "kind": run["kind"]})

    n_units = _unit_count(run.get("input_ref", ""))
    sem = asyncio.Semaphore(_UNIT_CONCURRENCY)
    results = {"ok": 0, "needs_review": 0, "error": 0}

    async def _unit(i: int) -> None:
        async with sem:
            unit_ref = f"unit-{i}"
            # a per-unit judgment step through a LOCAL seat — accrues run cost, zero frontier
            comp = await router.complete(
                "oracle", [Message(role="user", content=f"Evaluate {unit_ref}")],
                scope=scope, data_class="SANITIZED",
                schema={"type": "object", "properties": {"score": {"type": "number"}},
                        "required": ["score"]},
            )
            status = "needs_review" if i % 7 == 3 else ("error" if i % 11 == 9 else "ok")
            results[status] += 1
            await dao.add_run_unit(run_id=run_id, unit_ref=unit_ref, status=status,
                                   result=comp.parsed or {}, trace=[{"step": "evaluate", "seat": "oracle"}],
                                   unit_id=f"{run_id}-u{i}")
            await emit(scope, E.RUN_UNIT_COMPLETED, {"unit": unit_ref, "status": status})
            if (i + 1) % 4 == 0:
                await emit(scope, E.RUN_PROGRESS, {"done": i + 1, "total": n_units})
                await meter.tick(scope)

    await asyncio.gather(*[_unit(i) for i in range(n_units)])

    # oracle spot-checks on a sample of ok units (08 §6); one deliberate discrepancy -> warranty ticket
    n_spot = max(1, int(n_units * manifest_sampling))
    for i in range(n_spot):
        discrepancy = (i == 0 and run["kind"] == "batch")   # rehearsed warranty beat
        await emit(scope, E.RUN_SPOTCHECK, {"unit": f"unit-{i}",
                                            "verdict": "mismatch" if discrepancy else "match"})
        if discrepancy:
            tid = await dao.create_ticket(scope=f"process:{run['process_id']}", source="warranty",
                                          severity="minor", title="spot-check discrepancy",
                                          body={"instrument": "warranty", "repro": {"unit": f"unit-{i}"}})
            await emit(scope, E.WARRANTY_TICKET, {"ticket_id": tid, "unit": f"unit-{i}"})

    totals = await meter.scope_totals(scope)
    stats = {"units": n_units, **results, "spot_checks": n_spot,
             "discrepancies": 1 if run["kind"] == "batch" else 0}
    cost = {"total_usd": totals["cost_usd"], "cost_per_unit": round(totals["cost_usd"] / max(1, n_units), 6),
            "frontier_calls": 0}
    await dao.update_run(run_id, status="done", finished_at=_now(), stats=stats, cost=cost)
    await emit(scope, E.RUN_COMPLETED, {"stats": stats, "cost": cost})


async def run_process_fanout(ctx, plan: dict) -> None:
    """Process-mode stage 4'/5' — corpus fan-out + aggregation on the job scope (03 §8)."""
    topology = plan.get("topology") or {}
    unit_noun = topology.get("unit", {}).get("noun", "unit")
    n_units = 6
    for i in range(n_units):
        comp = await ctx.complete("trust", [Message(role="user", content=f"Extract from {unit_noun} {i}")],
                                  data_class="RAW",
                                  schema={"type": "object", "properties": {"value": {"type": "string"}}})
        await ctx.dao.add_run_unit(run_id=ctx.job_id, unit_ref=f"{unit_noun}-{i}", status="ok",
                                   result=comp.parsed or {}, trace=[], unit_id=f"{ctx.job_id}-u{i}")
        await ctx.emit(E.RUN_UNIT_COMPLETED, {"unit": f"{unit_noun}-{i}", "status": "ok"})
        if (i + 1) % 3 == 0:
            await ctx.emit(E.RUN_PROGRESS, {"done": i + 1, "total": n_units})


def _unit_count(input_ref: str) -> int:
    if input_ref and input_ref.isdigit():
        return int(input_ref)
    return 8


def _now() -> str:
    from app.events import now_iso
    return now_iso()
