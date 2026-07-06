# 🦄 Project idea — LOCKED (2026-07-07)

> Full design: [`../docs/plans/2026-07-07-enterprise-software-factory-design.md`](../docs/plans/2026-07-07-enterprise-software-factory-design.md). This file is the summary.

## One-liner

An AI software factory for **regulated enterprises**: a plain-language business request becomes a priced, planned, built, verified, and deployed application — while customer data never leaves customer-controlled AMD hardware.

## The pitch (for the deck)

- **Problem:** regulated enterprises (banks, insurers, fintechs, healthcare) can't use external AI on their real systems and data — so custom software still takes months of consultants. A frontier chat can't do these jobs anyway: too large for one context, data can't leave the boundary, and delivery requires validation against live systems.
- **Solution:** a hybrid pipeline — local trust layer (intake, PII firewall, OCR) → frontier planner that only ever sees sanitized specs → **local plan-verification loop** that certifies the plan and emits integration tests → elastic parallel coder fleet on AMD MI300X → consolidation gated by objective tests → adversarial QA with an independent **Numeric Oracle** → auto-deployed app + repo + docs + QA report + metered itemized invoice.
- **Target user:** regulated enterprises. Wedge sentence: **"we build where external AI is banned."**
- **Why now / why us:** open models on self-hosted AMD GPUs just crossed the quality threshold where the heavy middle of software delivery can run entirely on-prem; frontier intelligence is only needed at the ends (planning, targeted repair) — and in **Sovereign Mode**, not even there.
- **Market / product potential:** custom enterprise software + system integration is consultant-dominated, slow, and opaque; the itemized quote→invoice makes cost transparent per job.
- **Moat / originality:** the data-boundary architecture (external models never see raw data); the plan-verification loop (frontier plans, local model verifies — generation is frontier-hard, verification is structured analysis); dual-implementation QA via the oracle; Sovereign Mode toggle.

## AMD compute plan (mandatory — load-bearing)

- [x] **AMD Developer Cloud GPUs (ROCm):** elastic 1–5× MI300X running vLLM — trust layer (stage 0), plan verifier (stage 2), parallel coder fleet (stage 4), QA inspectors + oracle (stage 6). Live ROCm telemetry shown in the factory-floor UI.
- [x] **Fireworks AI API (AMD-hosted):** consolidator (stage 5); Sovereign Mode planner (stage 1); fallback path for the always-on live URL.
- [x] **Gemma:** two benchmark-justified roles — Numeric Oracle (AIME-tier math, local, cheap) and agentic inspector swarm (MoE ≈3.8B active params, τ2-bench-backed). Trust-layer seat currently Gemma but documented as model-agnostic. Validation gate before demos; go/no-go on the $2,000 Gemma prize.
- [x] **Visibility to judges:** README architecture section + diagram, vLLM/ROCm/Fireworks code paths in repo, live GPU telemetry in the demo UI, "where each stage runs" deck slide.

## Scope for the window (deadline Jul 11, 21:00 KT)

- **MVP (must work end-to-end):** the factory pipeline (stages 0–7), factory-floor UI, quote→metered invoice, and the hero demo (KYC/AML onboarding) delivered to a live URL.
- **Full target:** four demos in the gallery — KYC (hero) → Trading Surveillance w/ live Sovereign Mode toggle (finale) → Regulatory Report Factory → Claims Engine (**pre-decided cut** if time compresses) — plus judge-run mode (own scenario, budget-capped, queued, pre-warmed).
- **Explicitly optional (cut-first):** Gemma E4B edge beat (KYC voice intake); Claims demo; extra fleet GPUs beyond what the demos need.

## Tech stack (draft)

- **Models:** Gemma 4 (trust layer seat, oracle, inspectors — pending validation gate), Claude-class external planner + open frontier via Fireworks (Sovereign Mode), GLM 5.2-class verifier, Qwen-Coder/DeepSeek-class fleet (IDs TBD), large open consolidator on Fireworks.
- **Serving:** vLLM on ROCm, 1–5× MI300X (AMD Developer Cloud); Fireworks AI API.
- **Demo surface:** factory-floor mission-control web UI + per-job deployed apps + gallery.
- **Hosting for live URL:** factory infra with Fireworks-backed fallback (details during build).

## Open questions / decisions needed

See design doc §10. Highest priority: **product name** (blocks repo/deck/URL branding); exact model IDs; Gemma validation results; Claims demo go/no-go.
