# 02 — Model Seats & Routing

Locked 2026-07-07; revised 2026-07-08 (v2.1 — D7 full-local-except-planner, D8 conductor, D9 certifier RAW); revised 2026-07-09 (v2.2 — D12 capability-aware routing, §7; model catalog split out to [11](11-model-catalog.md)). Upstream: design v2 §3, §6 + v2.1/v2.2 addenda. Siblings: 01 (zones), 07 (fleet manager), 08 (validation gate procedure), 11 (model catalog).

**Principle:** application code addresses *seats*, never models. A seat is a role with a data-class clearance, a routing policy, and one or more backend bindings. Swapping a model (e.g. Gemma fails the validation gate) is a YAML edit, not a refactor. Within a pooled seat, **capability flags** pick the best member per task (§7) — the second routing layer under the same principle: code names neither models nor pool members. Customers (and the team, in dev) can extend the registry with their own API-backed models and rebind seats in the UI (§8, D13).

**Zone rule (D7):** the `planner` default binding is the **only** designed-in non-local dispatch in the system. Every other seat binds local; `fireworks:*` appears exclusively in `fallback` bindings (fleet down / always-on URL between sessions) and is badged as demo infrastructure when used.

## 1. Seat registry

Model ids below are the **resolved picks from the catalog ([11](11-model-catalog.md), researched + locked 2026-07-09)**; registry keys in `infra/models.yaml`. Node-B brain **locked (O4 closed)**: local `glm-46` on the 8× droplet (bf16 ~5 GPUs, or FP8 ~3 if the decode bench passes) with hosted **`glm-52-hosted`** (`fireworks:glm-5p2`, frontier-class) as the fallback binding; `glm-45-air-fp8` is the emergency profile only — 11 §0.

| Seat | Role (stages) | Data class seen | Default binding | Sovereign binding | Fallback (fleet down) |
|---|---|---|---|---|---|
| `trust` | Intake dialogue, mode classification, policy distillation, PII masking, OCR post-processing, consult sanitization sweep, doc generation (0, 2-egress, 7) | **RAW** | `local:A/gemma-4-26b-a4b` | same | `fireworks:glm-5p2` ⚠️ demo-exception badge (live-verified 11 §6; `gemma-4-*` 404) |
| `planner` | Topology + BoM authoring; constrained re-plans; refine consults (1, refine) | SANITIZED — **never anything else; enforced** | `openrouter:openai/gpt-5.6-sol` | `local:B/glm-46` — zero non-local calls | `fireworks:glm-5p2` ⚠️ badge |
| `certifier` | Plan completion & certification against **full raw context**; rehydration; triage; goal emission; test-spec emission; refine triage (2, refine) | **RAW** (D9) | `local:B/glm-46` | same | `fireworks:glm-5p2` ⚠️ demo-exception badge |
| `conductor` | Wave review between stage-4 waves: outputs vs plan + goal; bounded amendments to unbuilt regions; green flag (4) | **RAW** | `local:B/glm-46` (same instance as certifier, different prompt) | same | skip review (07 §3.1 proceed-without-review) |
| `coder` (pool) | Module implementation + defect fixes (4, QA loop); capability-routed (§7) | RAW (production-specific plan) | pool: `local:C/qwen3-coder-next`, `local:D/qwen36-27b`, `local:D/devstral-small-2` | same | `fireworks:deepseek-v4-pro` ⚠️ demo-exception badge (live-verified 11 §6; `qwen3p6-*`/`devstral-*` 404) |
| `consolidator` | Merge modules into coherent codebase (5) | RAW (production-specific plan) | `local:B/glm-46` (same instance, third prompt) | same | `fireworks:glm-5p2` ⚠️ demo-exception badge |
| `oracle` | Numeric Oracle: blind expected-output computation; operate spot-checks (2-vectors, 6, operate) | SANITIZED* | `local:A/gemma-4-31b` | same | `fireworks:glm-5p2` (live-verified 11 §6; `gemma-4-31b` 404 — badged demo infra) |
| `inspector` | Agentic QA probes incl. goal-fulfillment check; operate-phase probes (6, operate) | SANITIZED | `local:A/qwen36-35b-a3b` — **swapped from Gemma** (MCPMark 37.0 vs 18.1, 11 §4); optional mixed swarm w/ Gemma members | same | `fireworks:glm-5p2` (live-verified 11 §6; `qwen3p6-35b-a3b` 404 — badged demo infra) |

