from __future__ import annotations

import asyncio
import types

import pytest

from app.events import E
from app.fleet import stage4


class _Dao:
    def __init__(self):
        self.rows = []

    async def build_task_done(self, _task_id):
        return False

    async def upsert_build_task(self, **row):
        self.rows.append(row)


class _Coder:
    async def build_module(self, *_args, **_kwargs):
        return {"files": [{"path": "src/mod_a.py", "content": "VALUE = 1\n"}]}


def test_waves_from_dag_rejects_cycles():
    dag = [
        {"task": "a", "module": "mod_a", "deps": ["b"]},
        {"task": "b", "module": "mod_b", "deps": ["a"]},
    ]

    with pytest.raises(ValueError, match="cycle"):
        stage4.waves_from_dag(dag, [{"id": "mod_a"}, {"id": "mod_b"}])


def test_waves_from_dag_rejects_unknown_dependencies():
    dag = [{"task": "a", "module": "mod_a", "deps": ["missing"]}]

    with pytest.raises(ValueError, match="unknown dependencies: missing"):
        stage4.waves_from_dag(dag, [{"id": "mod_a"}])


def test_waves_from_dag_rejects_duplicate_task_ids():
    dag = [
        {"task": "same", "module": "mod_a", "deps": []},
        {"task": "same", "module": "mod_b", "deps": []},
    ]

    with pytest.raises(ValueError, match="duplicate task ids"):
        stage4.waves_from_dag(dag, [{"id": "mod_a"}, {"id": "mod_b"}])


def test_waves_from_dag_rejects_unknown_module_reference():
    dag = [{"task": "a", "module": "mod_missing", "deps": []}]

    with pytest.raises(ValueError, match="unknown module: mod_missing"):
        stage4.waves_from_dag(dag, [{"id": "mod_a"}])


def test_waves_from_dag_rejects_duplicate_module_ids():
    modules = [{"id": "mod_a"}, {"id": "mod_a"}]

    with pytest.raises(ValueError, match="duplicate module id: mod_a"):
        stage4.waves_from_dag([], modules)


@pytest.mark.parametrize("module_id", [None, "", "9module", "bad-module", "módulo"])
def test_waves_from_dag_rejects_invalid_module_ids(module_id):
    with pytest.raises(ValueError, match="invalid module id"):
        stage4.waves_from_dag([], [{"id": module_id}])


def test_waves_from_dag_rejects_duplicate_module_references():
    dag = [
        {"task": "a", "module": "mod_a", "deps": []},
        {"task": "b", "module": "mod_a", "deps": ["a"]},
    ]

    with pytest.raises(ValueError, match="duplicate module references: mod_a"):
        stage4.waves_from_dag(dag, [{"id": "mod_a"}])


def test_waves_from_dag_requires_coverage_of_every_module():
    dag = [{"task": "a", "module": "mod_a", "deps": []}]

    with pytest.raises(ValueError, match="does not cover plan modules: mod_b"):
        stage4.waves_from_dag(dag, [{"id": "mod_a"}, {"id": "mod_b"}])


async def _run_build(
    monkeypatch, tmp_path, dao, events, *, verification: str, allow_unverified: bool,
):
    async def emit(event_type, payload):
        events.append((event_type, payload))

    async def test_result(**_kwargs):
        return {
            "verification": verification,
            "total": 1,
            "passed": 1 if verification == "passed" else 0,
            "failed": 1 if verification == "failed" else 0,
            "sandboxed": verification != "unverified",
            "reason": f"verification is {verification}",
        }

    ctx = types.SimpleNamespace(job_id="job-stage4", dao=dao, emit=emit, complete=None)
    chosen = types.SimpleNamespace(model="coder-model")
    monkeypatch.setattr(stage4.pool, "pick_member", lambda *_args: (chosen, {}))
    monkeypatch.setattr(stage4, "seat", lambda _name: _Coder())
    monkeypatch.setattr(stage4.workspace, "write_files", lambda *_args, **_kwargs: ["src/mod_a.py"])
    monkeypatch.setattr(stage4.workspace, "agent_dir", lambda *_args: tmp_path)
    monkeypatch.setattr(stage4.workspace, "job_dir", lambda *_args: tmp_path)
    monkeypatch.setattr(stage4.codeexec, "run_tests", test_result)
    monkeypatch.setattr(
        stage4.codeexec,
        "unverified_demo_delivery_allowed",
        lambda: allow_unverified,
    )
    return await stage4._build_task(
        ctx,
        {"task": "build-a", "module": "mod_a", "_wave": 0},
        {"id": "mod_a"},
        {"interfaces": []},
        [],
        [chosen],
        {},
        asyncio.Semaphore(1),
    )


@pytest.mark.asyncio
async def test_build_task_failure_is_not_marked_done(monkeypatch, tmp_path):
    dao = _Dao()
    events = []

    with pytest.raises(RuntimeError, match="verification blocked delivery"):
        await _run_build(
            monkeypatch, tmp_path, dao, events,
            verification="failed", allow_unverified=False,
        )

    assert dao.rows[-1]["status"] == "failed"
    assert all(row["status"] != "done" for row in dao.rows)
    assert next(payload for event, payload in events if event == E.TASK_TESTS)["verification"] == "failed"
    assert any(event == E.TASK_FAILED for event, _payload in events)


@pytest.mark.asyncio
async def test_unverified_build_blocks_without_demo_override(monkeypatch, tmp_path):
    dao = _Dao()
    events = []

    with pytest.raises(RuntimeError, match="verification blocked delivery"):
        await _run_build(
            monkeypatch, tmp_path, dao, events,
            verification="unverified", allow_unverified=False,
        )

    tests_event = next(payload for event, payload in events if event == E.TASK_TESTS)
    assert tests_event["verification"] == "unverified"
    assert tests_event["sandboxed"] is False
    assert dao.rows[-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_unverified_build_with_explicit_demo_override_stays_labeled(monkeypatch, tmp_path):
    dao = _Dao()
    events = []

    result = await _run_build(
        monkeypatch, tmp_path, dao, events,
        verification="unverified", allow_unverified=True,
    )

    tests_event = next(payload for event, payload in events if event == E.TASK_TESTS)
    assert tests_event["verification"] == "unverified"
    assert tests_event["passed"] == tests_event["failed"] == 0
    assert tests_event["sandboxed"] is False
    assert dao.rows[-1]["status"] == "done"
    assert result["module"] == "mod_a"
    assert all(event != E.TASK_FAILED for event, _payload in events)
