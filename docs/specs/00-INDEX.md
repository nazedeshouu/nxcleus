# Engineering Spec Map — Index

**Status:** locked 2026-07-07 (architecture planning session); **revised 2026-07-08 (v2.1)** — full-local-except-planner, conductor seat, certifier RAW access, goal statement, confidentiality-policy intake (D7–D11); **revised 2026-07-09 (v2.2)** — capability-aware routing + model catalog (D12, spec 11). Implements the product design in
[`../plans/2026-07-07-adaptive-sovereign-platform-design.md`](../plans/2026-07-07-adaptive-sovereign-platform-design.md) (v2 + v2.1 addendum, authoritative)
— read that first for *what* we're building and *why*; these specs define *how*, on the logic / AI / backend side.
Frontend **visual** design is explicitly out of scope (separate session); the UI's **data contract** is fully specified here (06).

## The map

| # | Spec | Covers | Build order hint |
|---|---|---|---|
| [01](01-system-architecture.md) | System architecture | Hosts, zones, data boundary, AMD compute topology + judge-facing justification, repo layout, config/env, deployment | Day 1 (scaffold) |
| [02](02-model-seats-and-routing.md) | Model seats & routing | Seat registry, boundary classes, ModelRouter, Sovereign Mode routing, vLLM packing profiles, candidate model IDs, validation gate | Day 1 (router first) |
| [03](03-build-pipeline.md) | Build pipeline (stages 0–7) | Per-stage I/O contracts, plan JSON schema, amendment/consult formats, test-spec format, mode branches | Day 1–2 |
| [04](04-operate-refine-registry.md) | Operate / Refine / Registry | Process package format, runtime contracts, run execution, versioning, re-instantiation, warranty assurance | Day 2–3 |
| [05](05-data-model.md) | Data model | Full SQLite schema, event log, indexes, retention | Day 1 (with scaffold) |
| [06](06-api-and-events.md) | API & event catalog | REST endpoints, SSE channels, complete event type catalog, auth, replay | Day 1–2 (contract for UI) |
| [07](07-orchestrator-and-fleet.md) | Orchestrator & fleet | Event-sourced engine, stage state machine, worker pool, fleet manager, budget guards, sandbox queue | Day 1–2 |
| [08](08-qa-oracle-inspectors.md) | QA, Oracle, Inspectors | Stage-6 harness, Numeric Oracle protocol (build + operate), inspector agent loop, ticket lifecycle, Gemma validation gate procedure | Day 2–3 |
| [09](09-sandbox-and-seed-kits.md) | Sandbox & seed kits | Judge sandbox backend, three synthetic companies, demo seed kits, per-demo backend requirements, replay feature | Day 3–4 |
| [10](10-metering-and-economics.md) | Metering & economics | Meter events, cost attribution, rates config, quote engine, invoice, money-slide data | Day 2 (hooks) / Day 3 (quote) |
| [11](11-model-catalog.md) | Model catalog | The canonical model list: registry entries (`infra/models.yaml`), capability flags per model, seat/scenario assignment table, research evidence + sources | Day 1 (with O2) |

