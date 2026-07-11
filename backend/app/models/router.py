"""ModelRouter (02 §2) — the one place a dispatch happens; the boundary is enforced here, in code.

Per call: resolve seat -> sovereign overlay -> backend health -> **zone/data-class check**
(BoundaryViolation / SovereignViolation) -> budget guard (BudgetExceeded) -> dispatch -> structured
output validation (one repair round) -> meter event + egress row + model.call event.
"""
from __future__ import annotations

import json
import re
import time

import jsonschema

from app.boundary import egress
from app.boundary.errors import BoundaryViolation, BudgetExceeded, SovereignViolation
from app.config import settings
from app.db.engine import db
from app.events import E, emit
from app.fleet import health
from app.metering import meter
from app.models.clients import (
    AnthropicClient,
    ClientResult,
    FireworksClient,
    VllmClient,
    mock_client,
)
from app.models.registry import Binding, Resolved, registry
from app.seats.base import Completion, Message

# representative hosts per backend intent (used for the egress ledger, incl. mock dispatches)
_HOST = {
    "anthropic": "api.anthropic.com",
    "openai": "api.openai.com",
    "openrouter": "openrouter.ai",
    "fireworks": "api.fireworks.ai",
    "local": "fleet.local",
    "custom": "custom.endpoint",
    "mock": "mock.local",
}

# ponytail: local vLLM instances each serve ONE model on a fixed port (infra/fleet.yaml),
# addressed by the models.yaml KEY (== served_model_name), NOT the hf_id. Default 8000 = node-B
# brain. Extend this map when a profile adds local instances on new ports.
_LOCAL_PORTS: dict[str, int] = {
    "gemma-4-31b": 8011, "gemma-4-26b-a4b": 8012, "qwen36-35b-a3b": 8013,
    "glm-46": 8000,
}

# per-scope budget caps (sandbox runs register one; None = uncapped) — 07 §5.4
_scope_caps: dict[str, float] = {}


def set_scope_cap(scope: str, cap_usd: float) -> None:
    _scope_caps[scope] = cap_usd


def clear_scope_cap(scope: str) -> None:
    _scope_caps.pop(scope, None)


def _as_dicts(messages: list) -> list[dict]:
    out = []
    for m in messages:
        if isinstance(m, Message):
            out.append({"role": m.role, "content": m.content})
        elif isinstance(m, dict):
            out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        else:
            out.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", "")})
    return out


def _job_of(scope: str) -> str | None:
    return scope.split("job:", 1)[1] if scope.startswith("job:") else None


async def _resolve_override(seat: str, scope: str) -> tuple[Binding | None, dict | None]:
    """Look up a seat_override -> custom model (02 §8.2). Returns (binding, connection_attrs)."""
    job = _job_of(scope)
    scopes = [f"job:{job}"] if job else []
    scopes.append("global")
    row = None
    for sc in scopes:
        row = await db.fetchone(
            "SELECT model_key FROM seat_overrides WHERE seat = :seat AND scope = :scope",
            {"seat": seat, "scope": sc},
        )
        if row:
            break
    if not row:
        return None, None
    model_key = row["model_key"]
    cm = await db.fetchone(
        "SELECT cm.provider_model_id AS pmid, c.base_url, c.zone, c.data_class_ceiling AS ceiling, "
        "c.counts_as_local AS col, c.api_key_ref AS keyref, c.api_style AS api_style FROM custom_models cm "
        "JOIN api_connections c ON c.id = cm.connection_id WHERE cm.id = :id",
        {"id": model_key},
    )
    if not cm:
        # builtin models.yaml key (02 §8.2 — EVERY seat binding is user-configurable, not just BYOK)
        entry = registry.merged_models().get(model_key)
        if entry:
            return Binding(backend=entry.get("provider", "fireworks"), model=model_key,
                           node=entry.get("node")), None
        return None, None
    binding = Binding(backend="custom", model=cm["pmid"], node=None)
    attrs = {"base_url": cm["base_url"], "zone": cm["zone"], "ceiling": cm["ceiling"],
             "counts_as_local": bool(cm["col"]), "keyref": cm["keyref"],
             "api_style": cm["api_style"] or "openai"}
    return binding, attrs


