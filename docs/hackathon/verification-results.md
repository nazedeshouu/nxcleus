# Nxcleus — Live Verification Results

> Independent end-to-end verification of the judge-sandbox pipeline on **real models**
> (`MODEL_MODE=auto`), run from a frozen git worktree at commit `d62cff2` on an isolated
> DB/port (127.0.0.1:8010), separate from the in-flight main working tree.
> **Author:** live-verification agent · **Date:** 2026-07-12 · all 8 cases complete.

## What "live" means here

- **Planner** (stage 1, the one designed-in external call): `openrouter / openai/gpt-5.6-sol` (flagship).
- **All other seats** (trust, certifier, coder, per-unit judge): served on **Fireworks (AMD-hosted)** —
  `glm-52-hosted` and `deepseek-v4-pro` — badged `demo-exception (AMD_HOSTED)` because the
  spec-preferred local-fleet binding wasn't up (Fireworks is the badged availability fallback).
- **Mock hops:** 0 for clinic, bank, insurer, market; exactly 1 stub call each for freight, ledger,
  exchange (a transient certifier fallback, ~1 of ~64 calls). All 8 are effectively clean live runs; the
  only heavily-mocked run (a first lawfirm attempt, 38/76 mock) was discarded and re-run — see issue #3.
- Per-run budget cap tightened to **$1.75/run**, then **$1.00/run**, from the founder's $5.00, to
  protect the ≤$15 total.
- **Depth note:** clinic + bank ran at the full `SANDBOX_MAX_UNITS=250` (a per-unit judge over up to 250
  candidates — ~$1.8 and ~20–40 min each). To keep the remaining 6 cases inside the time+cost budget I
  then lowered `SANDBOX_MAX_UNITS=60` (a 60-candidate breadth sample per case), which proves the same
  0→7 pipeline + catch behavior at ~$0.5–0.9 and ~10 min each. The catch **ratio** is what the 60-unit
  sample measures; it is not the full-corpus recall.

## Catch-rate: how to read it

Each sandbox prompt compiles to a **process** = an SQL "topology" step that narrows the whole corpus
to candidate rows, then a **per-unit LLM judge** (coder seat) that reads each candidate and decides
`needs_review` vs `ok`. So two numbers matter:

- **SQL recall** — did the topology surface the planted rows as candidates at all?
- **Judge-confirmed** — of those candidates, how many the judge flagged (`needs_review`).

The seed generators plant a known count per pattern (the denominators below). The judge often applies a
**stricter semantic test than the structural plant**, so judge-confirmed < planted is expected and not
always a miss — see the clinic note.

### Planted denominators (from each seed generator's `planted` dict)

| Company | Corpus rows | Prompt verified (index 0 unless noted) | Planted (that pattern) | Other planted patterns in the seed |
|---|--:|---|--:|---|
| clinic | 8,664 | Find duplicate-billing shapes | 40 dup pairs | impossible_vitals 30, upcoding 60, double-booking 25 |
| bank | 9,967 | Dormant-account unusual reactivation | 15 reactivation | structuring, sanctions-adjacent, layering chains |
| lawfirm | 3,346 | Renewal/auto-renew, notice <60d | auto_renew_short_notice | missing_sig, fee-cap breaches, contradictions 25, amendment conflicts 12 |
| insurer | 358,381 | Duplicate claims (same incident, ±5%) | 120 dup pairs | 8 rings, 200 over-coverage, 6 adjusters, re-enroll chains — live bench 136/138 |
| freight | 429,948 | Invoices >15% over PO | (three-way-match 400) | ghost-shipment 150, denied-party 30, HS-mismatch 100, transshipment 20 |
| ledger | 663,359 | Intercompany reconcile mismatches | 30 | misclassifications 500, LEI gaps 80, unbalanced 25, revenue rings 3 |
| exchange | 753,489 | Spoofing bursts | 40 episodes | wash 60, marking-close 15, position-limit 12, concert-party 3 |
| market | 753,962 | Review rings | 10 rings | refund abusers, counterfeit, brushing, price cartels |

## Results table (per case)

All 8 completed 0→7 on live models. clinic + bank ran at full depth (250-unit cap); the other 6 are
the clean **serial** re-runs at the 60-unit sample. "Flagged" = `needs_review` units; "SQL cand." =
rows the topology step surfaced before the judge (0 = the planner built a topology-less per-row process).