\* Oracle test vectors derive from data inside the boundary; in production the seat is local-only — same demo-exception rule as `trust` applies.

Notes:
- Node A serves **three models** (trust-Gemma 26 GB + oracle-Gemma 31 GB + inspector-Qwen 35 GB ≈ 92 GB FP8, ~100 GB KV headroom — 11 §1). Node B serves **one GLM instance wearing four hats**: `certifier`, `conductor`, `consolidator`, and the Sovereign-Mode `planner` — different prompts, one set of weights.
- Post-stage-2 artifacts (certified plan, module specs) are data-class RAW (D9), which is why `coder`/`consolidator` clearances changed: everything they see stays in the LOCAL zone by construction. Their `fallback` bindings therefore ride the same `ALLOW_RAW_ON_AMD_HOSTED` demo exception as `trust` (synthetic data only, badge on).
- The Gemma-prize story is now **trust + oracle** (both defensible on merit — 11 §4: trust on multimodal/multilingual strength, oracle on lineage-independence from the Qwen coders); the inspector seat was swapped to Qwen on a measured ~2× tool-use gap. Both Gemma seats still pass through the validation gate (08 §7); the seat abstraction is the fallback plan. Gemma 4 is Apache 2.0 — no license caveats.

## 2. Router API (`app/models/router.py`)

```python
async def complete(
    seat: str,                      # registry name
    messages: list[Message],
    *,
    scope: Scope,                   # job/run/ticket ref — metering + events
    data_class: DataClass,          # RAW | SANITIZED — enforced, not advisory
    schema: dict | None = None,     # JSON Schema → structured output (see §2.1)
    stream: StreamHandler | None,   # token deltas → event bus
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Completion                     # .text | .parsed | .usage
```

Resolution order per call: seat → mode overlay (sovereign?) → backend health (fleet node up?) → **zone/data-class check** (01 §3 matrix; raises `BoundaryViolation` / `SovereignViolation`) → budget guard (10 §3) → dispatch → meter event + egress row + `model.call` event.

### 2.1 Structured output
All pipeline artifacts (specs, plans, findings, tickets, unit results) are schema-validated:
- vLLM backends: guided decoding (`response_format: json_schema`).
- Fireworks: JSON mode + schema in prompt.
- Anthropic: tool-call with the schema as input schema.
On validation failure: one repair round (error fed back), then raise to the stage's failure policy (07 §3). Never parse free text.

### 2.2 Clients
Three thin adapters behind one interface: `VllmClient` and `FireworksClient` (both OpenAI-compatible `/v1/chat/completions` via the shared egress client), `AnthropicClient` (official SDK, also egress-wrapped). Retries: 2 × exponential backoff on 429/5xx/timeouts; per-seat timeout config (planner 300 s, coder 240 s, others 120 s).

## 3. `infra/seats.yaml` (shape)

> **Normalization (AI Wave 1, 2026-07-09):** every binding's `model:` is a **key into
> `infra/models.yaml`** (validated by `infra/validate_config.py` — no dangling keys). The
> router resolves key → provider + hf_id + zone. Fallback IDs are live-verified per 11 §6
> (only `glm-52-hosted`/`deepseek-v4-pro` exist on the account). The example below uses keys.

```yaml
seats:
  oracle:
    data_class_max: SANITIZED
    temperature: 0.1
    bindings:
      default:   {backend: local,     node: A, model: gemma-4-31b}
      sovereign: default
      fallback:  {backend: fireworks, model: glm-52-hosted}   # live-verified 11 §6 (gemma-4-31b 404); model = infra/models.yaml KEY
    self_consistency: 3          # oracle-only: k votes, majority (08 §4)
  planner:
    data_class_max: SANITIZED          # hard ceiling — the one seat that can never see RAW
    temperature: 0.4
    bindings:
      default:   {backend: openrouter, model: openai/gpt-5.6-sol}
      sovereign: {backend: local,     node: B, model: glm-46}            # D7: sovereign = zero non-local calls
      fallback:  {backend: fireworks, model: accounts/fireworks/models/glm-5p2}   # demo infra only, badge on — frontier-class fallback (11 §0)
  certifier:
    data_class_max: RAW                # D9 — local seat, full context
    bindings:
      default:   {backend: local,     node: B, model: glm-46}           # locked (11 §0); emergency: glm-45-air-fp8
      sovereign: default
      fallback:  {backend: fireworks, model: accounts/fireworks/models/glm-5p2}    # demo exception, badge on
  conductor:                           # D8 — same served instance as certifier
    data_class_max: RAW
    bindings:
      default:   {backend: local,     node: B, model: glm-46}
      sovereign: default
      # no fallback: engine skips wave review when unavailable (07 §3.1)
  consolidator:
    data_class_max: RAW
    bindings:
      default:   {backend: local,     node: B, model: glm-46}
      sovereign: default
      fallback:  {backend: fireworks, model: accounts/fireworks/models/glm-5p2}    # demo exception, badge on
  # ... trust, coder (pool of qwen3-coder-next / qwen36-27b / devstral-small-2), inspector (qwen36-35b-a3b)
```

