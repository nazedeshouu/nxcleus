from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.delivery import stage7
from app.events import E
from app.qa import stage6


def _integration(state: str = "passed") -> dict:
    return {
        "verification": state,
        "total": 0 if state == "unverified" else 1,
        "passed": 1 if state == "passed" else 0,
        "failed": 1 if state == "failed" else 0,
    }


def _goal(verdict: str = "fulfilled") -> dict:
    return {"verdict": verdict, "gaps": []}


def _qa_evidence(
    integration: dict, *, verification: str, goal_verdict: str = "fulfilled",
    reasons: list[str] | None = None, demo_override: bool = False,
) -> dict:
    if verification == "passed":
        probe_outcomes = [{"scenario": "s", "outcome": "clear"}]
        oracle_outcomes = [{"vector": "v", "verdict": "match"}]
        ticket_outcomes = []
    elif verification == "failed":
        probe_outcomes = [{"scenario": "s", "outcome": "finding", "ticket_id": "ticket-1"}]
        oracle_outcomes = []
        ticket_outcomes = [{"ticket_id": "ticket-1", "status": "human_review"}]
    else:
        probe_outcomes = [{"scenario": "s", "outcome": "inconclusive"}]
        oracle_outcomes = []
        ticket_outcomes = []
    return {
        "verification": verification,
        "integration": dict(integration),
        "probes": {
            "total": len(probe_outcomes),
            "clear": sum(item["outcome"] == "clear" for item in probe_outcomes),
            "finding": sum(item["outcome"] == "finding" for item in probe_outcomes),
            "inconclusive": sum(item["outcome"] == "inconclusive" for item in probe_outcomes),
            "outcomes": probe_outcomes,
        },
        "oracles": {
            "total": len(oracle_outcomes),
            "match": sum(item["verdict"] == "match" for item in oracle_outcomes),
            "mismatch": sum(item["verdict"] == "mismatch" for item in oracle_outcomes),
            "no_actual": sum(item["verdict"] == "no_actual" for item in oracle_outcomes),
            "oracle_uncertain": sum(
                item["verdict"] == "oracle_uncertain" for item in oracle_outcomes),
            "outcomes": oracle_outcomes,
        },
        "tickets": {
            "opened": len(ticket_outcomes),
            "human_review": sum(
                item["status"] == "human_review" for item in ticket_outcomes),
            "outcomes": ticket_outcomes,
        },
        "goal_verdict": goal_verdict,
        "reasons": reasons if reasons is not None else (
            [] if verification == "passed" else ["QA is not verified"]),
        "demo_override": demo_override,
    }


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"integration": None}, "failed"),
        ({"integration": _integration("failed")}, "failed"),
        ({"probes": [{"scenario": "s", "outcome": "finding"}]}, "failed"),
        ({"oracles": [{"vector": "v", "verdict": "mismatch"}]}, "failed"),
        ({"goal_check": _goal("unfulfilled")}, "failed"),
        ({"staging_live": False}, "unverified"),
        ({"probes": [{"scenario": "s", "outcome": "inconclusive"}]}, "unverified"),
        ({"oracles": [{"vector": "v", "verdict": "no_actual"}]}, "unverified"),
        ({"oracles": [{"vector": "v", "verdict": "oracle_uncertain"}]}, "unverified"),
        ({"goal_check": _goal("partial")}, "unverified"),
    ],
)
def test_qa_classification_is_fail_closed(monkeypatch, overrides, expected):
    monkeypatch.setattr(settings, "model_mode", "live")
    values = {
        "integration": _integration(),
        "staging_live": True,
        "probes": [{"scenario": "s", "outcome": "clear"}],
        "oracles": [{"vector": "v", "verdict": "match"}],
        "goal_check": _goal(),
    }
    values.update(overrides)
    verification, reasons = stage6._classify(**values)
    assert verification == expected
    assert reasons


def test_mock_mode_caps_otherwise_green_qa_at_unverified(monkeypatch):
    monkeypatch.setattr(settings, "model_mode", "mock")
    verification, reasons = stage6._classify(
        integration=_integration(),
        staging_live=True,
        probes=[{"scenario": "s", "outcome": "clear"}],
        oracles=[{"vector": "v", "verdict": "match"}],
        goal_check=_goal(),
    )
    assert verification == "unverified"
    assert any("mock seats" in reason for reason in reasons)


