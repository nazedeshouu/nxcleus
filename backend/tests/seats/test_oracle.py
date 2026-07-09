"""Oracle: k-vote self-consistency, majority/uncertain logic, tolerance, adjudication."""
from _fake import Emits, FakeComplete, run

from app.seats import oracle


def test_majority_exact():
    val, uncertain = oracle.majority_vote([100.0, 100.0, 101.0], "exact")
    assert val == 100.0 and uncertain is False


def test_no_majority_is_uncertain():
    val, uncertain = oracle.majority_vote([100.0, 101.0, 102.0], "exact")
    assert uncertain is True and val is None


def test_epsilon_tolerance_clusters():
    val, uncertain = oracle.majority_vote([9.99, 10.00, 20.0], "epsilon:0.02")
    assert uncertain is False and abs(val - 9.99) < 0.02


def test_categorical_majority():
    val, uncertain = oracle.majority_vote(["amber", "Amber", "red"], "exact")
    assert val.lower() == "amber" and uncertain is False


def test_compute_runs_k_times_sanitized():
    fake = FakeComplete(responses=[{"value": 42.0, "working": "a"},
                                   {"value": 42.0, "working": "b"},
                                   {"value": 43.0, "working": "c"}])
    emits = Emits()
    result = run(oracle.compute(fake, emits, rule_text="score = a+b",
                                vector={"id": "V-1", "inputs": {"a": 1}}, k=3, tolerance="exact"))
    assert result["expected"] == 42.0 and result["uncertain"] is False
    assert len(result["votes"]) == 3
    assert len(fake.calls) == 3                      # k independent calls
    assert fake.data_classes_for("oracle") == {"SANITIZED"}
    assert "qa.oracle_vote" in emits.types()


def test_adjudicate():
    assert oracle.adjudicate(100.0, 100.004, "epsilon:0.01", False) == "match"
    assert oracle.adjudicate(100.0, 101.0, "exact", False) == "mismatch"
    assert oracle.adjudicate(None, 5, "exact", True) == "oracle_uncertain"