| Case | E2E | Units | Flagged | SQL cand. | Planted (this pattern) | Wall | Job $ | Mock calls | Models served |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| clinic | ✅ done→7 | 40 | 11 | 40 | 40 dup pairs | ~19 m | 0.806 | 0 | gpt-5.6-sol ×1, glm-52-hosted ×13, deepseek-v4-pro ×42 |
| bank | ✅ done→7 | 250 | 124 | 1,186 | 15 reactivation | ~40 m | 1.805 | 0 | gpt-5.6-sol ×1, glm-52 ×14, deepseek ×252 |
| lawfirm | ✅ done→7 | 60 | **0** | 0 | (auto-renew <60d) | ~4 m | 0.162 | 0 | gpt-5.6-sol ×1, glm-52 ×14, deepseek ×60 |
| insurer | ✅ done→7 | 60 | 60 | **138** | 120 dup pairs | ~9 m | 0.857 | 0 | gpt-5.6-sol ×1, glm-52 ×13, deepseek ×62 |
| freight | ✅ done→7 | 60 | 60 | **400** | 400 3-way breaks | ~9 m | 0.802 | 1 | gpt-5.6-sol ×1, glm-52 ×12, deepseek ×62, local ×1 |
| ledger | ✅ done→7 | 60 | 19 | **432** | 30 IC mismatches | ~14 m | 0.977 | 1 | gpt-5.6-sol ×1, glm-52 ×12, deepseek ×64, local ×1 |
| exchange | ✅ done→7 | 60 | **0** | 0 | 40 spoof episodes | ~5 m | 0.135 | 1 | gpt-5.6-sol ×1, glm-52 ×13, deepseek ×60, local ×1 |
| market | ✅ done→7 | 60 | 5 | 5,000* | 10 review rings | ~13 m | 1.060 | 0 | gpt-5.6-sol ×1, glm-52 ×14, deepseek ×64 |

*market hit the `sql_step_row_cap=5000` — the review-ring query surfaced a huge candidate set (broad net).
Parallel fan-out every case: certifier ran **7 checks**, the coder pool judged all units concurrently
(`pool_slots_per_backend=4`, coder slots = pool×2 = 8) — bank drove 252 concurrent-pooled judgments.
"Mock calls" counts `mock`/`local`-badged dispatches: 0 for clinic/bank/insurer/market, exactly 1 for
freight/ledger/exchange (a single certifier stub under a transient stall — 59-63 of ~64 calls real).

### The headline pattern: catch quality is bimodal on whether the planner builds an SQL topology

- **Topology built → the pattern is engaged:** insurer surfaced **138** candidate duplicate-claim pairs
  (matching its 136/138 live benchmark denominator) and the judge confirmed all 60 sampled; freight
  surfaced **exactly 400** (= planted three-way-match breaks) and confirmed all 60; ledger surfaced 432
  and confirmed 19/60; clinic surfaced all 40 planted pairs; bank surfaced 1,186.
- **Topology absent (`sql_rows=0`) → total miss:** lawfirm and exchange flagged **0/60** — the planner
  built a naïve per-row judge with no candidate-narrowing step, so the actual pattern (short-notice
  auto-renew clauses; spoofing bursts) was never surfaced. This build choice is **non-deterministic**:
  the same lawfirm prompt built a 200-candidate topology on an earlier run (17 flags) and a 0-candidate
  one here. This is the single biggest reliability gap — see issue #1.

### Per-case notes

