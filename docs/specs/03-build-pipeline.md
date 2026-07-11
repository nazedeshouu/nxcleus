# 03 — Build Pipeline (Stages 0–7): Contracts

Locked 2026-07-07; revised 2026-07-08 (v2.1 — D7–D11). Upstream: design v2 §3 + v2.1 addendum. Siblings: 02 (seats), 07 (engine executing these stages), 08 (stage 6 detail), 10 (stage 3 detail).

**The pipeline in one story:** a business that can't send its data to external AI describes what it needs — prompt, files, codebase, databases, connectors — plus its confidentiality policy (what must never leak). A local trust model strips everything the policy and the PII baseline forbid *without losing the specification*, and composes a **planner brief** for the frontier model. The frontier planner (GPT-5.6) — told exactly what execution fabric awaits its plan — designs the work topology. A strong local model then does what the frontier couldn't: checks and completes the plan against the **real, raw context** the frontier never saw, restores production specificity, and pins the **goal** — the sentence the whole job will be judged against. From here everything is local: waves of parallel sub-agents build, a conductor reviews between waves, a consolidator merges, adversarial QA attacks, and the delivered process — verified against the goal — lands in the registry, where it runs forever without another frontier call.

## 1. Stage table (canonical — also the README/deck "where each stage runs" table)

| # | Stage | Seat(s) | Zone | Emits (headline events) | Latency target |
|---|---|---|---|---|---|
| 0 | Intake, policy, classification & boundary | `trust` | LOCAL | `intake.*`, `boundary.sanitized` | <10 s/turn |
| 1 | Planning (topology + BoM) | `planner` | EXTERNAL / LOCAL (sovereign) | `plan.delta`, `plan.completed` | 1–3 min, streamed |
| 2 | Plan completion, rehydration & certification | `certifier` (+`planner` consults, sanitized) | LOCAL | `certify.finding/amendment/consult_*`, `certify.goal_set`, `certify.certified` | 2–5 min, streamed |
| 3 | Quote | — deterministic | — | `quote.issued` | <2 s |
| 4 | Parallel code generation in waves *(build)* | `coder` pool + `conductor` | LOCAL (fleet) | `task.*`, `conductor.*` | 5–15 min |
| 5 | Consolidation *(build)* | `consolidator` | LOCAL | `consolidate.*` | 3–8 min |
| 4′/5′ | Corpus fan-out & aggregation *(process)* | per BoM | LOCAL (fleet) | `run.unit_completed`, `run.progress` | width-dependent |
| 6 | Adversarial QA + goal check | `inspector`, `oracle`, `coder` (fixes) | LOCAL | `qa.*` | 5–10 min |
| 7 | Delivery → registry | `trust` (docs) | LOCAL | `deliver.registered` | <1 min |

Stage transitions, retries, and resumability: 07 §3–4. Everything below is the data contract per stage.

## 2. Stage 0 — Intake, policy, mode classification & data boundary

**In:** free-text request; optional file uploads (PDF/images/CSV); optional **codebase** (repo URL or archive) and **database** attachments (connection or schema dump); optional connector selections (mock connectors + MCP-style integrations, 09); optional **confidentiality policy** (§2.1).
**Interaction:** multi-turn clarification (`job_messages`). `trust` drives with a structured elicitation prompt; every turn updates a draft spec until the customer confirms.

### 2.1 Confidentiality policy (D11)

The customer states what must never leak, through any of three UI paths (all may be combined):

1. **Document upload** — their terms-of-use / data-handling policy (PDF/text) into a dedicated field;
2. **Typed free text** — "don't leak client names, account numbers, or our fee schedule";
3. **Voice dictation** — recorded in the UI, transcribed by **local Whisper** (whisper.cpp on the VM, O9). The recording and transcript never leave the box — worth a beat in the demo.

`trust` distills all sources into a structured **RedactionPolicy** (persisted to `jobs.policy_json`):

