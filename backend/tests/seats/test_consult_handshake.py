"""The certifier↔planner consult handshake: ONE scope-lock vocabulary, enforced at both ends.

Regression cover for the live dead-end where the certifier emitted JSONPath-ish `only_regions`
(`$.model_bom.seats`) that `planner.replan` rejected as out-of-scope, plus the amend-first soft
consult cap (a simple KYC plan should not emit eight consults).
"""
from _fake import Emits, FakeComplete, run

from app.seats import certifier, planner
from app.seats._common import normalize_regions, region_ids

PLAN = {
    "plan_id": "p1", "job_id": "j1", "version": 1, "mode": "build",
    "modules": [{"id": "mod_risk", "name": "risk"}, {"id": "mod_sanctions", "name": "sanctions"}],
    "interfaces": [{"id": "if_sanctions_result", "producer": "mod_sanctions"}],
    "dag": [{"task": "t_risk", "module": "mod_risk"}],
    "topology": {"unit": {"noun": "applicant"}, "steps": [{"id": "s_extract"}]},
    "model_bom": {"seats": [{"seat": "coder", "count": 1}], "fleet": {"parallel_width": 1}},
}


# ── the canonical vocabulary ──────────────────────────────────────────────────

def test_region_ids_covers_modules_interfaces_steps_and_dag():
    assert region_ids(PLAN) == {"mod_risk", "mod_sanctions", "if_sanctions_result",
                                "t_risk", "s_extract"}


def test_normalize_regions_passes_verbatim_ids():
    resolved, unresolved = normalize_regions(["mod_risk", "if_sanctions_result"], region_ids(PLAN))
    assert resolved == ["mod_risk", "if_sanctions_result"]
    assert unresolved == []


def test_normalize_regions_translates_jsonpath_forms():
    ids = region_ids(PLAN)
    resolved, unresolved = normalize_regions(
        ["$.modules.mod_risk", "modules[1].mod_sanctions", "mod_risk.algorithm"], ids)
    assert resolved == ["mod_risk", "mod_sanctions"]   # de-duped, order preserved
    assert unresolved == []


def test_normalize_regions_flags_untranslatable():
    resolved, unresolved = normalize_regions(["$.model_bom.seats", "risk_score"], region_ids(PLAN))
    assert resolved == []
    assert unresolved == ["$.model_bom.seats", "risk_score"]


# ── certifier end: emission is normalized / repaired / capped ─────────────────

def _checks_returning(consults_by_check: dict[str, dict]):
    """Handler that returns a scripted consult for named checks, empty for the rest, and
    canned goal/tests/scenarios so certify() runs end to end."""
    def handler(seat, messages, schema, idx):
        sysmsg = messages[0].content
        for check, consult in consults_by_check.items():
            if f"FOCUSED CHECK — {check}" in sysmsg:
                return {"findings": [consult]}
        if "FOCUSED CHECK" in sysmsg:
            return {"findings": []}
        if "You emit the GOAL" in sysmsg:
            return {"goal": "Applicants are screened and risk-scored."}
        if "IntegrationTestSpec" in sysmsg:
            return {"tests": [{"id": "T-1"}], "vectors": []}
        if "adversarial scenarios" in sysmsg:
            return {"scenarios": ["a", "b", "c"]}
        if "named plan regions that DO NOT EXIST" in sysmsg:  # repair reprompt
            return {"only_regions": ["mod_risk"]}
        return {"findings": []}
    return handler


def _consult(fid, only_regions):
    return {"finding_id": fid, "check": "data-completeness", "severity": "structural",
            "triage": "consult",
            "consult_request": {"scope": {"only_regions": only_regions}, "question": "redesign feed?"}}


def _run_certify(handler):
    fake = FakeComplete(handler=handler)
    emits = Emits()
    result = run(certifier.certify(fake, emits, plan=PLAN,
                                   raw_context={"request": "screen applicants", "vault": {}}))
    return result, emits, fake


def test_verbatim_consult_passes_through():
    result, emits, _ = _run_certify(_checks_returning(
        {"data-completeness": _consult("F-1", ["mod_risk"])}))
    consult = next(f for f in result["findings"] if f.get("triage") == "consult")
    assert consult["consult_request"]["scope"]["only_regions"] == ["mod_risk"]
    assert result["deferred_consults"] == []
    assert "certify.consult_requested" in emits.types()


