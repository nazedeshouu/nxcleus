"""Seat + model registry and binding resolution (02 §1–3).

Reads `infra/seats.yaml` + `infra/models.yaml` when present (the AI engineer owns those); otherwise
falls back to a built-in mock seat table that mirrors spec 02 §1 so zones/data-classes are realistic
even before the YAML lands. Resolution order (02 §2): seat -> sovereign overlay -> backend health ->
(zone/data-class check + budget happen in the router) -> chosen binding.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from app.config import settings

# backend kind -> boundary zone (01 §3)
ZONE = {
    "local": "LOCAL",
    "fireworks": "AMD_HOSTED",
    "anthropic": "EXTERNAL",
    "custom": "CUSTOM",
    "mock": "LOCAL",
}


@dataclass
class Binding:
    backend: str                 # local | fireworks | anthropic | custom
    model: str
    node: str | None = None

    @property
    def zone(self) -> str:
        return ZONE.get(self.backend, "LOCAL")


@dataclass
class SeatDef:
    name: str
    data_class_max: str = "SANITIZED"       # RAW | SANITIZED (hard ceiling — enforced)
    temperature: float = 0.3
    timeout_s: float = 120.0
    default: Binding | None = None
    sovereign: Binding | None = None
    fallback: Binding | None = None
    pool: list[Binding] = field(default_factory=list)
    self_consistency: int = 1

    def binding_for(self, *, sovereign: bool) -> Binding:
        if sovereign and self.sovereign is not None:
            return self.sovereign
        return self.default or (self.pool[0] if self.pool else self.fallback)  # type: ignore


@dataclass
class Resolved:
    seat: str
    backend: str                 # the target backend kind (real intent, even in mock mode)
    zone: str
    model: str
    node: str | None
    data_class_max: str
    temperature: float
    timeout_s: float
    use_mock: bool               # dispatch via MockClient (dev/CI or backend unavailable)
    badge: str | None = None     # UI badge: 'mock' | 'fallback-serving' | 'demo-exception' | None


# per-seat timeouts (02 §2.2)
_TIMEOUTS = {"planner": 300.0, "coder": 240.0}


def _builtin_seats() -> dict[str, SeatDef]:
    """Mirror of 02 §1 default bindings — used until infra/seats.yaml is present."""
    L = lambda node, model: Binding("local", model, node)  # noqa: E731
    return {
        "trust": SeatDef(
            "trust", "RAW", 0.3, default=L("A", "gemma-4-26b-a4b"),
            fallback=Binding("fireworks", "accounts/fireworks/models/gemma-4-26b-a4b-it"),
        ),
        "planner": SeatDef(
            "planner", "SANITIZED", 0.4, timeout_s=300.0,
            default=Binding("anthropic", "claude-fable-5"),
            sovereign=L("B", "glm-46"),
            fallback=Binding("fireworks", "accounts/fireworks/models/glm-5p2"),
        ),
        "certifier": SeatDef(
            "certifier", "RAW", 0.3, default=L("B", "glm-46"),
            fallback=Binding("fireworks", "accounts/fireworks/models/glm-5p2"),
        ),
        "conductor": SeatDef(
            "conductor", "RAW", 0.3, default=L("B", "glm-46"),  # no fallback: engine skips review
        ),
        "coder": SeatDef(
            "coder", "RAW", 0.2, timeout_s=240.0,
            pool=[L("C", "qwen3-coder-next"), L("D", "qwen36-27b"), L("D", "devstral-small-2")],
            fallback=Binding("fireworks", "accounts/fireworks/models/qwen3p6-27b"),
        ),
        "consolidator": SeatDef(
            "consolidator", "RAW", 0.2, default=L("B", "glm-46"),
            fallback=Binding("fireworks", "accounts/fireworks/models/glm-5p2"),
        ),
        "oracle": SeatDef(
            "oracle", "SANITIZED", 0.3, default=L("A", "gemma-4-31b"),
            fallback=Binding("fireworks", "accounts/fireworks/models/gemma-4-31b"),
            self_consistency=3,
        ),
        "inspector": SeatDef(
            "inspector", "SANITIZED", 0.7, default=L("A", "qwen36-35b-a3b"),
            fallback=Binding("fireworks", "accounts/fireworks/models/qwen3p6-35b-a3b"),
        ),
    }


def _binding_from_yaml(spec) -> Binding | None:
    if spec is None or spec == "default":
        return None
    return Binding(backend=spec.get("backend", "local"), model=spec.get("model", ""),
                   node=spec.get("node"))


def _pool_from_specs(specs) -> list[Binding]:
    return [Binding(b.get("backend", "local"), b.get("model", ""), b.get("node"))
            for b in (specs or []) if isinstance(b, dict)]


def _seats_from_yaml(data: dict) -> dict[str, SeatDef]:
    out: dict[str, SeatDef] = {}
    for name, sd in (data.get("seats") or {}).items():
        bindings = sd.get("bindings", {})
        raw_default = bindings.get("default")
        # A pooled seat authors its members as `bindings.default: [ {...}, {...} ]` (seats.yaml
        # style); a single-backend seat uses a dict. Support both, plus a top-level `pool:` key.
        if isinstance(raw_default, list):
            pool = _pool_from_specs(raw_default)
            default = None                       # binding_for falls through to pool[0]
        else:
            pool = _pool_from_specs(sd.get("pool"))
            default = _binding_from_yaml(raw_default)
        sovereign = _binding_from_yaml(bindings.get("sovereign")) or default or (pool[0] if pool else None)
        fallback = _binding_from_yaml(bindings.get("fallback"))
        out[name] = SeatDef(
            name=name,
            data_class_max=sd.get("data_class_max", "SANITIZED"),
            temperature=sd.get("temperature", 0.3),
            timeout_s=sd.get("timeout_s", _TIMEOUTS.get(name, 120.0)),
            default=default, sovereign=sovereign, fallback=fallback, pool=pool,
            self_consistency=sd.get("self_consistency", 1),
        )
    return out


class Registry:
    def __init__(self) -> None:
        self.seats = self._load()
        self.models = self._load_models()

    def _load(self) -> dict[str, SeatDef]:
        path = settings.config_path("seats")
        if path:
            try:
                data = yaml.safe_load(path.read_text()) or {}
                seats = _seats_from_yaml(data)
                if seats:
                    return seats
            except Exception as exc:
                # malformed YAML -> built-in table; nothing blocks on the AI engineer's file,
                # but a silent fallback at the demo would be a debugging nightmare — say it once.
                import sys
                print(f"[registry] WARNING: {path} unreadable ({type(exc).__name__}: {exc}); "
                      f"using built-in seat table", file=sys.stderr)
        return _builtin_seats()

    def _load_models(self) -> dict:
        path = settings.config_path("models")
        if path:
            try:
                return (yaml.safe_load(path.read_text()) or {}).get("models", {})
            except Exception:
                return {}
        return {}

    def seat(self, name: str) -> SeatDef:
        if name not in self.seats:
            raise KeyError(f"unknown seat {name!r}")
        return self.seats[name]

    def resolve(
        self,
        seat: str,
        *,
        sovereign: bool,
        healthy_local_nodes: set[str] | None = None,
        override: Binding | None = None,
    ) -> Resolved:
        sd = self.seat(seat)
        healthy_local_nodes = healthy_local_nodes or set()

        binding = override or sd.binding_for(sovereign=sovereign)
        badge: str | None = None

        # backend health: a local binding is real only if its node is registered+ready.
        local_ready = binding.backend == "local" and binding.node in healthy_local_nodes

        if settings.model_mode == "mock":
            use_mock = True
            badge = "mock"
        elif settings.model_mode == "live":
            use_mock = False
        else:  # auto
            if binding.backend == "local" and not local_ready and sd.fallback is not None:
                binding = sd.fallback           # fleet down -> fallback (badged)
                badge = "fallback-serving"
            real_ok = (
                (binding.backend == "anthropic" and bool(settings.anthropic_api_key))
                or (binding.backend == "fireworks" and bool(settings.fireworks_api_key))
                or (binding.backend == "local" and local_ready)
                or binding.backend == "custom"
            )
            use_mock = not real_ok
            if use_mock and badge is None:
                badge = "mock"

        return Resolved(
            seat=seat, backend=binding.backend, zone=binding.zone, model=binding.model,
            node=binding.node, data_class_max=sd.data_class_max, temperature=sd.temperature,
            timeout_s=sd.timeout_s, use_mock=use_mock, badge=badge,
        )

    def provider_id(self, model_key: str) -> str:
        """Resolve a models.yaml KEY to the id sent on the wire (its `hf_id` / provider model id).

        Bindings carry the registry key (so the pool scheduler can look up capability flags and
        metering can key rates on it — 02 §7.4, 10 §3); only the dispatch boundary needs the real id.
        Pass-through for anything not in the registry: built-in full-path bindings and BYOK custom
        provider ids are already wire-ready.
        """
        entry = self.models.get(model_key)
        if entry and entry.get("hf_id"):
            return str(entry["hf_id"])
        return model_key

    def merged_models(self) -> dict:
        """Builtin models.yaml entries — custom models are merged in the API layer from the DB."""
        return dict(self.models)


registry = Registry()