`coder` binds to a **pool**: a list of `{node, model}` entries referencing `infra/models.yaml` keys; the worker scheduler (07 §5.3) routes each task to the member whose capability flags best match the task's `task_flags` (§7, D12 — falls back to round-robin for unflagged tasks) and records which model built which module and why (renders in the BoM panel + invoice).

## 4. Enforcement (the boundary is code, not policy)

- `data_class` is a required argument; `RAW` outside `LOCAL` zone → `BoundaryViolation` unless `ALLOW_RAW_ON_AMD_HOSTED` demo exception (then: warning event + persistent UI badge on the job).
- Sovereign job + `EXTERNAL` zone → `SovereignViolation` (fail closed; the demo *proves* this by attempting a planner call with sovereign on and showing the red event).
- Every dispatch writes `egress_log` — the network monitor is a query, not a screenshot.

## 5. Fleet packing profiles (`infra/fleet.yaml` presets)

**Droplet reality (deep-dive 2026-07-09, 11 §0):** AMD Dev Cloud sells **1× ($1.99/hr) and 8× ($15.92/hr) MI300X** shapes only — no mid sizes on demand. The non-brain fleet alone (~223 GB FP8) exceeds a 1× card, so every full demo session runs on one 8× droplet; the old "one droplet per node" model is superseded — **node letters (A/B/C/D) are now logical GPU partitions of the 8× droplet**, except in P1 where "A" is a real 1× droplet. Weight estimates at FP8 unless noted; leave ≥60 GB headroom for KV per multi-seat GPU.

