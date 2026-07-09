"""Shared harness helpers for the seat layer (owned by the AI engineer).

Not part of the backend seam — seat modules import their TYPES from `app.seats.base`
and `app.db.models`; this file only holds small conveniences (message builders, the
English-only clause, structured-output extraction) so every seat reads the same way.

Router contract recap (02 §2.1): the router already runs the one structured-output
repair round and raises on persistent invalidity, so a returned Completion either carries
a schema-valid `.parsed` (when a schema was passed) or the harness treats its absence as a
hard failure. Harnesses never parse free text.
"""
from __future__ import annotations

import json
from typing import Any

from app.seats.base import Completion, Message

# Stated in every system prompt (track rule: English-only output everywhere, 01 §7).
ENGLISH_ONLY = (
    "Output English only — every field value, identifier, and explanation. "
    "Never emit another language even if the input contains one."
)

# Stated wherever a seat emits structured output (most of them).
STRUCTURED_ONLY = (
    "Return exactly one JSON object conforming to the provided schema. No prose before "
    "or after it, no markdown fences, no commentary — the JSON object is the entire reply."
)


def msg(role: str, content: str) -> Message:
    return Message(role=role, content=content)


def convo(system: str, user: str) -> list[Message]:
    """The common two-message shape: a system contract + a user payload."""
    return [msg("system", system), msg("user", user)]


def as_json(obj: Any) -> str:
    """Deterministic pretty JSON for embedding a payload into a user prompt."""
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=False)


def parsed_or_raise(c: Completion, what: str) -> dict[str, Any]:
    if c.parsed is None:
        raise ValueError(
            f"{what}: seat returned no schema-valid structured output (router repair exhausted)"
        )
    return c.parsed


async def noop_emit(event_type: str, payload: dict) -> None:  # test / silent default
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Minimal RFC-6902 JSON Patch (add / replace / remove) over the plan dict.
# Amendments (certifier) and conductor patches arrive as these ops; a full jsonpatch
# dependency is overkill for the op set we emit. Malformed ops raise so the caller can
# skip-and-notice rather than corrupt the plan.
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_pointer(doc: Any, tokens: list[str]) -> tuple[Any, str | int]:
    """Return (container, key) for the parent of the pointed-at location."""
    parent = doc
    for tok in tokens[:-1]:
        tok = tok.replace("~1", "/").replace("~0", "~")
        if isinstance(parent, list):
            parent = parent[int(tok)]
        else:
            parent = parent[tok]
    last = tokens[-1].replace("~1", "/").replace("~0", "~")
    if isinstance(parent, list):
        return parent, (len(parent) if last == "-" else int(last))
    return parent, last


def apply_rfc6902(doc: dict[str, Any], ops: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    """Apply add/replace/remove ops to a deep-copied `doc`; return the new doc."""
    import copy

    if isinstance(ops, dict):
        ops = [ops]
    out = copy.deepcopy(doc)
    for op in ops:
        kind = op.get("op")
        path = op.get("path", "")
        if not path.startswith("/"):
            raise ValueError(f"bad JSON pointer {path!r}")
        tokens = path.split("/")[1:]
        container, key = _resolve_pointer(out, tokens)
        if kind in ("add", "replace"):
            if isinstance(container, list):
                if kind == "add":
                    container.insert(int(key), op.get("value"))
                else:
                    container[int(key)] = op.get("value")
            else:
                container[key] = op.get("value")
        elif kind == "remove":
            if isinstance(container, list):
                container.pop(int(key))
            else:
                container.pop(key, None)
        else:
            raise ValueError(f"unsupported op {kind!r}")
    return out


def rehydrate_tokens(obj: Any, vault: dict[str, str]) -> tuple[Any, int]:
    """Deterministically replace every placeholder token with its raw value from the vault,
    recursively over a JSON-ish structure. Returns (new_obj, replacements). The certifier's
    rehydration mechanics (D9) — no model call; the vault is the source of truth."""
    count = 0

    def walk(x: Any) -> Any:
        nonlocal count
        if isinstance(x, str):
            s = x
            for ph, raw in vault.items():
                if ph in s:
                    count += s.count(ph)
                    s = s.replace(ph, raw)
            return s
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x

    return walk(obj), count