@pytest.mark.parametrize("integration", [
    {"verification": "passed", "total": 0, "passed": 0, "failed": 0},
    {"verification": "passed", "total": 2, "passed": 1, "failed": 0},
    {"verification": "passed", "total": "one", "passed": 1, "failed": 0},
])
def test_stage6_rejects_zero_inconsistent_or_malformed_pass_counts(monkeypatch, integration):
    monkeypatch.setattr(settings, "model_mode", "live")
    verification, reasons = stage6._classify(
        integration=integration, staging_live=True,
        probes=[{"scenario": "s", "outcome": "clear"}],
        oracles=[{"vector": "v", "verdict": "match"}], goal_check=_goal())
    assert verification == "failed"
    assert any("integration_result" in reason for reason in reasons)


def test_malformed_goal_gaps_are_inconclusive_and_normalized():
    goal = stage6._normalise_goal_check({
        "verdict": "fulfilled",
        "gaps": [None, "bad", {"goal_clause": "x", "severity": "caveat"}],
    })
    assert goal == {
        "verdict": "unknown",
        "gaps": [{"goal_clause": "x", "severity": "caveat"}],
    }
    verification, _reasons = stage6._classify(
        integration=_integration(), staging_live=True,
        probes=[{"scenario": "s", "outcome": "clear"}], oracles=[], goal_check=goal)
    assert verification == "unverified"


@pytest.mark.parametrize("gaps", [None, [None, "bad"]])
def test_unfulfilled_survives_missing_or_malformed_gap_evidence(monkeypatch, gaps):
    monkeypatch.setattr(settings, "model_mode", "live")
    goal = stage6._normalise_goal_check({"verdict": "unfulfilled", "gaps": gaps})
    assert goal == {"verdict": "unfulfilled", "gaps": []}
    verification, reasons = stage6._classify(
        integration=_integration(), staging_live=True,
        probes=[{"scenario": "s", "outcome": "clear"}], oracles=[], goal_check=goal)
    assert verification == "failed"
    assert any("unfulfilled" in reason for reason in reasons)


class _QaDao:
    def __init__(self) -> None:
        self.tickets: dict[str, dict] = {}
        self.oracle_checks: list[dict] = []

    async def current_plan(self, _job_id):
        return {"body": {"modules": [], "topology": {"steps": []}}}

    async def create_ticket(self, **fields):
        ticket_id = f"ticket-{len(self.tickets) + 1}"
        self.tickets[ticket_id] = {**fields, "status": "open"}
        return ticket_id

    async def update_ticket(self, ticket_id, *, status):
        self.tickets[ticket_id]["status"] = status

    async def create_oracle_check(self, **fields):
        self.oracle_checks.append(fields)
        return "oracle-check"


class _QaCtx:
    def __init__(self) -> None:
        self.job_id = "qa-job"
        self.scope = "job:qa-job"
        self.complete = None
        self.dao = _QaDao()
        self.checkpoints = {
            "tests": [{"id": "T-1"}],
            "vectors": [],
            "adversarial_scenarios": [],
            "integration_result": _integration(),
        }
        self.events: list[tuple[str, dict]] = []
        self.advances: list[str] = []

    async def refresh(self):
        return {"id": self.job_id, "mode": "build", "goal": "process records", "spec": {}}

    async def get_checkpoint(self, key):
        return self.checkpoints.get(key)

    async def checkpoint(self, key, value):
        self.checkpoints[key] = value

    async def emit(self, event, payload):
        self.events.append((event, payload))

    async def advance(self, status):
        self.advances.append(status)


class _Handle:
    base_url = "http://staging.test"

    def __init__(self) -> None:
        self.stopped = False

    async def stop(self):
        self.stopped = True


class _Oracle:
    async def compute(self, *_args, **_kwargs):
        return {"expected": 1, "votes": [], "uncertain": False}


