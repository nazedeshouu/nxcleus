"""Regressions for the honest, explicitly unsafe demo generated-process subprocess runtime."""
from __future__ import annotations

import ast
import builtins
import os
import time
from pathlib import Path

import httpx
import pytest

from app.boundary import proxy_token
from app.config import settings
from app.runtime import staging

_MANIFEST = {"process": "runtime-test", "goal": "test generated execution", "mode": "build",
             "unit_schema": {"type": "object", "required": ["id"]}}


def _workspace(tmp_path: Path, source: str, name: str = "workspace") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "process.py").write_text(source, encoding="utf-8")
    return root


async def _post(handle, unit: dict) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(f"{handle.base_url}/run_unit", json=unit)


async def test_official_async_process_runs_over_http_and_qa_reads_nested_output(
        tmp_path, monkeypatch):
    from app.qa import stage6

    root = _workspace(tmp_path, """\
class Process:
    async def run_unit(self, unit, ctx):
        ctx.log("scored", unit_id=unit["id"])
        return {"status": "needs_review", "output": {"risk_score": unit["amount"] * 2}}
""")
    handle = await staging.deploy("official", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "u1", "amount": 0.25})
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "status": "needs_review",
            "output": {"risk_score": 0.5},
            "trace": [{"event": "scored", "unit_id": "u1"}],
            "execution_mode": "unsafe-demo-subprocess",
        }
        # The application owns one client on one event loop. Pytest creates a fresh loop per test,
        # so isolate this direct helper call from connections retained by earlier test loops.
        async with httpx.AsyncClient() as qa_client:
            monkeypatch.setattr(stage6.egress, "http_client", qa_client)
            actual, obtained = await stage6._staged_actual(
                handle.base_url, {"id": "v1", "inputs": {"amount": 0.3},
                                  "output_field": "risk_score"},
                proxy_token.sign_token("official", ["oracle"]))
        assert obtained is True and actual == 0.6
    finally:
        await handle.stop()


async def test_qa_probe_tools_inject_valid_token_but_preserve_wrong_tenant_override(
        tmp_path, monkeypatch):
    from app.qa import stage6

    root = _workspace(tmp_path, "def run_unit(unit):\n    return {'seen': unit['id']}\n", "auth")
    handle = await staging.deploy("auth-process", _MANIFEST, str(root), expect_token=True)
    correct = proxy_token.sign_token("auth-process", ["inspector", "oracle"])
    wrong_tenant = proxy_token.sign_token("different-process", ["inspector"])
    try:
        async with httpx.AsyncClient() as qa_client:
            monkeypatch.setattr(stage6.egress, "http_client", qa_client)
            tools = stage6._probe_tools(handle.base_url, correct)
            default_result = await tools["http_request"](
                method="POST", path="/run_unit", body={"id": "u1"})
            wrong_result = await tools["http_request"](
                method="POST", path="/run_unit",
                headers={"X-Proxy-Token": wrong_tenant}, body={"id": "u2"})

        assert default_result["status"] == 200
        assert wrong_result["status"] == 401
        assert "unauthorized" in wrong_result["body"]
    finally:
        await handle.stop()


