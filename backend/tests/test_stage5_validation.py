from __future__ import annotations

import pytest

from app.consolidate import stage5
from app.events import E


def _verification(state: str) -> dict:
    return {
        "verification": state,
        "total": 1,
        "passed": 1 if state == "passed" else 0,
        "failed": 1 if state == "failed" else 0,
        "sandboxed": state != "unverified",
        "reason": state,
    }


class _Dao:
    def __init__(self):
        self.statuses = {}
        self.created = []

    async def get_plan(self, _plan_id):
        return {"body": {"modules": [{"id": "mod_a"}], "interfaces": [], "dag": []}}

    async def current_plan(self, _job_id):
        return await self.get_plan(None)

    async def create_ticket(self, **ticket):
        ticket_id = f"ticket-{len(self.created) + 1}"
        self.created.append((ticket_id, ticket))
        self.statuses[ticket_id] = "open"
        return ticket_id

    async def update_ticket(self, ticket_id, *, status):
        self.statuses[ticket_id] = status


class _Ctx:
    def __init__(self):
        self.job_id = "job-stage5"
        self.scope = "job:job-stage5"
        self.complete = None
        self.dao = _Dao()
        self.checkpoints = {"certified_plan_id": "plan-1", "tests": [{"id": "T-1"}]}
        self.events = []
        self.advances = []

    async def refresh(self):
        return {"id": self.job_id}

    async def get_checkpoint(self, key):
        return self.checkpoints.get(key)

    async def checkpoint(self, key, value):
        self.checkpoints[key] = value

    async def emit(self, event_type, payload):
        self.events.append((event_type, payload))

    async def advance(self, status):
        self.advances.append(status)