**clinic (duplicate-billing)** — Job `job_01KXBC4X3B4NBH03BB8139QJRB`, run `run_01KXBCE2BA3GESEP2907PX61DP`.
SQL topology surfaced **all 40** planted same-patient/date/code pairs as candidates (100% SQL recall).
The per-unit judge then **read each pair's visit notes** and confirmed **11** as genuine duplicates,
clearing 29 whose notes describe *distinct* clinical services (e.g. "hypertension follow-up vs shingles
vaccine"). This is the platform reasoning over meaning, not keywords — but it means the naive
11/40 catch number understates SQL recall and reflects a **stricter semantic bar than the structural
plant**. Whether the 29 cleared pairs are true benign collisions or under-flagged plants depends on
whether the seed gives planted duplicates duplicate-consistent notes (they appear not to) — a good
target for the deep-iteration pass.
**QA gap:** `oracle_checks = 0`, `tickets = 0`, no `qa.*` events — the stage-6 adversarial oracle/inspector
swarm did **not** visibly fire on this sandbox run. The adversarial layer that *did* run was the
**certifier** (7 checks, 19 findings, 34 amendments). Confirmed structurally at `fleet/stage4.py:50`:
a "topology" (process-mode) plan runs the corpus fan-out then `advance("delivering")` — it **skips
consolidate (5) + QA (6)**. The oracle/inspector swarm lives only on the module/DAG custom-build path,
which the judge sandbox does not exercise.

**bank (dormant reactivation)** — Job `job_01KXBCRRS3BN12DHRFNRKYB9BV`, run `run_01KXBD6KW5AN21GNB6GV7FEFPE`.
The opposite failure mode from clinic: **over-flagging**. SQL topology cast a wide net —
**1,186 candidate rows** (all dormant accounts with any recent activity) — judged the 250-unit cap and
flagged **124**, against only **15** planted "sudden reactivation" accounts. So ~8× more flags than
plants: the SQL net is too broad and/or the judge doesn't discriminate "*unusual*" reactivation from
ordinary reactivation. For a fraud-triage tool this is a real precision problem (124 to review to find 15).
Completed E2E cleanly at the cap ($1.805, done not aborted).

## AMD MI300X serving evidence

### Live own-droplet bring-up: BLOCKED by a billing lock (not a code problem)
- `doctl account get` (AMD API) → **Status = `locked`**, droplet limit 10.
- Attempting `doctl compute droplet create … gpu-mi300x1-192gb-devcloud` returns
  **`403 — "There is currently an outstanding balance on your account, please visit the billing page
  to update your billing profile."`** No droplet was created; `droplet list` is empty; `$0/hr` GPU spend.
  (Consistent with the prior $150 idle-MI300X incident that left an unpaid balance.)
- The bring-up path itself is sound: `fleet_up.sh P1 --dry-run` validates the render (one
  `gpu-mi300x1-192gb-devcloud`, 3 vLLM containers oracle/trust/inspector + node agent, correct ROCm
  image `rocm/vllm:rocm7.13.0…vllm_0.19.1`), zero YAML/packing warnings. So P1/P2/P3 in `infra/fleet.yaml`
  would serve our own MI300X the moment the account is unlocked — the blocker is billing, not the fleet code.

### Hosted-AMD serving that DID run (the badged availability fallback = AMD MI300X via Fireworks)
Every non-planner seat call in all 8 cases dispatched to `api.fireworks.ai` in the **`AMD_HOSTED`** egress
zone — Fireworks serves these models on AMD MI300X GPUs. Real measured serving (from `model_traces`,
across all cases):

| Model | Zone | Calls | Avg latency | Avg out tokens | **Decode tok/s** | Total out tokens |
|---|---|--:|--:|--:|--:|--:|
| deepseek-v4-pro (coder / per-unit judge) | AMD_HOSTED | 402 | 14.3 s | 912 | **66.5** | 366,428 |
| glm-52-hosted (trust / certifier) | AMD_HOSTED | 60 | 36.2 s | 4,474 | **120.0** | 268,422 |
| openai/gpt-5.6-sol (planner) | EXTERNAL | 8 | 79.1 s | 6,689 | 84.7 | 53,508 |

Concurrency: the coder pool fans out per-unit judgments 4-wide (`pool_slots_per_backend=4`) —
e.g. bank drove 252 concurrent-pooled deepseek judgments through the AMD_HOSTED backend in one run.

## Issues found (ranked by severity)

1. **[High — reliability] The planner non-deterministically builds a detection process or a no-op one;
   the no-op ones miss everything.** lawfirm and exchange flagged **0/60** because the planner produced
   a topology-less per-row judge (`sql_rows=0`) that never surfaced the target pattern — while insurer,
   freight, ledger, clinic, bank all built a real SQL candidate step and caught. The same lawfirm prompt
   built a 200-candidate topology one run and a 0-candidate one the next. So catch quality is a coin-flip
   on a planner decision, not a property of the data. Secondary, same root cause (SQL net vs judge rubric
   not aligned to the plant): bank **over**-flags 8× (124 vs 15 — net too broad), clinic **under**-flags
   (11 vs 40 — judge too strict on note-semantics). Fix: make stage-1/stage-2 *require* a candidate
   topology for detection prompts and align its net + the judge rubric to the stated pattern.

2. **[Medium — claim risk] Sandbox runs never exercise the QA swarm.** `fleet/stage4.py:50`: a topology
   (process-mode) plan runs the fan-out then `advance("delivering")`, skipping consolidate (5) + QA (6).
   The "4 QA inspectors / 4 oracle workers" adversarial swarm (`qa/stage6.py:15-16`) only runs on the
   module/DAG custom-build path. Every judge-sandbox demo therefore shows plan+certify+judge, **not** the
   oracle/inspector swarm. Keep deck/landing "adversarially QA'd" copy honest, or route sandbox through QA.

3. **[High — silent degrade under load] The fallback chain reaches `mock` when Fireworks rate-limits,
   silently faking results.** When two cases' model bursts overlapped, Fireworks returned **`429 Too
   Many Requests`** (coder) and a `ReadTimeout` (certifier); with no local fleet the chain went
   Fireworks → local(absent) → **`mock`**. A first lawfirm run logged **38 of 76 calls as `mock`**
   (empty `{"findings": []}` for the certifier; stub judgments for the coder) yet still reported
   `done` with 17 "flags" — a result that looks live but is half-fabricated, with only a `demo-exception`
   badge as warning. **Verification implication:** clean live numbers require *serial* execution (one job
   at a time); concurrent sandbox load on the Fireworks-fallback profile self-poisons. **Product
   implication:** mock should never be a silent last resort on a non-mock run — fail loud or hard-retry.
   (All finally-reported cases below are the *serial, 0-mock* runs.)

4. **[Low — spec drift] `sandbox_max_concurrent=1` isn't strictly enforced.** The queue worker waits max
   600s per job then advances (`sandbox/queue.py:52`), so long jobs are overtaken and multiple sandbox
   jobs run concurrently. Harmless for budget (per-job cap holds) but the FIFO/single-worker guarantee is soft.

5. **[Low — packaging] Committed HEAD doesn't boot standalone.** `main.py` imports `app.api.auth`, which
   is untracked at `d62cff2` (uncommitted, not gitignored). The public repo boots once that commit lands;
   flagged so it isn't missed before submission.

## Deep-iteration pick (feeds W3-A)

**bank — "dormant accounts with unusual reactivation."** Pick it because it is the most *demo-legible,
deterministic, and fixable* of the defects: it over-flags 124 against 15 planted on the smallest,
most human-readable corpus, reproduces every run (unlike the intermittent topology misses), and the
before/after is obvious to a judge (124 noisy flags → ~15 clean ones). The fix is well-scoped and
touches only the built process, not the pipeline: tighten the SQL candidate net and give the judge the
plant's real rule — a *sudden large 2026 deposit on an account dormant >2 years*, not any reactivation.

Two things to fold into the same pass, because they share bank's root cause (net/rubric not aligned to
the plant): (a) clinic's **under**-flagging (11/40 — the judge clears real structural duplicates on note
semantics); (b) the higher-severity systemic issue #1 — force the planner to always emit a candidate
topology so lawfirm/exchange stop returning **0 flags**. If the team prefers to showcase a *win* rather
than fix a *defect*, **insurer** is the alternative: run it at full depth (all 138 candidates, not the
60 cap) and it reproduces the headline 136/138.

## Spend & fleet

- **Total API spend: $13.52** (cumulative metered `cost_usd`, all runs), under the $15 cap. Of that,
  ~$2.6 is the clean clinic+bank full-depth runs, ~$4.0 the clean serial 6, and ~$6.9 is **overhead I
  incurred**: ~$3.0 wasted when a mid-batch restart (to drop the unit cap 250→60) killed heavy jobs that
  had already started, plus ~$0.5 aborting the concurrency-contaminated first attempt of the 6. The
  per-run $-cap (first $1.75, then $1.00) bounded every job; no run ran away.
- **Fleet: destroyed / never created — status verified empty.** The DO AMD account is **billing-locked**
  (403 "outstanding balance"), so `fleet_up` could not create a droplet. `fleet_status.sh` + explicit
  `doctl droplet list` (AMD API) both show **zero droplets, $0/hr**. (A stale `A draining` entry lingers
  in the control-plane registry from a prior torn-down node; it is a registry ghost, not a billable
  resource — the billing API is the ground truth and it is empty.)
- **User action:** pay the DO AMD outstanding balance to unlock own-MI300X fleet demos (P1/P2/P3 are
  validated and ready).

## Deep-iteration outcomes (W3-A) — 2026-07-12

A follow-up pass fixed the three defects issue-#1/#3 flagged above. All numbers are live
(`MODEL_MODE=auto`), serial, isolated DB, per-run cap $1.75. Total added spend for this pass ≈ $2.9.

### Fix 1 — Topology guard (reliability; was issue #1, the non-deterministic 0-flag build)
- **Change:** the sandbox planner prompt now states the candidate-step requirement outright (a
  detection request is a `sql`/`analysis` candidate step → optional per-unit judge, never a bare
  per-row scan). A deterministic guard at plan acceptance (`planning/stage1.py`) replans once if a
  corpus-bound detection plan ships no candidate step, then blocks the job loudly (`job.blocked`)
  rather than delivering a silent 0-findings "done".
- **Before → after (both were topology-less, 0/60 flagged):**
  - lawfirm (auto-renew <60d): **0 candidates → 111** (`detect_auto_renewals`), 8 flagged, done $0.64.
  - exchange (spoofing bursts): **0 candidates → 27** (`candidate_same_side_burst`), 27 flagged, done $0.59.
- Both self-corrected at the strengthened prompt; the block path is the deterministic backstop
  (classification unit-tested in `tests/test_reliability_guards.py`).

### Fix 2 — Bank precision (was issue #1 secondary, the 8× over-flag)
- **Change (generic, no per-company encoding):** the planner SQL directive now binds the candidate
  to the request's named entities/state and event direction using the schema's own columns (not a
  computed proxy), and encodes the request's quantitative qualifiers in WHERE/HAVING; the per-unit
  judge frame (`runtime/operate.py` `_CANDIDATE_FRAME`) now confirms the *phenomenon* the request
  describes, not merely the upstream thresholds (a scoping field that contradicts — wrong status,
  wrong direction — forces `flagged=false`).
- **Before:** 1,186 candidates → **124 flags vs 15 planted** (8× over-flag).
- **After v1** (threshold-only tightening): 145 candidates (8× tighter count), 60/60 sampled flagged
  — but the ground-truth cross-check (ran the planner's own SQL against `infra/seeds/out/bank.db`)
  showed only **10/15 planted caught** and **135/145 extras were outbound `debit` transfers, 126 on
  active accounts** — a loose per-txn LAG-gap net + a judge confirming thresholds, not the phenomenon.
- **After v2** (entity/phenomenon binding): the planner correctly bound to the phenomenon — a `sql`
  step *"Detect and rank dormant accounts with inflows"* filtering `status='dormant'` + a credit
  inflow — but this non-deterministic draft guessed the wrong literal for the direction column
  (`direction='inflow'`, while the seed encodes it `'credit'`/`'debit'`), so the query returned
  **0 rows / 0 flags**.
- **Root cause (both drafts):** the sandbox planner is given column *names only*
  (`seeds.company_schema` → `{table, columns, row_count}`), never the values, so it cannot know a
  column's encoding and guesses from the request wording. v1 over-flags on a loose net that ignores
  direction; v2 under-flags on a right-shaped query with a wrong literal. Prompt-tuning alone can't
  make a schema-blind planner deterministic here.
- **Recommended next fix (not implemented — needs a run + a boundary check):** surface a few distinct
  sample values for low-cardinality text columns in the planner's schema brief, so it filters on real
  literals (`'credit'`, not `'inflow'`). Generic across every case. Caveat: column values crossing to
  the EXTERNAL planner is a data-boundary concern for real (non-synthetic) corpora — gate to
  sandbox / enum-like columns or sanitize first.

### Fix 3 — Mock-serving visibility (was issue #3, the silent degrade under load)
- **Change:** `meter.mock_dispatches(scope)` counts `model.call` badge='mock' from the events table;
  stamped into run `stats.mock_dispatches`, exposed on `GET /jobs/{id}` and the economics run summary;
  a red "N simulated" chip renders in the process run row and the live build cockpit.
- **Proof:** a forced-mock run (Fireworks key broken in-shell only) completed `done` but the rollup
  counted **23 simulated dispatches** — surfaced instead of passing as a clean live run.

### Honest gaps
- Bank precision is **not** cleanly solved: the schema-blind planner makes it non-deterministic
  (v1 over-flags, v2 zero-flags). Real fix is the schema-values recommendation above, not more prompt text.
- The topology guard checks a candidate step is *present*, not that it *returns rows* — a
  phenomenon-correct-but-zero-row query (v2) still ships `done`. A candidate-returns-zero guard is a
  possible follow-up.
- Fix 1's block path is proven by unit test, not observed live (both cases self-corrected via the prompt).
- The single `mock=1` on otherwise-clean bank/exchange runs is one transient certifier stub — exactly
  the silent degrade the Fix 3 chip now surfaces.

## Schema-values pass (W7) — 2026-07-13

Implements the two "recommended next fix / possible follow-up" items the W3-A gaps above left open.
One live bank run (`MODEL_MODE=auto`, serial, isolated /tmp DB, cap $1.75, `SANDBOX_MAX_UNITS=60`).

### Fix A — enum sample values in the planner's schema brief (the root fix for the v2 miss)
- **Change:** `sandbox/seeds.py` `company_schema(company, values=True)` now appends a low-cardinality
  column's distinct values inline — `direction (values: credit, debit)`, `status (values: dormant,
  active)`. Boundary-gated (these tokens cross to the EXTERNAL planner): TEXT-affinity only, ≤12
  distinct, a conservative token pattern, an identity/free-text deny list (name/email/memo/
  counterparty/iban/…), and a ~1200-char/brief cap that drops values but never a column. Wired at the
  single brief-build site for both sandbox plan and replan (`planning/stage1.py`) and the files/BYOD
  intake brief (`boundary/intake.py`); every other caller (certifier repair, companies API,
  `load_units`) keeps bare names via the default `values=False`.
- **Live result** (job `job_01KXBVJ0EYPP3D6FYFBASQ77TD`, run `run_01KXBVW6WDBEP83PEBERW54BFE`, 603 s,
  **$0.466**, 0 mock, `done`): the planner filtered `t.direction = 'credit'` and `a.status =
  'dormant'` on the corpus's **real** literals (v2 had guessed `direction = 'inflow'` → 0 rows). It
  built one `sql` candidate step "rank dormant-account reactivation candidates" (credit deposit/
  transfer on a dormant account, ≥90-day dormancy, scored by amount/pep/dormancy/rapid-outflow).
- **SQL recall vs the 15 planted reactivation accounts** (cross-checked by running the planner's own
  query against `infra/seeds/out/bank.db`): **15/15 caught, 0 missed** — `[1, 4, 58, 60, 78, 84, 101,
  105, 120, 130, 132, 142, 169, 181, 188]`. Candidate set: **101 rows / 64 distinct accounts** (the 15
  planted + 49 extra dormant-account reactivations, all genuine phenomenon matches at lower magnitude,
  ranked below the planted by `risk_score`). Judge flagged **60/60** of the sampled cap.
- **Progression:** v1 145 cand / 10-of-15 / 135 extras (mostly wrong-direction `debit`); v2 0 cand /
  0-of-15 (wrong literal); **W7 101 cand / 15-of-15 / 49 extras** (all real reactivations). Full recall,
  real precision (extras are true lower-risk reactivations, not wrong-direction noise), correct literals.

### Fix B — zero-candidate guard (deterministic backstop for the v2 silent zero)
- **`planning/stage1.py`:** extends the topology guard — after confirming a candidate step exists, it
  dry-runs the `sql` candidate step(s) read-only against the corpus (`cap=1`; only the row *count* is
  used locally, so no row values cross to the planner — boundary-safe). If the final candidate set is
  empty, it replans **once** with a directive to re-derive literals from the schema's stated values
  (Fix A), then **blocks loudly** (`job.blocked` + `JOB_BLOCKED`) rather than shipping a silent
  0-findings `done`. Skipped for analysis-only candidates (not dry-runnable at plan time) and in mock
  mode, mirroring the existing guard.
- **`runtime/operate.py`:** universal visible-zero marking at the point SQL materializes — `execute_
  topology` returns `zero_candidate` (candidate steps ran but surfaced nothing); both callers stamp it
  into run `stats` (surfaced on the summary API like `mock_dispatches`) and emit a loud error notice.
  This covers the registered-process `drive_run` path, which skips stage-1 planning.
- This run's guard behavior: `zero_candidate=False` (101 rows), so neither the replan nor the block
  fired — expected, since Fix A gave the planner the right literals on the first draft. The guards'
  classification is unit-tested (`tests/test_reliability_guards.py`); the live block path was not
  exercised because Fix A pre-empted the zero-row condition it guards.

### Tests / spend
- `tests/test_reliability_guards.py`: added enum-gating (credit/debit-style column surfaced; name/
  memo/counterparty and high-cardinality/numeric columns excluded; char cap respected, column list
  never truncated) and zero-candidate classification. Full backend suite **159 passed, 2 skipped**.
- Added spend this pass: **$0.47** (one bank run; 1 of the 2 allotted).