def test_jsonpath_consult_is_translated_in_place():
    result, emits, _ = _run_certify(_checks_returning(
        {"data-completeness": _consult("F-1", ["$.modules.mod_risk", "if_sanctions_result.schema"])}))
    consult = next(f for f in result["findings"] if f.get("triage") == "consult")
    # normalized to verbatim plan ids, so the stage hands planner.replan a lock it will accept.
    assert consult["consult_request"]["scope"]["only_regions"] == ["mod_risk", "if_sanctions_result"]
    assert result["deferred_consults"] == []


def test_untranslatable_consult_is_repaired_then_kept():
    # only_regions names no real region -> one repair reprompt -> handler returns "mod_risk".
    result, emits, fake = _run_certify(_checks_returning(
        {"data-completeness": _consult("F-1", ["$.model_bom.seats"])}))
    consult = next((f for f in result["findings"] if f.get("triage") == "consult"), None)
    assert consult is not None
    assert consult["consult_request"]["scope"]["only_regions"] == ["mod_risk"]
    assert "certify.consult_repaired" in emits.types()
    assert result["deferred_consults"] == []


def test_untranslatable_consult_is_dropped_when_repair_also_fails():
    def handler(seat, messages, schema, idx):
        sysmsg = messages[0].content
        if "named plan regions that DO NOT EXIST" in sysmsg:
            return {"only_regions": ["still_not_a_region"]}   # repair fails too
        return _checks_returning({"data-completeness": _consult("F-9", ["$.model_bom.seats"])})(
            seat, messages, schema, idx)

    result, emits, _ = _run_certify(handler)
    assert all(f.get("triage") != "consult" for f in result["findings"])   # dropped from findings
    assert [d["finding_id"] for d in result["deferred_consults"]] == ["F-9"]
    assert result["deferred_consults"][0]["reason"] == "no_valid_region"
    assert "system.notice" in emits.types()


def test_soft_consult_cap_defers_overflow():
    # three checks each raise a valid consult; only SOFT_CONSULT_CAP are kept, the rest deferred.
    result, emits, _ = _run_certify(_checks_returning({
        "data-completeness": _consult("F-1", ["mod_risk"]),
        "error-coverage": _consult("F-2", ["mod_sanctions"]),
        "interface-compat": _consult("F-3", ["if_sanctions_result"]),
    }))
    kept = [f for f in result["findings"] if f.get("triage") == "consult"]
    assert len(kept) == certifier.SOFT_CONSULT_CAP == 2
    assert len(result["deferred_consults"]) == 1
    assert result["deferred_consults"][0]["reason"] == "consult_cap"
    assert "system.notice" in emits.types()


# ── planner end: it accepts exactly this vocabulary, still rejects out-of-scope ─

def test_replan_accepts_certifier_normalized_lock():
    """The ids the certifier emits are precisely the ids replan enforces — end-to-end agreement."""
    before = PLAN
    after = {**PLAN, "modules": [{"id": "mod_risk", "name": "risk-v2"},
                                 {"id": "mod_sanctions", "name": "sanctions"}]}
    fake = FakeComplete(responses=[after])
    emits = Emits()
    out = run(planner.replan(fake, emits, plan=before, findings=["fix risk"],
                             scope_lock={"only_regions": ["mod_risk"]}))
    assert out["modules"][0]["name"] == "risk-v2"
    assert "plan.scope_violation" not in emits.types()


def test_replan_still_rejects_edit_outside_lock():
    before = PLAN
    after = {**PLAN, "modules": [{"id": "mod_risk", "name": "risk"},
                                 {"id": "mod_sanctions", "name": "sanctions-EDITED"}]}
    fake = FakeComplete(responses=[after])
    emits = Emits()
    try:
        run(planner.replan(fake, emits, plan=before, findings=["x"],
                           scope_lock={"only_regions": ["mod_risk"]}))
    except ValueError:
        assert "plan.scope_violation" in emits.types()
        return
    raise AssertionError("expected ValueError: mod_sanctions edited outside the scope lock")
