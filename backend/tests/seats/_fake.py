"""Test doubles for the seat harnesses — a scripted CompleteFn, a collecting emit, and a
dependency-free JSON-Schema structural checker (jsonschema is not in the venv)."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from app.seats.base import Completion


class FakeComplete:
    """Implements the CompleteFn protocol with canned outputs.

    Either pass `responses` (consumed in order) or `handler(seat, messages, schema, idx)->dict`.
    Records every call so tests can assert seat/data_class/temperature/k."""

    def __init__(self, responses: list[dict] | None = None,
                 handler: Callable[[str, list, dict | None, int], dict] | None = None):
        self.responses = list(responses or [])
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, seat, messages, *, data_class, schema=None, stream=None,
                       temperature=None, max_tokens=None) -> Completion:
        idx = len(self.calls)
        self.calls.append({"seat": seat, "data_class": data_class, "temperature": temperature,
                           "schema": schema, "messages": messages})
        if stream is not None:
            await stream("<delta>")
        parsed = self.handler(seat, messages, schema, idx) if self.handler else self.responses.pop(0)
        return Completion(text=json.dumps(parsed, default=str), parsed=parsed,
                          usage={"tokens_in": 10, "tokens_out": 20})

    def seats_used(self) -> list[str]:
        return [c["seat"] for c in self.calls]

    def data_classes_for(self, seat: str) -> set[str]:
        return {c["data_class"] for c in self.calls if c["seat"] == seat}


class Emits(list):
    """Collecting EmitFn: stores (event_type, payload) tuples."""

    async def __call__(self, event_type: str, payload: dict) -> None:
        self.append((event_type, payload))

    def types(self) -> list[str]:
        return [t for t, _ in self]

    def payload(self, event_type: str) -> dict:
        for t, p in self:
            if t == event_type:
                return p
        raise KeyError(event_type)


def run(coro):
    """Drive an async harness from a sync test — no pytest-asyncio needed."""
    return asyncio.run(coro)


_SCALAR = {"string", "number", "integer", "boolean", "object", "array", "null"}


def is_valid_json_schema(s: Any, path: str = "$") -> list[str]:
    """Structural JSON-Schema validity check (catches typos without a jsonschema dependency).
    Returns a list of problems; empty == valid."""
    problems: list[str] = []
    if not isinstance(s, dict):
        return [f"{path}: schema node is not an object"]
    if "type" in s:
        t = s["type"]
        types = t if isinstance(t, list) else [t]
        for tt in types:
            if tt not in _SCALAR:
                problems.append(f"{path}.type: unknown type {tt!r}")
    if "enum" in s and not isinstance(s["enum"], list):
        problems.append(f"{path}.enum: must be a list")
    if "properties" in s:
        if not isinstance(s["properties"], dict):
            problems.append(f"{path}.properties: must be an object")
        else:
            for k, v in s["properties"].items():
                problems += is_valid_json_schema(v, f"{path}.properties.{k}")
    if "items" in s and isinstance(s["items"], dict):
        problems += is_valid_json_schema(s["items"], f"{path}.items")
    if "required" in s:
        req = s["required"]
        if not isinstance(req, list):
            problems.append(f"{path}.required: must be a list")
        elif "properties" in s and isinstance(s["properties"], dict):
            for r in req:
                if r not in s["properties"]:
                    problems.append(f"{path}.required: {r!r} not in properties")
    # pydantic-emitted schemas use $defs/$ref — accept them as valid nodes.
    for defs in ("$defs", "definitions"):
        if defs in s and isinstance(s[defs], dict):
            for k, v in s[defs].items():
                problems += is_valid_json_schema(v, f"{path}.{defs}.{k}")
    return problems