async def test_legacy_top_level_run_unit_is_normalized(tmp_path):
    root = _workspace(tmp_path, """\
def run_unit(unit):
    return {"legacy_id": unit["id"]}
""")
    handle = await staging.deploy("legacy", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "legacy-1"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["output"] == {"legacy_id": "legacy-1"}
        assert response.json()["status"] != "accepted"
    finally:
        await handle.stop()


@pytest.mark.parametrize(("source", "message"), [
    (None, "has no"),
    ("def run_unit(:\n    pass\n", "invalid Python syntax"),
    ("class Process:\n    def run_unit(self, unit, ctx): return {}\n", "requires async"),
    ("def run_unit(unit, unexpected):\n    return {}\n", "requires class Process"),
    ("VALUE = 1\n", "requires class Process"),
])
async def test_missing_broken_or_mismatched_entrypoint_fails_deploy(
        tmp_path, source, message):
    root = tmp_path / "broken"
    root.mkdir()
    if source is not None:
        (root / "process.py").write_text(source, encoding="utf-8")
    with pytest.raises(staging.StagingDeployError, match=message):
        await staging.deploy("broken", _MANIFEST, str(root))


async def test_non_utf8_entrypoint_fails_preflight(tmp_path):
    root = tmp_path / "non-utf8"
    root.mkdir()
    (root / "process.py").write_bytes(b"def run_unit(unit):\n    return {}\n# \xff")
    with pytest.raises(staging.StagingDeployError, match="not readable UTF-8"):
        await staging.deploy("non-utf8", _MANIFEST, str(root))


async def test_demo_runtime_gate_blocks_flag_off_and_live_mode(tmp_path, monkeypatch):
    root = _workspace(tmp_path, "def run_unit(unit):\n    return {}\n")

    monkeypatch.setattr(settings, "unsafe_demo_runtime", False)
    with pytest.raises(staging.StagingDeployError, match="execution is disabled"):
        await staging.deploy("disabled", _MANIFEST, str(root))

    monkeypatch.setattr(settings, "unsafe_demo_runtime", True)
    monkeypatch.setattr(settings, "model_mode", "live")
    with pytest.raises(staging.StagingDeployError, match="MODEL_MODE=mock"):
        await staging.deploy("live", _MANIFEST, str(root))


def test_unsafe_demo_runtime_defaults_off():
    assert settings.__class__.model_fields["unsafe_demo_runtime"].default is False


async def test_generated_import_side_effects_stay_out_of_parent_process(tmp_path, monkeypatch):
    marker = "_NXCLEUS_GENERATED_SIDE_EFFECT"
    monkeypatch.delattr(builtins, marker, raising=False)
    monkeypatch.setenv("NXCLEUS_PARENT_SECRET_MARKER", "must-not-cross")
    root = _workspace(tmp_path, f"""\
import builtins
import os
builtins.{marker} = "child-only"

class Process:
    async def run_unit(self, unit, ctx):
        return {{"status": "ok", "output": {{
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "secret": os.environ.get("NXCLEUS_PARENT_SECRET_MARKER"),
            "marker": getattr(builtins, "{marker}"),
        }}}}
""")
    handle = await staging.deploy("isolation", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "u1"})
        output = response.json()["output"]
        assert response.status_code == 200
        assert output["pid"] != os.getpid()
        # Windows venv launchers may insert one bootstrap process, so getppid() is not guaranteed
        # to equal pytest's pid; the generated interpreter itself must still be distinct.
        assert output["parent_pid"] != output["pid"]
        assert output["secret"] is None
        assert output["marker"] == "child-only"
        assert not hasattr(builtins, marker)
    finally:
        await handle.stop()


@pytest.mark.parametrize("capability", ["model", "connector"])
async def test_context_network_capabilities_fail_clearly(tmp_path, capability):
    call = ('await ctx.model(name="blocked", payload={})' if capability == "model"
            else 'ctx.connector("blocked")')
    root = _workspace(tmp_path, f"""\
class Process:
    async def run_unit(self, unit, ctx):
        {call}
        return {{"status": "ok", "output": {{}}}}
""")
    handle = await staging.deploy(f"no-{capability}", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "u1"})
        assert response.status_code == 500
        body = response.json()
        assert body["status"] == "error"
        assert body["output"]["error"] == "process_exception"
        assert f"ctx.{capability} is unavailable" in body["output"]["detail"]
    finally:
        await handle.stop()


async def test_invalid_unit_status_is_an_execution_error_not_an_ack(tmp_path):
    root = _workspace(tmp_path, """\
def run_unit(unit):
    return {"status": "accepted", "decision": "review"}
""")
    handle = await staging.deploy("invalid-status", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "u1"})
        assert response.status_code == 500
        assert response.json()["status"] == "error"
        assert "UnitResult.status" in response.json()["output"]["detail"]
    finally:
        await handle.stop()


async def test_worker_timeout_returns_error_without_hanging(tmp_path, monkeypatch):
    root = _workspace(tmp_path, """\
import asyncio
class Process:
    async def run_unit(self, unit, ctx):
        await asyncio.sleep(10)
        return {"status": "ok", "output": {}}
""")
    monkeypatch.setattr(staging, "_WORKER_TIMEOUT_S", 0.15)
    handle = await staging.deploy("timeout", _MANIFEST, str(root))
    try:
        started = time.monotonic()
        response = await _post(handle, {"id": "u1"})
        elapsed = time.monotonic() - started
        assert elapsed < 2.0
        assert response.status_code == 504
        assert response.json()["status"] == "error"
        assert response.json()["output"]["error"] == "worker_timeout"
    finally:
        await handle.stop()


async def test_worker_crash_returns_error_without_hanging(tmp_path):
    root = _workspace(tmp_path, """\
import os
def run_unit(unit):
    os._exit(7)
""")
    handle = await staging.deploy("crash", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "u1"})
        assert response.status_code == 500
        assert response.json()["status"] == "error"
        assert response.json()["output"]["error"] == "worker_crash"
    finally:
        await handle.stop()


async def test_placeholder_official_entrypoint_compiles_and_executes(tmp_path):
    from app.seats._placeholder import _process_entrypoint

    root = tmp_path / "placeholder"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod_one.py").write_text("""\
async def run_step(unit, ctx):
    ctx.log("module", module="mod_one")
    return {"seen": unit["id"]}
