"""Planted-pattern ground truth for the results 'Compare with planted patterns' surface (demo 5).

Ground truth here is INFERRED BY THE DETECTION RULE, not a per-row manifest. Each seed generator
plants patterns deterministically (fixed RNG salt → byte-identical regen), and the corpus's
authoritative answer to "what actually matches pattern X" is exactly the structural SQL the
generator self-verifies with (see infra/seeds/insurer.py __main__). So `planted_total` is the count
that rule surfaces over the final DB — e.g. 137 duplicate-claim pairs = 120 deliberately planted +
coincidental collisions that also satisfy the same ±5% rule — and a flagged unit is a true positive
iff it names one of those pairs. Only builtin sandbox corpora with a registered rule are supported;
BYOD / custom datasets have no known plant and are rejected upstream.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from app.sandbox import seeds

_INT = re.compile(r"\d+")


@dataclass(frozen=True)
class _Pattern:
    label: str                       # human name of the planted phenomenon
    sql: str                         # canonical detection over the seed DB (the generator's own rule)
    key: Callable[[dict], frozenset]  # the id-set that identifies one planted entity in a result row
    detail: Callable[[dict], dict]    # readable fields a human/judge can eyeball


# insurer plant (a): duplicate claims — same policy + incident_date, amounts within 5%.
# Rule is verbatim from insurer.py's self-check (lines ~532-534); the entity is the claim PAIR.
_INSURER_DUPLICATES = _Pattern(
    label="Duplicate claims (same policy + incident date, amounts within 5%)",
    sql="""SELECT a.id AS id_a, b.id AS id_b, a.policy_id AS policy_id,
                  a.incident_date AS incident_date,
                  a.amount_claimed AS amount_a, b.amount_claimed AS amount_b
           FROM claims a JOIN claims b
             ON a.policy_id=b.policy_id AND a.incident_date=b.incident_date AND a.id<b.id
           WHERE ABS(a.amount_claimed-b.amount_claimed) <= 0.05*a.amount_claimed""",
    key=lambda r: frozenset({int(r["id_a"]), int(r["id_b"])}),
    detail=lambda r: {
        "claims": [int(r["id_a"]), int(r["id_b"])],
        "policy_id": int(r["policy_id"]),
        "incident_date": r["incident_date"],
        "amounts": [round(float(r["amount_a"]), 2), round(float(r["amount_b"]), 2)],
        "label": f'claims #{int(r["id_a"])} & #{int(r["id_b"])} · policy {int(r["policy_id"])}'
                 f' · {r["incident_date"]} · ${float(r["amount_a"]):,.0f} / ${float(r["amount_b"]):,.0f}',
    },
)

# company -> pattern. One entry today (the duplicate-claims demo); add a pattern by dropping in its
# generator-verified SQL + key/detail. ponytail: not pre-building the other 4 insurer plants or the
# 8 sibling corpora until a run actually targets them.
_REGISTRY: dict[str, _Pattern] = {"insurer": _INSURER_DUPLICATES}


def supported(company: str | None) -> bool:
    return bool(company) and company in _REGISTRY


def _ints(cand: dict, unit_ref: str) -> frozenset[int]:
    """Every integer a flagged unit names — candidate-row values + the digits joined into unit_ref
    (which _row_ref built from the row's *id columns). A pair match needs BOTH claim ids present, so
    stray ids (policy_id) don't create false matches."""
    got: set[int] = set()
    for v in cand.values():
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            got.add(v)
        elif isinstance(v, str) and v.isdigit():
            got.add(int(v))
    got.update(int(m) for m in _INT.findall(unit_ref or ""))
    return frozenset(got)


def compare(company: str, flagged_units: list[dict]) -> dict:
    """Compare a run's flagged units against the corpus's planted ground truth for `company`.

    flagged_units: run_units rows with status=='needs_review' (each dict has 'unit_ref' and a
    'result' whose 'candidate' is the SQL row that was flagged).
    Raises ValueError if the company has no registered plant (endpoint maps that to 400).
    """
    pat = _REGISTRY.get(company)
    if pat is None:
        raise ValueError(f"no planted ground truth registered for corpus '{company}'")
    path = seeds.seed_db_path(company)
    if path is None:
        raise ValueError(f"seed corpus for '{company}' is not present")

    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        gt = {pat.key(dict(row)): pat.detail(dict(row)) for row in con.execute(pat.sql)}
    finally:
        con.close()

    matched: set[frozenset] = set()
    false_positives: list[dict] = []
    for u in flagged_units:
        cand = (u.get("result") or {}).get("candidate") or u.get("result") or {}
        if not isinstance(cand, dict):
            cand = {}
        ids = _ints(cand, u.get("unit_ref", ""))
        hit = next((k for k in gt if k <= ids), None)
        if hit is not None:
            matched.add(hit)
        else:
            false_positives.append({"unit_ref": u.get("unit_ref"),
                                    "candidate": {k: cand[k] for k in list(cand)[:8]}})
    missed = [gt[k] for k in gt if k not in matched]

    _CAP = 200
    return {
        "company": company,
        "pattern": pat.label,
        "ground_truth_basis": "detection rule over the seeded corpus (deterministic plant, "
                              "not a per-row manifest)",
        "planted_total": len(gt),
        "flagged_total": len(flagged_units),
        "true_positive_count": len(matched),
        "false_positive_count": len(false_positives),
        "missed_count": len(missed),
        "true_positives": [gt[k] for k in gt if k in matched][:_CAP],
        "false_positives": false_positives[:_CAP],
        "missed": missed[:_CAP],
    }


if __name__ == "__main__":  # ponytail: self-check — planted count + a synthetic-run comparison
    company = "insurer"
    path = seeds.seed_db_path(company)
    assert path is not None, "run infra/seeds to build out/insurer.db first"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    gt_rows = [dict(r) for r in con.execute(_INSURER_DUPLICATES.sql)]
    con.close()
    total = len(gt_rows)
    print("planted duplicate pairs (rule):", total)

    # perfect run: every planted pair flagged as a unit shaped like the real pipeline output
    perfect = [{"unit_ref": f"dup:{r['id_a']}-{r['id_b']}",
                "result": {"candidate": dict(r)}} for r in gt_rows]
    rep = compare(company, perfect)
    assert rep["planted_total"] == total
    assert rep["true_positive_count"] == total and rep["missed_count"] == 0
    assert rep["false_positive_count"] == 0
    # drop one pair + add a bogus flag: expect one miss + one false positive
    imperfect = perfect[:-1] + [{"unit_ref": "dup:99-100000000",
                                 "result": {"candidate": {"id_a": 99, "id_b": 100000000}}}]
    rep2 = compare(company, imperfect)
    assert rep2["missed_count"] == 1, rep2["missed_count"]
    assert rep2["false_positive_count"] == 1, rep2["false_positive_count"]
    assert rep2["true_positive_count"] == total - 1
    print("OK — perfect:", rep["true_positive_count"], "/", total,
          "| imperfect miss/fp:", rep2["missed_count"], rep2["false_positive_count"])