> **Exact slugs + availability (live account probe 2026-07-09, `doctl --api-url https://api-amd.digitalocean.com`):** shapes carry a **`-devcloud`** suffix — `gpu-mi300x1-192gb-devcloud` / `gpu-mi300x8-1536gb-devcloud`; region is **`atl1`-only**; base image `gpu-amd-base`. The **1× is self-serve** (`regions: ["atl1"]`). The **8× is request/allocation-gated, NOT self-serve** on this account: `available: true` but `regions: null` (vs the 1×'s populated region on the same API), and atl1's per-region inventory omits it — a create call has no enabled region to land in. **P2/P3 (the 8× hero profile) require the human to request 8× capacity via the AMD Dev Cloud console / organizers before the fleet can boot.** P1 (1×) is unblocked. Fleet automation + full findings: `infra/fleet/README.md`.

| Profile | Shape | Placement | When |
|---|---|---|---|
| **P0 — fallback** | 0 droplets | every seat on `fallback` binding (Fireworks, AMD-hosted; demo-infra badge on) — node-B fallback is **frontier-class GLM-5.2** | always-on URL between sessions; sandbox off-hours |
| **P1 — validation** | 1× droplet | `gemma-4-31b` (~31 GB) + `gemma-4-26b-a4b` (~26 GB) + `qwen36-35b-a3b` (~35 GB) ≈ 92 GB → trust, oracle, inspector local; GLM seats on `glm-5p2` fallback (badged), coder on Fireworks | validation gate, cheap dev, judging idle |
| **P2 — demo standard** | one 8× droplet | GPUs 0–4: `glm-46` **bf16** (~714 GB — dodges the FP8-decode caveat) → certifier/conductor/consolidator/sovereign planner · GPU 5: the A-trio (92 GB) · GPU 6: `qwen3-coder-next` (80 GB) · GPU 7: `qwen36-27b` + `devstral-small-2` (51 GB). Exact partition finalized at first boot | hero-demo rehearsal + live demos + recording |
| **P3 — wide fan-out** | same 8× droplet | brain switches to `glm-46` **FP8 on GPUs 0–2** (only if the decode bench passes, vLLM #31475), freeing GPUs 3–4 for coder replicas / process-mode width 8–16 | corpus fan-out beats, stage-4 width demos |

Note (D7): from P2 up, a default-mode build's only non-local dispatch is the stage-1 planner call to Anthropic; a Sovereign-Mode build dispatches nothing off-fleet at all.

Budget sketch (~$100 credit ≈ 6 fleet-hours at P2): **dev + validation-gate dry-runs go on the hackathon hosts' free GPU notebooks (≈8 h/day) wherever possible** to preserve credit; P1 validation ≈ 4 h → $8; P2 rehearsals ≈ 2×1.5 h → $48; P2 live demos + recording ≈ 2 h → $32; judging window pinned on P1 ≈ 4 h → $8. Total ≈ $96. Guarded by the idle watchdog (07 §5.4) + Discord alert — at $15.92/hr an idle 8× droplet burns a rehearsal per hour.

## 6. Model IDs — resolved (O2 closed 2026-07-09; full catalog with evidence + sources in [11](11-model-catalog.md))

Selection criteria that produced the picks, in order: (1) fits packing profile with KV headroom, (2) vLLM-on-ROCm support (all picks are AMD Day-0 or family-verified on MI300X), (3) benchmark fit for the role, (4) permissive license (all picks MIT or Apache 2.0). Day-1 smoke test per model still required before locking `infra/models.yaml`.

| Seat | Resolved pick | Understudy (validation-gate failure / fit issues) |
|---|---|---|
| certifier / conductor / consolidator / sovereign planner (node B, one instance) | `glm-46` local (locked) + `glm-52-hosted` fallback binding — 11 §0; emergency `glm-45-air-fp8`; **never GLM-4.7** (MI300X kernel crash) | `qwen36-35b-a3b` (fits trivially, top math, but only 3 B active — shallower certification) |
| coder pool | `qwen3-coder-next` + `qwen36-27b` + `devstral-small-2` (capability-diverse — 11 §2) | `qwen3-coder-30b-a3b-instruct` (in-band swap for Coder-Next) |
| trust / oracle | Gemma 4: `gemma-4-26b-a4b` / `gemma-4-31b` (prize seats, merit-defensible — 11 §4) | `qwen36-35b-a3b` for either — triggered only by validation-gate failure |
| inspector | `qwen36-35b-a3b` (swapped from Gemma — 11 §4) | mixed swarm with Gemma members (prize option) |
| Fireworks fallback bindings (P0 / fleet-down only) | exact catalog ids per 11 §6 | — |

## 7. Capability-aware routing inside pooled seats (D12, v2.2)

**Why:** models are not interchangeable — one coder model is strongest at greenfield generation, another at surgical refactoring, another at SQL; Gemma seats are cheap and excellent at extraction and prose. A pool that round-robins wastes that. Routing becomes two layers:

1. **Seat resolution** (§2, unchanged) — role → zone/data-class/binding.
2. **Member selection** (new) — within a pooled seat, pick the member whose capability flags best match the *task*.

### 7.1 The model registry — `infra/models.yaml`

Every servable model gets one entry; seats/pools reference entries by key. This file plus the assignment table in [11](11-model-catalog.md) is the canonical answer to "which model runs what, where, and when":

```yaml
models:
  <model-key>:                    # e.g. qwen35-coder-32b
    hf_id: "..."                  # exact HF repo (or provider id for fireworks/anthropic entries)
    serving: {vram_gb: 66, precision: bf16|fp8|awq, context: 131072}
    flags:                        # capability vocabulary — §7.2; values: strong | ok | weak
      greenfield-codegen: strong
      refactor-edit: ok
    evidence: "SWE-bench X%, Aider Y% (11 §sources)"   # why we believe the flags
    license: apache-2.0
```

### 7.2 Capability flag vocabulary (canonical — keep small, extend deliberately)

| Flag | Task smell |
|---|---|
| `greenfield-codegen` | new module from spec + interfaces |
| `refactor-edit` | surgical change to existing code; defect-fix tickets |
| `sql-data` | schema work, migrations, query-heavy modules, pandas aggregation steps |
| `test-writing` | emitting test files from specs |
| `docs-writing` | READMEs, runbooks, human-facing prose |
| `extraction` | structured data out of unstructured text (process-mode unit steps) |
| `math` | numeric recomputation, rule evaluation |
| `agentic-tool-use` | bounded tool loops (inspector probes) |
| `long-context` | whole-plan / whole-codebase inputs (certify, conduct, consolidate) |
| `merge-review` | cross-module coherence judgment |

### 7.3 Where task flags come from

- **Planner (stage 1):** the prompt contract (03 §3) now requires each module / topology step to carry `"task_flags": [...]` from this vocabulary — the planner knows what kind of work each unit is, so it declares it.
- **Certifier (stage 2):** `bom-sanity` check extends to flag sanity (a module that edits existing code must carry `refactor-edit`; missing/nonsense flags amended like any other gap).
- **Tickets:** inherit their module's flags + `refactor-edit` (a fix is an edit by definition).
- **Fallback:** an unflagged task routes as before (round-robin) — flags degrade gracefully to v2.1 behavior.

### 7.4 Selection algorithm (deterministic — runs in the scheduler, no LLM)

```
candidates = healthy members of the seat's pool
score(m)   = Σ over task.flags: {strong: +2, ok: +1, weak: −2, absent: 0}
pick       = argmax score; ties → least-loaded, then round-robin
no positive score → any healthy member + system.notice (never block on routing)
plan may pin explicitly: task {"model": "<model-key>"} overrides (BoM-visible)
```

The decision is recorded in the `task.started` payload (`routing: {flags, chosen, score, considered}`) and in `build_tasks.assigned_backend` / meter events as before — the BoM panel upgrades from "which model built which module" to "and *why*". Pools may be **heterogeneous** (e.g. the coder pool can carry a Gemma member flagged `docs-writing`/`extraction` for the DAG's non-code tasks) — better Gemma utilization with zero extra serving cost, since those instances are already warm on node A.

Scope note (hackathon): member selection applies to pooled seats (`coder`, and process-mode per-unit steps). Single-model seats (trust, oracle, certifier family) don't route — the registry still documents their flags so the catalog (11) is complete.

## 8. Custom connections & user-configurable seats (D13, v2.2)

The registry (§7.1) is extensible at runtime: customers — and the team during development — can plug in **their own API-backed models** and rebind seats, replicating the capability-flag architecture over external APIs.

### 8.1 Connections (BYOK)

UI flow: **add API key → point it at the endpoint → register models under it → tag each with capability flags.**

- A **connection** = `{name, base_url (OpenAI-compatible endpoint), api_key, data_class_ceiling, counts_as_local}`. Key is write-only: stored encrypted at rest, surfaced masked, **never** serialized into events, logs, or packages.
- `data_class_ceiling` defaults to **SANITIZED** — a third-party API is outside the boundary. Raising it to RAW requires an explicit **boundary attestation** in the UI ("this endpoint is inside my trust boundary" — e.g. the customer's own on-prem vLLM or private-VPC deployment); attested connections may also set `counts_as_local: true`, which makes them eligible for RAW seats *and* Sovereign Mode — that's the "on their metal" deployment story expressed in config.
- One connection can carry **many models**: each entry = `{provider_model_id, display_name, flags[] (same vocabulary as §7.2 — coding, refactoring, creative writing, …), context_len}`. Custom entries merge into the runtime registry alongside `infra/models.yaml`; capability routing (§7.4) treats them uniformly.

### 8.2 Seat rebinding

Every seat's binding is user-configurable in the UI (global or per-job) — GPT-5.6 is the *default* planner, not a hardcode. Eligibility is enforced, not advisory: a model is offered for a seat only if its connection's zone/ceiling satisfies the seat's data class (RAW seats: LOCAL or RAW-attested connections only) and Sovereign Mode additionally requires LOCAL or `counts_as_local`. Overrides emit `config.seat_bound` and render in the BoM panel — routing stays visible.

### 8.3 Enforcement & dev use

- New zone: **CUSTOM** in the 01 §3 matrix — SANITIZED ✅; RAW ❌ unless attested (then ⚠️ "customer-attested boundary" badge); sovereign ❌ unless `counts_as_local`. Every dispatch egress-logged like all zones.
- **Team dev runs:** bind the node-B seats to an API GLM-5.2 connection (Z.ai/OpenRouter) for convenience — synthetic data only, demo-exception badge on; demo/judging runs use the local P2 profile.

## 9. GPU telemetry

Node agent (infra/droplet/node-agent, ~100 LOC FastAPI): `GET /telemetry` → `rocm-smi --json` (VRAM used/total, GPU util, power, temp) + vLLM `/metrics` scrape (running/waiting requests, tokens/s). Control plane polls every 2 s per node → `telemetry.gpu` events → UI panel + stored 1-in-15 samples to `meter_events` for GPU-second attribution (10 §2).