## Locked decisions (this session, 2026-07-07)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Backend stack | **Python 3.12 + FastAPI**, async throughout; React frontend consumes REST+SSE | Best ecosystem for OpenAI-compatible clients (vLLM/Fireworks), agent loops, OCR/PII tooling; asyncio fits the fan-out orchestration |
| D2 | Hosting topology | **Always-on small VM (control plane, DB, UI, deployed processes) + elastic MI300X droplets (all model inference)** | See "hosting justification" in [01 §2](01-system-architecture.md) — written to be lifted verbatim into README + deck so judges cannot misread the VM as diluting AMD usage. Every token everywhere is generated on AMD silicon; the VM runs zero inference. Preserves the ~$100 GPU credit for live builds + the judging window instead of idle uptime, and keeps the live URL alive 24/7 via Fireworks (AMD-hosted) fallback routing |
| D3 | Orchestration | **Custom event-sourced asyncio engine** (no LangGraph/Temporal) | Full control of the demo-critical surfaces (streamed amendments, BoM panel, defect board, metering); event sourcing gives replay + resumability for free; ~600–900 LOC we own |
| D4 | Spec format | Index + subsystem specs (this directory), each executable standalone by a fresh agent | Matches the team's plan-in-one-session / execute-in-another workflow |
| D5 | Persistence | **SQLite (WAL mode)** on the VM, via SQLAlchemy Core + aiosqlite | Single control plane, no concurrent writers besides the API process; Postgres upgrade path noted in 05 but not needed in the window |
| D6 | Generated-code strategy | Generated processes implement a **standard runtime contract** (05/04); the platform provides execution, API chrome, and generic result renderers — no generated frontends | Removes the highest-variance failure mode (bespoke generated apps) while keeping code generation real and audit-grade |

## Locked decisions — v2.1 revision (2026-07-08)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D7 | Zone topology | **Full-local except the planner.** Every seat except `planner` (Anthropic Fable 5) runs on self-hosted MI300X: consolidator moves LOCAL (node B), Sovereign-Mode planner rebinds to the **local** GLM-class model (node B), not Fireworks. Fireworks is demoted to an **availability fallback only** (always-on URL between fleet sessions, fleet-down failover) — badged as demo infrastructure, never part of the product architecture | The product claim is "frontier intelligence without your data leaving your walls" — the only thing that ever crosses the boundary is the sanitized planner brief. A designed-in second cloud dilutes that claim; Sovereign Mode is now literally zero non-local calls. Deployment story: customer's own metal, or dedicated AMD capacity we operate for them |
| D8 | Wave orchestration | **GLM conductor hybrid.** The engine still dispatches deterministically (D3 stands), but stage 4 runs the DAG in **topological waves**; between waves a `conductor` seat (same served GLM as certifier) reviews wave outputs against the plan + goal and may issue **bounded amendments to not-yet-built regions** (same constrained-patch + hash-chain mechanics as certification) before green-flagging the next wave (03 §6, 07 §3.1) | Adaptivity of a model orchestrator without giving up replay/resumability; conductor failure never blocks a build (proceed-without-review policy) |
| D9 | Certifier data access | Certifier (and conductor) read **RAW**: initial prompt verbatim, uploaded files, code map, DB schemas, boundary vault. Stage 2 **rehydrates** the plan to production specificity; the certified plan is data-class RAW and stays inside LOCAL. Anything crossing back to the planner (consults, re-plan requests) passes the **consult sanitization gate** (03 §4.2) | The whole point of the local completion pass is fixing what the frontier couldn't know; post-planner the pipeline is all-local (D7), so production detail is boundary-safe |
| D10 | Goal statement | Stage 2 emits a **goal** — a semi-detailed plain-language statement of what must exist when the job is done, derived from the customer's original (raw) request + the certified plan. Carried on the job, checked by the conductor every wave, verified by a dedicated **goal-fulfillment check** at stage 6, stored in the registry and package manifest | Quality-control anchor: proves we built what was originally asked, not what survived translation through sanitization and planning |
| D11 | Confidentiality-policy intake | First-class stage-0 input: the customer's terms-of-use / "never leak" rules, via **document upload, typed text, or voice dictation** (transcribed by local Whisper — the recording never leaves the box). `trust` distills it into a structured **RedactionPolicy** that governs sanitization alongside the always-on PII baseline (03 §2.1) | Sanitization becomes contractual, not discretionary — the sensitivity report cites the customer's own policy clauses |