```jsonc
{
  "sources": [{"kind": "doc|text|voice", "ref": "..."}],
  "rules": [
    {"id": "RP-1", "kind": "never_leak|mask|generalize",
     "description": "client legal names", "applies_to": ["entities.*.fields[pii=true]", "documents"],
     "origin": "customer_policy §4.2 | pii_baseline"}
  ]
}
```

The **PII baseline is always on** (names, accounts, contacts, government IDs, credentials/secrets); the policy adds company-specific rules on top (e.g. internal product names, fee structures, table names). No policy provided → baseline alone, stated explicitly in the UI. Event: `intake.policy_registered`.

### 2.2 Context intake (codebase / database / files)

- **Codebase:** ingested locally into a **code map** — file tree, module/symbol inventory, dependency edges, framework fingerprint. Two renditions: *raw* (kept local for stage 2/4) and *sanitized* (identifiers generalized per policy, all literals/secrets/comments-with-data stripped) for the planner brief.
- **Database:** schema-only extraction — tables, fields, types, relations; **never rows**. Field/table names maskable per policy (typed placeholders with structure preserved: `«TABLE_A»(id, «FIELD_1»: decimal)`).
- **Documents:** OCR = local pipeline (`pytesseract` or vLLM-vision if trust model supports it — decide Day 1; docs are synthetic either way) → `trust` structures the text.

Both renditions persist under the job workspace; the sanitized rendition summary lands in `SanitizedSpec.context_pack`. Event: `intake.context_mapped` (counts: files, symbols, tables, masked identifiers).

### 2.3 Output — `SanitizedSpec` a.k.a. the planner brief (persisted to `jobs.spec_json`)

```jsonc
{
  "title": "KYC/AML customer onboarding",
  "narrative": "sanitized restatement — no raw values",
  "mode": {"recommended": "build|process|semi", "confirmed": null, "rationale": "..."},
  "entities": [{"name": "Applicant", "fields": [{"name": "full_name", "type": "string", "pii": true}]}],
  "acceptance_criteria": [{"id": "AC-1", "text": "...", "verify": "test|inspector|oracle"}],
  "numeric_rules": [{"id": "NR-1", "text": "risk score = weighted sum...", "inputs": [...], "output": "risk_score"}],
  "context_pack": {                       // sanitized renditions only (§2.2)
    "code_map": {"files": 214, "modules": [...], "framework": "...", "tree_ref": "..."},
    "db_schemas": [{"table": "«TABLE_A»", "fields": [...]}],
    "attachments": [{"kind": "policy_doc|spec_doc", "summary": "..."}]
  },
  "connectors": [{"name": "sanctions_list", "kind": "dataset|api|mcp", "mock": true}],
  "volume": {"units_estimate": 200, "unit_noun": "application"},
  "sensitivity_report": {"pii_fields_masked": 7, "documents_ocred": 3,
                         "policy_rules_applied": ["RP-1", "RP-3"], "identifiers_generalized": 12}
}
```

**Prompt framing (contract):** `trust`'s composition prompt states explicitly that it is **writing a brief for a stronger frontier planner** — its job is maximum specification fidelity per token under the RedactionPolicy: strip values, keep structure; describe the codebase and schemas well enough that a model that will never see them can still plan against them.

**Boundary mechanics:** PII masking = `trust` extracts + replaces values with typed placeholders (`«PERSON_1»`, `«ACCOUNT_A»`); the map raw→placeholder stays in `boundary_vault` (local table, never serialized into any artifact leaving the LOCAL zone). `boundary.sanitized` event carries the sensitivity report — the UI's "what the frontier will never see" moment, now citing the customer's own policy rule IDs.
**Gate:** customer confirms spec + mode → stage 1.

## 3. Stage 1 — Planning. The Plan artifact

`planner` receives only `SanitizedSpec` (the planner brief). Streams reasoning + emits `Plan v1`.

**Planner system-prompt contract** — the planner is told, explicitly, what fabric will execute its plan, so it designs *for* it rather than emitting generic advice:

