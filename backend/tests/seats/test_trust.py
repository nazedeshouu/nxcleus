"""Trust: intake, mode classification, policy distillation, brief composition, sweep, docs.
All trust dispatches are RAW (it reads raw input); the BRIEF it emits is sanitized content."""
from _fake import Emits, FakeComplete, run

from app.seats import trust


def test_intake_turn():
    fake = FakeComplete(responses=[{"spec_updates": {"title": "KYC"}, "assistant_message": "Got it.",
                                    "missing": ["volume"], "ready_for_planning": False}])
    emits = Emits()
    out = run(trust.intake_turn(fake, emits, draft_spec={}, history=[], user_message="build KYC"))
    assert out["assistant_message"] == "Got it." and out["ready_for_planning"] is False
    assert fake.data_classes_for("trust") == {"RAW"}
    assert "intake.turn" in emits.types()


def test_classify_mode():
    fake = FakeComplete(responses=[{"recommended": "process", "confirmed": None,
                                    "rationale": "independent units"}])
    emits = Emits()
    mode = run(trust.classify_mode(fake, emits, spec={"title": "sweep contracts"}))
    assert mode["recommended"] == "process"
    assert "intake.mode_classified" in emits.types()


def test_distill_policy_baseline_flag():
    fake = FakeComplete(responses=[{"rules": [
        {"id": "RP-1", "kind": "never_leak", "description": "client names", "origin": "pii_baseline"},
        {"id": "RP-2", "kind": "mask", "description": "account numbers", "origin": "pii_baseline"}]}])
    emits = Emits()
    policy = run(trust.distill_policy(fake, emits, sources=[{"kind": "text", "ref": "typed"}]))
    assert len(policy["rules"]) == 2
    assert emits.payload("intake.policy_registered")["baseline_only"] is True


def test_compose_brief_emits_sensitivity():
    spec = {"title": "KYC/AML onboarding", "narrative": "sanitized restatement",
            "mode": {"recommended": "build"},
            "entities": [{"name": "Applicant", "fields": [{"name": "full_name", "type": "string", "pii": True}]}],
            "sensitivity_report": {"pii_fields_masked": 7, "documents_ocred": 3,
                                   "policy_rules_applied": ["RP-1", "RP-3"], "identifiers_generalized": 12}}
    fake = FakeComplete(responses=[spec])
    emits = Emits()
    brief = run(trust.compose_brief(fake, emits, raw_request="onboard customers",
                                    raw_context={}, policy={"rules": []}))
    assert brief["title"] == "KYC/AML onboarding"
    assert brief["sensitivity_report"]["pii_fields_masked"] == 7
    assert fake.data_classes_for("trust") == {"RAW"}
    assert emits.payload("boundary.sanitized")["identifiers_generalized"] == 12


def test_sanitization_sweep_flags_residual():
    fake = FakeComplete(responses=[{"clean": False,
                                    "residuals": [{"span": "John Roe", "kind": "person",
                                                   "replacement": "«PERSON_1»"}],
                                    "masked_payload": "flag «PERSON_1»"}])
    emits = Emits()
    out = run(trust.sanitization_sweep(fake, emits, candidate_payload="flag John Roe",
                                       placeholder_tokens=["«PERSON_1»"]))
    assert out["clean"] is False and len(out["residuals"]) == 1
    assert emits.payload("boundary.sweep")["residuals"] == 1


def test_generate_docs():
    fake = FakeComplete(responses=[{"readme_md": "# KYC\n...", "runbook_md": "# Runbook\n..."}])
    emits = Emits()
    out = run(trust.generate_docs(fake, emits, plan={"mode": "build"}, goal="screen applicants"))
    assert out["readme_md"].startswith("# KYC")
    assert "deliver.docs_generated" in emits.types()