def _prepare_workspace(monkeypatch, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod_a.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (tmp_path / "process.py").write_text("VALUE = 'entry'\n", encoding="utf-8")
    monkeypatch.setattr(stage5.workspace, "job_dir", lambda _job_id: tmp_path)
    monkeypatch.setattr(stage5.workspace, "merge_agent_src", lambda _job_id: [])


def test_source_mapping_and_fix_preserve_canonical_path_case(monkeypatch, tmp_path):
    (tmp_path / "src").mkdir()
    source_path = tmp_path / "src" / "Mod_A.py"
    source_path.write_text("VALUE = 'old'\n", encoding="utf-8")
    monkeypatch.setattr(stage5.workspace, "job_dir", lambda _job_id: tmp_path)

    current = stage5._source_mapping("job-stage5")
    fixed = stage5._content_changing_fix(
        {"files": [{"path": "src/mod_a.py", "content": "VALUE = 'fixed'\n"}]},
        current,
    )

    assert current == {"src/Mod_A.py": "VALUE = 'old'\n"}
    assert fixed[0]["path"] == "src/Mod_A.py"


@pytest.mark.asyncio
async def test_fix_is_written_rerun_passes_and_ticket_is_verified(monkeypatch, tmp_path):
    _prepare_workspace(monkeypatch, tmp_path)
    ctx = _Ctx()
    captured = {}

    class Consolidator:
        async def consolidate(self, *_args, **kwargs):
            captured["source_files"] = kwargs["source_files"]
            return {"files": [{"path": "process.py", "content": "VALUE = 'entry'\n"}]}

    class Coder:
        async def fix(self, *_args, **kwargs):
            captured["module_src"] = kwargs["module_src"]
            return {"files": [{"path": "src/mod_a.py", "content": "VALUE = 'fixed'\n"}]}

    seats = {"consolidator": Consolidator(), "coder": Coder()}
    monkeypatch.setattr(stage5, "seat", lambda name: seats[name])
    results = iter([_verification("failed"), _verification("passed")])

    async def run_tests(**_kwargs):
        return next(results)

    monkeypatch.setattr(stage5.codeexec, "run_tests", run_tests)
    await stage5.run(ctx)

    assert any(source["content"] == "VALUE = 'old'\n" for source in captured["source_files"])
    assert captured["module_src"]["src/mod_a.py"] == "VALUE = 'old'\n"
    assert (tmp_path / "src" / "mod_a.py").read_text(encoding="utf-8") == "VALUE = 'fixed'\n"
    assert ctx.dao.statuses == {"ticket-1": "verified"}
    assert ctx.advances == ["qa"]
    assert any(event == E.TICKET_VERIFIED for event, _payload in ctx.events)


@pytest.mark.asyncio
async def test_resume_verifies_tracked_ticket_after_crash_post_write(monkeypatch, tmp_path):
    _prepare_workspace(monkeypatch, tmp_path)
    ctx = _Ctx()

    class SimulatedProcessCrash(BaseException):
        pass

    class Consolidator:
        async def consolidate(self, *_args, **_kwargs):
            return {"files": [{"path": "process.py", "content": "VALUE = 'entry'\n"}]}

    class Coder:
        async def fix(self, *_args, **_kwargs):
            return {"files": [{"path": "src/mod_a.py", "content": "VALUE = 'fixed'\n"}]}

    seats = {"consolidator": Consolidator(), "coder": Coder()}
    monkeypatch.setattr(stage5, "seat", lambda name: seats[name])
    results = iter([_verification("failed"), _verification("passed")])

    async def run_tests(**_kwargs):
        return next(results)

    monkeypatch.setattr(stage5.codeexec, "run_tests", run_tests)
    real_write_files = stage5.workspace.write_files
    writes = {"count": 0}

    def crash_after_write(*args, **kwargs):
        written = real_write_files(*args, **kwargs)
        writes["count"] += 1
        if writes["count"] == 2:
            raise SimulatedProcessCrash
        return written

    monkeypatch.setattr(stage5.workspace, "write_files", crash_after_write)
    with pytest.raises(SimulatedProcessCrash):
        await stage5.run(ctx)

    state = ctx.checkpoints[stage5._FIX_STATE_CHECKPOINT]
    assert state == {"attempts": 1, "tickets": ["ticket-1"]}
    assert ctx.dao.statuses == {"ticket-1": "in_fix"}
    assert (tmp_path / "src" / "mod_a.py").read_text(encoding="utf-8") == "VALUE = 'fixed'\n"

    monkeypatch.setattr(stage5.workspace, "write_files", real_write_files)
    await stage5.run(ctx)

    assert ctx.dao.statuses == {"ticket-1": "verified"}
    assert ctx.advances == ["qa"]
    assert any(event == E.TICKET_IN_FIX for event, _payload in ctx.events)
    assert any(event == E.TICKET_VERIFIED for event, _payload in ctx.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("fix_files", [
    [],
    [{"path": "src/mod_a.py", "content": "VALUE = 'old'\n"}],
])
async def test_empty_or_noop_fix_goes_to_human_review_and_does_not_advance(
    monkeypatch, tmp_path, fix_files,
):
    _prepare_workspace(monkeypatch, tmp_path)
    ctx = _Ctx()

    class Consolidator:
        async def consolidate(self, *_args, **_kwargs):
            return {"files": [{"path": "process.py", "content": "VALUE = 'entry'\n"}]}

    class Coder:
        async def fix(self, *_args, **_kwargs):
            return {"files": fix_files}

    seats = {"consolidator": Consolidator(), "coder": Coder()}
    monkeypatch.setattr(stage5, "seat", lambda name: seats[name])

    async def failed(**_kwargs):
        return _verification("failed")

    monkeypatch.setattr(stage5.codeexec, "run_tests", failed)
    with pytest.raises(ValueError, match="no files|did not change"):
        await stage5.run(ctx)

    assert ctx.dao.statuses == {"ticket-1": "human_review"}
    assert ctx.advances == []


@pytest.mark.asyncio
async def test_fix_cap_still_failing_blocks_before_qa(monkeypatch, tmp_path):
    _prepare_workspace(monkeypatch, tmp_path)
    ctx = _Ctx()
    calls = {"fix": 0}

    class Consolidator:
        async def consolidate(self, *_args, **_kwargs):
            return {"files": [{"path": "process.py", "content": "VALUE = 'entry'\n"}]}

    class Coder:
        async def fix(self, *_args, **_kwargs):
            calls["fix"] += 1
            return {"files": [{"path": "process.py",
                                "content": f"VALUE = 'fix-{calls['fix']}'\n"}]}

    seats = {"consolidator": Consolidator(), "coder": Coder()}
    monkeypatch.setattr(stage5, "seat", lambda name: seats[name])

    async def failed(**_kwargs):
        return _verification("failed")

    monkeypatch.setattr(stage5.codeexec, "run_tests", failed)
    with pytest.raises(RuntimeError, match="fix cap"):
        await stage5.run(ctx)

    assert calls["fix"] == stage5._FIX_CAP
    assert set(ctx.dao.statuses.values()) == {"human_review"}
    assert ctx.advances == []


@pytest.mark.asyncio
@pytest.mark.parametrize("override, expected_advance", [(False, []), (True, ["qa"])])
async def test_unverified_requires_explicit_demo_override(
    monkeypatch, tmp_path, override, expected_advance,
):
    _prepare_workspace(monkeypatch, tmp_path)
    ctx = _Ctx()

    class Consolidator:
        async def consolidate(self, *_args, **_kwargs):
            return {"files": [{"path": "process.py", "content": "VALUE = 'entry'\n"}]}

    monkeypatch.setattr(stage5, "seat", lambda _name: Consolidator())

    async def unverified(**_kwargs):
        return {**_verification("unverified"), "sandboxed": True}

    monkeypatch.setattr(stage5.codeexec, "run_tests", unverified)
    monkeypatch.setattr(
        stage5.codeexec, "unverified_demo_delivery_allowed", lambda: override)

    if override:
        await stage5.run(ctx)
    else:
        with pytest.raises(RuntimeError, match="unverified"):
            await stage5.run(ctx)

    assert ctx.checkpoints["integration_result"]["verification"] == "unverified"
    assert ctx.advances == expected_advance
    if override:
        completed = next(
            payload for event, payload in ctx.events if event == E.CONSOLIDATE_COMPLETED)
        assert completed["verification"] == "unverified"
        assert completed["sandboxed"] is True
