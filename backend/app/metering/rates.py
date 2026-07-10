"""Rates config loader (10 §3). Reads `infra/rates.yaml` over built-in defaults.

Token prices are placeholders until the Day-1 price sheet lands (spec 10 §3 TODO); local tokens are
priced as GPU-seconds, not per-token (10 §2). The invoice footnote states the GPU estimate is an
approximation — regulated-enterprise honesty is on-brand.
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from app.config import settings

_DEFAULTS: dict = {
    "gpu": {"mi300x_hour_usd": 2.00},
    "backends": {
        # $/Mtok — placeholders pending the Day-1 price sheet (10 §3)
        "anthropic": {
            "claude-fable-5": {"in_per_mtok": 3.0, "out_per_mtok": 15.0},
            "default": {"in_per_mtok": 3.0, "out_per_mtok": 15.0},
        },
        "openrouter": {   # flagship + gpt-5.5 fallback — catalogue-verified 2026-07-10/11
            "openai/gpt-5.6-sol": {"in_per_mtok": 5.0, "out_per_mtok": 30.0},
            "openai/gpt-5.5": {"in_per_mtok": 5.0, "out_per_mtok": 30.0},
            "default": {"in_per_mtok": 5.0, "out_per_mtok": 30.0},
        },
        "openai": {   # no builtin models; kept for direct bindings — UNVERIFIED placeholder
            "default": {"in_per_mtok": 10.0, "out_per_mtok": 50.0},
        },
        "fireworks": {
            "default": {"in_per_mtok": 0.90, "out_per_mtok": 0.90},
        },
        "local": {"default": {"in_per_mtok": 0.0, "out_per_mtok": 0.0}},
        "custom": {"default": {"in_per_mtok": 0.0, "out_per_mtok": 0.0}},
        "mock": {"default": {"in_per_mtok": 0.0, "out_per_mtok": 0.0}},
    },
    "margin": 0.0,
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache
def load_rates() -> dict:
    path = settings.config_path("rates")
    if path:
        try:
            data = yaml.safe_load(path.read_text()) or {}
            return _deep_merge(_DEFAULTS, data)
        except Exception as exc:
            # stale built-in prices silently billing the money slide would be a demo lie — say it
            import sys
            print(f"[rates] WARNING: {path} unreadable ({type(exc).__name__}: {exc}); "
                  f"using built-in rate card", file=sys.stderr)
    return dict(_DEFAULTS)


def token_rate(backend: str, model: str) -> tuple[float, float]:
    rates = load_rates()["backends"].get(backend, {})
    entry = rates.get(model) or rates.get("default") or {"in_per_mtok": 0.0, "out_per_mtok": 0.0}
    return entry["in_per_mtok"], entry["out_per_mtok"]


def gpu_hour_usd() -> float:
    return float(load_rates()["gpu"]["mi300x_hour_usd"])
