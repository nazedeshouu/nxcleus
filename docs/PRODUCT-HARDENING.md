# Product Hardening — production-readiness marks + business-scenario gap analysis

**Date:** 2026-07-10. Basis: full backend read (roast session), four architecture visualizations in
`docs/viz/`, dataset overview in `docs/demo-datasets.md`. This file is the shared reference for the
hardening wave; the locked wave scope is at the bottom.

---

## 1. Not production ready — the marks

Classification: **SIMULATED** (demo theater where product is claimed), **BROKEN** (bug defeating a
design decision), **MISSING** (product surface that doesn't exist), **INSECURE** (fails a trust
boundary), **FRAGILE** (works until it doesn't).

### SIMULATED — the operate phase (highest concentration)

| # | What | Where | Reality |
|---|---|---|---|
| S1 | **Registered-process runs** (`kind=batch` — the "runs forever on your data" promise) | `runtime/operate.py:24-78` `drive_run` | Synthetic `unit-{i}` refs; verdicts by `i%7`/`i%11`; one **rehearsed** warranty discrepancy on unit-0 of every batch; unit count parsed from `input_ref` as a digit string, default 8. No real data ever enters a registered-process run. The real execution path (`run_process_fanout`) only runs during stage 4 of a build. |
| S2 | Oracle "self-consistency k=3" | `seats/_placeholder.py:246` | One model call, votes fabricated, vectors ending in "2" scripted "uncertain". Mock mode only, but mock mode is what tests + offline demos run. |
| S3 | "Generated" process code | `seats/_placeholder.py:181` | Canned `_PROCESS_PY` appended over whatever the coder produced; generated file paths all rewritten to one path. Mock path only. |
| S4 | Oracle rule text | `qa/stage6.py:28` | `_RULE_TEXT` hardcodes the KYC formula in the QA stage source; the "blind" oracle reads it from a constant, not from certifier-emitted vectors. **Live path too.** |
| S5 | QA fix loop "verified" | `qa/stage6.py:300`, `consolidate/stage5.py:49` | `coder.fix()` → ticket stamped `verified` with zero retest. Goal-check manifest reports `integration_tests_passed: len(tests)` — a count, not results (`stage6.py:161`). |
| S6 | Non-sandbox process corpus | `runtime/operate.py:122` | No corpus attached → 6 nominal refs. Real customer data intake (uploads/connectors) does not exist. |

### BROKEN — bugs that defeat locked design decisions

| # | What | Where | Effect |
|---|---|---|---|
| B1 | **Goal anchor + certifier RAW access read an empty string** | `boundary/intake.py` (spec overwrite) → `certify/stage2.py:35` → `seats/certifier.py:392` | `SanitizedSpec` has no `request` field; intake overwrites `job.spec`; D9/D10 run on `""` in the live path. Raw request survives only in `messages`, never re-read. **One-line fix.** |
| B2 | Conductor amendments don't persist | `conduct/conductor.py:44` | Applied to the in-memory plan dict; DB plan row never updated; stage retry/resume reloads from DB → hash-chained log points at vanished changes. |
| B3 | Scope-lock is substring matching | `conduct/conductor.py:34` | `mid in ref` — `mod_ocr` unlocks `mod_ocr2` regions. |
| B4 | ~20 SSE event types never reach the UI | ~20 raw-string `ctx.emit()` types absent from `events.py` `E` **and** frontend `KNOWN_EVENT_TYPES` | Named SSE events without a registered listener are silently dropped by EventSource (`qa.probe_started`, `certify.consult_requested`, `conductor.goal_drift`, …). Mission control is blind to them. |
| B5 | `system` scope is write-only | config/admin events emit to `system`; no SSE endpoint subscribes | Live visibility zero; replay-only. |
| B6 | Engine infinite-loop hazard | `orchestrator/engine.py:125` | Driver trusts stages to advance status; a stage returning without advancing = hot loop. No same-status guard. |
| B7 | Stage-4 gather double-spend | `fleet/stage4.py:77` | No `return_exceptions`; first coder failure propagates while siblings keep burning tokens; stage retry re-dispatches. |

### INSECURE — trust boundaries

| # | What | Where |
|---|---|---|
| I1 | `allow_raw_on_amd_hosted = True` **by default** — RAW crosses to Fireworks with only a badge | `config.py:67` |
| I2 | Router fail-open: unknown backend → silent mock output | `models/router.py:276` |
| I3 | No-docker → all tests pass; "integration suite" without a generated suite is `py_compile` | `orchestrator/codeexec.py:66,87` |
| I4 | Single env-var auth for demo AND admin tiers; empty = fully open (advertised via `/config/public` `demo:true`); CORS `*` | `main.py:37,62`, `api/deps.py` |
| I5 | HMAC proxy tokens minted only in tests; live staging deploys `expect_token=False`; header name mismatch (`X-Process-Token` vs `x-proxy-token`) | `boundary/proxy_token.py`, `runtime/staging.py` |
| I6 | Egress ledger is honor-system — router records voluntarily; nothing intercepts sockets | `boundary/egress.py` |
| I7 | PII baseline = 6 regexes (US-SSN-shaped GOV_ID only, no names/addresses/DOBs); model layer is the real coverage | `boundary/sanitize.py:16` |
| I8 | Zero Pydantic request models; every write handler `body: dict` + permissive `.get` defaults | all of `api/` |

### MISSING — product surface a paying business needs (see §2 scenario)

| # | What |
|---|---|
| M1 | **Deliverables**: no export of any kind — no CSV, no PDF, no report artifact. Run results are JSON rows in `run_units` + a stats dict with `flagged_refs[:20]`. |
| M2 | **Clarifying intake**: single-shot auto-confirm (`intake.py` advances to planning unconditionally). The platform never asks "what format do you want the output in?", "what threshold?", "which population?" — the `confirm-spec` endpoint exists but nothing routes a *question* to the customer. |
| M3 | **Cross-row analytics**: fan-out is strictly one-row-one-unit (`seeds.load_units` → per-row LLM judgment). Every flagship dataset use case is a JOIN/aggregation (spoofing = order bursts, wash trades = matched pairs, dup claims = pair detection, intercompany = grouped balances). Per-row LLM guessing cannot find pairs **by construction**. No SQL/aggregate step type exists. |
| M4 | **Corpus scale**: `LIMIT 250` (`sandbox_max_units`), first-N not sampled — 0.05% of the exchange orders table, unordered. |
| M5 | **Run data binding**: `start_run` takes `input_ref` (a count string). No way to say "this month's new claims" — no source binding, no watermark/incremental, no schedule. |
| M6 | **Next steps**: nothing anywhere suggests what to do after a build/run (refine, schedule, review, export). |
| M7 | **Review ergonomics**: approve/reject + note exists (`/units/{id}/review`), but no evidence view (the joined rows that made the unit suspicious), no bulk actions, no reviewer identity. |
| M8 | Users/roles/audit: one shared token, no identity on reviews/approvals. |

### FRAGILE

- Stale built-in rate card ($3/$15 vs real $10/$50; YAML wins when readable) — `metering/rates.py`.
- `_noop_complete` makes real RAW-class calls billed to scope `system` — `api/jobs.py:147`.
- Policy voice upload written to `/tmp`, never cleaned — `api/jobs.py:68`.
- Engine `_tasks` dict never evicts done tasks — `engine.py`.
- Test suite runs mock mode → placeholder seats; real prompts exercised only live.

---

## 2. The scenario — Cascadia Mutual runs a claims-leakage program

*Persona: Dana, claims-integrity lead. Data: `insurer.db` (50k policies, 140k claims, 167k payments;
planted: 120 duplicate pairs, 8 staged rings, 200 over-coverage payouts, 6 anomalous adjusters).
Ask: "Every month, flag duplicate claims and coverage breaches; the claims committee gets a PDF case
file per flagged entity and a CSV for the recovery team."*

| Step | What Dana expects | What happens today | Gap |
|---|---|---|---|
| 1. Intake | Platform asks: output format? materiality threshold? population (all open claims or new since last run)? | Single-shot auto-confirm; her one prompt is all the platform will ever know. Policy terms default in (nice — D11 works), but **no clarifying dialogue**, and "PDF per flagged entity" silently becomes nothing because no deliverable concept exists | M2, M1 |
| 2. Quote | Cost + time + "try it on a sample first" | USD quote exists (real). No time estimate, no sample-run option | minor |
| 3. Build (mission control) | See what the fleet is doing mid-task | Stages tick, but ~20 event types (probe starts, consult requests, goal drift…) never render — dead named events; `certify.check_started` fires before the model runs | B4, roast |
| 4. Detection quality | The 120 planted duplicate pairs found | Fan-out sends **one claim row at a time** to a local model. A duplicate *pair* (same policy+date, amounts within 5%) is invisible to any single-row judgment. Same for rings (shop+phone clusters) and coverage breaches (SUM(payments) vs limit). The sweep runs, costs money, finds ~nothing — **wrong compute shape, not wrong model** | **M3** |
| 5. Scale | All 140k claims considered | First 250 rows (`LIMIT 250`) | M4 |
| 6. Results | Ranked findings with evidence (the joined rows), case files | `run_units` JSON blobs; review queue is approve/reject on a ref string with no evidence panel; `flagged_refs` truncated at 20 | M7, M1 |
| 7. Delivery | PDF per flagged entity + CSV to recovery | Nothing. No export endpoint, no artifact, no email/webhook | **M1** |
| 8. Month 2 | "Run on claims filed since last run", scheduled | `start_run` is the **simulated** `drive_run` — synthetic units, `i%7` verdicts, a rehearsed warranty beat. No binding, no watermark, no schedule | **S1, M5** |
| 9. Governance | Who approved which write-off; RAW stays local | Reviews are anonymous; `allow_raw_on_amd_hosted=True` means her claims rows may cross to Fireworks with a badge | M8, I1 |
| 10. What next? | "Tune the 5% threshold; add adjuster review; schedule monthly" | No next-steps surface anywhere | M6 |
| 11. IT config | Bind judgment seats to their EU BYOK endpoint, keys managed per connection | API surface exists (connections + seat_overrides + attestation flag); UI clarity TBD (frontend recon) | E-scope |

**Same story, other datasets:** Northgate's denied-party screening (freight) is the one use case
that IS per-row (consignee vs watchlist) — it works today at ≤250 rows; its pain is delivery
(compliance case files, M1) and schedule (M5). Ashford's spoofing (exchange) is the hardest —
time-windowed burst detection over 550k orders; pure LLM fan-out is off by three orders of magnitude
on both scale and shape (M3+M4).

**The through-line:** the build pipeline is a real product with real bones; the *operate* phase — the
part the customer pays for monthly — is a mock, and the compute model only fits per-row judgment
tasks. The money slide says "frontier is capex, runs are cheap opex"; today the runs are fake and the
one real sweep shape can't express the demos' own headline use cases.

---

## 3. Wave scope — LOCKED 2026-07-10 (demo-first, product-honest)

**Tracks:** (1) real operate + SQL steps, (2) deliverables engine (HTML case files + CSV,
print→PDF), (3) clarifying intake, (4) config/mission-control/next-steps UX, (5) verbose prompt
tracing (per-dispatch prompt/response inspector — internal debugging tool). Plus all seven
correctness blockers (B1–B3, S4, S5, I1, I2) and the B6 no-advance guard.

**Split:** backend agent owns `backend/**` (+ small static additions under `backend/app/sandbox/`),
frontend agent owns `frontend/src/**`. Contract (endpoints, event names, payload shapes) is frozen in
the two agent briefs; additive changes only, no renames. No git commits by agents.

---

## 4. createTool() + per-agent workspace isolation — design (added 2026-07-10, second directive)

### 4.1 The primitive

`create_tool(purpose: str, args_example: dict)` — available to any agent loop. Dispatches to the
**coder seat with `task_flags=["greenfield-codegen"]`** (capability routing already lands this on
Qwen3-Coder-Next / Qwen3.6-27B — no new seat, no new serving, boundary enforced by the router as for
any coder call). The toolsmith returns ONE self-contained Python file:

```python
TOOL = {"name": "...", "description": "...", "args_schema": {...}}   # JSON schema for args
SELF_TEST = {"args": {...}, "expect_keys": ["..."]}                   # smoke contract
def run(args: dict) -> dict: ...                                      # stdlib + sqlite3 only, no network
```

**Trust chain (why the agent can rely on it):** the platform executes `SELF_TEST` in the code-exec
sandbox (docker, `--network none`, agent-folder mount only, 20s timeout) BEFORE registering the tool;
failure gets one repair round (same pattern as the router's schema repair); second failure returns a
structured error to the caller. Only a self-tested tool is handed back. Execution of a registered
tool = same sandbox, args as stdin JSON, result as stdout JSON.

**Persistence & visibility:** `tools` table (scope, agent_dir, name, description, args_schema, code,
self_test_passed, created_by_seat, model) + `GET /api/tools?scope=` + `tool.created` /
`tool.invoked` SSE events. Toolsmith dispatches flow through the router → they appear in the prompt
trace inspector with full code, which makes createTool part of the internal debugging story.

### 4.2 Who gets it

1. **Inspector loop** (`seats/inspector.py` — the one real tool loop): `create_tool` joins
   `read_manifest`/`http_request` in the injected tools dict; on success the runner registers the new
   tool into the SAME dict mid-loop. Prompt gains one instruction: commission a tool when a probe
   needs computation (parsing, aggregation, statistical comparison), then call it.
2. **Topology step kind `"analysis"`** (complements `"sql"`): `{id, kind:"analysis", purpose,
   per_unit:false}` — the runtime commissions the tool once per step (cached in `tools`), then runs it
   over the candidate rows deterministically (`{"rows":[...]}` → `{"findings":[...]}`). SQL finds
   what SQL can; analysis tools cover fuzzy matching, cross-field logic, statistics. The platform
   builds its own instruments; the BoM/trace shows which model built which tool.

### 4.3 Per-agent folders

Today every coder writes into one flat job dir (stage 4 even rewrites all paths to `src/<mid>.py`).
New layout: `data/workspaces/job_<id>/agents/<slug>/` (slug = module id for coders, `toolsmith`,
`inspector-<n>`), tools under `agents/<slug>/tools/`, shared read-only interface specs under
`shared/`. Stage 4 passes each build task its own folder; **codeexec mounts only the calling agent's
folder** (real isolation, not convention); the consolidator is the single cross-folder reader and
merges `agents/*/` into the package. Conductor reviews reference folders 1:1 with build tasks.

### 4.4 Planner/certifier awareness

Planner system prompt: new capability paragraph — workers may commission focused tools; when a
module/step needs computed evidence, emit an `analysis` step (process mode) or flag the module
`tool-assisted` (build mode); declare per-module touch points knowing agents are folder-isolated and
cross-module files must be interfaces, not shared scratch. Certifier `bom-sanity` extends: `analysis`
steps must carry a concrete, testable `purpose`; vague purposes get amended.

**Sequencing:** implemented as backend T8/T9 AFTER the core demo path (T1–T4) is green; partial
delivery acceptable and reported honestly.

---

## 5. Wave result + demo-day notes (closed 2026-07-10)

All tracks delivered and independently verified (backend 105 passed + 2 skipped, frontend build
green, live mock boot: clarify park → answers → quote → 0-7 → registered process → real corpus run →
case-file report + CSV + traces + next-steps; `run.artifacts` on the run object confirmed).

**Demo-day notes:**
- **Restart colima/docker before the demo** if createTool is in the script — tools refuse to
  register without the daemon (by design; the docker round-trip test skips daemon-aware).
- Mock-mode demos: use **process-mode (topology) runs** — the mock placeholder `process.py` has a
  syntax error, so build-mode registered runs degrade to the shim ack.
- Mock clarification trigger is the literal word "clarify" in the request; live mode is model-judged.
- `allow_raw_on_amd_hosted` now defaults **False**; the repo `.env` explicitly opts back in for the
  demo — that flag is the boundary-enforcement moment in the pitch.
- On commit: verify `backend/app/models/` and all new files are tracked (bare `models/` gitignore
  pattern previously swallowed them; .gitignore fix must land in the same commit).
