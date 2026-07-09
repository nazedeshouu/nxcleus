# 11 — Model Catalog: Who Runs What, Where, and When

Created 2026-07-09 (v2.2, D12); **filled 2026-07-09 from the Opus 4.8 research pass** (verified against July-2026 releases; sources §7). Siblings: 02 (seats + capability routing §7), 07 §5.3 (scheduler consuming the flags), 08 §7 (validation gate). This file is the **canonical model list**: every servable model, its capability flags with evidence, and the seat/scenario assignment table. `infra/models.yaml` is generated/maintained from this document — when one changes, change both in the same commit (00 change protocol).

Confidence tags carried from the research pass: **[A]** authoritative (HF card / official blog / AMD/vLLM docs), **[M]** cross-checked secondary, **[L]** LOW-CONFIDENCE. Sizing convention: FP8 ≈ 1.0 GB/B params, bf16 ≈ 2.0 GB/B, W4 ≈ 0.55 GB/B; MI300X = 192 GB; "fits 1 card" = weights leave ≥60 GB KV headroom.

## 0. Node-B brain — RESOLVED (O4 closed 2026-07-09, team decision after the GLM-5.2 deep-dive)

**Decision: local `GLM-4.6` is the sovereign brain; hosted `GLM-5.2` (`fireworks:glm-5p2`) is node-B's fallback binding.** The team's GLM-5.2-first instinct was honored with a focused deep-dive; the evidence resolved it as follows.

**The droplet fact that reframed everything [M]:** AMD Dev Cloud (DigitalOcean GPU droplets) sells only **1× ($1.99/hr) and 8× ($15.92/hr) MI300X** shapes. The non-brain fleet alone (coders ~131 GB + trust/oracle/inspector ~92 GB ≈ 223 GB FP8) doesn't fit a 1× card — so any full demo session runs on an **8× droplet regardless of brain choice**. On that node, GLM-4.6 takes 3–5 of the 8 GPUs and the whole fleet fills the rest: one machine, all-local. GLM-5.2 (753B/~40B-active, novel `glm_moe_dsa` arch, 1M ctx, MIT [A]) monopolizes all 8 GPUs (FP8 ≈ 750 GB) and forces a **second** 8× droplet → $31.84/hr ≈ 3 sessions per $100 credit vs ~6.

**Deep-dive verdict matrix (full evidence + sources §8):**