async def _run_qa(
    monkeypatch, *, probe_outcome: str, model_mode: str, override: bool, with_vector: bool = False,
):
    ctx = _QaCtx()
    if with_vector:
        ctx.checkpoints["vectors"] = [{
            "id": "V-1", "rule": "R-1", "rule_text": "return one", "inputs": {},
            "output_field": "value", "tolerance": "exact",
        }]
    handle = _Handle()
    goal_inputs = {"deploy_calls": 0}

    class Inspector:
        async def probe(self, *_args, scenario, **_kwargs):
            if probe_outcome == "finding":
                return {"title": "known defect", "severity": "major", "repro": {}}
            if probe_outcome == "inconclusive":
                raise stage6.ProbeInconclusive("instrument timeout", outcome="timeout")
            return None

        async def goal_check(self, *_args, probe_results, **_kwargs):
            goal_inputs["probe_results"] = probe_results
            return _goal()

    seats = {"inspector": Inspector(), "oracle": _Oracle()}

    async def deploy(*_args, **_kwargs):
        goal_inputs["deploy_calls"] += 1
        return handle

    async def staged_actual(*_args, **_kwargs):
        return 2, True

    monkeypatch.setattr(settings, "model_mode", model_mode)
    monkeypatch.setattr(stage6, "seat", lambda name: seats[name])
    monkeypatch.setattr(stage6, "_deploy_staging", deploy)
    monkeypatch.setattr(stage6, "_probe_tools", lambda *_args: {})
    monkeypatch.setattr(stage6, "_add_create_tool", lambda *_args: None)
    monkeypatch.setattr(stage6, "_staged_actual", staged_actual)
    monkeypatch.setattr(
        stage6.codeexec, "unverified_demo_delivery_allowed", lambda: override)
    return ctx, handle, goal_inputs


async def test_unverified_override_advances_without_qa_passed(monkeypatch):
    ctx, handle, goal_inputs = await _run_qa(
        monkeypatch, probe_outcome="inconclusive", model_mode="mock", override=True)

    await stage6.run(ctx)

    result = ctx.checkpoints["qa_result"]
    assert result["verification"] == "unverified"
    assert result["demo_override"] is True
    assert result["probes"]["inconclusive"] == result["probes"]["total"]
    assert result["oracles"]["outcomes"] == []
    assert result["tickets"]["outcomes"] == []
    assert result["goal_verdict"] == "fulfilled"
    assert goal_inputs["probe_results"]
    assert len(goal_inputs["probe_results"]) == len(stage6._GENERIC)
    assert {item["outcome"] for item in goal_inputs["probe_results"]} == {"inconclusive"}
    event_types = [event for event, _payload in ctx.events]
    assert E.QA_COMPLETED in event_types
    assert E.QA_PASSED not in event_types
    assert ctx.advances == ["delivering"]
    assert handle.stopped is True


async def test_known_finding_checkpoints_failed_and_never_calls_coder_or_advances(monkeypatch):
    ctx, _handle, _goal_inputs = await _run_qa(
        monkeypatch, probe_outcome="finding", model_mode="live", override=True)

    with pytest.raises(RuntimeError, match="QA verification failed"):
        await stage6.run(ctx)

    result = ctx.checkpoints["qa_result"]
    assert result["verification"] == "failed"
    assert result["demo_override"] is False
    assert result["tickets"]["opened"] == result["probes"]["finding"]
    assert result["tickets"]["human_review"] == result["tickets"]["opened"]
    assert set(ticket["status"] for ticket in ctx.dao.tickets.values()) == {"human_review"}
    event_types = [event for event, _payload in ctx.events]
    assert E.QA_COMPLETED in event_types
    assert E.QA_PASSED not in event_types
    assert E.TICKET_FIX_APPLIED not in event_types
    assert ctx.advances == []


async def test_failed_qa_retry_reuses_checkpoint_without_duplicate_side_effects(monkeypatch):
    ctx, _handle, goal_inputs = await _run_qa(
        monkeypatch, probe_outcome="finding", model_mode="live", override=True,
        with_vector=True)

    with pytest.raises(RuntimeError, match="QA verification failed"):
        await stage6.run(ctx)
    first_events = list(ctx.events)
    first_tickets = dict(ctx.dao.tickets)
    first_oracle_checks = list(ctx.dao.oracle_checks)

    with pytest.raises(RuntimeError, match="QA verification failed"):
        await stage6.run(ctx)

    assert ctx.events == first_events
    assert ctx.dao.tickets == first_tickets
    assert ctx.dao.oracle_checks == first_oracle_checks
    assert len(ctx.dao.oracle_checks) == 1
    assert goal_inputs["deploy_calls"] == 1


