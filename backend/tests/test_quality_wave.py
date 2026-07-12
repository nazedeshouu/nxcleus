"""Demo-quality wave (2026-07-10): judge-prompt confirmation frame (T1), zero-findings deliverables
(T2), and the bounded QA stage — probe sample + hard fix budget (T4). Mock mode, no live calls."""
from __future__ import annotations

import types

from app.db import dao
from app.qa import stage6
from app.runtime import deliverables
from app.runtime.operate import _CANDIDATE_FRAME, _DEFAULT_STEP, _judge_prompt, _judge_schema


# ---------------------------------------------------------------- T1: judge prompt confirmation frame
def test_judge_prompt_pair_unit_carries_both_sides_and_confirmation_frame():
    """A candidate-derived pair unit must reach the judge with BOTH sides' key fields AND the
    confirmation frame — so a true duplicate isn't rejected because its narratives legitimately
    differ (the demo-critical duplicate-claims miss)."""
    pair = {"claim_a": 140047, "claim_b": 140048, "policy_id": 469, "incident_date": "2025-07-08",
            "amount_a": 103693.31, "amount_b": 102007.58,
            "fnol_a": "a falling limb punched through overhead",
            "fnol_b": "a supply line under the sink let go and flooded the cooking area"}
    step = {"id": "s_judge", "prompt_spec": "Confirm whether this candidate pair is a duplicate claim."}
    prompt = _judge_prompt(step, pair, "flag duplicate claims", from_candidate=True)

    for field in ("140047", "140048", "103693.31", "102007.58", "469", "2025-07-08"):
        assert field in prompt, f"pair prompt missing {field}"
    assert _CANDIDATE_FRAME in prompt                 # confirmation framing present
    assert "Confirm whether this candidate pair" in prompt

    # a raw corpus unit (no upstream detection) is judged on its own content — no confirmation frame
    raw = _judge_prompt(step, {"note": "single row"}, "req", from_candidate=False)
    assert _CANDIDATE_FRAME not in raw


# -------------------------------------------------- T1b: malformed generated schema must not error units
def test_judge_schema_falls_back_when_output_schema_is_a_bare_ref():
    """A planner-generated step whose output_schema is a bare named $ref (unresolvable at judge time)
    gets the self-contained default schema, not the dangling ref."""
    assert _judge_schema({"output_schema": {"$ref": "reviewed_duplicate_pairs"}}) == \
        _DEFAULT_STEP["output_schema"]
    assert _judge_schema({}) == _DEFAULT_STEP["output_schema"]
    real = {"type": "object", "properties": {"flagged": {"type": "boolean"}}}
    assert _judge_schema({"output_schema": real}) == real   # a usable schema is kept


def test_schema_error_accepts_completion_when_schema_ref_is_unresolvable():
    """An unresolvable $ref is a schema bug, not a data failure — validation must accept the parsed
    completion rather than raise (which erroed every unit of a live run)."""
    from app.models.router import router
    # a real ValidationError still reports (repair path preserved)
    assert router._schema_error({}, {"type": "object", "required": ["x"]}) is not None
    # an unresolvable named $ref does NOT raise / does NOT fail the unit
    assert router._schema_error({"flagged": True}, {"$ref": "does_not_exist"}) is None


# ---------------------------------------------------------------- T2: zero-findings still delivers
def test_zero_findings_run_still_writes_both_artifacts():
    """A completed run with 0 flagged units must still produce report.html + a headers-only
    findings.csv, and the report must state what was checked (not a blank page)."""
    units = [{"unit_ref": f"sql:{i}", "status": "ok",
              "result": {"candidate": {"claim_a": i, "claim_b": i + 1}}} for i in range(5)]
    stats = {"units": 137, "ok": 137, "needs_review": 0, "error": 0, "sql_rows": 137}
    cost = {"total_usd": 0.6, "cost_per_unit": 0.004, "frontier_calls": 0}
    arts = deliverables.generate("ZEROFIND", process_name="Duplicate claims",
                                 goal="flag duplicate claims", corpus="insurer", stats=stats,
                                 cost=cost, units=units, deliverable=None)
    d = deliverables.run_dir("ZEROFIND")
    assert {a["kind"] for a in arts} == {"csv", "report"}
    assert (d / "report.html").exists() and (d / "findings.csv").exists()
    # headers-only CSV (no flagged rows), still a valid downloadable
    assert (d / "findings.csv").read_text().strip() == "unit_ref,status,review_verdict,review_note"
    report = (d / "report.html").read_text()
    assert "No findings flagged" in report and "137 candidate(s) examined" in report
    assert "flag duplicate claims" in report          # says what was checked

    # both endpoint-backed artifacts must ALWAYS land regardless of the planner's free-form
    # deliverable spec — odd casing ("CSV") OR a spec that names only one format must not 404 the
    # other download. Live runs hit both variants.
    for spec in ({"formats": ["CSV", "Report"]}, {"formats": ["csv"]}, {"formats": ["report"]}):
        arts_s = deliverables.generate(f"ZERO{abs(hash(str(spec)))}", process_name="P", goal="g",
                                       corpus="insurer", stats=stats, cost=cost, units=units,
                                       deliverable=spec)
        assert {a["kind"] for a in arts_s} == {"csv", "report"}, spec
        ds = deliverables.run_dir(f"ZERO{abs(hash(str(spec)))}")
        assert (ds / "report.html").exists() and (ds / "findings.csv").exists(), spec


