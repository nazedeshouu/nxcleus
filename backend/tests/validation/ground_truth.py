"""Ground-truth for the Gemma validation gate (08 §7) — HAND-WRITTEN plain Python.

CRITICAL (track rule + 08 §7): the `expected` values here are computed by independent Python
below and are NEVER shipped to any model. Only each vector's `rule_text` (sanitized, in words)
and `inputs` are sent to the oracle seat; the oracle must recompute `expected` blind. This file
is the referee, not a model input.

Two rule sets — KYC risk (a bank onboarding rule) and Claims payout (an insurance rule) —
40 vectors total, matching the 08 §7 oracle bench.
"""
from __future__ import annotations

from typing import Any

# ── KYC risk scoring (sanitized rule text — this is what the model sees) ──────────
KYC_SCORE_RULE = (
    "risk_score = 40*sanctions_hit + 25*pep_hit + 20*adverse_media "
    "+ 10*high_risk_country + 5*structuring_flag, where each flag is 0 or 1. "
    "Cap the result at 100."
)
KYC_LEVEL_RULE = (
    "Given a risk_score in 0..100: level is 'red' if score >= 70, 'amber' if 40 <= score < 70, "
    "otherwise 'green'."
)


def kyc_score(v: dict[str, int]) -> int:
    s = (40 * v["sanctions_hit"] + 25 * v["pep_hit"] + 20 * v["adverse_media"]
         + 10 * v["high_risk_country"] + 5 * v["structuring_flag"])
    return min(s, 100)


def kyc_level(score: int) -> str:
    return "red" if score >= 70 else "amber" if score >= 40 else "green"


# ── Claims payout (sanitized rule text) ──────────────────────────────────────────
CLAIMS_PAYOUT_RULE = (
    "payout = max(0, min(claim_amount, policy_limit) - deductible). "
    "If fraud_flag is 1, payout is 0 regardless. Round to cents."
)


def claims_payout(v: dict[str, float]) -> float:
    if v.get("fraud_flag", 0) == 1:
        return 0.0
    return round(max(0.0, min(v["claim_amount"], v["policy_limit"]) - v["deductible"]), 2)


def _flags(sanc, pep, media, country, structuring) -> dict[str, int]:
    return {"sanctions_hit": sanc, "pep_hit": pep, "adverse_media": media,
            "high_risk_country": country, "structuring_flag": structuring}


# 20 KYC input sets (varied) → score + level vectors.
_KYC_INPUTS = [
    _flags(0, 0, 0, 0, 0), _flags(1, 0, 0, 0, 0), _flags(0, 1, 0, 0, 0), _flags(0, 0, 1, 0, 0),
    _flags(0, 0, 0, 1, 0), _flags(0, 0, 0, 0, 1), _flags(1, 1, 0, 0, 0), _flags(1, 0, 1, 0, 0),
    _flags(1, 1, 1, 0, 0), _flags(1, 1, 1, 1, 0), _flags(1, 1, 1, 1, 1), _flags(0, 1, 1, 1, 1),
    _flags(1, 0, 0, 1, 1), _flags(0, 0, 1, 1, 1), _flags(1, 1, 0, 1, 0), _flags(0, 1, 0, 0, 1),
    _flags(1, 0, 1, 1, 0), _flags(0, 1, 1, 0, 1), _flags(1, 1, 0, 0, 1), _flags(0, 0, 0, 1, 1),
]

# 20 Claims input sets (varied).
_CLAIMS_INPUTS = [
    {"claim_amount": 1000.0, "policy_limit": 5000.0, "deductible": 250.0, "fraud_flag": 0},
    {"claim_amount": 8000.0, "policy_limit": 5000.0, "deductible": 250.0, "fraud_flag": 0},
    {"claim_amount": 300.0, "policy_limit": 5000.0, "deductible": 500.0, "fraud_flag": 0},
    {"claim_amount": 5000.0, "policy_limit": 5000.0, "deductible": 0.0, "fraud_flag": 0},
    {"claim_amount": 2500.5, "policy_limit": 10000.0, "deductible": 500.25, "fraud_flag": 0},
    {"claim_amount": 9999.99, "policy_limit": 10000.0, "deductible": 1000.0, "fraud_flag": 0},
    {"claim_amount": 4000.0, "policy_limit": 3000.0, "deductible": 1000.0, "fraud_flag": 0},
    {"claim_amount": 4000.0, "policy_limit": 3000.0, "deductible": 1000.0, "fraud_flag": 1},
    {"claim_amount": 750.0, "policy_limit": 2000.0, "deductible": 100.0, "fraud_flag": 0},
    {"claim_amount": 100.0, "policy_limit": 2000.0, "deductible": 100.0, "fraud_flag": 0},
    {"claim_amount": 6200.0, "policy_limit": 6000.0, "deductible": 250.0, "fraud_flag": 0},
    {"claim_amount": 6200.0, "policy_limit": 6000.0, "deductible": 250.0, "fraud_flag": 1},
    {"claim_amount": 12000.0, "policy_limit": 15000.0, "deductible": 2000.0, "fraud_flag": 0},
    {"claim_amount": 500.0, "policy_limit": 500.0, "deductible": 500.0, "fraud_flag": 0},
    {"claim_amount": 3333.33, "policy_limit": 10000.0, "deductible": 333.33, "fraud_flag": 0},
    {"claim_amount": 20000.0, "policy_limit": 10000.0, "deductible": 5000.0, "fraud_flag": 0},
    {"claim_amount": 1200.0, "policy_limit": 1000.0, "deductible": 0.0, "fraud_flag": 0},
    {"claim_amount": 1200.0, "policy_limit": 1000.0, "deductible": 0.0, "fraud_flag": 1},
    {"claim_amount": 850.75, "policy_limit": 5000.0, "deductible": 200.0, "fraud_flag": 0},
    {"claim_amount": 0.0, "policy_limit": 5000.0, "deductible": 200.0, "fraud_flag": 0},
]


def build_vectors() -> list[dict[str, Any]]:
    """The 40 oracle vectors with hand-computed ground truth. `expected` is NEVER sent to a model.
    15 KYC-score (numeric) + 5 KYC-level (categorical) + 20 Claims-payout (money)."""
    vectors: list[dict[str, Any]] = []
    for i, inp in enumerate(_KYC_INPUTS[:15]):
        vectors.append({"id": f"V-KYC-S{i+1:02d}", "rule": "NR-KYC-SCORE",
                        "rule_text": KYC_SCORE_RULE, "inputs": inp,
                        "expected": kyc_score(inp), "tolerance": "exact"})
    for i, inp in enumerate(_KYC_INPUTS[15:]):
        score = kyc_score(inp)
        vectors.append({"id": f"V-KYC-L{i+1:02d}", "rule": "NR-KYC-LEVEL",
                        "rule_text": KYC_LEVEL_RULE, "inputs": {"risk_score": score},
                        "expected": kyc_level(score), "tolerance": "exact"})
    for i, inp in enumerate(_CLAIMS_INPUTS):
        vectors.append({"id": f"V-CLM-{i+1:02d}", "rule": "NR-CLAIMS-PAYOUT",
                        "rule_text": CLAIMS_PAYOUT_RULE, "inputs": inp,
                        "expected": claims_payout(inp), "tolerance": "exact"})
    return vectors


VECTORS = build_vectors()
assert len(VECTORS) == 40, f"expected 40 ground-truth vectors, got {len(VECTORS)}"