def test_stage7_missing_gate_blocks_even_when_override_is_enabled(monkeypatch):
    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: True)
    with pytest.raises(RuntimeError, match="missing required checkpoint"):
        stage7._build_delivery_gate(None, {
            "verification": "unverified", "demo_override": True, "reasons": []}, _goal())


def test_stage7_failed_gate_cannot_be_overridden(monkeypatch):
    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: True)
    integration = _integration("failed")
    with pytest.raises(RuntimeError, match="delivery gate failed"):
        stage7._build_delivery_gate(
            integration,
            _qa_evidence(integration, verification="failed"),
            _goal(),
        )


def test_stage7_inconsistent_passed_integration_counts_block(monkeypatch):
    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: True)
    inconsistent = {"verification": "passed", "total": 2, "passed": 1, "failed": 0}
    with pytest.raises(RuntimeError, match="integration"):
        stage7._build_delivery_gate(
            inconsistent,
            _qa_evidence(
                inconsistent, verification="unverified", reasons=["unverified"],
                demo_override=True),
            _goal(),
        )


def test_stage7_requires_and_cross_checks_stable_qa_evidence():
    integration = _integration()
    with pytest.raises(RuntimeError, match="missing stable QA evidence"):
        stage7._build_delivery_gate(
            integration, {"verification": "passed", "reasons": [], "demo_override": False},
            _goal())

    qa_result = _qa_evidence(integration, verification="passed")
    qa_result["goal_verdict"] = "partial"
    with pytest.raises(RuntimeError, match="does not match goal_check"):
        stage7._build_delivery_gate(integration, qa_result, _goal())


def test_stage7_rejects_passed_qa_with_inconclusive_outcome():
    integration = _integration()
    qa_result = _qa_evidence(integration, verification="passed")
    qa_result["probes"] = {
        "total": 1, "clear": 0, "finding": 0, "inconclusive": 1,
        "outcomes": [{"scenario": "s", "outcome": "inconclusive"}],
    }
    with pytest.raises(RuntimeError, match="inconsistent passed QA evidence"):
        stage7._build_delivery_gate(integration, qa_result, _goal())


def test_stage7_rejects_passed_qa_with_no_probe_evidence():
    integration = _integration()
    qa_result = _qa_evidence(integration, verification="passed")
    qa_result["probes"] = {
        "total": 0, "clear": 0, "finding": 0, "inconclusive": 0, "outcomes": [],
    }
    with pytest.raises(RuntimeError, match="inconsistent passed QA evidence"):
        stage7._build_delivery_gate(integration, qa_result, _goal())


@pytest.mark.parametrize("known_failure", ["finding", "mismatch"])
def test_stage7_demo_override_cannot_hide_known_qa_failure(monkeypatch, known_failure):
    monkeypatch.setattr(stage7.codeexec, "unverified_demo_delivery_allowed", lambda: True)
    integration = _integration("unverified")
    qa_result = _qa_evidence(
        integration, verification="unverified", reasons=["inconclusive"], demo_override=True)
    if known_failure == "finding":
        qa_result["probes"] = {
            "total": 1, "clear": 0, "finding": 1, "inconclusive": 0,
            "outcomes": [{"scenario": "s", "outcome": "finding"}],
        }
    else:
        qa_result["oracles"] = {
            "total": 1, "match": 0, "mismatch": 1, "no_actual": 0,
            "oracle_uncertain": 0,
            "outcomes": [{"vector": "v", "verdict": "mismatch"}],
        }
    with pytest.raises(RuntimeError, match="delivery gate failed"):
        stage7._build_delivery_gate(integration, qa_result, _goal())


class _DeliveryDao:
    def __init__(self) -> None:
        self.version = None

    async def get_plan(self, _plan_id):
        return {"id": "plan-1", "body": {"mode": "build", "modules": [], "model_bom": {}}}

    async def current_plan(self, _job_id):
        return await self.get_plan("plan-1")

    async def list_amendments(self, _plan_id):
        return []

    async def list_consults(self, _plan_id):
        return []

    async def get_quote(self, _job_id):
        return None

    async def get_process_by_slug(self, _slug):
        return None

    async def create_process(self, **_fields):
        return "process-1"

    async def update_process(self, *_args, **_kwargs):
        return None

    async def create_version(self, **fields):
        self.version = fields
        return "version-1"

    async def update_run(self, *_args, **_kwargs):
        return None


