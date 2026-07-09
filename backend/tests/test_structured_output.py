"""Structured-output repair round (02 §2.1) — one repair on invalid, then raise."""
from __future__ import annotations

from app.models.router import router
from app.seats.base import Message

_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


async def test_repair_round_recovers():
    # the sentinel makes MockClient return an invalid instance once, then valid on repair
    comp = await router.complete("oracle", [Message(role="user", content="[[mock_invalid_once]] go")],
                                 scope="job:repair", data_class="SANITIZED", schema=_SCHEMA)
    assert comp.parsed is not None and "answer" in comp.parsed
    # two dispatches happened (original + repair) => two meter rows in scope
    from app.metering.meter import scope_totals
    st = await scope_totals("job:repair")
    assert st["calls"] == 2


async def test_valid_first_pass_no_repair():
    comp = await router.complete("oracle", [Message(role="user", content="clean")],
                                 scope="job:clean", data_class="SANITIZED", schema=_SCHEMA)
    assert comp.parsed is not None
    from app.metering.meter import scope_totals
    st = await scope_totals("job:clean")
    assert st["calls"] == 1
