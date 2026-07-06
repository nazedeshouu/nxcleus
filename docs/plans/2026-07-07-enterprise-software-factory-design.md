# Enterprise Software Factory — Consolidated Design

**Status:** locked after brainstorm sessions, 2026-07-07.
**Track:** AMD Hackathon ACT II, Track 3 (Unicorn / Open Innovation). Deadline **Jul 11, 2026, 21:00 KT (UTC+5)**.
**Team:** duo, near full-time.
**Working title:** TBD (see Open decisions — avoid "software factory" as a brand; Factory.ai collision).

## 1. Concept

A pipeline that turns a plain-language business request into priced, planned, built, verified, and deployed software with a transparent itemized invoice. Positioning: **regulated enterprises** — organizations that cannot paste their data or systems into external AI. Customer data never leaves customer-controlled AMD hardware; external frontier models only ever see sanitized specifications, and a **Sovereign Mode** removes external calls entirely.

Why a single frontier chat cannot substitute: jobs are too large for one context (dozens of modules), the data is private and cannot leave the boundary, and delivery requires a build–test–fix loop validated against real systems and connectors.

## 2. Pipeline architecture

| # | Stage | Runs on | Model class |
|---|---|---|---|
| 0 | Intake & data boundary | Self-hosted MI300X (vLLM/ROCm) | Local trust model (currently Gemma 4; seat is model-agnostic) |
| 1 | Planning | External API, or Fireworks in Sovereign Mode | Frontier (Claude-class default; open frontier in Sovereign Mode) |
| 2 | Plan verification loop | Self-hosted MI300X | Strong local analyst (GLM 5.2-class) |
| 3 | Quote | — (deterministic + planner output) | — |
| 4 | Parallel code generation | Elastic 1–5× MI300X (vLLM/ROCm) | Multiple open coder models (Qwen-Coder/DeepSeek-class; IDs TBD) |
| 5 | Consolidation | Fireworks (AMD-hosted) | Large open model |
| 6 | Adversarial QA | Self-hosted MI300X + deployed app | Inspector agents + Numeric Oracle |
| 7 | Delivery | Factory infra | — |

### Stage 0 — Intake & data boundary
- Clarification dialogue with the customer; produces a structured spec + acceptance criteria.
- PII masking and schema abstraction: raw records in, sanitized abstractions out. This is the **only stage that touches raw customer data**.
- Document OCR/extraction for document-driven jobs (e.g. KYC) happens here, locally.

### Stage 1 — Planning (dual, with Sovereign Mode)
- Default planner: Claude-class external model (permitted by track rules; sees only Gemma-sanitized specs — never raw data).
- **Sovereign Mode:** a toggle that swaps the planner for a Fireworks-hosted open frontier model so the entire pipeline runs on AMD-hosted infrastructure with zero external calls. Product feature and demo insurance.
- Output: module decomposition, typed interfaces, algorithm pseudocode, data schemas, task DAG, initial estimate.

### Stage 2 — Plan verification loop (local)
- A strong self-hosted model (GLM 5.2-class) runs structured verification of the full plan **before any code is written**: interface compatibility across modules, data-model completeness, error-handling coverage, consistency of auth/state patterns.
- On failure: specific, sanitized feedback goes back to the planner for a **constrained re-plan** (cheaper than regenerating from scratch). Max 2–3 iterations.
- On pass: the verifier emits **integration test specs**, giving coder models concrete targets and giving consolidation an automated pass/fail signal instead of subjective review.
- Rationale: plan *generation* is frontier-hard creative work; plan *verification* is structured analysis a strong local model handles. The frontier model is used at both ends (planning, targeted repair); the middle stays local.

### Stage 3 — Quote
- Itemized estimate presented upfront: architecture/planning, projected token usage by tier, projected GPU time.
- Delivery reconciles the estimate against **metered actuals** (real tokens, real GPU-seconds). Quote is a range; the invoice is exact.

### Stage 4 — Parallel code generation
- Elastic fleet of 1–5× MI300X droplets (192 GB HBM each) running vLLM on ROCm, hosting multiple open coder models concurrently.
- Workers build modules in parallel against the verified typed interfaces and test specs.
- Fleet size scales with job size; per-GPU usage feeds the invoice.

### Stage 5 — Consolidation
- A larger open model (Fireworks, AMD-hosted) merges generated modules into a coherent codebase.
- Gate: the stage-2 integration test specs must pass. Objective signal, not review-by-vibes.

### Stage 6 — Adversarial QA
- Inspector agents probe the **deployed** app: API calls, auth/tenant-isolation probes, edge-case walks — against acceptance criteria, connectors, and masked/synthetic data.
- **Numeric Oracle** (see §4): independent computation of expected outputs for quantitative business rules; assert `code output == oracle output`.
- Defects are filed as structured tickets routed back to the fleet. Loop until green; irreducible disagreements are **flagged for human review**, not auto-resolved.

