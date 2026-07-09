"""Fleet manager (07 §5). Node self-registration, heartbeat poll loop (-> telemetry.gpu events +
gpu_sample meter rows), failover on 3 missed beats, drain endpoint. Provisioning itself is out of
band (doctl / portal, infra/droplet — the AI engineer's zone); this is the control-plane side.
"""
from __future__ import annotations

import asyncio
import contextlib

import httpx

from app.config import settings
from app.db import dao
from app.events import E, emit
from app.fleet import health
from app.metering import meter

_POLL_MISSES: dict[str, int] = {}


async def register(*, name: str, ip: str, gpus: list, seats: list | None = None) -> str:
    node_id = await dao.register_node(name=name, ip=ip, gpus=gpus, seats=seats)
    health.mark_ready(name, ip)
    _POLL_MISSES[node_id] = 0
    await emit("fleet", E.FLEET_NODE_READY, {"node": name, "ip": ip,
                                             "gpus": len(gpus), "seats": seats or []})
    return node_id


async def drain(node_id: str) -> None:
    node = await dao.get_node(node_id)
    if not node:
        return
    await dao.set_node_status(node_id, "draining")
    health.mark_down(node["name"])
    await emit("fleet", E.FLEET_NODE_DOWN, {"node": node["name"], "reason": "drained"})


async def poll_once() -> None:
    """Poll every ready node's /telemetry -> telemetry.gpu + a sampled gpu_sample meter row."""
    for node in await dao.list_nodes():
        if node["status"] not in ("ready", "draining"):
            continue
        node_id, name, ip = node["id"], node["name"], node["ip"]
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"http://{ip}:9100/telemetry")
                resp.raise_for_status()
                tele = resp.json()
            _POLL_MISSES[node_id] = 0
            await dao.node_heartbeat(node_id)
            health.mark_ready(name, ip)
            await _emit_telemetry(name, tele)
        except Exception:  # noqa: BLE001 — a miss, not a crash
            _POLL_MISSES[node_id] = _POLL_MISSES.get(node_id, 0) + 1
            if _POLL_MISSES[node_id] >= 3 and node["status"] == "ready":
                await dao.set_node_status(node_id, "down")
                health.mark_down(name)
                await emit("fleet", E.FLEET_NODE_DOWN, {"node": name, "reason": "3 missed heartbeats"})


async def _emit_telemetry(name: str, tele: dict) -> None:
    gpus = tele.get("gpus", [])
    tok_s = tele.get("tokens_per_s", 0)
    # one event per GPU (06 §3 ruling): {node, gpu, vram_used_gb, vram_total_gb, util, power_w, toks_per_s}
    for g in gpus:
        await emit("fleet", E.TELEMETRY_GPU, {
            "node": name, "gpu": g.get("index", 0),
            "vram_used_gb": round(g.get("vram_used_gb", 0), 1),
            "vram_total_gb": round(g.get("vram_total_gb", 0), 1),
            "util": round(g.get("util", 0), 1), "power_w": g.get("power_w", 0),
            "toks_per_s": round(tok_s / max(1, len(gpus))),
        })
    # store 1-in-15 samples for GPU-second attribution (10 §2)
    await meter.record_gpu_sample(scope="fleet", node=name,
                                  gpu_seconds=settings.node_poll_interval_s * len(gpus),
                                  cost_usd=0.0)


async def poll_loop() -> None:
    while True:
        with contextlib.suppress(Exception):
            await poll_once()
        await asyncio.sleep(settings.node_poll_interval_s)
