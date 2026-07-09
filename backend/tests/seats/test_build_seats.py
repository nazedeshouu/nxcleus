"""Coder (implement/fix) and consolidator (merge) return typed CoderOutput with files."""
from _fake import Emits, FakeComplete, run

from app.seats import coder, consolidator


def test_coder_implement():
    fake = FakeComplete(responses=[{"files": [{"path": "src/mod_sanctions.py", "content": "async def run(): ..."}],
                                    "notes": "implemented"}])
    emits = Emits()
    out = run(coder.implement(fake, emits,
                              module_spec={"id": "mod_sanctions", "task_flags": ["greenfield-codegen"]},
                              interfaces=[{"id": "if_applicant"}], test_specs=[{"id": "T-1"}]))
    assert out["files"][0]["path"] == "src/mod_sanctions.py"
    assert fake.data_classes_for("coder") == {"RAW"}
    assert emits.payload("task.files_written")["module"] == "mod_sanctions"


def test_coder_fix():
    fake = FakeComplete(responses=[{"files": [{"path": "src/mod_risk.py", "content": "fixed"}],
                                    "notes": "banker's rounding"}])
    emits = Emits()
    out = run(coder.fix(fake, emits, ticket={"title": "rounding off"},
                        module_src={"src/mod_risk.py": "old"}, tests=[{"id": "T-2"}]))
    assert out["files"][0]["content"] == "fixed"
    assert "task.fix_applied" in emits.types()


def test_consolidator_detects_entrypoint():
    fake = FakeComplete(responses=[{"files": [
        {"path": "process.py", "content": "class Process: ..."},
        {"path": "src/mod_a.py", "content": "..."}], "notes": "wired"}])
    emits = Emits()
    out = run(consolidator.consolidate(fake, emits, modules=[{"id": "mod_a"}],
                                       interfaces=[], plan={"dag": []}))
    assert len(out["files"]) == 2
    assert emits.payload("consolidate.assembled")["has_entrypoint"] is True
    assert fake.data_classes_for("consolidator") == {"RAW"}
