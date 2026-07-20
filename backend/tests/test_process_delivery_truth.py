from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.delivery import stage7
from app.events import E
from app.fleet import stage4
from app.orchestrator import toolsmith
from app.runtime import deliverables, operate
from app.sandbox import seeds


def _artifact(verification: str = "passed") -> dict:
    return {
        "verification": verification,
        "degraded": verification != "passed",
        "reason": None if verification == "passed" else "artifact generator used a stub",
        "artifacts": [
            {"kind": "csv", "url": "/api/runs/run-1/export.csv"},
            {"kind": "report", "url": "/api/runs/run-1/report"},
        ],
    }


def _execution() -> dict:
    return {
        "counts": {"ok": 2, "needs_review": 0, "error": 0},
        "flagged": [], "done": 2, "total": 2, "partial": False,
        "sql_rows": 0, "spot_checks": 0, "discrepancies": 0,
        "zero_candidate": False, "execution_errors": [],
        "actual_units": True, "synthetic_units": False, "mock_dispatches": 0,
    }


def _fanout(execution: dict | None = None, artifact: dict | None = None, *, override=False) -> dict:
    execution = deepcopy(execution or _execution())
    artifact = deepcopy(artifact or _artifact())
    execution["artifact"] = artifact
    outcome = operate._classify_process_fanout(execution, artifact)
    return {
        "run_id": "run-1", **outcome, "stats": {}, "cost": {},
        "execution": execution, "artifact": artifact, "demo_override": override,
    }


@pytest.mark.parametrize(("case", "expected"), [
    ("unit_error", "failed"),
    ("partial", "unverified"),
    ("zero_candidate", "unverified"),
    ("no_actual", "unverified"),
    ("degraded_artifact", "unverified"),
])
def test_fanout_classifier_never_passes_missing_or_failed_evidence(case, expected):
    execution = _execution()
    artifact = _artifact()
    if case == "unit_error":
        execution["counts"] = {"ok": 1, "needs_review": 0, "error": 1}
    elif case == "partial":
        execution.update({"done": 1, "total": 2, "partial": True})
        execution["counts"] = {"ok": 1, "needs_review": 0, "error": 0}
    elif case == "zero_candidate":
        execution.update({"done": 0, "total": 0, "zero_candidate": True})
        execution["counts"] = {"ok": 0, "needs_review": 0, "error": 0}
    elif case == "no_actual":
        execution["actual_units"] = False
    else:
        artifact = _artifact("unverified")

    outcome = operate._classify_process_fanout(execution, artifact)

    assert outcome["verification"] == expected
    assert outcome["status"] != "done"
    assert outcome["reasons"]


async def test_malformed_analysis_candidates_persist_failure_and_cannot_deliver(monkeypatch):
    updates: list[dict] = []
    checkpoints: dict[str, object] = {}
    events: list[tuple[str, dict]] = []
    persisted_units: list[dict] = []

    class FakeDao:
        async def create_run(self, **_fields):
            return "run-1"

        async def update_run(self, run_id, **fields):
            updates.append({"run_id": run_id, **fields})

        async def add_run_unit(self, **fields):
            persisted_units.append(fields)

    class FakeContext:
        scope = "job:job-1"
        complete = None
        dao = FakeDao()

        async def refresh(self):
            return {"origin": "sandbox", "spec": {"company": "acme"}, "goal": "audit"}

        async def get_checkpoint(self, name):
            return checkpoints.get(name)

        async def checkpoint(self, name, value):
            checkpoints[name] = value

        async def emit(self, event, payload):
            events.append((event, payload))

    async def cached_tool(_tool_id):
        return {"name": "malformed-candidate-tool"}

    async def malformed_findings(_scope, _name, _args):
        return {"findings": "not-a-list"}

    async def totals(_scope):
        return {"cost_usd": 0.0, "calls": 0}

    async def mock_dispatches(_scope):
        return 0

    async def artifacts(*_args, **_kwargs):
        return _artifact()

    monkeypatch.setattr(seeds, "load_units", lambda *_args, **_kwargs: [
        ("u-1", {"id": "u-1"}), ("u-2", {"id": "u-2"}),
    ])
    monkeypatch.setattr(toolsmith, "get_tool", cached_tool)
    monkeypatch.setattr(toolsmith, "invoke_tool", malformed_findings)
    monkeypatch.setattr(operate.meter, "scope_totals", totals)
    monkeypatch.setattr(operate.meter, "mock_dispatches", mock_dispatches)
    monkeypatch.setattr(operate, "_finalize_artifacts", artifacts)

    result = await operate.run_process_fanout(
        FakeContext(), {"topology": {
            "unit": {"noun": "claim"},
            "steps": [{
                "id": "candidate-analysis", "kind": "analysis", "per_unit": False,
                "purpose": "find anomalous claims",
            }],
        }})

    assert result["status"] == "failed"
    assert result["verification"] == "failed"
    assert "malformed findings" in result["execution"]["execution_errors"][0]
    assert checkpoints["fanout_result"] == result
    assert updates[-1]["status"] == "failed"
    assert persisted_units == []
    assert E.RUN_COMPLETED not in [event for event, _ in events]
    with pytest.raises(RuntimeError, match="process delivery gate failed"):
        stage7._process_delivery_gate(result)


