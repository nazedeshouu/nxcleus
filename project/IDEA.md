# 🦄 Project idea — LOCKED v2 (2026-07-07)

> Full design: [`../docs/plans/2026-07-07-adaptive-sovereign-platform-design.md`](../docs/plans/2026-07-07-adaptive-sovereign-platform-design.md). This file is the summary. (v1 "software factory" design is superseded, kept for history.)

## One-liner

**"Describe an internal process. Get it running inside your walls — built, verified, and yours to run forever."** An adaptive platform for regulated enterprises: a plain-language description of an internal process becomes a running, verified, sovereign process automation — while customer data never leaves customer-controlled AMD hardware.

## The pitch (for the deck)

- **Problem:** regulated enterprises (banks, insurers, fintechs, healthcare, legal) can't hand their data or systems to external AI — so internal processes still run on consultants, manual work, and months-long software projects. A frontier chat can't do these jobs anyway: too large for one context, data can't leave the boundary, and trust requires verification against live systems.
- **Solution — a lifecycle, not a factory:**
  - **Build (once):** local trust layer (intake, PII firewall, OCR) → frontier planner that only ever sees sanitized specs and designs the *work topology* + model bill-of-materials → local GLM **completes and certifies** the plan (triage: small gaps patched locally with a signed amendment log; hard/structural issues escalated to the frontier as scoped consults) → elastic parallel fleet on AMD MI300X (coder models, or corpus fan-out for processing jobs) → consolidation gated by objective tests → adversarial QA with an independent **Numeric Oracle** → the process lands in the **operations registry**.
  - **Operate (forever):** the certified process runs on new data fully locally — zero frontier calls, metered per run, oracle spot-checks as a live warranty.
  - **Refine (on demand):** change requests re-open planning under the same triage model; every refinement ships a versioned, diffed, re-certified v(n+1); old versions stay runnable.
- **Adaptive delivery modes:** the planner designs the best structure per task — **build mode** (construct a process automation), **process mode** (fan local models out over a corpus — documents, records, codebases — one unit per worker, aggregate into a dashboard/dataset), **semi-automated mode** (human-review steps designed in). All modes produce saved, re-runnable, refinable workflows.
- **Target user:** regulated enterprises. Wedge sentence: **"we operate where external AI is banned."**
- **Money slide:** **frontier intelligence is a capital expense, not a marginal cost** — paid once at plan time, on sanitized specs; every run after that is local and cheap. Competitors pay frontier tokens *and* surrender data on every run.
- **Moat / originality:** the data-boundary architecture; the triage authority model (frontier authors, local model finishes and certifies, frontier on-call — with a visible amendment log); adaptive topology planning with a model BoM driving GPU provisioning; dual-implementation QA via the oracle; Sovereign Mode toggle; lifecycle-as-asset.

## AMD compute plan (mandatory — load-bearing)

- [x] **AMD Developer Cloud GPUs (ROCm):** elastic 1–5× MI300X running vLLM — trust layer (stage 0), plan certification (stage 2), parallel fleet: coders or corpus fan-out (stage 4/4′), QA inspectors + oracle (stage 6), **and all operate-phase runs**. Live ROCm telemetry in the Build view.
- [x] **Fireworks AI API (AMD-hosted):** consolidator (stage 5); Sovereign Mode planner (stage 1); fallback path for the always-on live URL.
- [x] **Gemma:** two benchmark-justified roles — Numeric Oracle (AIME-tier math, local, cheap; now also operate-phase spot-checks) and agentic inspector swarm (MoE ≈3.8B active params, τ2-bench-backed; now also periodic operate-phase probes). Trust-layer seat currently Gemma but documented as model-agnostic. Validation gate before demos; go/no-go on the $2,000 Gemma prize.
- [x] **Visibility to judges:** README architecture section + diagram, vLLM/ROCm/Fireworks code paths in repo, live GPU telemetry in the demo UI, "where each stage runs" deck slide, **GPU allocation justified by the plan's model BoM**.

## Scope for the window (deadline Jul 11, 21:00 KT)

- **MVP (must work end-to-end):** the build pipeline (stages 0–7), Build view UI, operations registry (modest: table + run batch), quote→metered invoice, and the hero demo (KYC/AML onboarding, ending in the registry with a live batch run) on a live URL.
- **Full target:** KYC hero (with live refinement beat → v2 deploy) → Trading Surveillance w/ live Sovereign Mode toggle (finale) → Regulatory Report Factory (the re-run demo: Q3 on new data, zero frontier calls) → **judge sandbox** (three synthetic companies — bank, clinic, law firm — with browsable mock data + suggested & freeform prompts; every sandbox run is a real process-mode job; doubles as the process-mode demo — one work item) → Claims Engine (**pre-decided cut**).
- **Explicitly optional (cut-first):** Gemma E4B edge beat; Claims demo; extra fleet GPUs beyond what the demos need.

## Tech stack (draft)

- **Models:** Gemma 4 (trust layer seat, oracle, inspectors — pending validation gate), Claude Fable-class external planner + open frontier via Fireworks (Sovereign Mode), GLM 5.2-class plan completion/certification, Qwen-Coder/DeepSeek-class fleet (IDs TBD), large open consolidator on Fireworks.
- **Serving:** vLLM on ROCm, 1–5× MI300X (AMD Developer Cloud); Fireworks AI API.
- **Demo surface:** Build view (mission control) + Operations view (registry) + per-job deployed processes + gallery + judge sandbox.
- **Hosting for live URL:** platform infra with Fireworks-backed fallback (details during build).

## Open questions / decisions needed

See design doc §12. Highest priority: **product name** (blocks repo/deck/URL branding; "factory" root doubly excluded); exact model IDs; Gemma validation results; sandbox dataset scope; Claims demo go/no-go.