def test_write_stub_guarantees_no_404_on_generator_failure():
    """The never-404 safety net: write_stub always leaves both artifacts on disk."""
    d = deliverables.run_dir("STUBRUN")
    arts = deliverables.write_stub("STUBRUN", process_name="P", goal="g", corpus="insurer",
                                   stats={"units": 3, "ok": 3}, cost={"total_usd": 0.0})
    assert {a["kind"] for a in arts} == {"csv", "report"}
    assert (d / "report.html").exists()
    assert (d / "findings.csv").read_text().startswith("unit_ref,status")


def test_report_surfaces_headline_stats_and_per_entity_reasoning():
    """The judge-readable report: scannable headline cards, the egress-by-zone card, a human
    summary sentence per flagged pair, and the model's cited reasoning where stored on the unit."""
    units = [
        {"unit_ref": "dup:497:48980", "status": "needs_review",
         "result": {"candidate": {"policy_id": 28909, "incident_date": "2024-03-30",
                                   "claim_id_1": 497, "claim_id_2": 48980,
                                   "amount_claimed_1": 494122.32, "amount_claimed_2": 519036.05,
                                   "percent_difference": 4.8}}},
        {"unit_ref": "dup:18330:39510", "status": "needs_review",
         "result": {"judge-shared-loss-event": {"findings": "Same policy 27189, within 5%.",
                                                 "flagged": True}}},
    ]
    stats = {"units": 138, "ok": 99, "needs_review": 39, "error": 0, "sql_rows": 138}
    cost = {"total_usd": 0.8552, "cost_per_unit": 0.006, "frontier_calls": 0}
    html = deliverables._report_html("R1", process_name="Duplicate claims", goal="flag dupes",
                                     corpus="insurer", stats=stats, cost=cost, units=units,
                                     granularity="per_entity",
                                     egress={"EXTERNAL": 0, "AMD_HOSTED": 138, "LOCAL": 12},
                                     duration_s=71.0)
    for needle in ("Units scanned", "Flagged", "Run cost", "Duration", "1m 11s", "138",
                   "amd hosted", "inside the boundary",          # egress card
                   "Claims", "494,122.32", "different claim IDs",  # human summary sentence
                   "Same policy 27189, within 5%."):              # per-entity model reasoning
        assert needle in html, needle


# ---------------------------------------------------------------- T4: bounded QA stage
def test_sample_probes_caps_and_keeps_every_source():
    scenarios = ([{"id": f"ac-{i}", "source": "ac"} for i in range(30)]
                 + [{"id": f"gen-{i}", "source": "generic"} for i in range(7)]
                 + [{"id": f"plan-{i}", "source": "plan"} for i in range(60)])
    out = stage6._sample_probes(scenarios, 40)
    assert len(out) == 40
    assert {s["source"] for s in out} == {"ac", "generic", "plan"}   # no whole class dropped
    # under the cap: untouched
    small = scenarios[:10]
    assert stage6._sample_probes(small, 40) == small


async def test_fix_loop_hard_budget_parks_overflow_and_reports_partial(monkeypatch):
    """More fixable tickets than the budget: coder.fix is called at most _FIX_ATTEMPT_BUDGET times,
    the overflow is parked for human review, and the loop reports partial QA. Always terminates."""
    scope = "job:qabudget"
    n = stage6._FIX_ATTEMPT_BUDGET + 5
    for i in range(n):
        await dao.create_ticket(scope=scope, source="inspector", severity="major",
                                title=f"t{i}", body={"i": i})

    fix_calls = {"n": 0}

    class _Coder:
        async def fix(self, *a, **k):
            fix_calls["n"] += 1

    monkeypatch.setattr(stage6, "seat", lambda name: _Coder())

    async def _emit(t, p=None):
        pass

    async def _ckpt(_k):
        return []

    ctx = types.SimpleNamespace(dao=dao, scope=scope, emit=_emit, complete=None, get_checkpoint=_ckpt)
    partial = await stage6._fix_loop(ctx)

    assert partial is True
    assert fix_calls["n"] == stage6._FIX_ATTEMPT_BUDGET          # never exceeds the hard budget
    assert await dao.list_tickets(scope=scope, status="open") == []   # nothing left to spin on
    assert len(await dao.list_tickets(scope=scope, status="human_review")) == 5   # the overflow


async def test_fix_loop_within_budget_is_not_partial(monkeypatch):
    """Fewer tickets than the budget: all fixed, no partial marker."""
    scope = "job:qasmall"
    for i in range(3):
        await dao.create_ticket(scope=scope, source="inspector", severity="major",
                                title=f"t{i}", body={"i": i})

    class _Coder:
        async def fix(self, *a, **k):
            pass

    monkeypatch.setattr(stage6, "seat", lambda name: _Coder())

    async def _emit(t, p=None):
        pass

    async def _ckpt(_k):
        return []

    ctx = types.SimpleNamespace(dao=dao, scope=scope, emit=_emit, complete=None, get_checkpoint=_ckpt)
    assert await stage6._fix_loop(ctx) is False
    assert len(await dao.list_tickets(scope=scope, status="fix_applied")) == 3