### Stage 7 — Delivery
- Auto-deploy to a per-job URL on factory infrastructure.
- Package: live URL + repo + generated documentation + QA report + final metered invoice.

## 3. Factory floor (mission-control UI)

The real-time view that is both the product's control plane and the demo's spine:
- Live task DAG (modules lighting up as they start/finish).
- Parallel worker panels streaming code side by side.
- Per-GPU ROCm telemetry.
- Cost accrual meter (running total vs. quote).
- Plan-verification view: verifier findings annotated on the plan → constrained re-plan diff → certified plan.
- QA defect board (open → in-fix → verified).

This UI is the landing page of the live demo URL.

## 4. Gemma: justified roles only

**Honest position:** the trust layer (intake, PII masking, OCR, doc generation) is a *local-model* requirement, not a *Gemma* requirement — Qwen/Llama-class local models could fill it equally well. Gemma currently occupies the seat, but this alone is not a "best use of Gemma" claim and we do not present it as one.

Two roles are Gemma-specific, based on the team's benchmark deep-dive (figures below are from that deep-dive and must be **re-validated on our workload during build week**):

### 4.1 Numeric Oracle
- **Seat requirements (all three simultaneously):** locally hosted (test vectors derive from real data and must stay inside the boundary); cheap enough to run per-rule at volume; competition-grade quantitative reasoning.
- **Benchmark basis:** Gemma 4 31B — AIME 89.2%, vs. Qwen 3.5 27B ≈ 49% and DeepSeek V4 42.5%. No other locally hostable model meets all three requirements at once.
- **Function:** for each numeric business rule in the spec, independently compute expected outputs for test vectors (e.g. claim payout, filing aggregates, risk score) **without seeing the generated code**. QA asserts code output equals oracle output. Dual-implementation testing where the second implementation is a reasoning model.
- **Limits:** the oracle is not infallible; oracle-vs-code disagreements are flagged for review, never auto-trusted. This produces the "N adjudicated correctly, M flagged for human review" delivery stat.

### 4.2 Agentic inspector swarm
- **Seat requirements:** always-on post-deploy probing means many concurrent agent loops; cost scales with active parameters.
- **Benchmark basis:** Gemma 4 26B MoE activates ≈3.8B parameters per forward pass; Gemma 4 31B scores 86.4% on τ2-bench (agentic tool use). Alternatives activate ≥17B for comparable capability — several times the GPU cost per concurrent inspector.
- **Function:** drive the deployed app agentically (API/browser tool use), probe auth and isolation, walk edge cases, file structured defect tickets. Inspectors do **not** write code; coder models implement fixes.

### 4.3 Validation gate and fallback
Before the demos are locked: replicate both claims on our workload (oracle accuracy on the demo rule sets vs. a Qwen baseline; inspector task-completion rate). If Gemma underperforms, swap the seat for the better local model and drop the Gemma-prize pursuit. All seats are model-agnostic by design; the architecture does not depend on Gemma.

### 4.4 Edge (optional, cut-first)
Gemma E4B on-device (≈1.5 GB RAM, offline, native audio): one deck slide on run-time sovereignty (delivered apps can embed an on-prem assistant); optionally one demo beat (KYC voice intake). No build dependency; first thing cut under time pressure.

## 5. Demos

Four demos, one factory. Each demo is a seed kit (synthetic data, mock connectors, validators) plus a rehearsed run — no canned outputs (track rule: no hardcoding).

**Build priority / cut order:** KYC (hero) → Sovereign Surveillance (finale) → Regulatory Report Factory → Claims Engine (**pre-decided cut** if time compresses; overlaps Reg Report most; its "flagged for review" stat grafts onto KYC risk scoring).

### Demo 1 (hero) — KYC/AML Customer Onboarding Pipeline
- **Request:** customer submits documents → OCR → sanctions screening → PEP checks → adverse-media check → risk scoring → case file + audit trail.
- **Spotlights:** every layer. Documents are read locally at stage 0 (no external system ever sees them); planner architects the decision-tree pipeline; verification loop catches cross-check gaps (e.g. risk scoring ignoring the sanctions result); the independent checks fan out naturally across the fleet; oracle validates risk-score math.
- **Seed kit:** synthetic identity documents; public OFAC/EU consolidated sanctions lists (real public data); synthetic PEP/adverse-media fixtures.
- **End state:** visible case file with green/amber/red risk rating + audit trail.
- **Why this buyer:** every bank, insurer, and regulated fintech does KYC.

