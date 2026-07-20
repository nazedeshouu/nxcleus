from __future__ import annotations

import pytest

from app.boundary import intake
from app.certify import stage2
from app.db import dao
from app.ids import deterministic
from app.orchestrator.engine import _block_job, engine
from app.runtime import workspace


async def test_retry_claims_blocked_job_once(monkeypatch):
    job_id = await dao.create_job(title="retry", request="build a claims review process")
    await _block_job(job_id, "planning", "planner unavailable")
    wakes: list[str] = []
    monkeypatch.setattr(engine, "wake_job", wakes.append)

    job, retried, target = await engine.retry_job(job_id)
    assert retried is True and target == "planning"
    assert job["status"] == "planning" and wakes == [job_id]

    job, retried, target = await engine.retry_job(job_id)
    assert retried is False and target == "planning"
    assert job["status"] == "planning" and wakes == [job_id]


async def test_correction_reenters_intake_and_reaches_trust_context(monkeypatch):
    request = "build a claims review process"
    correction = "Only review claims above 2500 USD and return a CSV."
    job_id = await dao.create_job(title="correct", request=request)
    await _block_job(job_id, "planning", "the threshold was ambiguous")
    monkeypatch.setattr(engine, "wake_job", lambda _job_id: None)

    job, retried, target = await engine.retry_job(job_id, correction)
    assert retried is True and target == "intake" and job["status"] == "intake"
    messages = await dao.list_messages(job_id)
    assert [m["content"] for m in messages] == [request, correction]
    assert await dao.get_checkpoint(f"job:{job_id}", "retry_context") == {
        "failed_stage": "planning",
        "target_stage": "intake",
        "correction": correction,
    }

    captured: dict = {}

    class Trust:
        async def distill_policy(self, *_args, **_kwargs):
            return {"sources": [], "rules": []}

        async def build_spec(self, *_args, **kwargs):
            captured["messages"] = kwargs["messages"]
            return {
                "title": "Claims review",
                "narrative": "Review claims above the corrected threshold.",
                "mode": {"recommended": "build", "rationale": "interdependent workflow"},
                "sensitivity_report": {},
            }

    monkeypatch.setattr(intake, "seat", lambda _name: Trust())

    class Context:
        job_id = ""
        sovereign = False
        complete = None
        dao = dao

        def __init__(self, jid: str):
            self.job_id = jid

        async def refresh(self):
            return await dao.get_job(self.job_id)

        async def emit(self, *_args, **_kwargs):
            return None

        async def checkpoint(self, key, value):
            await dao.set_checkpoint(f"job:{self.job_id}", key, value)

        async def advance(self, status):
            await dao.update_job(self.job_id, status=status)

    await intake.run(Context(job_id))
    assert captured["messages"] == [
        {"role": "customer", "content": request},
        {"role": "customer", "content": correction},
    ]


async def test_build_retry_clears_terminal_fanout_evidence(monkeypatch):
    job_id = await dao.create_job(title="retry fanout", request="audit the claims corpus")
    scope = f"job:{job_id}"
    await dao.set_checkpoint(scope, "fanout_run_id", "run-old")
    await dao.set_checkpoint(scope, "fanout_result", {
        "run_id": "run-old", "status": "failed", "verification": "failed",
    })
    await _block_job(job_id, "building", "fan-out failed")
    monkeypatch.setattr(engine, "wake_job", lambda _job_id: None)

    _job, retried, target = await engine.retry_job(job_id)

    assert retried is True and target == "building"
    assert await dao.get_checkpoint(scope, "fanout_run_id") is None
    assert await dao.get_checkpoint(scope, "fanout_result") is None


async def test_qa_retry_discards_terminal_qa_evidence(monkeypatch):
    job_id = await dao.create_job(title="retry qa", request="build a claims review process")
    scope = f"job:{job_id}"
    await dao.set_checkpoint(scope, "qa_result", {
        "verification": "failed", "reasons": ["probe failed"],
    })
    await dao.set_checkpoint(scope, "goal_check", {
        "verdict": "not_fulfilled", "gaps": ["probe failed"],
    })
    await _block_job(job_id, "qa", "probe failed")
    monkeypatch.setattr(engine, "wake_job", lambda _job_id: None)

    _job, retried, target = await engine.retry_job(job_id)

    assert retried is True and target == "qa"
    assert await dao.get_checkpoint(scope, "qa_result") is None
    assert await dao.get_checkpoint(scope, "goal_check") is None


async def test_correction_discards_old_generated_state(monkeypatch):
    job_id = await dao.create_job(title="correct build", request="build a claims review process")
    scope = f"job:{job_id}"
    derived = (
        "clarifications", "tests", "vectors", "adversarial_scenarios", "certified_plan_id",
        "fanout_result", "fanout_run_id", "consolidation_assembled",
        "consolidation_fix_state", "integration_result", "qa_result", "goal_check",
    )
    for key in derived:
        await dao.set_checkpoint(scope, key, {"stale": key})
    await dao.upsert_build_task(
        task_id="bt_old", job_id=job_id, module_id="old-module", wave=0, status="done",
        assigned_backend="local:test", attempts=1,
    )
    root = workspace.job_dir(job_id)
    stale_file = root / "src" / "old_result.py"
    stale_file.write_text("OLD_RESULT = True\n", encoding="utf-8")
    await _block_job(job_id, "qa", "old QA failed")
    monkeypatch.setattr(engine, "wake_job", lambda _job_id: None)

    _job, retried, target = await engine.retry_job(job_id, "Use the corrected threshold.")

    assert retried is True and target == "intake"
    assert [await dao.get_checkpoint(scope, key) for key in derived] == [None] * len(derived)
    assert await dao.list_build_tasks(job_id) == []
    assert not root.exists()


async def test_correction_certifies_new_draft_and_carries_conversation(monkeypatch):
    request = "build a claims review process"
    correction = "Only review claims above 2500 USD."
    job_id = await dao.create_job(title="correct plan", request=request)
    await dao.add_message(job_id, "customer", request)
    await dao.add_message(job_id, "customer", correction)
    await dao.create_plan(
        job_id=job_id, version=1, status="draft", body={"marker": "corrected"},
        plan_id=deterministic("plan", job_id, "v1"),
    )
    await dao.create_plan(
        job_id=job_id, version=2, status="certified", body={"marker": "stale"},
        plan_id=deterministic("plan", job_id, "certified"),
    )
    captured: dict = {}

    class Captured(Exception):
        pass

    class Certifier:
        async def certify(self, _complete, _emit, *, plan, raw_context, policy):
            captured.update(plan=plan, raw_context=raw_context, policy=policy)
            raise Captured

    class Context:
        sovereign = False
        complete = None
        dao = dao

        def __init__(self, jid: str):
            self.job_id = jid

        async def refresh(self):
            return await dao.get_job(self.job_id)

        async def emit(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(stage2, "seat", lambda _name: Certifier())

    with pytest.raises(Captured):
        await stage2.run(Context(job_id))

    assert captured["plan"]["marker"] == "corrected"
    assert captured["raw_context"]["messages"] == [
        {"role": "customer", "content": request},
        {"role": "customer", "content": correction},
    ]
