# 08 — Adversarial QA: Inspectors, Numeric Oracle, Tickets

Locked 2026-07-07. Upstream: design v2 §3 (stage 6), §4 (continuous assurance), §6 (Gemma roles). Siblings: 03 §4 (where test specs/vectors come from), 04 §6 (warranty), 02 (seats).

QA never reviews code by vibes. Three objective instruments: the **integration suite** (deterministic, from stage 2), the **inspector swarm** (behavioral probes against the deployed process), and the **Numeric Oracle** (independent recomputation). All three file the same currency: **tickets**.

## 1. Stage-6 sequence

1. Deploy candidate package to a **staging** process-runtime container (identical to production runtime, 04 §3).
2. Integration suite runs (already green from stage 5's gate; re-run here against the *deployed* runtime, not the workspace).
3. Inspector swarm probes (§2–3) and oracle checks (§4–5) run **concurrently** — both stream events.
4. Tickets route to `coder` for fixes (§6); loop ≤3 rounds; then `qa.passed` (stats) or park with human-review flags.
5. **Goal-fulfillment check (§1.5, D10)** — runs after the fix loop settles, before `qa.passed`.
6. QA report (counts, probes run, vectors checked, tickets by outcome, goal verdict) lands in the package `docs/`.

### 1.5 Goal-fulfillment check (D10)

The instruments above verify the plan was *built right*; this check verifies we *built the right thing*. One `inspector` scenario, elevated: input = `jobs.goal` + the process manifest + the acceptance-criteria outcomes + 2–3 live probe results of the main path; the inspector's contract is to judge the **deliverable against the goal statement in the customer's own terms**, not against the plan (the plan may have drifted through amendments — the goal is the fixed star). Structured verdict:

```jsonc
{"verdict": "fulfilled|partial|unfulfilled", "gaps": [{"goal_clause": "...", "evidence": "...", "severity": "blocker|caveat"}]}
```

`fulfilled` / `partial`-with-caveats-only → proceed (verdict renders at delivery: "goal fulfilled — 2 caveats"). Any `blocker` gap → ticket (severity `blocker`) into the §6 lifecycle; `unfulfilled` parks the job for human review — a process that doesn't do what was asked never quietly reaches the registry. Event: `qa.goal_check`.

## 2. Inspector agent loop

Seat `inspector` (Qwen3.6-35B-A3B — swapped from Gemma 2026-07-09 on a measured ~2× tool-use gap, MCPMark 37.0 vs 18.1; still MoE-cheap at ~3 B active params, which is what keeps the swarm affordable. Mixed-swarm Gemma members remain a prize option — 11 §4). N concurrent agents (default 4, config), each running a bounded tool loop (≤15 steps, ≤60 s per scenario):

```
tools:
  http_request(method, path, headers?, body?)   # scoped: process staging base URL ONLY (egress-enforced)
  read_manifest()                                # process manifest + schemas
  submit_finding(finding)                        # structured, ends scenario or continues
```

System prompt contract: *you are probing a deployed business process; you cannot see its code; try to break the claim, not to fix it; every finding needs a reproducible request/response pair.* English-only, temperature 0.7 (diverse probing).

## 3. Scenario generation

Scenarios come from three generators, merged and deduped:
- **AC-derived:** one scenario per acceptance criterion with `verify: inspector` (03 §2).
- **Generic probe suite** (static library, applies to any process): malformed units, missing required fields, boundary values (0, negatives, maxima), duplicate submission/idempotency, oversized payloads, wrong-tenant/process token misuse (auth probe against the model-proxy scoping), needs-review pathway exercised.
- **Plan-aware:** `certifier` emits 3–5 process-specific adversarial scenarios during stage 2 (e.g. "sanctions hit + name transliteration variant"), stored with the test specs.

## 4. Numeric Oracle protocol

Seat `oracle` (Gemma 4 31B — AIME-tier quantitative reasoning per the benchmark deep-dive; re-validated in §7). For each `OracleVector` (inputs only, 03 §4):

1. Prompt = the *sanitized numeric rule text from the spec* + vector inputs. **Never the plan's pseudocode, never generated code** — independence is the point (dual implementation, where the second implementation is a reasoning model).
2. Self-consistency k=3 (temperature 0.3), numeric answers extracted via structured output; majority verdict. No majority → `oracle_uncertain` (counts as a flag, not a failure).
3. Compare to the deployed process's actual output for the same inputs (tolerance per rule: exact for money after rounding-rule application, epsilon for scores — encoded per vector).
4. `match` → green tick event. `mismatch` → ticket `severity: disagreement`. **Never auto-trusted in either direction** — a human resolves whether code or oracle is wrong (design rule). This yields the "N adjudicated correctly, M flagged for human review" delivery stat.

## 5. Oracle & inspectors in the operate phase (continuous assurance)

- Per-run spot-checks: sample `manifest.sampling` (default 5%) of `ok` units → oracle recompute → `run.spotcheck` events; mismatch → **warranty ticket** (04 §6).
- Periodic probes: hourly scheduler runs 2–3 generic-suite scenarios per registered process against its live runtime.
- Both are metered like everything else — assurance cost is visible on the per-run cost line (an honest line item, ~pennies; reinforces the money slide rather than undermining it).

## 6. Ticket lifecycle

```
opened → in_fix → verified            (fix confirmed: originating instrument re-run green)
       ↘ human_review                 (3 fix attempts, or severity=disagreement)
       ↘ wont_fix                     (presenter decision, note required)
```

Ticket body (structured, from all instruments): `{title, instrument, repro: {request, response} | {vector, expected, actual}, suspected_modules[], severity}`. Fixes are stage-4 micro-loops scoped to `suspected_modules` (worker gets ticket + module source + relevant tests). The defect board in the Build view is a direct render of this table.

## 7. Gemma validation gate (design §6.3 — run Day 2, before demos are locked)

Go/no-go procedure, scripted in `backend/tests/validation/` so it's re-runnable and citable in the deck:

| Claim | Procedure | Pass bar |
|---|---|---|
| Oracle accuracy | 40 vectors across the KYC + Claims rule sets (ground truth = hand-written Python in the seed kit, never shipped to any model). Run `gemma-4-31b` k=3 vs `qwen36-35b-a3b` k=3 on P1 fleet (the understudy per 11 — AIME 89.2 vs 92.7, so the bar is business-vector accuracy, not AIME) | Gemma ≥90% exact-match **and** within 1 vector of the Qwen baseline; else swap seat + rework the Gemma-prize story to trust-only |
| Inspector completion | 12 scenarios from the generic suite against a stub process with 4 planted defects, run on `qwen36-35b-a3b` (current default) | ≥9/12 scenarios completed within step budget, ≥3/4 planted defects found; else revisit seat |
| Mixed-swarm Gemma option | same 12 scenarios on `gemma-4-26b-a4b` members | ≥7/12 completed, ≥2/4 defects → Gemma members join the swarm (third prize touchpoint); else prize story stays trust+oracle |

Results (numbers + date + model IDs) recorded in this file under a "Validation results" heading when run — the deck cites this section. Seat swap = `infra/seats.yaml` edit only (02 §1).
