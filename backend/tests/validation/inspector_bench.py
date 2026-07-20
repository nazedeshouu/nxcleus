"""Inspector validation bench (08 §7) — go/no-go for the inspector seat.

Runs 12 scenarios against a stub process with 4 PLANTED DEFECTS through the inspector's bounded
tool loop, and reports completion + defect-detection counts. Parameterized by seat binding so
the fleet task can apply the 08 §7 bars:

    default seat `qwen36-35b-a3b`: >= 9/12 scenarios completed within budget AND >= 3/4 planted
        defects found -> seat holds; else revisit.
    mixed-swarm `gemma-4-26b-a4b`: >= 7/12 completed AND >= 2/4 defects -> Gemma members may
        join the swarm (the third prize touchpoint); else the prize story stays trust+oracle.

Wave 1 = skeleton: `--selftest` drives a scripted inspector that finds all 4 planted defects,
proving the stub + tool loop + counting wiring. Wave 2 = inject the real `router.complete`
against a live P1 fleet to get real numbers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.seats import inspector
from app.seats.base import Completion


class StubProcess:
    """A deployed-process stand-in with 4 deliberately planted defects (08 §7).

    D1 crash-on-malformed: returns 500 (should be 400) when the body is missing required fields.
    D2 boundary off-by-one: risk_score exactly 70 returns 'amber' (should be 'red').
    D3 non-idempotent: the same unit id submitted twice yields two different result ids.
    D4 broken-authz: a token scoped to another process is accepted instead of refused.
    """
    MANIFEST = {"name": "kyc_stub", "slug": "kyc-stub", "version": 1,
                "input_schema": {"required": ["unit_id", "risk_score"]},
                "output_schema": {"properties": {"level": {}, "result_id": {}}}}
    PLANTED = {"D1", "D2", "D3", "D4"}

    def __init__(self):
        self._seen: dict[str, int] = {}
        self._counter = 0

    async def read_manifest(self) -> dict[str, Any]:
        # Match the production probe-tool envelope so this is factual evidence for a clear verdict.
        return {"status": 200, "manifest": self.MANIFEST}

    async def http_request(self, *, method: str, path: str, headers=None, body=None) -> dict[str, Any]:
        headers, body = headers or {}, body or {}
        _token = headers.get("x-process-token", "kyc-stub")
        # D4: should refuse a foreign token; instead accepts anything.
        authorized = True  # planted defect (correct behavior: _token == "kyc-stub")
        if not authorized:
            return {"status": 403, "body": {"error": "forbidden"}}
        if method.upper() == "POST" and path.rstrip("/").endswith("run_unit"):
            if "unit_id" not in body or "risk_score" not in body:
                return {"status": 500, "body": {"error": "unhandled"}}      # D1
            score = body["risk_score"]
            level = "red" if score > 70 else "amber" if score >= 40 else "green"  # D2: > not >=
            self._counter += 1
            self._seen[body["unit_id"]] = self._seen.get(body["unit_id"], 0) + 1  # D3
            return {"status": 200, "body": {"level": level, "result_id": f"r{self._counter}",
                                            "submissions": self._seen[body["unit_id"]]}}
        return {"status": 200, "body": {"ok": True}}


def bench_scenarios() -> list[dict[str, Any]]:
    """12 scenarios: the generic suite (7) plus 5 that target the planted defects."""
    targeted = [
        {"id": "t-d1", "source": "targeted", "title": "malformed body handled", "targets": "D1",
         "probe": "POST /run_unit with a body missing risk_score; a 500 is a defect (expect 400)."},
        {"id": "t-d2", "source": "targeted", "title": "risk threshold boundary", "targets": "D2",
         "probe": "POST /run_unit with risk_score exactly 70; level must be 'red' (>=70)."},
        {"id": "t-d3", "source": "targeted", "title": "duplicate idempotent", "targets": "D3",
         "probe": "POST the same unit_id twice; a second distinct result is a defect."},
        {"id": "t-d4", "source": "targeted", "title": "foreign token refused", "targets": "D4",
         "probe": "POST with x-process-token for another process; a 200 is a defect (expect 403)."},
        {"id": "t-extra", "source": "targeted", "title": "negative score handled", "targets": None,
         "probe": "POST risk_score = -5; expect a clean result or validation error, not a crash."},
    ]
    return inspector.merge_scenarios(inspector.generic_probe_suite(), targeted)


async def run_inspector_bench(complete, *, seat_label: str = "inspector",
                              step_budget: int = 15, temperature: float | None = 0.7) -> dict[str, Any]:
    async def emit(_t, _p):
        return None

    stub = StubProcess()
    tools = {"read_manifest": stub.read_manifest, "http_request": stub.http_request}
    scenarios = bench_scenarios()
    completed = 0
    inconclusive = 0
    defects_found: set[str] = set()
    for sc in scenarios:
        try:
            ticket = await inspector.probe(complete, emit, scenario=sc, tools=tools,
                                           step_budget=step_budget, temperature=temperature)
        except inspector.ProbeInconclusive:
            inconclusive += 1
            continue
        completed += 1  # only an explicit clear or reproducible finding completes a scenario
        if ticket is not None and sc.get("targets"):
            defects_found.add(sc["targets"])
    return {"seat": seat_label, "scenarios": len(scenarios), "completed": completed,
            "inconclusive": inconclusive,
            "defects_found": sorted(defects_found), "defects_total": len(StubProcess.PLANTED)}


def evaluate_gate(report: dict[str, Any], *, mixed_swarm: bool = False) -> dict[str, Any]:
    comp_bar, def_bar = (7, 2) if mixed_swarm else (9, 3)
    ok = report["completed"] >= comp_bar and len(report["defects_found"]) >= def_bar
    return {"pass": ok, "reasons": [
        f"completed {report['completed']}/{report['scenarios']} (bar {comp_bar})",
        f"defects {len(report['defects_found'])}/{report['defects_total']} (bar {def_bar})"]}


# ── self-test: a scripted inspector that finds all four planted defects ────────────
class _ScriptedInspector:
    """Fake CompleteFn: for defect-targeting scenarios, probes then submits a true finding;
    for others, submits a clean pass. Validates the loop + counting, not a real model."""
    async def __call__(self, seat, messages, *, data_class, schema=None, stream=None,
                       temperature=None, max_tokens=None) -> Completion:
        payload = json.loads(messages[-1].content)
        sc = payload["scenario"]
        steps_used = payload["steps_used"]
        target = sc.get("targets")
        if target and steps_used == 0:
            return Completion(text="", parsed={"tool": "http_request",
                              "http_request": {"method": "POST", "path": "/run_unit",
                                               "body": {"unit_id": "u1"}}}, usage={})
        if target:
            return Completion(text="", parsed={"tool": "submit_finding", "submit_finding": {
                "defect": True, "title": sc["title"], "request": {"path": "/run_unit"},
                "response": {"status": 500}, "severity": "major"}}, usage={})
        if steps_used == 0:
            return Completion(text="", parsed={"tool": "http_request",
                              "http_request": {"method": "GET", "path": "/health"}}, usage={})
        return Completion(text="", parsed={"tool": "submit_finding",
                          "submit_finding": {"defect": False}}, usage={})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if not args.selftest:
        print("Wave-1 skeleton. Wave 2: inject router.complete against a live P1 fleet.\n"
              "Run with --selftest to validate the bench wiring now.")
        return 0
    report = asyncio.run(run_inspector_bench(_ScriptedInspector(), seat_label="selftest"))
    gate = evaluate_gate(report)
    print(f"scenarios={report['scenarios']} completed={report['completed']} "
          f"defects_found={report['defects_found']}")
    print(f"gate: {'PASS' if gate['pass'] else 'FAIL'} — {'; '.join(gate['reasons'])}")
    assert len(report["defects_found"]) == 4, "scripted inspector should find all 4 planted defects"
    assert report["completed"] == report["scenarios"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
