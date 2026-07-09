"""Conductor and planner scope-lock enforcement (unbuilt-regions-only + only_regions)."""
from _fake import Emits, FakeComplete, run

from app.seats import conductor, planner


def _plan():
    return {"plan_id": "p1", "job_id": "j1", "version": 1, "mode": "build",
            "modules": [{"id": "mod_built", "name": "built"},
                        {"id": "mod_unbuilt", "name": "unbuilt"}],
            "interfaces": [], "dag": [{"task": "t_built", "module": "mod_built"},
                                       {"task": "t_unbuilt", "module": "mod_unbuilt"}],
            "model_bom": {"seats": [], "fleet": {"profile": "P2", "parallel_width": 1}}}


def test_conductor_drops_out_of_scope_amendments_and_dedupes_rework():
    fake = FakeComplete(responses=[{
        "verdict": "amend", "wave_assessment": "ok", "goal_drift": None,
        "amendments": [
            {"plan_ref": "mod_unbuilt", "patch": [{"op": "replace", "path": "/x", "value": 1}],
             "rationale": "in scope"},
            {"plan_ref": "mod_built", "patch": [{"op": "replace", "path": "/y", "value": 2}],
             "rationale": "ILLEGAL — already built"}],
        "rework": [{"module_id": "mod_built", "instruction": "fix a"},
                   {"module_id": "mod_built", "instruction": "fix a again"}],  # dupe
    }])
    emits = Emits()
    review = run(conductor.review(fake, emits, plan=_plan(), goal="g",
                                  wave_outputs={}, remaining_regions=["mod_unbuilt"]))
    assert len(review["amendments"]) == 1                    # out-of-scope dropped
    assert review["amendments"][0]["plan_ref"] == "mod_unbuilt"
    assert len(review["rework"]) == 1                        # deduped to 1 per module
    assert "plan.scope_violation" in emits.types()
    assert fake.data_classes_for("conductor") == {"RAW"}


def test_planner_replan_accepts_in_scope_change():
    before = _plan()
    after = _plan()
    after["modules"][1]["name"] = "unbuilt-v2"               # only mod_unbuilt changed
    fake = FakeComplete(responses=[after])
    emits = Emits()
    out = run(planner.replan(fake, emits, current_plan=before,
                             findings=["fix mod_unbuilt"], only_regions=["mod_unbuilt"]))
    assert out["modules"][1]["name"] == "unbuilt-v2"
    assert fake.data_classes_for("planner") == {"SANITIZED"}  # boundary: planner never RAW


def test_planner_replan_rejects_out_of_scope_change():
    before = _plan()
    after = _plan()
    after["modules"][0]["name"] = "built-EDITED"             # mod_built NOT in only_regions
    fake = FakeComplete(responses=[after])
    emits = Emits()
    try:
        run(planner.replan(fake, emits, current_plan=before,
                           findings=["x"], only_regions=["mod_unbuilt"]))
    except ValueError:
        assert "plan.scope_violation" in emits.types()
        return
    raise AssertionError("expected ValueError on out-of-scope re-plan")


def test_sandbox_out_of_scope_emits_notice():
    empty_topo_plan = {"plan_id": "p", "job_id": "j", "version": 1, "mode": "process",
                       "topology": {"unit": {"noun": "x"}, "steps": []},
                       "risks": ["That request needs data this company does not have."],
                       "model_bom": {"seats": [], "fleet": {}}}
    fake = FakeComplete(responses=[empty_topo_plan])
    emits = Emits()
    run(planner.sandbox_plan(fake, emits, prompt="do the impossible",
                             company="Meridian Bank", company_schema={"tables": []}))
    assert "system.notice" in emits.types()
