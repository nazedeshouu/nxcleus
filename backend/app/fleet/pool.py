"""Worker pool member selection — capability-aware routing inside a pooled seat (02 §7.4, D12).

Deterministic argmax over capability flags; ties -> least-loaded -> round-robin; no positive score ->
any healthy member. The decision is recorded in the `task.started` payload so the BoM panel shows not
just which model built a module but *why*.
"""
from __future__ import annotations

from itertools import count

from app.models.registry import Binding, registry

_SCORE = {"strong": 2, "ok": 1, "weak": -2}

# fallback flag hints for the built-in coder pool when infra/models.yaml is absent (02 §11 catalog)
_BUILTIN_FLAGS: dict[str, dict[str, str]] = {
    "qwen3-coder-next": {"greenfield-codegen": "strong", "refactor-edit": "ok", "test-writing": "ok"},
    "devstral-small-2": {"refactor-edit": "strong", "greenfield-codegen": "ok"},
    "qwen36-27b": {"sql-data": "strong", "math": "ok", "greenfield-codegen": "ok"},
}

_rr = count()


def _flags_for(model: str) -> dict[str, str]:
    entry = registry.models.get(model)
    if entry and isinstance(entry.get("flags"), dict):
        return entry["flags"]
    return _BUILTIN_FLAGS.get(model, {})


def pick_member(pool: list[Binding], task_flags: list[str], load: dict[str, int]) -> tuple[Binding, dict]:
    if not pool:
        raise ValueError("empty coder pool")
    scored = []
    for b in pool:
        flags = _flags_for(b.model)
        score = sum(_SCORE.get(flags.get(f, "absent"), 0) for f in task_flags)
        scored.append((score, load.get(b.model, 0), b))
    best = max(s[0] for s in scored)
    if best <= 0 and task_flags:
        # no positive score -> round-robin (never block on routing)
        chosen = pool[next(_rr) % len(pool)]
        return chosen, {"flags": task_flags, "chosen": chosen.model, "score": 0,
                        "considered": [b.model for b in pool], "reason": "round-robin (no flag match)"}
    top = [t for t in scored if t[0] == best]
    top.sort(key=lambda t: t[1])   # least-loaded first
    chosen = top[0][2]
    return chosen, {"flags": task_flags, "chosen": chosen.model, "score": best,
                    "considered": [b.model for b in pool], "reason": "capability argmax"}