## Locked decisions — v2.2 revision (2026-07-09)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D12 | Capability-aware routing | Second routing layer under the seat abstraction: every servable model gets a registry entry (`infra/models.yaml`) with **capability flags** (greenfield-codegen, refactor-edit, sql-data, docs-writing, extraction, math, …); the planner tags every module/step with `task_flags`; the pool scheduler picks the member with the best flag match (deterministic argmax, no LLM; unflagged → round-robin) (02 §7, 03 §3, 07 §5.3). Canonical model list + evidence lives in spec [11](11-model-catalog.md) | Models aren't interchangeable — route refactors to the editor, SQL to the data model, prose to Gemma. Better output *and* better Gemma utilization at zero extra serving cost; the BoM panel shows not just which model built each module but why |
| D13 | BYOK connections + user-configurable seats | Customers add **API connections** in the UI (key + endpoint), register models under each, and tag them with the same capability flags; custom entries merge into the routing registry. **Every seat's binding is user-configurable** (Fable 5 is the default planner, not a hardcode). Boundary enforced per connection: SANITIZED ceiling by default; RAW/sovereign eligibility only via explicit boundary attestation / `counts_as_local` (02 §8, 01 §3 CUSTOM zone, 05, 06) | Replicates the capability-flag architecture over external APIs; expresses the "your metal or your trusted provider" deployment story in config; also how the team dev-runs against API GLM-5.2 without touching demo profiles |
| D14 | Node-B brain (closes O4) | **Local GLM-4.6** (bf16 across ~5 GPUs of the 8× droplet; FP8/3-GPU variant if the decode bench passes) + **hosted GLM-5.2 (`fireworks:glm-5p2`) as the node-B fallback binding**. GLM-5.2 local is the post-deadline upgrade; GLM-4.5-Air is the emergency profile; GLM-4.7 excluded (MI300X kernel crash). Full verdict matrix: [11 §0](11-model-catalog.md) | Deep-dive evidence: droplet shapes are 1×/8× only, so local 5.2 means a second 8× droplet (~3 vs ~6 sessions per $100) + unproven DSA-kernel risk days before deadline; on plan certification specifically 4.6 (GPQA ≈ Claude-4.5-class, 200K ctx) is not materially worse — 5.2's edge lands on safety-netted/recoverable surfaces, and the fallback binding keeps frontier GLM-5.2 in the system |

## Open decisions (carried from design §12 + new)

| # | Item | Blocks | Resolve by |
|---|---|---|---|
| O1 | ~~Product name~~ **RESOLVED 2026-07-09** — the product is **Nxcleus** (team decision; propagate to repo name, live URL, README, deck, and the frontend brand token) | — | done |
| O2 | ~~Exact model IDs~~ **RESOLVED 2026-07-09** — catalog locked in spec [11](11-model-catalog.md) (GLM-4.5-Air/4.6, Qwen3-Coder-Next, Qwen3.6-27B, Devstral-Small-2, Gemma 4 ×2, Qwen3.6-35B-A3B); Day-1 vLLM-ROCm smoke test per model remains | `infra/models.yaml` values | smoke tests, Day 1 |
| O3 | Gemma validation results (oracle accuracy; trust-seat checks; mixed-swarm inspector option) — prize seats now **trust + oracle** (inspector swapped to Qwen, 11 §4) | Gemma-prize go/no-go; seat swap if failed | validation gate, Day 2 (08 §7) |
| O4 | ~~Node-B brain~~ **RESOLVED 2026-07-09 → D14** (local GLM-4.6 + hosted GLM-5.2 fallback; deep-dive in 11 §0). Residual: FP8-vs-bf16 decode bench at first boot picks the P2 GPU split | `infra/fleet.yaml` partition values | first fleet boot, Day 1 |
| O9 | ~~Whisper placement~~ **RESOLVED 2026-07-09 (recon)** — whisper.cpp on the VM CPU; dev machine already has `whisper-cli` (Homebrew) + `ggml-large.bin`; `WHISPER_MODEL_PATH` points at the model file | — | done |
| O5 | ~~Droplet automation~~ **RESOLVED 2026-07-09 (recon) + IMPLEMENTED (fleet wave)** — `doctl --api-url https://api-amd.digitalocean.com` verified live; scripts in `infra/fleet/` (`fleet_up/down/status/watchdog`, shellcheck-clean, dry-run-tested). Exact slugs carry a **`-devcloud`** suffix: `gpu-mi300x8-1536gb-devcloud` ($15.92/hr) / `gpu-mi300x1-192gb-devcloud` ($1.99/hr), **`atl1`-only**; base image `gpu-amd-base`. 1× self-serve; 8× catalog-orderable but capacity-gated (not region-advertised). Real create/drain/destroy + idle auto-destroy behind a flag. Manual portal = fallback | needs `DIGITALOCEAN_ACCESS_TOKEN` | done |
| O6 | Regulatory schema for Demo 3 | seed kit only | Day 3 |
| O7 | Claims demo go/no-go (pre-decided cut) | nothing structural | Day 4 |
| O8 | Sandbox dataset depth | seed volume only | Day 3 |

