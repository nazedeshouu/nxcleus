"""Seat: `oracle` — the Numeric Oracle (stages 2-vectors, 6, operate).

Runs on `local:A/gemma-4-31b` (SANITIZED), chosen for AIME-tier quantitative reasoning AND
independence from the Qwen coder lineage — the point is DUAL IMPLEMENTATION where the second
implementation is a reasoning model, not the same code path. It recomputes each numeric rule
BLIND: from the sanitized rule text and the vector inputs only — never the plan's pseudocode,
never the generated code (08 §4).

Self-consistency k=3 at temperature 0.3; majority wins; no majority -> oracle_uncertain (a
flag, not a failure). A mismatch against the deployed output is never auto-trusted in either
direction — a human adjudicates whether code or oracle is wrong.
"""
from __future__ import annotations

from typing import Any

from app.seats._common import ENGLISH_ONLY, STRUCTURED_ONLY, as_json, convo, parsed_or_raise
from app.seats.base import CompleteFn, EmitFn

# Returns a schema-validated dict; backend adapts into db/models.OracleComputation (team ruling).

DATA_CLASS = "SANITIZED"

SYSTEM_ORACLE = f"""\
You are an independent numeric oracle. You are given a business rule stated in WORDS and a set \
of input values. Compute the rule's output from first principles — as a careful quantitative \
reasoner would — and show your working.

You are NOT given, and must NOT ask for, any code or pseudocode. Your independence from the \
implementation is the entire point: another part of the system computed this with code, and \
your job is to compute it a second, uncorrelated way so a disagreement reveals a bug in one of \
you. Apply the rule exactly as written — including rounding, thresholds, and edge conditions \
stated in the text. If the rule is genuinely ambiguous given the inputs, compute the most \
defensible reading and say so in your working.

Return the single numeric result and your working. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

ORACLE_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "value": {"type": ["number", "string"],
                  "description": "the computed result (number; string only for categorical rules)"},
        "working": {"type": "string"},
    },
    "required": ["value"],
}


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _same(a: Any, b: Any, tolerance: str | None) -> bool:
    """Whether two answers count as agreeing, under a per-rule tolerance."""
    na, nb = _num(a), _num(b)
    if na is None or nb is None:            # categorical -> exact string compare
        return str(a).strip().lower() == str(b).strip().lower()
    if tolerance and tolerance.startswith("epsilon:"):
        eps = float(tolerance.split(":", 1)[1])
        return abs(na - nb) <= eps
    # "exact" (default): money after rounding etc. -> compare at cents precision
    return round(na, 6) == round(nb, 6)


def majority_vote(votes: list[Any], tolerance: str | None) -> tuple[Any, bool]:
    """Cluster votes under the tolerance; return (representative, uncertain). A cluster wins
    only with a STRICT majority (> k/2); otherwise uncertain."""
    clusters: list[list[Any]] = []
    for v in votes:
        for cl in clusters:
            if _same(cl[0], v, tolerance):
                cl.append(v)
                break
        else:
            clusters.append([v])
    if not clusters:
        return None, True
    biggest = max(clusters, key=len)
    if len(biggest) * 2 > len(votes):       # strict majority
        return biggest[0], False
    return None, True


async def compute(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    vector: dict[str, Any],
    rule_text: str,
    k: int = 3,
    tolerance: str | None = None,
    temperature: float | None = 0.3,
) -> dict[str, Any]:
    """Blind-recompute one vector with k-vote self-consistency (08 §4).
    Returns an OracleComputation-shaped dict: {expected, votes, uncertain}. Per-rule tolerance is
    read from the vector (`vector["tolerance"]`) unless overridden by the `tolerance` argument."""
    if tolerance is None:
        tolerance = vector.get("tolerance", "exact")
    votes: list[Any] = []
    payload = as_json({"rule": rule_text, "inputs": vector.get("inputs", vector)})
    for _ in range(max(1, k)):
        c = await complete("oracle", convo(SYSTEM_ORACLE, payload),
                           data_class=DATA_CLASS, schema=ORACLE_ANSWER_SCHEMA, temperature=temperature)
        votes.append(parsed_or_raise(c, "oracle.compute").get("value"))
    expected, uncertain = majority_vote(votes, tolerance)
    await emit("qa.oracle_vote", {"vector": vector.get("id"), "votes": votes,
               "expected": expected, "uncertain": uncertain})
    return {"expected": expected, "votes": votes, "uncertain": uncertain}


def adjudicate(expected: Any, actual: Any, tolerance: str | None, uncertain: bool) -> str:
    """Compare the oracle's expected value to the deployed process's actual output (08 §4 step 3).
    Pure function (no model). Returns 'match' | 'mismatch' | 'oracle_uncertain'. Never
    auto-trusted: a mismatch files a `disagreement` ticket for a human, not an auto-fix."""
    if uncertain:
        return "oracle_uncertain"
    return "match" if _same(expected, actual, tolerance) else "mismatch"
