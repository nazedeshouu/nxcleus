#!/usr/bin/env python3
"""Standalone validator for the Nxcleus infra YAMLs (models / seats / fleet / rates).

Cross-checks (Wave-1 DoD):
  * every seats.yaml binding `model` resolves to a models.yaml key (no dangling keys);
  * every fleet.yaml instance `model` resolves to a models.yaml key;
  * node-A packing sums <= 192 GB with >=60 GB headroom (reported);
  * per shared GPU, gpu_memory_utilization sums <= 0.90 (no VRAM over-subscription);
  * seat data_class vs binding zone sanity (RAW never bound to anthropic/EXTERNAL);
  * rates.yaml references known backends.

Run:  uv run --with pyyaml infra/validate_config.py
Exit non-zero on any hard error; warnings are printed but don't fail.
"""
from __future__ import annotations

import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
MI300X_GB = 192.0
NODE_A_HEADROOM_MIN_GB = 60.0

PROVIDER_ZONE = {"local": "LOCAL", "fireworks": "AMD_HOSTED", "anthropic": "EXTERNAL"}


def load(name: str) -> dict:
    with open(HERE / name) as fh:
        return yaml.safe_load(fh)


def iter_bindings(binding):
    """Yield each concrete {backend, model, ...} mapping from a binding value.

    A binding may be a single mapping, a list (pool), or the string "default"/"pool"
    (an alias resolved elsewhere)."""
    if binding is None or isinstance(binding, str):
        return
    if isinstance(binding, list):
        for b in binding:
            if isinstance(b, dict):
                yield b
        return
    if isinstance(binding, dict):
        yield binding


def main() -> int:
    models = load("models.yaml")["models"]
    seats = load("seats.yaml")["seats"]
    fleet = load("fleet.yaml")
    rates = load("rates.yaml")

    errors: list[str] = []
    warnings: list[str] = []
    model_keys = set(models)

    # ── seats.yaml: every binding model resolves; zone vs data_class sanity ───────
    for seat, cfg in seats.items():
        dc_max = cfg.get("data_class_max")
        for slot, binding in cfg.get("bindings", {}).items():
            for b in iter_bindings(binding):
                mk = b.get("model")
                if mk not in model_keys:
                    errors.append(f"seats.{seat}.bindings.{slot}: dangling model key {mk!r}")
                    continue
                backend = b.get("backend")
                zone = PROVIDER_ZONE.get(backend)
                if zone is None:
                    errors.append(f"seats.{seat}.bindings.{slot}: unknown backend {backend!r}")
                # RAW seat must never DEFAULT to EXTERNAL; fireworks RAW only under demo exception.
                if dc_max == "RAW" and zone == "EXTERNAL":
                    errors.append(
                        f"seats.{seat}.bindings.{slot}: RAW seat bound to EXTERNAL (boundary violation)"
                    )
                if dc_max == "RAW" and zone == "AMD_HOSTED" and not b.get("demo_exception"):
                    warnings.append(
                        f"seats.{seat}.bindings.{slot}: RAW->AMD_HOSTED without demo_exception flag"
                    )
                # models.yaml provider must agree with the binding backend.
                mp = models[mk].get("provider")
                if mp != backend:
                    errors.append(
                        f"seats.{seat}.bindings.{slot}: backend {backend!r} != models.yaml provider {mp!r} for {mk!r}"
                    )

    # planner hard ceiling
    if seats.get("planner", {}).get("data_class_max") != "SANITIZED":
        errors.append("planner.data_class_max must be SANITIZED (hard ceiling, D7)")

    # ── fleet.yaml: every instance model resolves; per-GPU memory + packing ───────
    for pname, prof in fleet.get("profiles", {}).items():
        gpu_mem: dict[int, float] = {}
        gpu_weights: dict[int, float] = {}
        for inst in prof.get("instances", []) or []:
            mk = inst.get("model")
            if mk not in model_keys:
                errors.append(f"fleet.{pname}: instance {inst.get('name')} dangling model key {mk!r}")
                continue
            util = float(inst.get("gpu_memory_utilization", 0.0))
            gpus = inst.get("gpus", []) or []
            serving = models[mk].get("serving", {})
            vram = float(serving.get("vram_gb", 0.0))
            # An instance may serve a lower precision than the registry default (e.g. the
            # brain runs bf16 in P2 but FP8 in P3 via hf_id_override). FP8 ~= half of bf16.
            if inst.get("quantization") == "fp8" and serving.get("precision") == "bf16":
                vram *= 0.5
            tp = max(1, int(inst.get("tensor_parallel_size", 1)))
            per_gpu_weight = vram / tp if tp else vram
            for g in gpus:
                gpu_mem[g] = gpu_mem.get(g, 0.0) + util
                gpu_weights[g] = gpu_weights.get(g, 0.0) + per_gpu_weight
        for g, tot in sorted(gpu_mem.items()):
            if tot > 0.901:
                errors.append(
                    f"fleet.{pname}: GPU {g} gpu_memory_utilization sums to {tot:.2f} > 0.90 (over-subscribed)"
                )
        for g, w in sorted(gpu_weights.items()):
            if w > MI300X_GB:
                errors.append(
                    f"fleet.{pname}: GPU {g} weights ~{w:.0f} GB exceed {MI300X_GB:.0f} GB card"
                )

    # ── node-A packing check (P2): trust + oracle + inspector on one GPU ──────────
    node_a_models = ["gemma-4-26b-a4b", "gemma-4-31b", "qwen36-35b-a3b"]
    node_a_gb = sum(float(models[m]["serving"]["vram_gb"]) for m in node_a_models)
    headroom = MI300X_GB - node_a_gb
    if node_a_gb > MI300X_GB:
        errors.append(f"node-A packing {node_a_gb:.0f} GB exceeds {MI300X_GB:.0f} GB")
    elif headroom < NODE_A_HEADROOM_MIN_GB:
        warnings.append(
            f"node-A headroom {headroom:.0f} GB < {NODE_A_HEADROOM_MIN_GB:.0f} GB target"
        )

    # ── rates.yaml: backends known ────────────────────────────────────────────────
    for backend in rates.get("backends", {}):
        if backend not in PROVIDER_ZONE:
            warnings.append(f"rates.backends.{backend}: unknown backend")

    # ── report ────────────────────────────────────────────────────────────────────
    print(f"models: {len(models)} entries")
    print(f"seats:  {len(seats)} seats")
    print(f"fleet:  {len(fleet.get('profiles', {}))} profiles")
    print(
        f"node-A packing (P2): {node_a_gb:.0f} GB weights + ~{headroom:.0f} GB KV headroom "
        f"(models: {', '.join(node_a_models)})"
    )
    for w in warnings:
        print(f"WARN  {w}")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"\nFAILED with {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"\nOK — no dangling keys, packing valid. {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
