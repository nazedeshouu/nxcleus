#!/usr/bin/env python3
"""Render docs/specs/prompts-review.md from the actual seat-module prompt constants.

Keeps the review file honest — it shows the SHIPPED prompt text, not a hand copy that can
drift. Run from backend/:  ./.venv/bin/python ../infra/droplet/gen_prompts_review.py
"""
from __future__ import annotations

import pathlib

from app.seats import certifier, coder, conductor, consolidator, inspector, oracle, planner, trust

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "specs" / "prompts-review.md"

# (seat, blurb, [(label, text) ...]) — builders are rendered with representative args.
SECTIONS = [
    ("trust", "local:A/gemma-4-26b-a4b · RAW · the boundary guardian", [
        ("SYSTEM_INTAKE", trust.SYSTEM_INTAKE),
        ("SYSTEM_CLASSIFY", trust.SYSTEM_CLASSIFY),
        ("SYSTEM_POLICY (RedactionPolicy distillation, D11)", trust.SYSTEM_POLICY),
        ("SYSTEM_BRIEF (planner-brief composition — the load-bearing framing, 03 §2.3)", trust.SYSTEM_BRIEF),
        ("SYSTEM_SWEEP (consult residual gate, 03 §4.2)", trust.SYSTEM_SWEEP),
        ("SYSTEM_DOCS (stage-7 delivery docs)", trust.SYSTEM_DOCS),
    ]),
    ("planner", "anthropic:claude-fable-5 (sovereign: local:B/glm-46) · SANITIZED hard ceiling", [
        ("SYSTEM_PLAN (execution-fabric contract, 03 §3)", planner.SYSTEM_PLAN),
        ("REPLAN_GUIDANCE (constrained re-plan, scope-locked)", planner.REPLAN_GUIDANCE),
        ("sandbox_system(company, schema) — sample render (09 §2)",
         planner.sandbox_system("Meridian Bank",
                                {"tables": {"customers": ["id", "name"], "transactions": ["id", "amount"]}})),
    ]),
    ("certifier", "local:B/glm-46 · RAW (D9) · plan completion + certification", [
        ("check_system('production-fit') — the pass only the local seat can do (D9)",
         certifier.check_system("production-fit")),
        ("check_system('interface-compat') — representative of the 7-check suite",
         certifier.check_system("interface-compat")),
        ("SYSTEM_GOAL (D10 — derived from the RAW request)", certifier.SYSTEM_GOAL),
        ("SYSTEM_TESTS (IntegrationTestSpec + OracleVector emission)", certifier.SYSTEM_TESTS),
        ("SYSTEM_SCENARIOS (plan-aware adversarial, 08 §3)", certifier.SYSTEM_SCENARIOS),
        ("SYSTEM_REFINE_TRIAGE (04 §5)", certifier.SYSTEM_REFINE_TRIAGE),
    ]),
    ("conductor", "local:B/glm-46 · RAW · between-wave review (D8, no fallback)", [
        ("SYSTEM_REVIEW (03 §6)", conductor.SYSTEM_REVIEW),
    ]),
    ("coder", "pool (qwen3-coder-next / qwen36-27b / devstral-small-2 + gemma guest) · RAW", [
        ("SYSTEM_IMPLEMENT (targets the 04 §3 runtime contract)", coder.SYSTEM_IMPLEMENT),
        ("SYSTEM_FIX (defect micro-loop)", coder.SYSTEM_FIX),
    ]),
    ("consolidator", "local:B/glm-46 · RAW · stage-5 merge", [
        ("SYSTEM_CONSOLIDATE (Process protocol entrypoint, 04 §3)", consolidator.SYSTEM_CONSOLIDATE),
    ]),
    ("oracle", "local:A/gemma-4-31b · SANITIZED · blind numeric recomputation (08 §4)", [
        ("SYSTEM_ORACLE (never sees code/pseudocode — independence is the point)", oracle.SYSTEM_ORACLE),
    ]),
    ("inspector", "local:A/qwen36-35b-a3b · SANITIZED · agentic probes (08 §2)", [
        ("SYSTEM_PROBE (bounded tool loop; break the claim)", inspector.SYSTEM_PROBE),
        ("SYSTEM_GOAL_CHECK (08 §1.5 — deliverable vs goal)", inspector.SYSTEM_GOAL_CHECK),
    ]),
]


def main() -> None:
    lines = [
        "# Per-seat system prompts — review file",
        "",
        "> **Generated** from the shipped prompt constants by "
        "`infra/droplet/gen_prompts_review.py` — do not hand-edit; edit the seat modules and "
        "re-render. This is the orchestrator's prompt-quality gate (AI Wave-1 DoD).",
        "",
        "Every prompt states the English-only clause and a structured-output-first contract; "
        "temperature/timeouts come from `infra/seats.yaml`, never hardcoded. Data-class per "
        "call is enforced by the router (02 §4), shown per seat below.",
        "",
    ]
    for seat, blurb, prompts in SECTIONS:
        lines.append(f"## `{seat}` — {blurb}")
        lines.append("")
        for label, text in prompts:
            lines.append(f"### {label}")
            lines.append("")
            lines.append("```text")
            lines.append(text.strip())
            lines.append("```")
            lines.append("")
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(lines)} lines, {len(SECTIONS)} seats)")


if __name__ == "__main__":
    main()
