"""Oracle validation bench (08 §7) — go/no-go for the Gemma oracle seat.

Runs the 40 ground-truth vectors through the oracle seat (k=3 self-consistency), compares each
result to the HAND-WRITTEN expected value (ground_truth.py — never shipped to the model), and
reports exact-match accuracy. Parameterized by seat binding so the fleet task can run it against
`gemma-4-31b` and the `qwen36-35b-a3b` understudy and apply the 08 §7 bar:

    Gemma >= 90% exact-match AND within 1 vector of the Qwen baseline -> KEEP Gemma oracle;
    else swap the seat and rework the Gemma-prize story to trust-only.

Wave 1 = skeleton: `--selftest` proves the bench wiring with a perfect fake oracle. Wave 2 =
inject the real `router.complete` (a live P1 fleet) to get the actual numbers.

Usage:
    python tests/validation/oracle_bench.py --selftest
    # Wave 2 (from backend, with a live fleet):
    #   from app.models.router import complete
    #   asyncio.run(run_oracle_bench(complete, seat_label="gemma-4-31b"))
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from app.seats import oracle
from app.seats.base import Completion

from tests.validation.ground_truth import VECTORS


async def run_oracle_bench(complete, *, seat_label: str = "oracle", k: int = 3,
                           temperature: float | None = 0.3) -> dict[str, Any]:
    """Run all vectors; return {seat, n, correct, accuracy, uncertain, mismatches[]}."""
    async def emit(_t, _p):  # bench is silent
        return None

    correct = uncertain = 0
    mismatches: list[dict[str, Any]] = []
    for vec in VECTORS:
        comp = await oracle.compute(complete, emit, rule_text=vec["rule_text"], vector=vec,
                                    k=k, tolerance=vec["tolerance"], temperature=temperature)
        verdict = oracle.adjudicate(comp["expected"], vec["expected"], vec["tolerance"], comp["uncertain"])
        if verdict == "match":
            correct += 1
        elif verdict == "oracle_uncertain":
            uncertain += 1
        else:
            mismatches.append({"id": vec["id"], "expected": vec["expected"],
                               "oracle": comp["expected"], "votes": comp["votes"]})
    n = len(VECTORS)
    return {"seat": seat_label, "n": n, "correct": correct, "accuracy": round(correct / n, 4),
            "uncertain": uncertain, "mismatches": mismatches}


def evaluate_gate(gemma: dict[str, Any], qwen: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply the 08 §7 pass bar. Returns {pass, reasons}."""
    reasons = []
    ok = gemma["accuracy"] >= 0.90
    reasons.append(f"gemma accuracy {gemma['accuracy']:.0%} {'>=' if ok else '<'} 90%")
    if qwen is not None:
        within = (qwen["correct"] - gemma["correct"]) <= 1
        reasons.append(f"gemma within {'1' if within else '>1'} vector of qwen "
                       f"({gemma['correct']} vs {qwen['correct']})")
        ok = ok and within
    return {"pass": ok, "reasons": reasons}


# ── self-test: a perfect fake oracle (returns the ground truth) proves the wiring ──
class _PerfectOracle:
    """Fake CompleteFn that answers each vector correctly — validates the bench, not a model."""
    def __init__(self):
        self._by_inputs = {repr(v["inputs"]): v["expected"] for v in VECTORS}

    async def __call__(self, seat, messages, *, data_class, schema=None, stream=None,
                       temperature=None, max_tokens=None) -> Completion:
        import json
        # the user message carries {"rule":..., "inputs":...}; look up the truth by inputs
        payload = json.loads(messages[-1].content)
        val = self._by_inputs.get(repr(payload["inputs"]))
        return Completion(text="", parsed={"value": val, "working": "selftest"}, usage={})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="run against a perfect fake oracle")
    args = ap.parse_args()
    if not args.selftest:
        print("This is the Wave-1 skeleton. Wave 2: inject router.complete against a live P1 fleet.\n"
              "Run with --selftest to validate the bench wiring now.")
        return 0
    report = asyncio.run(run_oracle_bench(_PerfectOracle(), seat_label="selftest"))
    gate = evaluate_gate(report)
    print(f"vectors={report['n']} correct={report['correct']} "
          f"accuracy={report['accuracy']:.0%} uncertain={report['uncertain']}")
    print(f"gate: {'PASS' if gate['pass'] else 'FAIL'} — {'; '.join(gate['reasons'])}")
    assert report["accuracy"] == 1.0, "perfect fake oracle should score 100% — bench wiring bug"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
