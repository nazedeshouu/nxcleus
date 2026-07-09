"""Seat resolver (brief item 7).

Wave-1 mock skeleton runs on the backend-owned placeholders: their fixture hints make MockClient
produce coherent KYC artifacts (empty synth would give module-less plans). The AI engineer's real
`app/seats/<seat>.py` modules carry the real prompts and take over when dispatching to real models.

`seat(name)` returns a proxy: when `prefer_real` is on (any non-mock model mode), it uses the real
module's entrypoint if present and falls back to the placeholder for anything not yet aligned — so a
real module conforming to the canonical call-site names (see the backend Wave-1 report) is picked up
with zero stage edits.
"""
from __future__ import annotations

import importlib

from app.config import settings
from app.seats import _placeholder

_real_cache: dict[str, object | None] = {}


def _real_module(name: str) -> object | None:
    if name not in _real_cache:
        try:
            _real_cache[name] = importlib.import_module(f"app.seats.{name}")
        except ModuleNotFoundError:
            _real_cache[name] = None
    return _real_cache[name]


class SeatProxy:
    def __init__(self, real: object | None, placeholder: object, prefer_real: bool) -> None:
        self._real = real
        self._ph = placeholder
        self._prefer_real = prefer_real

    def __getattr__(self, attr: str):
        if self._prefer_real and self._real is not None and hasattr(self._real, attr):
            return getattr(self._real, attr)
        return getattr(self._ph, attr)


def seat(name: str) -> object:
    placeholder = getattr(_placeholder, name)
    prefer_real = settings.model_mode != "mock"
    return SeatProxy(_real_module(name), placeholder, prefer_real)


def reset_cache() -> None:
    _real_cache.clear()
