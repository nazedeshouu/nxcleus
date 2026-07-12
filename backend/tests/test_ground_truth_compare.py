"""Ground-truth compare (demo 5): the results surface diffs a run's flagged units against the
corpus's planted ground truth. Verifies the planted denominator over the real insurer seed and that
a synthetic run (perfect and imperfect) scores correctly. Pure function, no DB/app — fast.

Skips if infra/seeds/out/insurer.db has not been generated.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.sandbox import ground_truth

_DB = Path(__file__).resolve().parents[2] / "infra" / "seeds" / "out" / "insurer.db"
pytestmark = pytest.mark.skipif(not _DB.exists(), reason="insurer seed not generated")


def _planted_pairs() -> list[dict]:
    con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(ground_truth._INSURER_DUPLICATES.sql)]
    finally:
        con.close()


def test_perfect_run_matches_every_planted_pair():
    pairs = _planted_pairs()
    assert len(pairs) >= 120  # 120 deliberately planted + coincidental collisions in the same rule
    units = [{"unit_ref": f"dup:{p['id_a']}-{p['id_b']}", "result": {"candidate": dict(p)}}
             for p in pairs]
    rep = ground_truth.compare("insurer", units)
    assert rep["planted_total"] == len(pairs)
    assert rep["true_positive_count"] == len(pairs)
    assert rep["missed_count"] == 0
    assert rep["false_positive_count"] == 0


def test_imperfect_run_surfaces_miss_and_false_positive():
    pairs = _planted_pairs()
    units = [{"unit_ref": f"dup:{p['id_a']}-{p['id_b']}", "result": {"candidate": dict(p)}}
             for p in pairs[:-1]]  # drop one planted pair -> one miss
    units.append({"unit_ref": "dup:99-100000000",       # not a real pair -> one false positive
                  "result": {"candidate": {"id_a": 99, "id_b": 100_000_000}}})
    rep = ground_truth.compare("insurer", units)
    assert rep["missed_count"] == 1 and len(rep["missed"]) == 1
    assert rep["false_positive_count"] == 1 and len(rep["false_positives"]) == 1
    assert rep["true_positive_count"] == len(pairs) - 1


def test_unregistered_corpus_rejected():
    with pytest.raises(ValueError):
        ground_truth.compare("bank", [])
    assert not ground_truth.supported("bank")
    assert ground_truth.supported("insurer")