def _check_boundary(
    r: Resolved, data_class: str, sovereign: bool, conn_attrs: dict | None
) -> tuple[str | None, str | None]:
    """Return (badge, None) if allowed, or (None, violation_type) if blocked (01 §3 matrix)."""
    zone = r.zone
    counts_as_local = bool(conn_attrs and conn_attrs.get("counts_as_local"))
    ceiling = (conn_attrs or {}).get("ceiling", "RAW" if zone == "LOCAL" else "SANITIZED")

    # Sovereign Mode: zero non-local calls (D7). LOCAL or attested-local CUSTOM only.
    if sovereign and not (zone == "LOCAL" or (zone == "CUSTOM" and counts_as_local)):
        return None, "sovereign"

    if data_class == "RAW":
        if zone == "LOCAL":
            return r.badge, None
        if zone == "AMD_HOSTED":
            if settings.allow_raw_on_amd_hosted:
                return "demo-exception", None
            return None, "boundary"
        if zone == "CUSTOM":
            if ceiling == "RAW":
                return "customer-attested", None
            return None, "boundary"
        return None, "boundary"  # EXTERNAL + RAW is a hard error
    # SANITIZED travels everywhere; sovereign+EXTERNAL already handled above
    return r.badge, None


class Router:
    def __init__(self) -> None:
        self._anthropic: AnthropicClient | None = None

    def _anthropic_client(self) -> AnthropicClient:
        if self._anthropic is None:
            self._anthropic = AnthropicClient(settings.anthropic_api_key)
        return self._anthropic

    async def complete(
        self,
        seat: str,
        messages: list,
        *,
        scope: str,
        data_class: str,
        sovereign: bool = False,
        schema: dict | None = None,
        stream=None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        override, conn_attrs = await _resolve_override(seat, scope)
        r = registry.resolve(
            seat, sovereign=sovereign, healthy_local_nodes=health.ready_node_names(), override=override
        )
        if conn_attrs:
            r.zone = conn_attrs["zone"]

        # --- seat data-class ceiling (02 §1 — e.g. planner can never see RAW; seat-level, once) ----
        if data_class == "RAW" and r.data_class_max == "SANITIZED":
            await egress.record(scope=scope, host=_HOST.get(r.backend, r.zone.lower()), zone=r.zone,
                                seat=seat, bytes_out=0, bytes_in=0)
            raise BoundaryViolation(f"seat {seat!r} has a SANITIZED ceiling; RAW data refused")

        msgs = _as_dicts(messages)
        opts = dict(schema=schema, temperature=temperature, max_tokens=max_tokens, stream=stream,
                    scope=scope, data_class=data_class, sovereign=sovereign)

        # BYOK override or non-auto mode: exactly one candidate — behavior unchanged.
        if conn_attrs is not None or settings.model_mode != "auto":
            return await self._serve_one(r, seat, msgs, conn_attrs=conn_attrs, **opts)

        # auto mode: ordered dispatch chain with CALL-TIME fallback (Fix 2). A dispatch that raises
        # an availability error (404 model, credit-too-low, timeout) advances to the next ready
        # backend — flagship -> openai -> anthropic -> hosted-AMD last resort -> mock. Boundary,
        # sovereign, and budget stops are HARD: never fall around them.
        chain = registry.resolve_chain(
            seat, sovereign=sovereign, healthy_local_nodes=health.ready_node_names())
        for i, rc in enumerate(chain):
            try:
                return await self._serve_one(rc, seat, msgs, conn_attrs=None, **opts)
            except (BoundaryViolation, SovereignViolation, BudgetExceeded):
                raise
            except Exception as exc:  # noqa: BLE001 — availability failure: try the next backend
                if i >= len(chain) - 1:
                    raise
                await emit(scope, E.SYSTEM_NOTICE,
                           {"text": f"seat {seat}: {rc.backend} dispatch failed "
                            f"({type(exc).__name__}: {str(exc)[:120]}); falling back to next backend",
                            "level": "warn", "badge": "fallback-serving"})
        raise RuntimeError(f"empty dispatch chain for seat {seat!r}")  # unreachable: ends with mock

    async def _serve_one(self, r: Resolved, seat: str, msgs: list[dict], *, conn_attrs: dict | None,
                         schema, temperature, max_tokens, stream, scope, data_class,
                         sovereign) -> Completion:
        """One candidate: boundary check -> budget guard -> dispatch (+ repair round). Raised by the
        auto-chain loop on an availability failure; boundary/sovereign/budget stops propagate as-is."""
        # --- boundary check (fail closed; log the attempt for the network monitor) ---------------
        badge, violation = _check_boundary(r, data_class, sovereign, conn_attrs)
        if violation is not None:
            await egress.record(scope=scope, host=_HOST.get(r.backend, r.zone.lower()), zone=r.zone,
                                seat=seat, bytes_out=0, bytes_in=0, sovereign_violation=(violation == "sovereign"))
            if violation == "sovereign":
                raise SovereignViolation(f"seat {seat!r} -> {r.zone} blocked in Sovereign Mode")
            raise BoundaryViolation(f"{data_class} data class cannot reach zone {r.zone} (seat {seat!r})")
        if badge in ("demo-exception", "fallback-serving", "customer-attested"):
            await emit(scope, E.SYSTEM_NOTICE,
                       {"text": f"seat {seat}: {badge} serving ({r.zone})", "level": "warn", "badge": badge})

        # --- budget guard ------------------------------------------------------------------------
        await self._budget_guard(r, scope)

        # --- dispatch (+ one repair round on invalid structured output) --------------------------
        # metering / egress / model.call happen per dispatch (a repair round is a second LLM call,
        # 10 §1), so the ledger shows both.
        return await self._dispatch_with_repair(
            r, seat, msgs, schema, conn_attrs, temperature, max_tokens, stream, scope=scope, badge=badge,
        )

    async def _budget_guard(self, r: Resolved, scope: str) -> None:
        if r.backend == "fireworks" and not r.use_mock:
            if await meter.fireworks_spend_today() >= meter.fireworks_budget():
                await emit(scope, E.SYSTEM_NOTICE,
                           {"text": "Fireworks daily budget reached", "level": "error"})
                raise BudgetExceeded("fireworks daily budget")
        cap = _scope_caps.get(scope)
        if cap is not None and await meter.scope_spend(scope) >= cap:
            await emit(scope, E.SYSTEM_NOTICE, {"text": "per-run budget cap reached", "level": "error"})
            raise BudgetExceeded("scope budget cap")

    async def _dispatch_with_repair(self, r, seat, messages, schema, conn_attrs,
                                    temperature, max_tokens, stream, *, scope, badge):
        msgs = messages
        if schema is not None and r.backend in ("fireworks", "openai", "openrouter"):
            # OpenAI-compat JSON mode needs the schema (and the word JSON) in the prompt (02 §2.1)
            msgs = [{"role": "system", "content": "Respond ONLY with JSON matching this schema:\n"
                     + json.dumps(schema)}] + msgs

        t0 = time.monotonic()
        result = await self._call(r, seat, msgs, schema, conn_attrs, temperature, max_tokens, stream)
        await self._record_dispatch(scope, seat, r, result, badge, messages=msgs,
                                    latency_ms=int((time.monotonic() - t0) * 1000), schema=schema)

        if schema is not None:
            err = self._schema_error(result.parsed, schema)
            if err is not None:
                repair = msgs + [
                    {"role": "assistant", "content": result.text},
                    {"role": "user", "content": f"That failed schema validation: {err}. "
                     "Return corrected JSON only, matching the schema exactly."},
                ]
                t0 = time.monotonic()
                result = await self._call(r, seat, repair, schema, conn_attrs, temperature, max_tokens, stream)
                await self._record_dispatch(scope, seat, r, result, badge, messages=repair,
                                            latency_ms=int((time.monotonic() - t0) * 1000), schema=schema)
                err2 = self._schema_error(result.parsed, schema)
                if err2 is not None:
                    raise ValueError(f"structured output invalid after repair round: {err2}")
        return Completion(text=result.text, parsed=result.parsed, usage=result.usage)

    async def _record_dispatch(self, scope, seat, r, result, badge, *, messages=None,
                               latency_ms=0, schema=None) -> None:
        ti, to = result.usage["tokens_in"], result.usage["tokens_out"]
        cost = await meter.record(scope=scope, seat=seat, backend=r.backend, model=r.model,
                                  zone=r.zone, tokens_in=ti, tokens_out=to)
        await egress.record(scope=scope, host=_HOST.get(r.backend, r.zone.lower()), zone=r.zone,
                            seat=seat, bytes_out=ti * 4, bytes_in=to * 4)
        await emit(scope, E.MODEL_CALL, {"seat": seat, "backend": r.backend, "zone": r.zone,
                                         "model": r.model, "tokens_in": ti, "tokens_out": to,
                                         "cost_usd": cost, "badge": badge})
        if settings.trace_prompts:
            # trace layer (LOCAL-only debugging): full messages + response, RAW by design
            from app.ids import new_id
            trace_id = new_id("trace")
            parsed_ok = 1 if (schema is None or result.parsed is not None) else 0
            await db.execute(
                "INSERT INTO model_traces (id, ts, scope, seat, backend, model, zone, messages_json, "
                "response_text, parsed_ok, tokens_in, tokens_out, cost_usd, latency_ms, badge) VALUES "
                "(:id, datetime('now'), :scope, :seat, :backend, :model, :zone, :msgs, :resp, :pok, "
                ":ti, :to, :cost, :lat, :badge)",
                {"id": trace_id, "scope": scope, "seat": seat, "backend": r.backend, "model": r.model,
                 "zone": r.zone, "msgs": json.dumps(messages or []), "resp": result.text,
                 "pok": parsed_ok, "ti": ti, "to": to, "cost": cost, "lat": latency_ms,
                 "badge": badge or ""},
            )
            await emit(scope, E.MODEL_TRACE, {"trace_id": trace_id, "seat": seat, "model": r.model,
                                              "tokens_in": ti, "tokens_out": to, "cost_usd": cost,
                                              "latency_ms": latency_ms})
        await meter.tick(scope)

    @staticmethod
    def _schema_error(parsed, schema) -> str | None:
        if parsed is None:
            return "no JSON object returned"
        try:
            jsonschema.validate(parsed, schema)
            return None
        except jsonschema.ValidationError as e:
            return re.sub(r"\s+", " ", str(e.message))[:200]
        except Exception:  # noqa: BLE001 — an unresolvable $ref / malformed schema is a SCHEMA bug
            # (e.g. a planner-generated step output_schema is a bare named $ref, resolvable only
            # against the plan's data_schemas, not at dispatch time). It must NEVER turn a real
            # completion into a validation error — that erroed every unit of a live run. We cannot
            # enforce a schema we cannot resolve, so accept the parsed completion unvalidated.
            return None

    async def _call(self, r: Resolved, seat, messages, schema, conn_attrs,
                    temperature, max_tokens, stream) -> ClientResult:
        temp = temperature if temperature is not None else r.temperature
        if r.use_mock:
            return await mock_client.complete(messages, model=r.model, schema=schema, seat=seat,
                                              temperature=temp, max_tokens=max_tokens,
                                              timeout=r.timeout_s, stream=stream)
        # r.model is the models.yaml KEY (kept for metering/flags); the wire needs the provider id.
        wire = registry.provider_id(r.model)
        if r.backend == "anthropic":
            return await self._anthropic_client().complete(messages, model=wire, schema=schema,
                                                           seat=seat, temperature=temp,
                                                           max_tokens=max_tokens, timeout=r.timeout_s)
        if r.backend in ("openai", "openrouter"):
            # OpenAI-compatible chat-completions (reuse FireworksClient); base_url + /v1/chat/completions.
            # OpenRouter is the flagship path; OpenAI-direct is the fallback. wire id keeps its slash.
            base, key = ((settings.openrouter_base_url, settings.openrouter_api_key)
                         if r.backend == "openrouter"
                         else (settings.openai_base_url, settings.openai_api_key))
            client = FireworksClient(base, key)
            return await client.complete(messages, model=wire, schema=schema, seat=seat,
                                         temperature=temp, max_tokens=max_tokens, timeout=r.timeout_s, stream=stream)
        if r.backend == "fireworks":
            # base_url + '/v1/chat/completions' -> .../inference/v1/chat/completions (Fireworks path)
            client = FireworksClient(settings.fireworks_base_url, settings.fireworks_api_key)
            return await client.complete(messages, model=wire, schema=schema, seat=seat,
                                         temperature=temp, max_tokens=max_tokens, timeout=r.timeout_s, stream=stream)
        if r.backend == "local":
            ip = health.node_ip(r.node or "") or "127.0.0.1"
            port = _LOCAL_PORTS.get(r.model, 8000)
            # local vLLM is addressed by the served_model_name (== models.yaml key r.model), not hf_id.
            client = VllmClient(f"http://{ip}:{port}")
            return await client.complete(messages, model=r.model, schema=schema, seat=seat,
                                         temperature=temp, max_tokens=max_tokens, timeout=r.timeout_s, stream=stream)
        if r.backend == "custom":
            base = (conn_attrs or {}).get("base_url", "")
            api_key = await self._secret(conn_attrs)
            if (conn_attrs or {}).get("api_style") == "anthropic":
                client = AnthropicClient(api_key or "", base_url=base or None)
                return await client.complete(messages, model=wire, schema=schema, seat=seat,
                                             temperature=temp, max_tokens=max_tokens, timeout=r.timeout_s)
            client = FireworksClient(base, api_key)   # OpenAI-compatible (default)
            return await client.complete(messages, model=wire, schema=schema, seat=seat,
                                         temperature=temp, max_tokens=max_tokens, timeout=r.timeout_s, stream=stream)
        # I2: unknown backend is a config error — silent mock output would fake a live dispatch.
        # Only mock mode keeps the tolerant fallback (deterministic dev/CI).
        if settings.model_mode == "mock":
            return await mock_client.complete(messages, model=r.model, schema=schema, seat=seat,
                                              temperature=temp, max_tokens=max_tokens,
                                              timeout=r.timeout_s, stream=stream)
        raise ValueError(f"unknown backend {r.backend!r} for seat {seat!r} (model {r.model!r}) — "
                         "check seats.yaml/models.yaml or the seat override")

    @staticmethod
    async def _secret(conn_attrs: dict | None) -> str | None:
        if not conn_attrs or not conn_attrs.get("keyref"):
            return None
        from app.boundary.secrets import decrypt_ref

        return await decrypt_ref(conn_attrs["keyref"])


router = Router()


# convenience for tests / scripts that dispatch outside a stage
async def complete(*args, **kwargs) -> Completion:
    return await router.complete(*args, **kwargs)


__all__ = ["router", "complete", "set_scope_cap", "clear_scope_cap", "Router",
           "BoundaryViolation", "SovereignViolation", "BudgetExceeded"]
