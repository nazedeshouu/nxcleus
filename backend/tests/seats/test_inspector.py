"""Inspector: bounded tool loop (step cap, timeout, finding, pass), goal check, generators."""
from _fake import Emits, FakeComplete, run

from app.seats import inspector


async def _manifest():
    return {"name": "kyc", "input_schema": {}, "output_schema": {}}


async def _http(**kw):
    return {"status": 200, "body": {"ok": True}}


TOOLS = {"read_manifest": _manifest, "http_request": _http}


def test_step_cap_enforced():
    # model NEVER submits a finding -> loop must stop at step_budget and return None.
    fake = FakeComplete(handler=lambda *a: {"tool": "http_request",
                                            "http_request": {"method": "GET", "path": "/run"}})
    emits = Emits()
    ticket = run(inspector.probe(fake, emits, scenario={"id": "s1"}, tools=TOOLS, step_budget=5))
    assert ticket is None
    assert len(fake.calls) == 5                       # exactly the budget, never more
    assert "qa.probe_exhausted" in emits.types()


def test_submit_defect_returns_ticket():
    fake = FakeComplete(responses=[
        {"tool": "read_manifest"},
        {"tool": "submit_finding", "submit_finding": {
            "defect": True, "title": "500 on empty body", "request": {"path": "/run"},
            "response": {"status": 500}, "suspected_modules": ["mod_a"], "severity": "major"}},
    ])
    emits = Emits()
    ticket = run(inspector.probe(fake, emits, scenario={"id": "s2"}, tools=TOOLS, step_budget=15))
    assert ticket is not None
    assert ticket["instrument"] == "inspector" and ticket["severity"] == "major"
    assert ticket["repro"]["response"] == {"status": 500}
    assert "qa.finding" in emits.types()


def test_submit_pass_returns_none():
    fake = FakeComplete(responses=[{"tool": "submit_finding", "submit_finding": {"defect": False}}])
    emits = Emits()
    ticket = run(inspector.probe(fake, emits, scenario={"id": "s3"}, tools=TOOLS, step_budget=15))
    assert ticket is None
    assert "qa.probe_passed" in emits.types()


def test_deadline_short_circuits():
    fake = FakeComplete(handler=lambda *a: {"tool": "read_manifest"})
    emits = Emits()
    ticket = run(inspector.probe(fake, emits, scenario={"id": "s4"}, tools=TOOLS,
                                 step_budget=15, scenario_deadline_s=-1.0))
    assert ticket is None
    assert "qa.probe_timeout" in emits.types()
    assert len(fake.calls) == 0                       # deadline checked before first call


def test_goal_check():
    fake = FakeComplete(responses=[{"verdict": "partial",
                                    "gaps": [{"goal_clause": "flag adverse media",
                                              "evidence": "not implemented", "severity": "caveat"}]}])
    emits = Emits()
    check = run(inspector.goal_fulfillment_check(fake, emits, goal="screen applicants",
                                                 manifest={}, ac_outcomes=[], probe_results=[]))
    assert check["verdict"] == "partial" and len(check["gaps"]) == 1
    assert fake.data_classes_for("inspector") == {"SANITIZED"}
    assert "qa.goal_check" in emits.types()


def test_scenario_generators_merge_and_dedupe():
    generic = inspector.generic_probe_suite()
    assert len(generic) >= 7
    ac = inspector.ac_derived_scenarios([{"id": "AC-1", "text": "x", "verify": "inspector"},
                                         {"id": "AC-2", "text": "y", "verify": "test"}])
    assert len(ac) == 1                               # only the inspector-verified AC
    plan = inspector.plan_aware_scenarios(["transliterated sanctions name"])
    merged = inspector.merge_scenarios(generic, ac, plan, generic)  # duplicate generic ignored
    titles = [s["title"] for s in merged]
    assert len(titles) == len(set(titles))            # deduped
    assert any(s["source"] == "plan" for s in merged)