- Downstream is a **fleet of parallel sub-agents** (coder models or per-unit workers), a **conductor** that reviews between waves, a **consolidator** that merges, and an adversarial QA gate — the plan is an executable work order, not prose.
- Two topology archetypes, choose (or hybridize) per task:
  - **Independent parallelism** — the work shards into disjoint units with no cross-dependencies (rows 1–200 / 201–400, one document per worker). Emit a `topology` (process mode); each worker needs only its shard spec.
  - **Interdependent parallelism** — units depend on each other (app modules, refactor sites). Emit `modules` + typed `interfaces` + `dag`; every module declares its **touch points** — the exact interfaces it consumes and provides — so agents that never see each other's work cannot diverge at the seams.
- A local model with **full production context you never saw** will complete and correct the plan afterward: mark every assumption forced by sanitization (`"assumptions": [...]` per module/step) so it can verify them cheaply.
- The executing fleet routes each task to the pool member best at that *kind* of work (02 §7): tag every module and topology step with `"task_flags": [...]` from the canonical vocabulary (02 §7.2) — greenfield vs refactor vs SQL vs docs vs extraction is a planning fact, so declare it.
- The **BoM is mandatory** — name the seats, counts, and fan-out width the topology needs.

```jsonc
{
  "plan_id": "pln_01J...", "job_id": "job_01J...", "version": 1, "mode": "build",
  "modules": [                                   // build mode
    {"id": "mod_sanctions", "name": "sanctions_screening", "purpose": "...",
     "consumes": ["if_applicant"], "provides": ["if_sanctions_result"],
     "algorithm": "pseudocode...", "complexity": "S|M|L",
     "task_flags": ["greenfield-codegen", "sql-data"],
     "assumptions": ["schema «TABLE_A» assumed to have a unique applicant key"]}
  ],
  "interfaces": [
    {"id": "if_sanctions_result", "producer": "mod_sanctions", "consumers": ["mod_risk"],
     "schema": {"$schema": "...", "properties": {...}}}
  ],
  "dag": [{"task": "t_sanctions", "module": "mod_sanctions", "deps": ["t_ocr"]}],
  "topology": {                                  // process mode (modules/dag absent)
    "unit": {"noun": "contract", "source": "corpus", "schema": {...}},
    "steps": [{"id": "s_extract", "seat": "trust", "per_unit": true,
               "prompt_spec": "...", "output_schema": {...}},
              {"id": "s_aggregate", "per_unit": false, "kind": "aggregate",
               "spec": {"group_by": [...], "tables": [...], "charts": [...]}}]
  },
  "data_schemas": {...},
  "model_bom": {
    "seats": [{"seat": "oracle", "why": "3 numeric rules", "sampling": 0.05},
              {"seat": "coder", "count": 3, "why": "6 modules, width 3"}],
    "fleet": {"profile": "P3", "nodes": 3, "parallel_width": 8}
  },
  "estimates": {"frontier_tokens": 120000, "local_tokens": 2.5e6, "gpu_hours": 1.8},
  "risks": ["..."]
}
```

Schema is shared by both modes; mode picks which sections are required. **The BoM is mandatory in every plan** — it drives stage-3 pricing and fleet provisioning (the "GPU allocation justified by the plan" judging line).

**Constrained re-plan** (from stage-2 consults or refine): same seat, input = current plan + consult findings + **scope lock** (`"only_regions": ["mod_risk", "if_risk_result"]`); output = patch to those regions only, schema-validated against the lock (out-of-scope edits rejected).

## 4. Stage 2 — Plan completion, rehydration & certification

**In (D9 — this is the pass the frontier could never do):** Plan v1 + the **full raw context**: the customer's original request verbatim, all uploaded files, the *raw* code map, real DB schemas, the boundary vault, and the RedactionPolicy. The certifier is local; nothing here can leak.