| Config | Quality on the 4 node-B jobs | $/fleet-hr | Risk | Verdict |
|---|---|---|---|---|
| **B-max: GLM-4.6 + full fleet on ONE 8× droplet** — bf16 across ~5 GPUs (dodges the FP8-decode caveat, vLLM #31475) or FP8 across 3 if the decode bench passes | GPQA 82.9 (≈ Claude-4.5-class) [M], 200K ctx, same structured-output lineage as 5.2 — clears the certification bar with margin | $15.92 (~6 sessions/$100) | LOW–MED (mature `glm4_moe`) | **LOCKED — the sovereign brain** |
| **Hosted GLM-5.2 as node-B fallback** (`accounts/fireworks/models/glm-5p2`; also Together/OpenRouter/Z.ai [A]) | Frontier (AA Index v4.1 = 51, #1 open; GPQA 91.2, Terminal-Bench 82.7 [A]) on the always-on URL | ~$0 GPU (per-token, idle-only) | LOW. **Never carries RAW sovereign traffic** — node-B seats read RAW (D9), so hosted 5.2 is fallback-zone only, badged | **LOCKED — alongside B-max** |
| B-lite: GLM-4.5-Air-FP8 (106 GB, 1 card) | GPQA 73.3 [M]; **128K ctx is the operative risk** for whole-codebase certification | enables cheap 2×1× rehearsals | LOW | Emergency profile only |
| B-ultra: GLM-5.2 local (8× + second 8× for fleet) | Best raw; edge concentrated on conductor (safety-netted by proceed-without-review) and Sovereign finale | $31.84 (~3 sessions/$100) | **HIGH** — fresh DSA/tilelang kernel path; confirmed block-FP8 correctness bug on sibling gfx950 (sglang #28685; MI300X=gfx942 unconfirmed [L]) | **Post-deadline upgrade path** |

**Task-level honesty (why 4.6 suffices where it matters):** plan certification is bounded by context coverage and structured-output reliability, not frontier IQ — the 5.2→4.6 gap there is small; 5.2's large agentic edge lands on the conductor (quality-of-polish, never correctness-gating) and the Sovereign finale (recovered by the fallback binding on the always-on URL). **Do not use `GLM-4.7`** — active MoE-kernel crash on MI300X (sglang #16025) [A].

**Dev-runs note:** for the team's own development runs (synthetic data), node-B seats may bind to API-hosted GLM-5.2 via a custom connection (D13, 02 §8) for convenience; demo/judging runs use the local B-max profile.

## 1. Registry entries (→ `infra/models.yaml`)

| Key | HF id | Params (tot/act) | VRAM @ precision | Ctx | License | vLLM-ROCm | Serves seats |
|---|---|---|---|---|---|---|---|
| `glm-46` | `zai-org/GLM-4.6` (bf16) / `zai-org/GLM-4.6-FP8` | 357B/~32B | ~714 GB bf16 (≈5 GPUs of the 8× node) / ~357 GB FP8 (3 GPUs, if decode bench passes) | 200K | MIT [A] | supported 1/2/4/8-GPU (`glm4_moe`, mature); FP8-decode caveat §0 [A] | **THE BRAIN (locked):** certifier, conductor, consolidator, sovereign planner |
| `glm-52-hosted` | `accounts/fireworks/models/glm-5p2` (753B/~40B, 1M ctx, MIT) | — (hosted) | — | 1M | MIT [A] | n/a (Fireworks serving) | node-B **fallback binding only** — always-on URL between fleet sessions; never RAW sovereign traffic. Local serving = post-deadline upgrade (§0) |
| `glm-45-air-fp8` | `zai-org/GLM-4.5-Air-FP8` | 106B/12B | ~106 GB FP8 (1 card) | 128K | MIT [A] | mature (family verified single-MI300X) [A] | emergency brain profile only (§0) |
| `qwen3-coder-next` | `Qwen/Qwen3-Coder-Next` | 80B/3B | ~80 GB FP8 | 262K | Apache 2.0 [A] | **AMD Day-0** (GDN fusion + Fused-Shared-Expert) [A] | coder pool (node C) |
| `qwen36-27b` | `Qwen/Qwen3.6-27B` | 27B dense | ~27 GB FP8 | 262K | Apache 2.0 [A] | Day-0 [A] | coder pool (node D) |
| `devstral-small-2` | `mistralai/Devstral-Small-2-24B-Instruct-2512` | 24B dense | ~24 GB FP8 | 256K | Apache 2.0 [A] | standard Mistral arch, FP8 tool-calling [A] | coder pool (node D — shares card with `qwen36-27b`: 27+24=51 GB) |
| `gemma-4-26b-a4b` | `google/gemma-4-26B-A4B-it` | 26B/4B | ~26 GB FP8 | 256K | **Apache 2.0** (new for Gemma 4) [A] | AMD Day-0; needs transformers ≥5.5 [A] | trust (+ optional mixed-swarm inspector members; coder-pool guest for docs/extraction) |
| `gemma-4-31b` | `google/gemma-4-31B-it` | 31B dense | ~31 GB FP8 | 256K | Apache 2.0 [A] | Day-0 [A] | oracle |
| `qwen36-35b-a3b` | `Qwen/Qwen3.6-35B-A3B` | 35B/3B | ~35 GB FP8 | 262K | Apache 2.0 [A] | Day-0 [A] | **inspector (default — swapped from Gemma, §4)**; understudy for trust/oracle if validation gate fails |

Node-A packing check: trust 26 + oracle 31 + inspector 35 = **92 GB FP8, ~100 GB KV headroom** on one card — the whole QA/trust layer still fits node A.

## 2. Capability-flag matrix (evidence per `strong` claim; benchmarks §3)

| Model | greenfield-codegen | refactor-edit | sql-data | test-writing | docs-writing | extraction | math | agentic-tool-use | long-context | merge-review |
|---|---|---|---|---|---|---|---|---|---|---|
| `glm-46` (brain; `glm-52-hosted` fallback) | ok | ok | ok | ok | ok | ok | strong | strong | **strong** (whole-plan/codebase) | **strong** (the brain's job) |
| `qwen3-coder-next` | strong | strong | ok | strong | ok | weak | ok | **strong** (long-horizon agent-tuned) | **strong** (262K) | ok |
| `qwen36-27b` | **strong** (SWE-V 77.2) | strong | **strong** | **strong** | **strong** (multimodal, writing) | ok | strong | ok–strong | ok–strong | ok |
| `devstral-small-2` | ok | **strong** (multi-file, SWE-agent/OpenHands-tuned) | weak–ok | ok | weak | weak | weak | **strong** (harness-native) | ok (256K) | weak |
| `gemma-4-26b-a4b` | ok | weak | weak | ok | **strong** (multilingual prose, 140 langs) | **strong** (multimodal helps OCR post-proc) | ok | weak–ok (MCPMark 18.1) | ok | weak |
| `gemma-4-31b` | ok | weak | weak | ok | ok | ok | **strong** (AIME 89.2, dense/stable) | ok | ok | weak |
| `qwen36-35b-a3b` | ok | ok | ok | ok | ok | **strong** (OmniDocBench 89.9) | **strong** (AIME'26 92.7) | **strong** (MCPMark 37.0) | strong (262K) | ok |

## 3. Key benchmark evidence (why the `strong`s)

| Model | Numbers (tag) |
|---|---|
| GLM-4.6 | LiveCodeBench v6 ~82.8, AIME'25 ~93.9 [M — HF-card tiles render inconsistently; directional]; official: competitive w/ Claude Sonnet 4 / DeepSeek-V3.1 [A] |
| Qwen3-Coder-Next | SWE-bench Verified **70.6**, SWE-Pro 44.3, Terminal-Bench 2.0 36.2 [A]; Aider ~71 [M] |
| Qwen3.6-27B | SWE-bench Verified **77.2**, SWE-Pro 53.5, Terminal-Bench 59.3, LiveCodeBench v5 70.7 [A/vendor — scaffold-dependent ±3–5 pts] |
| Devstral-Small-2 | SWE-bench Verified **68.0**, SWE-Multilingual 55.7, Terminal-Bench 22.5 [A] |
| Gemma-4-26B-A4B | MMLU-Pro 82.6, GPQA-D 82.3, AIME 88.3, LiveCodeBench 77.1; multimodal, 140 languages [A]; MCPMark ~18.1 [A] |
| Gemma-4-31B | **AIME 89.2**, MMLU-Pro 85.2, GPQA-D 84.3 [A] |
| Qwen3.6-35B-A3B | **AIME'26 92.7**, GPQA 86.0, **MCPMark 37.0**, BFCL/MCP-Atlas 62.8, Terminal-Bench 51.5, OmniDocBench 89.9 [A] |

## 4. Gemma decision (feeds 08 §7 validation gate + the $2k prize story)

Research verdict per seat — Gemma 4 is now **Apache 2.0** (no custom-license concerns) and genuinely competitive, but not everywhere:

| Seat | Verdict | Rationale |
|---|---|---|
| trust | **KEEP Gemma 26B-A4B** | Multimodal (OCR post-proc), 140-language breadth, strong prose; gap to Qwen is small and task-dependent — defensible on merit, not just prize |
| oracle | **KEEP Gemma 31B** | AIME 89.2 vs Qwen 92.7 (−3.5) — but the oracle's value is **independence from the Qwen coder lineage** (dual implementation); dense = stable at k=3. The gap is the price of decorrelation, and it's the *stronger* technical story |
| inspector | **SWAP → Qwen3.6-35B-A3B** | MCPMark 37.0 vs 18.1 — ~2× on exactly the seat's job (agentic tool loops). Keeping Gemma here is prize-chasing at a measured 2× quality cost |

**Prize posture:** two benchmark-justified Gemma seats (trust + oracle) remain — the prize story survives with honest numbers. Optional third touchpoint: run the inspector as a **mixed swarm** (mostly Qwen members + some Gemma members) — heterogeneous probing is defensible on diversity grounds; decide at the validation gate. Note the node-A instance-sharing changes: trust no longer shares a served model with the inspector; it's three models on node A (§1 packing check still fits).

## 5. Scenario assignment table (the "when" — judge/deck-facing)

| Scenario | Seat | Routed by | Winner |
|---|---|---|---|
| New module from spec | `coder` pool | `greenfield-codegen` | `qwen36-27b` (highest SWE-V, dense/deterministic) |
| Long-horizon / long-context module, big interface surface | `coder` pool | `agentic-tool-use` + `long-context` | `qwen3-coder-next` |
| Defect-fix ticket / multi-file refactor | `coder` pool | `refactor-edit` | `devstral-small-2` (SWE-agent-tuned; vendor-diverse) |
| Schema/migration/query module; test files | `coder` pool | `sql-data` / `test-writing` | `qwen36-27b` |
| README/runbook, non-code DAG task | `coder` pool (guest) / `trust` | `docs-writing` | `gemma-4-26b-a4b` (warm on node A, strong prose) |
| Process-mode extraction step | per-BoM pool | `extraction` | `qwen36-35b-a3b` (OmniDocBench 89.9) or `gemma-4-26b-a4b` (multilingual corpora) |
| Numeric rule recomputation | `oracle` | fixed seat (`math`) | `gemma-4-31b` — independent of Qwen lineage by design |
| Inspector probe loop | `inspector` | fixed seat (`agentic-tool-use`) | `qwen36-35b-a3b` (mixed-swarm Gemma option, §4) |
| Plan certify / wave review / merge / sovereign planning | node-B family | fixed seats (`long-context`, `merge-review`) | `glm-46` local (locked); `glm-52-hosted` fallback binding |

## 6. Fireworks fallback bindings (catalog-verified, `accounts/fireworks/models/…`)

| Seat | Local | Fireworks fallback |
|---|---|---|
| node-B brain | GLM-4.6 (locked) | **`glm-5p2`** (locked — frontier-class fallback; "GLM-5.2 Fast" endpoint also available) |
| coder A | `qwen3-coder-next` | not hosted → `qwen3-coder-480b-a35b-instruct` (up) or `qwen3-coder-30b-a3b-instruct` (down) |
| coder B | `qwen36-27b` | `qwen3p6-27b` (exact) |
| coder C | `devstral-small-2` | `devstral-small-2-24b-instruct-2512` (exact) |
| trust | `gemma-4-26b-a4b` | `gemma-4-26b-a4b-it` (exact) |
| oracle | `gemma-4-31b` | `gemma-4-31b-it` (exact) |
| inspector | `qwen36-35b-a3b` | `qwen3p6-35b-a3b` (exact) |

## 7. Recency notes (Apr–Jul 2026) & rejected candidates

- **Gemma 4 went Apache 2.0** — first Gemma without the custom license; removes all commercial-use concerns [A].
- **GLM-5.2** (Jun 13) — #1 open on AA Intelligence Index v4.1, but ~754B multi-node only; **GLM-4.7** has active MI300X ROCm bugs → the specs' former "GLM-5.2-class" placeholder resolves to **GLM-4.6/4.5-Air** for this window.
- **DeepSeek V4** (Apr 24) — V4-Pro leads SWE-bench ~80.6 but 1.6T multi-node → relevant as Fireworks-hosted only, not local.
- **MiniMax M3** (Jun 1) — 1M-ctx multimodal; revisit only for video/screenshot corpora.
- **Nemotron 3 Ultra** — OpenMDW license (not Apache/MIT) [M] → excluded pending license read.

## 8. Sources

- Gemma 4: HF blog `huggingface.co/blog/gemma4` · Google blog · `ai.google.dev/gemma/docs/core` · AMD Day-0 article · vLLM recipe (`docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html`)
- GLM: HF `zai-org/GLM-4.6`, `GLM-4.6-FP8`, `GLM-4.5-Air-FP8` · sglang #16025 (4.7 MI300X crash) · vLLM #31475 (FP8 MoE decode) · andyluo7.github.io MI300X GLM-4.6V walkthrough
- Qwen: HF `Qwen/Qwen3.6-35B-A3B`, `Qwen3.6-27B`, `Qwen3-Coder-Next` · qwen.ai blog (3.6-27B) · AMD Day-0 article (Coder-Next) · vLLM blog (qwen3-next GDN)
- Devstral: HF `mistralai/Devstral-Small-2-24B-Instruct-2512` · mistral.ai/news/devstral
- ROCm/vLLM: rocm.blogs.amd.com LLM inference README · vLLM ROCm attention-backend blog (2026-02-27) · vLLM v0.24.0 release notes · FP8 quantization docs
- Fireworks catalog: fireworks.ai/models
- Recency: openrouter.ai June-2026 open-weights roundup · interconnects.ai open artifacts #21 · artificialanalysis.ai recent-launches

Confidence caveats: GLM-4.6 AIME/LCB figures are [M] (directional); Qwen3.6-27B SWE-V 77.2 is vendor-reported and scaffold-dependent (±3–5 pts); cross-model "AIME 2026" numbers from SEO blogs were excluded.
