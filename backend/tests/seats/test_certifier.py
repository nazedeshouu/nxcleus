"""Certifier: full certify() orchestration — checks, amendment application, consult routing,
deterministic rehydration, goal + tests + scenarios emission."""
from _fake import Emits, FakeComplete, run

from app.seats import certifier

PLAN = {
    "plan_id": "p1", "job_id": "j1", "version": 1, "mode": "build",
    "modules": [{"id": "mod_a", "name": "a", "task_flags": ["greenfield-codegen"],
                 "assumptions": ["«TABLE_A» has a unique key"]}],
    "interfaces": [], "dag": [{"task": "t_a", "module": "mod_a", "deps": []}],
    "model_bom": {"seats": [{"seat": "coder", "count": 1}],
                  "fleet": {"profile": "P2", "parallel_width": 1}},
}


def _handler(seat, messages, schema, idx):
    sysmsg = messages[0].content
    if "FOCUSED CHECK — interface-compat" in sysmsg:
        return {"findings": [{
            "finding_id": "F-1", "check": "interface-compat", "plan_ref": "modules.mod_a",
            "severity": "gap", "triage": "amend",
            "amendment": {"plan_ref": "modules.mod_a",
                          "patch": [{"op": "replace", "path": "/modules/0/name", "value": "sanctions"}],
                          "rationale": "real module name"}}]}
    if "FOCUSED CHECK — data-completeness" in sysmsg:
        return {"findings": [{
            "finding_id": "F-2", "check": "data-completeness", "plan_ref": "modules.mod_a",
            "severity": "structural", "triage": "consult",
            "consult_request": {"scope": {"only_regions": ["mod_a"]}, "question": "redesign feed?"}}]}
    if "FOCUSED CHECK" in sysmsg:
        return {"findings": []}
    if "You emit the GOAL" in sysmsg:
        return {"goal": "Applicants are screened against sanctions and risk-scored."}
    if "IntegrationTestSpec" in sysmsg:
        return {"tests": [{"id": "T-1", "module": "mod_a"}],
                "vectors": [{"id": "V-1", "rule": "NR-1", "inputs": {}}]}
    if "adversarial scenarios" in sysmsg:
        return {"scenarios": ["transliterated name", "dormant reactivation", "structuring run"]}
    return {"findings": []}


def test_certify_end_to_end():
    fake = FakeComplete(handler=_handler)
    emits = Emits()
    result = run(certifier.certify(fake, emits, plan=PLAN, raw_request="screen my applicants",
                                   raw_context={"tables": ["customers"]},
                                   vault={"«TABLE_A»": "customers"}))

    # 7 checks + goal + tests + scenarios = 10 calls, all RAW.
    assert len(fake.calls) == 10
    assert fake.data_classes_for("certifier") == {"RAW"}

    # both findings surfaced; one amended, one consulted.
    assert len(result["findings"]) == 2
    assert "certify.amendment" in emits.types()
    assert "certify.consult_requested" in emits.types()

    # rehydration replaced the one placeholder; version bumped; amended plan returned.
    assert result["identifiers_rehydrated"] == 1
    assert emits.payload("certify.certified")["version"] == 2
    assert result["certified_plan"]["version"] == 2
    assert result["certified_plan"]["modules"][0]["name"] == "sanctions"   # amendment applied
    assert "«TABLE_A»" not in str(result["certified_plan"])                # rehydrated

    # goal + tests + vectors + scenarios emitted.
    assert result["goal"].startswith("Applicants are screened")
    assert len(result["tests"]) == 1 and len(result["vectors"]) == 1
    assert len(result["adversarial_scenarios"]) == 3
    assert "certify.goal_set" in emits.types()


def test_refine_triage():
    fake = FakeComplete(responses=[{"finding_id": "R-1", "check": "refine", "triage": "amend",
                                    "severity": "gap",
                                    "amendment": {"plan_ref": "modules.mod_a",
                                                  "patch": [{"op": "add", "path": "/modules/0/x", "value": 1}],
                                                  "rationale": "add field"}}])
    emits = Emits()
    finding = run(certifier.refine_triage(fake, emits, certified_plan=PLAN,
                                          refine_request="also flag adverse media"))
    assert finding["triage"] == "amend"
    assert "refine.triaged" in emits.types()
