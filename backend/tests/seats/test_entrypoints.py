"""Canonical engine entrypoints (app/seats/_placeholder.py names) are present on the real
modules and delegate to the rich harnesses — so seatlib's per-attribute SeatProxy swaps them in
with zero stage edits."""
from _fake import Emits, FakeComplete, run

from app.seats import (certifier, coder, conductor, consolidator, inspector, oracle, planner, trust)

# The canonical surface the engine calls (must exist on the real modules).
CANONICAL = {
    "trust": ["build_spec", "distill_policy", "write_docs", "sanitize_consult"],
    "planner": ["plan", "replan"],
    "certifier": ["certify", "triage_refine"],
    "conductor": ["review"],
    "coder": ["build_module", "fix"],
    "consolidator": ["consolidate"],
    "oracle": ["compute"],
    "inspector": ["goal_check"],   # probe still under negotiation (tools vs base_url) — flagged
}
MODS = {"trust": trust, "planner": planner, "certifier": certifier, "conductor": conductor,
        "coder": coder, "consolidator": consolidator, "oracle": oracle, "inspector": inspector}


def test_canonical_entrypoints_present():
    for seat, names in CANONICAL.items():
        for n in names:
            assert hasattr(MODS[seat], n), f"{seat}.{n} missing (breaks seatlib swap)"


def test_build_spec_delegates():
    spec = {"title": "KYC", "narrative": "n", "mode": {"recommended": "build"},
            "sensitivity_report": {"pii_fields_masked": 3}}
    fake = FakeComplete(responses=[spec])
    out = run(trust.build_spec(fake, emits := Emits(), request="onboard customers", files=[],
                               code_map={}, db_schema={}, policy={"rules": []}, messages=[]))
    assert out["title"] == "KYC"
    assert "boundary.sanitized" in emits.types()


def test_write_docs_shape():
    fake = FakeComplete(responses=[{"readme_md": "# R", "runbook_md": "# B"}])
    out = run(trust.write_docs(fake, Emits(), plan={"mode": "build", "modules": [{"id": "m", "name": "sanctions"}]},
                               goal="screen"))
    assert set(out) == {"readme", "runbook", "qa_report", "entry_module"}
    assert out["entry_module"] == "sanctions"


def test_sanitize_consult_returns_pair():
    fake = FakeComplete(responses=[{"clean": True, "residuals": [], "masked_payload": "hi «PERSON_1»"}])
    masked, receipt = run(trust.sanitize_consult(fake, Emits(), payload="hi John",
                                                 vault_map={"John": "«PERSON_1»"}))
    assert isinstance(masked, str) and isinstance(receipt, dict)
    assert receipt["clean"] is True


def test_build_module_delegates():
    fake = FakeComplete(responses=[{"files": [{"path": "src/m.py", "content": "..."}], "notes": "ok"}])
    out = run(coder.build_module(fake, Emits(), module={"id": "m"}, interfaces=[], tests=[]))
    assert out["files"][0]["path"] == "src/m.py"


def test_triage_refine_shape():
    fake = FakeComplete(responses=[{"finding_id": "R-1", "check": "refine", "triage": "consult",
                                    "severity": "structural",
                                    "consult_request": {"scope": {"only_regions": ["mod_x"]},
                                                        "question": "redesign?"}}])
    out = run(certifier.triage_refine(fake, Emits(), plan={"modules": []}, request="add Spanish"))
    assert out["triage"] == "consult" and out["regions"] == ["mod_x"]
    assert out["rationale"] == "redesign?"


def test_goal_check_alias():
    fake = FakeComplete(responses=[{"verdict": "fulfilled", "gaps": []}])
    out = run(inspector.goal_check(fake, Emits(), goal="g", manifest={}, ac_outcomes=[], probe_results=[]))
    assert out["verdict"] == "fulfilled"


def test_conductor_review_accepts_dag_dicts_as_remaining():
    plan = {"modules": [{"id": "mod_a"}], "dag": [{"task": "t_a", "module": "mod_a"}],
            "model_bom": {}}
    fake = FakeComplete(responses=[{"verdict": "proceed", "wave_assessment": "ok",
                                    "amendments": [], "rework": []}])
    review = run(conductor.review(fake, Emits(), plan=plan, goal="g", wave_outputs=[],
                                  remaining=[{"task": "t_b", "module": "mod_b"}]))
    assert review["verdict"] == "proceed"