### Demo 2 (finale) — Trading Compliance Surveillance, Sovereign Mode
- **Request:** spoofing/wash-trade detection pipeline over broker order/trade blotters, with case management and regulator-ready reports; must run fully on-prem.
- **Spotlights:** Sovereign Mode toggled **live** — pipeline reruns with the network monitor proving zero external calls. Only demo that does this. Presentation ends here.
- **Seed kit:** synthetic blotters with planted spoofing/wash-trade sequences.
- **Risk note:** detection logic must fire on the planted patterns; deterministic seeds, rehearse.

### Demo 3 — Regulatory Report Factory
- **Request:** quarterly filing pipeline: pull from source systems, apply reporting rules, validate against the regulator's schema, generate the submission-ready filing + audit trail.
- **Spotlights:** consolidation + test validation. Objective pass/fail: validation wall goes from partial failures to **143/143 green** after the defect-fix loop.
- **Seed kit:** mock source systems; a real public regulatory schema; synthetic financials.

### Demo 4 (cut candidate) — Insurance Claims Engine
- **Request:** claims adjudication: intake → policy lookup → coverage rules → fraud flags → payout calculation → decision letters → human-review queue.
- **Spotlights:** rules-dense planning; verification loop catches rule-interaction bugs; oracle computes expected payouts.
- **End state:** 500 synthetic claims run through: **487 adjudicated correctly, 13 edge cases flagged for human review** — the flagged cases demonstrate the system knows its limits.

## 6. Live demo URL

- **Landing:** the factory floor, live.
- **Gallery:** the four delivered apps, each clickable at its own deployed URL, with per-job repo/docs/QA report/invoice.
- **Judge-run mode:** the full workflow on the judge's own scenario. Guards: per-run budget cap, job queue, pre-warmed fleet (no cold starts). Real generation — no canned outputs.

## 7. Judging alignment

| Criterion | Where we score |
|---|---|
| Creativity & originality | Plan-verification loop (local verification of frontier plans); Numeric Oracle (dual-implementation testing); data-boundary architecture; Sovereign Mode |
| Product/market potential | Regulated-enterprise wedge ("we build where external AI is banned"); itemized quote→invoice; four buyer-aligned demos |
| Completeness | Working end-to-end pipeline; deployed apps in gallery; judge-run mode; QA reports |
| Use of AMD platforms | Stages 0, 2, 4, 6 self-hosted on MI300X/ROCm/vLLM; stages 1 (Sovereign) and 5 on Fireworks (AMD-hosted); GPU time as an invoice line item |

**AMD gate evidence (mandatory, auto-pre-screened from repo + PDF deck + live URL — the video is not processed):**
- README section: AMD infrastructure architecture + diagram.
- Code paths: vLLM/ROCm configs, Fireworks client, fleet orchestration.
- Live ROCm telemetry visible in the factory floor UI.
- Deck slide: where each stage runs.

**Gemma prize ("Best AMD-Hosted Gemma Project", $2,000):** pursued via §4 roles; go/no-go at the §4.3 validation gate.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Judge-run fails live | Budget cap + queue + pre-warm; gallery of completed runs as the always-working surface |
| Verification-loop latency at the front of the demo | Stream verifier findings as they're produced; measure loop latency early in build week |
| GPU credits (~$100 AMD Cloud + Fireworks credits) | Elastic fleet sized per job; Fireworks-backed paths for the always-on URL; droplets scheduled around the judging window |
| Four demos in four days | Seed kits are content, not architecture; pre-decided cut (Claims); hero demo rehearsed first |
| Gemma benchmark claims don't reproduce | §4.3 validation gate; all seats model-agnostic; swap and continue |
| Generated apps fail QA repeatedly | Verified typed interfaces + test specs narrow the target; defect loop bounded, then flagged-for-human list |
| 30s response-time rule (general) | Applies to harness tracks; for our long-running builds the UI streams progress continuously so no request appears hung |

## 9. Compliance checklist (track rules)

- [ ] Public GitHub repo, MIT-compliant, README with setup + usage.
- [ ] Slide deck as **PDF**.
- [ ] Demo video showing the real system.
- [ ] Live URL reachable through judging.
- [ ] All output in English; no hardcoded/canned answers.
- [ ] Any shipped container built `linux/amd64`.
- [ ] AMD usage legible in repo + deck + live URL within 30 seconds of skimming.

## 10. Open decisions

1. **Product name** (blocker for repo/deck/URL branding). Avoid "factory" as brand root (Factory.ai). Candidates to be brainstormed separately.
2. Exact coder-fleet model IDs (Qwen-Coder/DeepSeek-class; choose during build against MI300X capacity).
3. Verifier deployment config: GLM 5.2-class size/quantization vs. dedicating a GPU to it in the elastic plan.
4. GPU count vs. credit budget: measured after first end-to-end run.
5. §4.3 Gemma validation results → Gemma-prize go/no-go.
6. Whether Demo 4 (Claims) ships or is cut.
7. Edge/E4B beat in KYC demo: only if all four demos land early.