async def test_degraded_artifacts_return_explicit_unverified_evidence(monkeypatch):
    async def no_counts(_scope):
        return {}

    async def no_run(_run_id):
        return None

    async def no_units(_run_id, *, limit):
        return []

    async def quiet_emit(*_args, **_kwargs):
        return None

    def broken_generate(*_args, **_kwargs):
        raise RuntimeError("report broke")

    monkeypatch.setattr(operate.dao, "trace_zone_counts", no_counts)
    monkeypatch.setattr(operate.dao, "get_run", no_run)
    monkeypatch.setattr(operate.dao, "list_run_units", no_units)
    monkeypatch.setattr(operate, "emit", quiet_emit)
    monkeypatch.setattr(deliverables, "generate", broken_generate)
    monkeypatch.setattr(deliverables, "write_stub", lambda *_args, **_kwargs: _artifact()["artifacts"])

    evidence = await operate._finalize_artifacts(
        "run-1", scope="run:run-1", process_name="Audit", goal="audit",
        corpus="acme", stats={}, cost={}, deliverable=None)

    assert evidence["verification"] == "unverified"
    assert evidence["degraded"] is True
    assert "degraded to stub" in evidence["reason"]


def test_process_delivery_gate_blocks_failure_and_labels_mock_override(monkeypatch):
    failed_execution = _execution()
    failed_execution["counts"] = {"ok": 1, "needs_review": 0, "error": 1}
    failed = _fanout(failed_execution, override=True)
    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: True)
    with pytest.raises(RuntimeError, match="process delivery gate failed"):
        stage7._process_delivery_gate(failed)

    no_actual = _execution()
    no_actual["actual_units"] = False
    unverified = _fanout(no_actual, override=True)
    gate = stage7._process_delivery_gate(unverified)
    assert gate["verification"] == "unverified"
    assert gate["label"] == "UNVERIFIED DEMO"
    assert gate["demo_override"] is True

    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: False)
    with pytest.raises(RuntimeError, match="process delivery gate unverified"):
        stage7._process_delivery_gate(unverified)


def test_process_delivery_gate_rejects_forged_passed_artifact(monkeypatch):
    fanout = _fanout()
    fanout["artifact"]["degraded"] = True
    fanout["artifact"]["reason"] = "stub"
    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: True)

    with pytest.raises(RuntimeError, match="contradictory fan-out evidence"):
        stage7._process_delivery_gate(fanout)


async def test_stage4_advances_unverified_only_with_current_demo_override(monkeypatch):
    advanced: list[str] = []

    class FakeDao:
        async def get_plan(self, _plan_id):
            return {"id": "plan-1", "body": {"topology": {"steps": []}}}

    context = SimpleNamespace(
        job_id="job-1",
        dao=FakeDao(),
        refresh=lambda: _async_value({"goal": "audit"}),
        get_checkpoint=lambda _name: _async_value("plan-1"),
        advance=lambda state: _async_append(advanced, state),
    )

    async def fanout(_ctx, _plan):
        return {
            "verification": "unverified", "status": "unverified",
            "reasons": ["no actual units"], "demo_override": True,
        }

    monkeypatch.setattr(operate, "run_process_fanout", fanout)
    monkeypatch.setattr(stage4.codeexec, "unverified_demo_delivery_allowed", lambda: False)
    with pytest.raises(RuntimeError, match="process fan-out unverified"):
        await stage4.run(context)
    assert advanced == []

    monkeypatch.setattr(stage4.codeexec, "unverified_demo_delivery_allowed", lambda: True)
    await stage4.run(context)
    assert advanced == ["delivering"]


async def _async_value(value):
    return value


async def _async_append(values: list, value):
    values.append(value)