## Glossary (canonical names — use everywhere)

- **Seat** — a named model role (`trust`, `planner`, `certifier`, `conductor`, `coder`, `consolidator`, `oracle`, `inspector`). Seats bind to backends at runtime; code never names models directly.
- **Backend** — a serving endpoint: `local:<node>/<model>` (vLLM on MI300X), `fireworks:<model-id>` (AMD-hosted, **fallback only** per D7), `anthropic:<model-id>` (external frontier).
- **Zone** — `LOCAL` (self-hosted MI300X), `AMD_HOSTED` (Fireworks, fallback), `EXTERNAL` (Anthropic).
- **Data class** — `RAW` (customer data / production-specific artifacts) or `SANITIZED` (masked/abstracted). Only `SANITIZED` ever reaches `EXTERNAL`.
- **Job** — one trip through the build pipeline (stages 0–7). **Process** — a registered, versioned automation in the registry. **Run** — one execution of a process version on new data.
- **Plan** — the frontier-authored, certifier-rehydrated-and-amended JSON artifact at the center of everything (schema in 03 §3). Sanitized as authored (v1); RAW once certified (D9).
- **Planner brief** — stage 0's sanitized package for the planner: spec + context pack + policy summary, framed as input to a stronger model (03 §2.3).
- **RedactionPolicy** — the customer's distilled "never leak" rules (doc / typed / dictated), governing sanitization alongside the PII baseline (03 §2.1).
- **Goal** — the plain-language statement of what must exist when the job is done; emitted at stage 2, enforced at stage 6 (D10).
- **Wave** — one topological level of the build DAG; the unit the conductor reviews and green-flags (03 §6, 07 §3.1).
- **Independent / interdependent parallelism** — the two topology archetypes the planner chooses between: disjoint fan-out with no cross-dependencies (process mode) vs. modules with declared interfaces and touch points (build mode) (03 §3).
- **BoM** — the plan's model bill-of-materials; drives fleet provisioning and the quote.
- **Model registry / capability flags** — `infra/models.yaml` + runtime custom entries: one entry per servable model with flags (what it's good at); pooled seats route each task to the best-flagged member (02 §7, D12). Catalog with evidence: spec 11.
- **Task flags** — the plan's per-module/step declaration of work kind (`greenfield-codegen`, `refactor-edit`, `sql-data`, `docs-writing`, `extraction`, …) consumed by the scheduler.
- **Connection (BYOK)** — a customer-added OpenAI-compatible endpoint (key + base URL) carrying one or more flag-tagged custom models; zone `CUSTOM`, SANITIZED ceiling unless boundary-attested (02 §8, D13).
- **Amendment / Consult** — a local patch to the plan (origin: certifier or conductor) vs. escalation to the planner (03 §5). Consults cross the boundary and are therefore sanitized.
- **Ticket** — structured defect (inspector, oracle, consolidation, or warranty origin).

## Change protocol

These specs are the single source of truth for the build. When implementation reality diverges (model IDs, GPU fit, latency), update the spec in the same commit as the code change — a fresh session must always be able to trust this directory.
