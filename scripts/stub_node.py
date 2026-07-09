#!/usr/bin/env python
"""Stub node agent (brief item 12) — emits fake rocm-smi telemetry so the fleet manager's poll loop
produces telemetry.gpu events in dev without a real MI300X droplet. Mirrors the real node agent's
`GET /telemetry` shape (02 §9). Self-registers with the control plane on boot.

Run:  uv run --project backend python scripts/stub_node.py --name A --gpus 8 --control http://localhost:8000
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

import random  # noqa: E402

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402

app = FastAPI(title="Nxcleus stub node agent")
_N_GPUS = 8


@app.get("/telemetry")
async def telemetry() -> dict:
    gpus = []
    for i in range(_N_GPUS):
        used = random.uniform(70, 150)
        gpus.append({"index": i, "vram_used_gb": round(used, 1), "vram_total_gb": 192,
                     "util": round(random.uniform(40, 95), 1), "power_w": round(random.uniform(400, 620)),
                     "temp_c": round(random.uniform(55, 78))})
    return {"gpus": gpus, "tokens_per_s": round(random.uniform(1200, 2400)),
            "requests_running": random.randint(0, 8), "requests_waiting": random.randint(0, 4)}


def main() -> None:
    global _N_GPUS
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="A")
    ap.add_argument("--gpus", type=int, default=8)
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--ip", default="127.0.0.1")
    ap.add_argument("--control", default="http://localhost:8000")
    ap.add_argument("--admin-token", default="")
    args = ap.parse_args()
    _N_GPUS = args.gpus

    headers = {"X-Admin-Token": args.admin_token} if args.admin_token else {}
    try:
        httpx.post(f"{args.control}/api/admin/nodes/register",
                   json={"name": args.name, "ip": args.ip,
                         "gpus": [{"index": i, "vram_total_gb": 192} for i in range(args.gpus)],
                         "seats": []},
                   headers=headers, timeout=5.0)
        print(f"registered node {args.name} with {args.control}")
    except Exception as e:  # noqa: BLE001
        print(f"registration failed (control plane up?): {e}")

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
