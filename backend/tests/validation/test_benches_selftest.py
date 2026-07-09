"""Validation-gate benches are wired correctly (self-test mode). The REAL go/no-go runs in
Wave 2 against a live P1 fleet (08 §7); these assert the harness + ground-truth plumbing."""
from tests.validation.ground_truth import VECTORS, claims_payout, kyc_level, kyc_score
from tests.validation.inspector_bench import _ScriptedInspector, evaluate_gate as insp_gate
from tests.validation.inspector_bench import run_inspector_bench
from tests.validation.oracle_bench import _PerfectOracle, evaluate_gate as orc_gate
from tests.validation.oracle_bench import run_oracle_bench

from _fake import run


def test_ground_truth_is_forty_vectors_with_expected():
    assert len(VECTORS) == 40
    assert all("expected" in v and "rule_text" in v and "inputs" in v for v in VECTORS)


def test_ground_truth_math():
    assert kyc_score({"sanctions_hit": 1, "pep_hit": 1, "adverse_media": 1,
                      "high_risk_country": 1, "structuring_flag": 1}) == 100
    assert kyc_level(70) == "red" and kyc_level(69) == "amber" and kyc_level(39) == "green"
    assert claims_payout({"claim_amount": 8000, "policy_limit": 5000,
                          "deductible": 250, "fraud_flag": 0}) == 4750.0
    assert claims_payout({"claim_amount": 8000, "policy_limit": 5000,
                          "deductible": 250, "fraud_flag": 1}) == 0.0


def test_oracle_bench_wiring_and_gate():
    report = run(run_oracle_bench(_PerfectOracle(), seat_label="selftest"))
    assert report["accuracy"] == 1.0 and report["correct"] == 40
    assert orc_gate(report)["pass"] is True


def test_inspector_bench_wiring_and_gate():
    report = run(run_inspector_bench(_ScriptedInspector(), seat_label="selftest"))
    assert report["completed"] == 12 and len(report["defects_found"]) == 4
    assert insp_gate(report)["pass"] is True
    # the mixed-swarm (looser) bar also passes
    assert insp_gate(report, mixed_swarm=True)["pass"] is True
