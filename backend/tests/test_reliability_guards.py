"""Deep-iteration reliability guards: the topology guard's plan classification (a corpus-bound
detection plan must narrow the corpus with a candidate step) and the mock-dispatch rollup
(a run that fell through to simulated backends is counted, not hidden)."""
from __future__ import annotations

import pytest

from app.events import E, emit
from app.metering import meter
from app.planning.stage1 import _has_candidate_step, _is_detection_plan, _is_refusal


def _plan(steps, *, mode="process", risks=None):
    return {"mode": mode, "topology": {"steps": steps}, "risks": risks or []}


def test_topology_classification():
    # sql candidate step present -> real narrowing
    assert _has_candidate_step(_plan([{"kind": "sql", "sql": "SELECT 1"}]))
    # analysis candidate step present
    assert _has_candidate_step(_plan([{"kind": "analysis", "purpose": "trace chains"}]))
    # judgment-only topology (the lawfirm/exchange 0-flag failure) -> NO candidate step
    assert not _has_candidate_step(_plan([{"id": "judge", "per_unit": True, "prompt_spec": "read it"}]))
    # a sql step with no actual query doesn't count
    assert not _has_candidate_step(_plan([{"kind": "sql", "sql": ""}]))

    # a deliberate out-of-scope refusal (empty topology + a risk) is NOT the silent-miss failure
    assert _is_refusal(_plan([], risks=["out of scope for this company"]))
    assert not _is_refusal(_plan([{"kind": "sql", "sql": "SELECT 1"}], risks=["x"]))
    assert not _is_refusal(_plan([]))  # empty + no risk is ambiguous, not a refusal

    assert _is_detection_plan(_plan([{"kind": "sql", "sql": "SELECT 1"}]))
    assert _is_detection_plan({"mode": "process"})
    assert not _is_detection_plan({"mode": "build", "modules": [{"id": "m"}]})


@pytest.mark.asyncio
async def test_mock_dispatch_rollup():
    scope = "run:test-rollup"
    # two live dispatches + one that fell through to a simulated (mock) backend
    await emit(scope, E.MODEL_CALL, {"seat": "coder", "backend": "fireworks", "badge": None})
    await emit(scope, E.MODEL_CALL, {"seat": "coder", "backend": "fireworks", "badge": "fallback-serving"})
    await emit(scope, E.MODEL_CALL, {"seat": "coder", "backend": "local", "badge": "mock"})
    # a different scope's mock must not leak into this one
    await emit("run:other", E.MODEL_CALL, {"seat": "coder", "badge": "mock"})

    assert await meter.mock_dispatches(scope) == 1
    assert await meter.mock_dispatches("run:none") == 0