**Prompt framing (contract):** the certifier's system prompt states its position in the chain — *a stronger model authored this plan without seeing the real context; your job is to find and fix everything that gap caused* — verify each marked `assumption`, correct details the sanitization blurred, and restore production specificity.

`certifier` runs the checklist suite over the full plan, one focused pass per check (parallelizable):

| Check | Question |
|---|---|
| interface-compat | every `consumes` matched by a `provides` with schema compatibility |
| data-completeness | every field any module/step reads is produced somewhere |
| error-coverage | every external call / parse / division has a specified failure branch |
| pattern-consistency | auth/state/rounding/locale conventions uniform across modules |
| ac-coverage | every acceptance criterion maps to ≥1 planned test/probe/vector |
| bom-sanity | every judgment step has a seat; fleet width ≥ DAG max parallelism; every module/step carries sane `task_flags` (a module editing existing code must carry `refactor-edit` — D12, 02 §7.3) |
| production-fit *(new, D9)* | every planner assumption checked against the raw context: real module paths, real table/field names and types, actual framework conventions, actual data shapes |

Each finding is triaged (structured output):

```jsonc
{"finding_id": "F-012", "check": "error-coverage", "plan_ref": "modules.mod_payout.algorithm",
 "severity": "gap|inconsistency|structural",
 "triage": "amend|consult",
 "amendment": {"patch": {...RFC6902...}, "rationale": "banker's rounding per spec §1.4", "spec_ref": "AC-3"},
 "consult_request": null}
```

- **Amendments** apply immediately to the plan; each writes an `amendments` row (`origin: certifier`) that is **hash-chained** (`hash = sha256(prev_hash + patch + rationale)`) — the audit-grade amendment log rendered in the UI.
- **Consults** batch per round → constrained re-plan → re-check affected regions. Hard cap 3 rounds, then remaining structural findings go to a human-review flag (job pauses with `certify.blocked`).

### 4.1 Rehydration (D9)

After checks pass, the certifier **rehydrates** the plan: placeholders whose real values the build needs (`«TABLE_A»` → real table name, generalized identifiers → real symbols) are resolved from the boundary vault and raw context. The certified plan is thereafter **data-class RAW** — legal everywhere in the LOCAL zone (which, per D7, is everything downstream), illegal to serialize outward. Placeholder↔value resolution is logged per amendment-log rules (rendered as "restored 12 production identifiers", values not shown in UI by default).

### 4.2 Consult sanitization gate

Consults and constrained re-plan requests go **back to the planner (EXTERNAL)** and therefore re-cross the boundary: outbound payloads are re-masked against the vault (mechanical reverse-substitution of every known raw value) and then swept by `trust` for residuals, before dispatch. Returned patches arrive placeholder-based and are rehydrated on application. The egress ledger shows each consult as `EXTERNAL / SANITIZED` — auditable in the demo.

### 4.3 Goal statement (D10)

With checks done, the certifier emits the **goal**: a semi-detailed, plain-language statement of what must exist when this job is finished — derived from the customer's *original raw request* (not the sanitized brief) plus the certified plan; concrete enough to verify against, short enough to hold in one prompt. Persisted to `jobs.goal`, event `certify.goal_set`. Consumers: the conductor (every wave review, stage 4), the **goal-fulfillment check** (stage 6), the registry + package manifest (stage 7), and the UI (pinned on the Build view — the "what we promised" line).

**Certification output:** certified plan (version++, rehydrated) + goal + `IntegrationTestSpec[]` + `OracleVector[]` (inputs only):

```jsonc
// test spec
{"id": "T-012", "module": "mod_risk", "kind": "integration",
 "given": {"if_sanctions_result": {...}, "if_pep_result": {...}},
 "expect": [{"path": "risk.level", "op": "eq", "value": "amber"}]}
// oracle vector — expected computed blind at stage 6 by the oracle, never stored here
{"id": "V-003", "rule": "NR-1", "inputs": {...}}
```

**Guardrail (design §3): certifier emits the tests that cover its own amendments** — a bad local patch dies at the same QA gate as bad code.