class _DeliveryCtx:
    def __init__(self, *, unverified: bool) -> None:
        self.job_id = "delivery-job"
        self.scope = "job:delivery-job"
        self.dao = _DeliveryDao()
        integration_state = "unverified" if unverified else "passed"
        qa_state = "unverified" if unverified else "passed"
        goal_verdict = "partial" if unverified else "fulfilled"
        integration = _integration(integration_state)
        self.checkpoints = {
            "certified_plan_id": "plan-1",
            "integration_result": integration,
            "qa_result": _qa_evidence(
                integration,
                verification=qa_state,
                goal_verdict=goal_verdict,
                reasons=["mock evidence"] if unverified else [],
                demo_override=unverified,
            ),
            "goal_check": _goal(goal_verdict),
            "tests": [{"id": "T-1"}],
            "vectors": [{"id": "V-1"}],
        }
        self.events = []
        self.advances = []

    async def refresh(self):
        return {
            "id": self.job_id, "title": "Build truth", "goal": "truthful build",
            "mode": "build", "spec": {}, "origin": "build",
        }

    async def get_checkpoint(self, key):
        return self.checkpoints.get(key)

    async def emit(self, event, payload):
        self.events.append((event, payload))

    async def advance(self, status):
        self.advances.append(status)


async def test_stage7_requires_process_entrypoint_before_package_writes(monkeypatch, tmp_path):
    ctx = _DeliveryCtx(unverified=False)
    monkeypatch.setattr(stage7.workspace, "job_dir", lambda _job_id: tmp_path)

    with pytest.raises(RuntimeError, match="missing required build entrypoint process.py"):
        await stage7.run(ctx)

    assert ctx.dao.version is None
    assert ctx.events == []


async def test_stage7_rejects_process_entrypoint_symlink_escape(monkeypatch, tmp_path):
    ctx = _DeliveryCtx(unverified=False)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    try:
        (workspace_dir / "process.py").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this platform: {exc}")
    monkeypatch.setattr(stage7.workspace, "job_dir", lambda _job_id: workspace_dir)

    with pytest.raises(RuntimeError, match="rejected unsafe process.py path"):
        await stage7.run(ctx)

    assert ctx.dao.version is None
    assert ctx.events == []


@pytest.mark.parametrize(
    ("unverified", "label", "verification"),
    [(False, "VERIFIED", "passed"), (True, "UNVERIFIED DEMO", "unverified")],
)
async def test_stage7_packages_truthful_verification_and_null_image(
    monkeypatch, tmp_path: Path, unverified: bool, label: str, verification: str,
):
    ctx = _DeliveryCtx(unverified=unverified)
    captured = {}
    (tmp_path / "process.py").write_text(
        "def run_unit(unit):\n    return unit\n", encoding="utf-8")

    class Trust:
        async def write_docs(self, *_args, **_kwargs):
            return {"readme": "# Readme", "runbook": "# Runbook", "qa_report": "# QA"}

    async def invoice(*_args, **_kwargs):
        return {"total_usd": 0.0, "frontier_calls": 0}

    def assemble_package(**fields):
        captured.update(fields)
        return str(tmp_path / "package")

    monkeypatch.setattr(stage7, "seat", lambda _name: Trust())
    monkeypatch.setattr(stage7.invoice_mod, "build_invoice", invoice)
    monkeypatch.setattr(stage7.workspace, "read_src", lambda _job_id: [])
    monkeypatch.setattr(stage7.workspace, "job_dir", lambda _job_id: tmp_path)
    monkeypatch.setattr(stage7.workspace, "assemble_package", assemble_package)
    monkeypatch.setattr(
        stage7.codeexec, "unverified_demo_delivery_allowed", lambda: unverified)

    await stage7.run(ctx)

    manifest = captured["manifest"]
    assert manifest["verification"] == verification
    assert manifest["delivery_label"] == label
    assert manifest["image_tag"] is None
    assert manifest["package_summary"] == {
        "source_files": 1,
        "test_specs": 1,
        "oracle_vectors": 1,
        "runtime_image_built": False,
        "image_tag": None,
    }
    assert ctx.dao.version["image_tag"] is None
    registered = next(payload for event, payload in ctx.events if event == E.DELIVER_REGISTERED)
    assert registered["verification"] == verification
    assert registered["delivery_label"] == label
    assert registered["image_tag"] is None
    assert ctx.advances == ["done"]
