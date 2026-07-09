#!/usr/bin/env python3
"""Render a docker-compose.yml for a fleet profile (one vLLM service per instance).

Reads infra/models.yaml + infra/fleet.yaml, resolves each instance's hf_id and serving
flags, and emits a compose file that bootstrap.sh brings up with `docker compose up -d`.
Runs on any machine (no GPUs needed) so bootstrap.sh --dry-run can validate the launch
plan on this Mac.

Usage:  render_compose.py --profile P2 [--out docker-compose.gen.yml]
                          [--control-plane-url URL] [--image IMG]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]      # repo root
INFRA = ROOT / "infra"
# MI300X == gfx942 (CDNA3), which AMD publishes under the gfx94X-dcgpu (datacenter) family tag.
# The literal `gfx942` tag does NOT exist on Docker Hub; verified 2026-07-09 (rocm/vllm registry:
# HTTP 404 for gfx942, HTTP 200 for gfx94X-dcgpu on the same rocm7.13.0/vllm0.19.1 train).
DEFAULT_IMAGE = "rocm/vllm:rocm7.13.0_gfx94X-dcgpu_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1"


def render(profile: str, image: str, control_plane_url: str) -> str:
    models = yaml.safe_load((INFRA / "models.yaml").read_text())["models"]
    fleet = yaml.safe_load((INFRA / "fleet.yaml").read_text())
    prof = fleet["profiles"].get(profile)
    if prof is None:
        raise SystemExit(f"unknown profile {profile!r} (have: {list(fleet['profiles'])})")

    services: dict[str, dict] = {}
    endpoints: list[str] = []
    all_gpus: set[int] = set()
    prev_vllm: str | None = None   # for the sequential-start depends_on chain (see below)

    for inst in prof.get("instances", []) or []:
        mk = inst["model"]
        model = models[mk]
        hf_id = inst.get("hf_id_override") or model["hf_id"]
        served = inst["served_model_name"]
        port = inst["port"]
        gpus = inst.get("gpus", [])
        all_gpus.update(gpus)
        endpoints.append(f"{served}@{port}")

        cmd = [
            "vllm", "serve", hf_id,
            "--served-model-name", served,
            "--port", str(port),
            "--host", "0.0.0.0",
            "--tensor-parallel-size", str(inst.get("tensor_parallel_size", 1)),
            "--max-model-len", str(inst["max_model_len"]),
            "--gpu-memory-utilization", str(inst["gpu_memory_utilization"]),
            "--trust-remote-code",
        ]
        if inst.get("quantization") and inst["quantization"] != "none":
            cmd += ["--quantization", inst["quantization"]]
        if inst.get("dtype"):
            cmd += ["--dtype", inst["dtype"]]
        # --enforce-eager skips cudagraph capture: less VRAM overhead + faster startup. Needed when
        # several instances share one GPU (first-boot tuning, D14/O4) — the capture overhead pushed
        # the P1 A-trio past the 0.90 util sum into KV-cache OOM (live-verified 2026-07-09).
        if inst.get("enforce_eager"):
            cmd += ["--enforce-eager"]

        services[f"vllm-{inst['name']}"] = {
            "image": image,
            "container_name": f"vllm-{inst['name']}",
            "restart": "unless-stopped",
            # ROCm device + IPC requirements for MI300X.
            "devices": ["/dev/kfd", "/dev/dri"],
            "security_opt": ["seccomp=unconfined"],
            # Only "video" — the container image's /etc/group has no "render" entry (name-based
            # group_add resolves against the CONTAINER's group file), so "render" fails to start.
            # The container runs as root, which owns /dev/kfd, so "video" (for /dev/dri) suffices.
            # Live-verified on gpu-amd-base (MI300X VF): torch.cuda.is_available()==True (2026-07-09).
            "group_add": ["video"],
            "ipc": "host",
            "shm_size": "16gb",
            "ports": [f"{port}:{port}"],
            "volumes": ["/data/hf-cache:/root/.cache/huggingface"],
            "environment": {
                "HIP_VISIBLE_DEVICES": ",".join(str(g) for g in gpus),
                "ROCR_VISIBLE_DEVICES": ",".join(str(g) for g in gpus),
                "HF_TOKEN": "${HF_TOKEN}",
                "VLLM_USE_TRITON_FLASH_ATTN": "0",
            },
            "command": cmd,
            "healthcheck": {
                "test": ["CMD", "python3", "-c",
                         f"import urllib.request;urllib.request.urlopen('http://localhost:{port}/health')"],
                "interval": "30s", "timeout": "5s", "retries": 40, "start_period": "600s",
            },
        }
        # Sequential start: each vLLM waits for the previous to be HEALTHY before loading. vLLM
        # profiles GPU memory GLOBALLY, so co-located instances starting concurrently over-commit
        # and hit KV-cache OOM (live-verified 2026-07-09). Chaining on service_healthy serializes
        # the loads so each measures free VRAM accurately.
        svc = f"vllm-{inst['name']}"
        if prev_vllm is not None:
            services[svc]["depends_on"] = {prev_vllm: {"condition": "service_healthy"}}
        prev_vllm = svc

    # node-agent as a slim-python sidecar (no image build needed — public amd64 base).
    services["node-agent"] = {
        "image": "python:3.12-slim",
        "container_name": "nxcleus-node-agent",
        "restart": "unless-stopped",
        "network_mode": "host",     # scrape localhost vLLM /metrics + reach control plane
        "volumes": [f"{INFRA}/droplet/node-agent:/agent:ro"],
        "working_dir": "/agent",
        "environment": {
            "NODE_NAME": "${NODE_NAME:-B}",
            "NODE_GPUS": ",".join(str(g) for g in sorted(all_gpus)) or "0",
            "CONTROL_PLANE_URL": control_plane_url,
            "ADMIN_TOKEN": "${ADMIN_TOKEN}",
            "VLLM_ENDPOINTS": ",".join(endpoints),
            "NODE_AGENT_PORT": "9100",
        },
        "command": ["sh", "-c",
                    "pip install --no-cache-dir -r requirements.txt && "
                    "python -m uvicorn agent:app --host 0.0.0.0 --port 9100"],
    }

    return yaml.safe_dump({"services": services}, sort_keys=False, width=120)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="P2")
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--control-plane-url", default="http://localhost:8080")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()
    text = render(args.profile, args.image, args.control_plane_url)
    if args.out == "-":
        sys.stdout.write(text)
    else:
        pathlib.Path(args.out).write_text(text)
        print(f"wrote {args.out} ({text.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