## 5. Stage 3 — Quote

Deterministic function of BoM + estimates + rates config (10 §4). Emits itemized `quote.issued`; job pauses until `POST /approve-quote` (demo clicks it on stage). Skipped-with-defaults for sandbox jobs (auto-approved under the sandbox budget cap).

## 6. Stage 4 — Parallel code generation in waves (build mode)

Execution is **wave-based** (D8): the engine partitions the DAG into topological levels — wave 1 = tasks with no unbuilt deps, wave 2 = tasks unblocked by wave 1, etc. In independent-parallelism plans there is exactly one wave; interdependent plans get the develop → review → develop rhythm.

**Within a wave:**
- Tasks dispatch to the `coder` pool (07 §6); concurrency = BoM width capped by fleet slots.
- Worker in: module spec (rehydrated — real names, real schemas) + its interfaces (**touch points**: exactly what it consumes/provides, so parallel workers can't diverge at the seams) + relevant test specs + coding standards prompt. Worker out (structured): `{"files": [{"path": "src/mod_sanctions.py", "content": "..."}], "notes": "..."}`.
- Module micro-loop: write files to workspace → run module's own tests in the code-exec sandbox (`--network none`) → ≤2 fix iterations → `task.completed` (or `task.failed` → 07 retry policy).
- Generated code targets the **runtime contract** (04 §3): pure-Python modules, judgment steps as declared `ctx.model(seat=...)` calls — never raw HTTP, never hardcoded model names.

**Between waves — conductor review (D8):** when a wave's tasks settle, the `conductor` receives the certified plan + goal + the wave's outputs (files, test results, worker notes) + the remaining DAG, and returns (structured):

```jsonc
{"verdict": "proceed|amend",
 "wave_assessment": "...",
 "goal_drift": null,                       // or a description — surfaces in the UI
 "amendments": [{"plan_ref": "modules.mod_risk", "patch": {...RFC6902...}, "rationale": "..."}],
 "rework": [{"module_id": "mod_pep", "instruction": "..."}]}
```

- Amendments may touch **only not-yet-built plan regions** (schema-validated against the remaining DAG — the same scope-lock mechanics as constrained re-plans); they hash-chain into the amendment log with `origin: conductor`. Problems in *already-built* modules become `rework` orders (≤1 per module per wave, runs as a module micro-loop) — never silent plan edits under finished work.
- Caps: ≤2 review rounds per wave; conductor unavailable/failing → **proceed without review** (07 §3.1) — the reviewer must never dead-end a build.
- Events: `conductor.wave_started`, `conductor.review`, `conductor.amendment`, `conductor.green_flag` — the Build view renders the wave rhythm ("wave 2/4 green-flagged, 1 amendment").

Final wave green-flagged → stage 5.

## 7. Stage 5 — Consolidation (build mode)

`consolidator` (local, node B — D7) receives all module files + interfaces + wiring spec; emits the assembled package (entrypoint `process.py` implementing the contract, imports resolved, config threaded). Gate: **full stage-2 integration suite** runs in the code-exec sandbox; failures → structured defect tickets → `coder` fixes (≤3 rounds) → re-run. Objective pass/fail, not review-by-vibes. The Demo-3 "validation wall" (partial → 143/143 green) is this gate rendered live.

## 8. Stages 4′/5′ — Corpus fan-out & aggregation (process mode)

No code generation. The **topology runner** (04 §4) executes the plan's `topology` directly: units stream through per-unit steps on the seats the BoM allocated (fleet fan-out, one unit per worker slot); aggregate steps run server-side (pandas) per the aggregation spec; oracle samples per `sampling` rate. Output = dataset + dashboard payload (generic renderers). This is also exactly what every judge-sandbox run executes (09).

## 9. Stage 6 — Adversarial QA + goal check

Full contract in 08. Summary: inspectors probe the **deployed-to-staging** process (real HTTP against a process-runtime container); oracle computes expected outputs for the stage-2 vectors blind; disagreements and probe failures file tickets → `coder` fixes → bounded loop → irreducible disagreements flagged for human review (the "N correct, M flagged" stat).

Last gate before delivery: the **goal-fulfillment check** (08 §1.5, D10) — the deliverable is verified against `jobs.goal`, holistically: does what exists match what was originally asked, in the customer's own terms? Verdict + gaps render at delivery ("goal fulfilled — 2 caveats").

## 10. Stage 7 — Delivery → operations registry

Assemble the **process package** (04 §2): certified plan + amendment log (certifier + conductor origins) + consult history, **goal statement + goal-fulfillment verdict**, code or topology, test specs + vectors, connector bindings, generated docs (`trust` writes README + runbook from the plan), QA report, final metered invoice (10 §5). Register `processes` + `process_versions` v1 (goal stored on the process row), build/tag the runtime image (build mode), emit `deliver.registered`. Job closes; everything after this is the operate phase (04).

---

## Wave-2 backend deviation (live integration, 2026-07-09)

Flagged per the change protocol.

- **Consults are best-effort at stage 2 (§4.2).** A certifier consult (escalation to the planner via a scope-locked re-plan) can fail against a real model — a `planner.replan` that touches regions outside the scope lock, a timeout, or a planner refusal. `certify/stage2.py` now catches those, emits a `system.notice`, and **continues** with the certifier's already-applied local amendments, rather than failing the whole certify stage. This matches the conductor's proceed-without-review policy (§6 / 07 §3.1): a bounded escalation must not be able to hard-block certification. The certifier's consult-emission prompt (`app/seats/certifier.py`) was separately tightened (soft consult cap; scope locks must quote verbatim region ids) so consults are both rarer and honour the scope lock.
- **Certifier output schemas relaxed for real-model variance:** `TESTS_SCHEMA` no longer requires `vectors` (a process with no numeric rules legitimately has none; the harness defaults it to `[]`); `SCENARIOS_SCHEMA` dropped the 3–5 `minItems/maxItems` cardinality. Both were forcing spurious structured-output validation failures + costly full-stage retries on live GLM output.

### 2026-07-10 hardening wave

Stage 0 gains **clarifying intake**: the trust brief may emit `clarifications` (≤3 questions — delivery / threshold / population / scope — only when the answer changes the built artifact). Non-sandbox jobs park at a new `awaiting_input` status (stage 0) and resume via `POST /jobs/{id}/answers`, which folds answers into the spec (`spec.clarification_answers`, delivery answers populate `spec.deliverable`) and re-runs intake with the answers binding; sandbox/reinstantiate jobs auto-answer and never park. The RAW original request now persists on a `jobs.request` column — intake's spec overwrite no longer erases the certifier's D9/D10 anchor (stage 2 and operate read it from there). Conductor amendments are persisted to the plan row (resume sees amended plans) and the conductor scope-lock uses exact region-id token matching. Stage 2's production-fit now **executes** every `kind:"sql"` topology step read-only against the bound corpus, with one certifier repair round (`certifier.repair_sql`); a still-failing query is dropped so the run degrades to per-unit judgment.

**T8/T9 addendum (same wave):** stage-4 build agents are now folder-isolated — each coder writes only `data/workspaces/<job>/agents/<module_id>/` and its per-task test run sandbox-mounts THAT folder alone; stage 2 publishes the certified interfaces read-only at `shared/interfaces.json`; the consolidator is the single cross-folder reader (`workspace.merge_agent_src` merges `agents/*/` into the package `src/` tree before assembly). The planner system prompt now teaches the three-way step vocabulary (sql for structured joins/aggregates/windows; per-unit judgment for semantic free-text fields like `*_narrative`/notes/memo — read, never keyword-matched; `analysis` for multi-hop/statistical logic via createTool) plus the folder-isolation capability paragraph; certifier bom-sanity amends vague `analysis` purposes.
