"""Backend adapters behind one interface (02 §2.2).

Four thin clients returning `(text, parsed, usage)`:
- `VllmClient`, `FireworksClient` — OpenAI-compatible `/v1/chat/completions` via the shared
  egress-wrapped httpx client (01 §3).
- `AnthropicClient` — official SDK, handed the same httpx client so every byte leaves through one place.
- `MockClient` — deterministic, schema-valid completions for dev/CI. Reads canned-by-seat fixtures
  from `scripts/fixtures/` so the mock pipeline produces coherent artifacts; synthesizes a minimal
  valid instance from the JSON schema otherwise. Supports a one-shot invalid response to exercise the
  router's repair round.

Structured output (02 §2.1): vLLM guided decoding (`response_format: json_schema`); Fireworks JSON
mode + schema in the prompt; Anthropic tool-call with the schema as the tool input schema.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from app.boundary.egress import http_client
from app.config import REPO_ROOT

FIXTURES_DIR = REPO_ROOT / "scripts" / "fixtures"
_FIXTURE_RE = re.compile(r"\[\[fixture:([A-Za-z0-9_./-]+)\]\]")
_INVALID_ONCE = "[[mock_invalid_once]]"


@dataclass
class ClientResult:
    text: str
    parsed: dict | None
    usage: dict


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _messages_text(messages: list[dict]) -> str:
    return "\n".join(m.get("content", "") for m in messages)


# ------------------------------------------------------------------ JSON-schema synthesis (mock)
def synthesize(schema: dict) -> object:
    """Build a minimal instance that satisfies `schema` (deterministic)."""
    if not isinstance(schema, dict):
        return None
    # resolve a couple of common composed forms
    if "anyOf" in schema or "oneOf" in schema:
        opts = schema.get("anyOf") or schema.get("oneOf")
        return synthesize(opts[0]) if opts else None
    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0])
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = schema.get("required", [])   # absent 'required' => nothing required (minimal instance)
        return {k: synthesize(v) for k, v in props.items() if k in required}
    if t == "array":
        items = schema.get("items", {})
        return [synthesize(items)] if items and schema.get("minItems", 0) > 0 else []
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    if t == "string":
        return ""
    if t == "null":
        return None
    return {}


def _break_instance(instance: object, schema: dict) -> object:
    """Return a deliberately schema-invalid variant (drop a required key) for the repair-round test."""
    if isinstance(instance, dict):
        required = schema.get("required") or list((schema.get("properties") or {}).keys())
        if required:
            bad = dict(instance)
            bad.pop(required[0], None)
            return bad
    return "not-an-object"


# ------------------------------------------------------------------ Mock
class MockClient:
    backend = "mock"

    async def complete(
        self, messages: list[dict], *, model: str, schema: dict | None = None,
        temperature: float | None = None, max_tokens: int | None = None,
        timeout: float | None = None, stream=None, seat: str = "", **_,
    ) -> ClientResult:
        text_in = _messages_text(messages)
        tokens_in = _estimate_tokens(text_in)
        is_repair = any(m.get("role") == "assistant" for m in messages)

        if schema is not None:
            parsed = self._structured(text_in, schema, seat, is_repair)
            body = json.dumps(parsed)
            if stream is not None:
                await stream(body)
            return ClientResult(body, parsed, {"tokens_in": tokens_in, "tokens_out": _estimate_tokens(body)})

        # free text — deterministic English, clearly mock
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        text = f"[mock:{seat or model}] acknowledged. English-only output. Re: {last_user[:160]}".strip()
        if stream is not None:
            await stream(text)
        return ClientResult(text, None, {"tokens_in": tokens_in, "tokens_out": _estimate_tokens(text)})

    def _structured(self, text_in: str, schema: dict, seat: str, is_repair: bool) -> dict:
        # one-shot invalid to drive the router's repair round: invalid on the first (no assistant
        # turn) attempt, valid once the repair round appends its correction message. Stateless.
        if _INVALID_ONCE in text_in and not is_repair:
            return _break_instance(self._resolve(text_in, schema, seat), schema)  # type: ignore
        return self._resolve(text_in, schema, seat)  # type: ignore

    def _resolve(self, text_in: str, schema: dict, seat: str) -> object:
        m = _FIXTURE_RE.search(text_in)
        if m:
            fp = FIXTURES_DIR / f"{m.group(1)}.json"
            if fp.exists():
                return json.loads(fp.read_text())
        return synthesize(schema)


# ------------------------------------------------------------------ OpenAI-compatible (vLLM / Fireworks)
class _OpenAICompatClient:
    backend = "openai-compat"

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _response_format(self, schema: dict | None) -> dict | None:  # overridden per backend
        return None

    async def complete(
        self, messages: list[dict], *, model: str, schema: dict | None = None,
        temperature: float | None = None, max_tokens: int | None = None,
        timeout: float | None = None, stream=None, seat: str = "", **_,
    ) -> ClientResult:
        payload: dict = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        rf = self._response_format(schema)
        if rf:
            payload["response_format"] = rf
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = f"{self.base_url}/v1/chat/completions"
        # ponytail: read window = the seat's timeout_s (external reasoning seats like the planner
        # carry 300s in seats.yaml; a bare float would also stretch connect to 300s). Keep connect
        # short so a dead host fails fast instead of hanging the whole read window.
        to = httpx.Timeout(timeout or 120.0, connect=10.0)
        resp = await http_client.post(url, json=payload, headers=headers, timeout=to)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage_raw = data.get("usage", {})
        usage = {"tokens_in": usage_raw.get("prompt_tokens", _estimate_tokens(_messages_text(messages))),
                 "tokens_out": usage_raw.get("completion_tokens", _estimate_tokens(text))}
        parsed = _parse_json(text) if schema is not None else None
        return ClientResult(text, parsed, usage)


class VllmClient(_OpenAICompatClient):
    backend = "local"

    def _response_format(self, schema: dict | None) -> dict | None:
        if schema is None:
            return None
        return {"type": "json_schema", "json_schema": {"name": "artifact", "schema": schema}}


class FireworksClient(_OpenAICompatClient):
    backend = "fireworks"

    def _response_format(self, schema: dict | None) -> dict | None:
        # Fireworks: JSON mode; schema is also injected into the prompt by the router/seat
        return {"type": "json_object"} if schema is not None else None


# ------------------------------------------------------------------ Anthropic (official SDK)
class AnthropicClient:
    backend = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        from anthropic import AsyncAnthropic

        kw = {"api_key": api_key, "http_client": http_client}
        if base_url:                       # BYOK anthropic-style endpoint (custom base_url)
            kw["base_url"] = base_url
        self._client = AsyncAnthropic(**kw)

    async def complete(
        self, messages: list[dict], *, model: str, schema: dict | None = None,
        temperature: float | None = None, max_tokens: int | None = None,
        timeout: float | None = None, stream=None, seat: str = "", **_,
    ) -> ClientResult:
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        turns = [{"role": m["role"], "content": m["content"]}
                 for m in messages if m.get("role") in ("user", "assistant")]
        kwargs: dict = {
            "model": model, "messages": turns or [{"role": "user", "content": ""}],
            "max_tokens": max_tokens or 4096,
        }
        # `system` only when non-empty: passing system=None 400s ("system: Input should be a valid
        # array") on the Fable 5 family; a string system is fine. `temperature` is REJECTED on
        # claude-fable-5 / opus-4.8 / 4.7 ("temperature is deprecated for this model"), so the
        # param is accepted for interface parity with the OpenAI-compat clients but never sent.
        if system:
            kwargs["system"] = system
        if schema is not None:
            kwargs["tools"] = [{"name": "emit_artifact",
                                "description": "Return the artifact matching the schema.",
                                "input_schema": schema}]
            kwargs["tool_choice"] = {"type": "tool", "name": "emit_artifact"}

        # Refusal safety net for the single external, demo-critical seat: Fable/Mythos may decline
        # (stop_reason="refusal"); a server-side fallback to Opus 4.8 rescues it in one round trip.
        if model.startswith(("claude-fable", "claude-mythos")):
            msg = await self._client.beta.messages.create(
                **kwargs, betas=["server-side-fallback-2026-06-01"],
                fallbacks=[{"model": "claude-opus-4-8"}],
            )
        else:
            msg = await self._client.messages.create(**kwargs)

        if getattr(msg, "stop_reason", None) == "refusal":
            cat = getattr(getattr(msg, "stop_details", None), "category", None)
            raise ValueError(f"seat {seat!r} request refused by safety classifier (category={cat})")
        usage = {"tokens_in": msg.usage.input_tokens, "tokens_out": msg.usage.output_tokens}
        if schema is not None:
            tool_use = next((b for b in msg.content if getattr(b, "type", None) == "tool_use"), None)
            parsed = tool_use.input if tool_use else None
            return ClientResult(json.dumps(parsed), parsed, usage)
        text = "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", None) == "text")
        return ClientResult(text, None, usage)


def _parse_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None


# single mock instance (holds the invalid-once memory)
mock_client = MockClient()
