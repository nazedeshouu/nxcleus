"""Nxcleus node agent — GPU telemetry + self-registration for one MI300X droplet.

Spec: docs/specs/02 §9, 07 §5.1. ~120 LOC FastAPI.

  GET /health     -> {"ok": true, "mode": "rocm"|"synthetic"}
  GET /telemetry  -> rocm-smi JSON + per-vLLM-instance /metrics scrape
                     (running/waiting requests, tokens/s). Polled every 2 s by the
                     control plane -> telemetry.gpu events (02 §9).

Graceful in dev: when rocm-smi is absent (this Mac), returns a SYNTHETIC payload with
the SAME SHAPE the backend stub uses (scripts/stub_node.py) so the UI panel renders
identically whether or not a real droplet is up. `build_telemetry()` is a plain function
so it is unit-testable without a server.

On startup the agent self-registers with the control plane:
    POST {CONTROL_PLANE_URL}/api/admin/nodes/register {name, ip, gpus}
(Authorization: Bearer {ADMIN_TOKEN}). Registration failure is logged, not fatal —
the control plane also treats nodes as cattle-by-heartbeat.

Config via env:
  NODE_NAME (A|B|C|D), NODE_GPUS ("0,1,2,3,4"), CONTROL_PLANE_URL, ADMIN_TOKEN,
  VLLM_ENDPOINTS ("glm-46@8000,oracle@8011,..."  served_model_name@port), NODE_AGENT_PORT.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request

from fastapi import FastAPI

NODE_NAME = os.getenv("NODE_NAME", "A")
NODE_GPUS = [int(g) for g in os.getenv("NODE_GPUS", "0").split(",") if g.strip() != ""]
CONTROL_PLANE_URL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8080").rstrip("/")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
# "served_model_name@port" pairs; the port hosts a vLLM OpenAI server with /metrics.
VLLM_ENDPOINTS = [e for e in os.getenv("VLLM_ENDPOINTS", "").split(",") if e.strip()]

app = FastAPI(title="Nxcleus node agent")
_prev_tokens: dict[int, tuple[float, float]] = {}   # port -> (ts, generation_tokens_total)


def _have_rocm() -> bool:
    return shutil.which("rocm-smi") is not None


def _rocm_gpus() -> list[dict]:
    """Parse `rocm-smi --showmeminfo vram --showuse --showpower --showtemp --json`."""
    try:
        out = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--showuse", "--showpower",
             "--showtemp", "--json"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        raw = json.loads(out)
    except Exception as exc:  # noqa: BLE001 — telemetry must never crash the agent
        return [{"index": g, "error": str(exc)} for g in NODE_GPUS]
    gpus = []
    for key, card in raw.items():
        if not key.lower().startswith("card"):
            continue
        idx = int("".join(ch for ch in key if ch.isdigit()) or 0)

        def _num(*names: str) -> float:
            for n in names:
                for k, v in card.items():
                    if n.lower() in k.lower():
                        try:
                            return float(str(v).split()[0])
                        except (ValueError, IndexError):
                            pass
            return 0.0

        used = _num("VRAM Total Used Memory", "Used Memory") / 1e9
        total = _num("VRAM Total Memory", "Total Memory") / 1e9
        gpus.append({
            "index": idx,
            "vram_used_gb": round(used, 1),
            "vram_total_gb": round(total, 1) or 192.0,
            "util_pct": _num("GPU use (%)", "GPU use"),
            "power_w": _num("Average Graphics Package Power", "Current Socket Graphics Package Power"),
            "temp_c": _num("Temperature (Sensor edge)", "Temperature (Sensor junction)"),
        })
    return gpus or [{"index": g, "vram_used_gb": 0.0, "vram_total_gb": 192.0,
                     "util_pct": 0.0, "power_w": 0.0, "temp_c": 0.0} for g in NODE_GPUS]


def _scrape_vllm(port: int) -> dict:
    """Scrape a vLLM /metrics (Prometheus text) endpoint on localhost."""
    running = waiting = tokens_total = 0.0
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/metrics", timeout=3) as r:
            for line in r.read().decode().splitlines():
                if line.startswith("#") or " " not in line:
                    continue
                name, _, val = line.rpartition(" ")
                try:
                    fval = float(val)
                except ValueError:
                    continue
                if name.startswith("vllm:num_requests_running"):
                    running = fval
                elif name.startswith("vllm:num_requests_waiting"):
                    waiting = fval
                elif name.startswith("vllm:generation_tokens_total"):
                    tokens_total += fval
    except Exception:  # noqa: BLE001 — instance may be warming up
        return {"port": port, "up": False, "running": 0, "waiting": 0, "tokens_per_s": 0.0}
    now = time.time()
    tps = 0.0
    if port in _prev_tokens:
        pts, ptok = _prev_tokens[port]
        dt = now - pts
        if dt > 0:
            tps = max(0.0, (tokens_total - ptok) / dt)
    _prev_tokens[port] = (now, tokens_total)
    return {"port": port, "up": True, "running": int(running),
            "waiting": int(waiting), "tokens_per_s": round(tps, 1)}


def build_telemetry() -> dict:
    """The canonical telemetry payload (matches the backend stub shape)."""
    rocm = _have_rocm()
    if rocm:
        gpus = _rocm_gpus()
        vllm = [dict(_scrape_vllm(int(e.split("@")[1])), served_model_name=e.split("@")[0])
                for e in VLLM_ENDPOINTS if "@" in e]
    else:  # dev / synthetic — SAME SHAPE as production
        gpus = [{"index": g, "vram_used_gb": 92.0, "vram_total_gb": 192.0,
                 "util_pct": 68.0, "power_w": 465.0, "temp_c": 61.0} for g in NODE_GPUS]
        vllm = [{"served_model_name": e.split("@")[0], "port": int(e.split("@")[1]),
                 "up": True, "running": 2, "waiting": 0, "tokens_per_s": 220.0}
                for e in VLLM_ENDPOINTS if "@" in e]
    return {"node": NODE_NAME, "ts": time.time(), "mode": "rocm" if rocm else "synthetic",
            "gpus": gpus, "vllm": vllm}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "mode": "rocm" if _have_rocm() else "synthetic"}


@app.get("/telemetry")
def telemetry() -> dict:
    return build_telemetry()


def register() -> None:
    """Self-register with the control plane (best-effort)."""
    ip = os.getenv("NODE_IP") or socket.gethostbyname(socket.gethostname())
    body = json.dumps({"name": NODE_NAME, "ip": ip, "gpus": NODE_GPUS}).encode()
    req = urllib.request.Request(
        f"{CONTROL_PLANE_URL}/api/admin/nodes/register", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {ADMIN_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"[node-agent] registered node {NODE_NAME} -> {r.status}")
    except Exception as exc:  # noqa: BLE001
        print(f"[node-agent] registration failed (non-fatal): {exc}")


@app.on_event("startup")
def _startup() -> None:
    register()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("NODE_AGENT_PORT", "9100")))