""", encoding="utf-8")
    source = _process_entrypoint([{"id": "mod_one"}])
    ast.parse(source)
    (root / "process.py").write_text(source, encoding="utf-8")

    handle = await staging.deploy("placeholder", _MANIFEST, str(root))
    try:
        response = await _post(handle, {"id": "u1"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["output"] == {"seen": "u1"}
    finally:
        await handle.stop()

async def test_operate_respects_runtime_unit_status(tmp_path, monkeypatch):
    from app.boundary import egress
    from app.runtime import operate

    root = _workspace(tmp_path, """\
class Process:
    async def run_unit(self, unit, ctx):
        if unit["id"] == "unit-0":
            return {"status": "error", "output": {"reason": "broken unit"}}
        return {"status": "needs_review", "output": {"reason": "human check"}}
""", name="operate")
    persisted: list[dict] = []

    async def capture_unit(**fields):
        persisted.append(fields)
        return fields.get("unit_id", "unit")

    async def emit(*args, **kwargs):
        return None

    monkeypatch.setattr(operate.dao, "add_run_unit", capture_unit)
    async with httpx.AsyncClient() as runtime_client:
        monkeypatch.setattr(egress, "http_client", runtime_client)
        summary = await operate._drive_build_units(
            {"process_id": "process-1", "input_ref": "2"}, "run-1", root, None, emit)

    assert summary["counts"] == {"ok": 0, "needs_review": 1, "error": 1}
    assert summary["partial"] is True
    assert [unit["status"] for unit in persisted] == ["error", "needs_review"]


async def test_operate_preserves_legacy_review_signal_in_nested_output(tmp_path, monkeypatch):
    from app.boundary import egress
    from app.runtime import operate

    root = _workspace(tmp_path, """\
def run_unit(unit):
    return {"decision": "review", "details": {"flagged": False}}
""", name="legacy-operate")
    persisted: list[dict] = []

    async def capture_unit(**fields):
        persisted.append(fields)
        return fields.get("unit_id", "unit")

    async def emit(*args, **kwargs):
        return None

    monkeypatch.setattr(operate.dao, "add_run_unit", capture_unit)
    async with httpx.AsyncClient() as runtime_client:
        monkeypatch.setattr(egress, "http_client", runtime_client)
        summary = await operate._drive_build_units(
            {"process_id": "legacy-process", "input_ref": "1"},
            "legacy-run", root, None, emit)

    assert summary["counts"] == {"ok": 0, "needs_review": 1, "error": 0}
    assert persisted[0]["status"] == "needs_review"
    normalized = persisted[0]["result"]["output"]
    assert normalized["status"] == "ok"
    assert normalized["output"]["decision"] == "review"


async def test_run_outcome_with_errors_is_failed_and_never_emits_completed(monkeypatch):
    from app.events import E
    from app.runtime import operate

    updates: list[dict] = []
    events: list[tuple[str, dict]] = []

    async def update_run(run_id, **fields):
        updates.append({"run_id": run_id, **fields})

    async def emit(event, payload):
        events.append((event, payload))

    monkeypatch.setattr(operate.dao, "update_run", update_run)
    status = await operate._persist_run_outcome(
        "run-errors",
        {"counts": {"ok": 2, "needs_review": 1, "error": 1}, "done": 4, "total": 4,
         "partial": True, "zero_candidate": False, "actual_units": True,
         "mock_dispatches": 0},
        {"units": 4, "artifact": {"verification": "passed", "degraded": False,
         "reason": None, "artifacts": [{"kind": "csv", "url": "/csv"},
                                         {"kind": "report", "url": "/report"}]}},
        {"total_usd": 0.1},
        emit,
    )

    assert status == "failed"
    assert updates[0]["status"] == "failed"
    assert [event for event, _ in events] == [E.SYSTEM_NOTICE, E.RUN_FINISHED]
    assert "1 unit(s)" in events[0][1]["text"]


async def test_budget_only_partial_run_is_explicitly_unverified(monkeypatch):
    from app.events import E
    from app.runtime import operate

    updates: list[dict] = []
    events: list[tuple[str, dict]] = []

    async def update_run(run_id, **fields):
        updates.append({"run_id": run_id, **fields})

    async def emit(event, payload):
        events.append((event, payload))

    monkeypatch.setattr(operate.dao, "update_run", update_run)
    status = await operate._persist_run_outcome(
        "run-budget",
        {"counts": {"ok": 2, "needs_review": 0, "error": 0}, "done": 2, "total": 4,
         "partial": True, "zero_candidate": False, "actual_units": True,
         "mock_dispatches": 0},
        {"units": 4, "artifact": {"verification": "passed", "degraded": False,
         "reason": None, "artifacts": [{"kind": "csv", "url": "/csv"},
                                         {"kind": "report", "url": "/report"}]}},
        {"total_usd": 0.1},
        emit,
    )

    assert status == "partial"
    assert updates[0]["status"] == "partial"
    assert [event for event, _ in events] == [E.SYSTEM_NOTICE, E.RUN_FINISHED]
    assert events[-1][1]["verification"] == "unverified"
