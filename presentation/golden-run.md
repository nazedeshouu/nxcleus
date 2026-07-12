# Golden run — verified live E2E

There are **two takes**. Pick per what the shot needs — neither is both-good, and both allowed live
runs are spent.

| | **V1 (recommended for the RUN)** | **V2 (full-architecture ledger only)** |
|---|---|---|
| Flagged | **138 / 138** ✅ | 39 / 138 ❌ (undershoots the "138 planted" story) |
| Egress ledger | AMD_HOSTED only — **no LOCAL rows** | **trust → LOCAL / `fleet.local` (MI300X)** ✅ |
| External calls | exactly 1 (planner) | exactly 1 (planner) |
| mock dispatches | 0 | 0 |
| Wall-clock | 5 m 13 s | 13 m 12 s |
| Cost | $0.41 | $1.41 |

**Recommendation:** film the RUN against **V1** (the 138/138 headline). If you want the "even the
boundary-touching seats run on our own MI300X" beat, cut to **V2's** traces/egress ledger for ~5 s and
do **not** show its flagged count. V1 has the numbers; V2 has the LOCAL proof.

---

# V1 — recommended take (numbers)

**Verdict: CAMERA-READY.** One clean end-to-end live run in `MODEL_MODE=auto`. The stage-1
planner was served by the flagship (OpenRouter `openai/gpt-5.6-sol`) as the *primary* path — not a
fallback — exactly one external call left the boundary, and the pipeline flagged **138 / 138** planted
duplicate-claim patterns with **zero** simulated/mock dispatches.

Captured 2026-07-12 (job `created_at` 19:23:49Z). Corpus: `insurer` (Cascadia Mutual), seeded from
`infra/seeds/out/insurer.db`.

## IDs (feed the video-script placeholders)

| Placeholder | Value |
|---|---|
| `{{GOLDEN_JOB_ID}}` | `job_01KXBWJB2Q4W05GYQP8Y94V4TV` |
| `{{GOLDEN_PRC_ID}}` | `prc_01KXBWVWH90X32B01BKS2BZPQV` (slug `sandbox-insurer-3`) |
| `{{FLAGGED_COUNT}}` | `138` |
| run id (deliverables) | `run_01KXBWSZCC0XJP5ZP09431WSZR` |

Prompt used (insurer suggested prompt #1):
> Flag duplicate claims filed against the same policy for one incident — same incident date,
> amounts within 5%, different claim IDs

## The numbers (step-3 verification)

**(a) Planner served-by — flagship primary, NOT a fallback.**
`seat=planner` → `backend=openrouter`, `model=openai/gpt-5.6-sol`, `zone=EXTERNAL`, `badge=null`
(null badge = flagship primary path; a fallback hop would badge `fallback-serving`). tokens 2785 in /
3884 out, cost **$0.130445**, latency **42.8 s**. Host on the egress ledger: `openrouter.ai`.

**(b) Exactly one EXTERNAL call.** Egress ledger for `scope=job:…`: 14 rows → `EXTERNAL: 1`,
`AMD_HOSTED: 13`. Only the planner crossed the boundary; every other seat stayed on AMD silicon.

**(c) Flagged findings: 138 / 138 planted.** Candidate SQL step (`duplicate-claim-candidate-sql`)
returned 138 rows; the local judge confirmed **all 138** → `needs_review=138, ok=0, error=0,
partial=false, zero_candidate=false`. (Prior best was 136/138; this run is a clean sweep.)

**(d) Deliverables both 200.**
- `report.html` → **200**, 180,760 bytes
- `export.csv` → **200**, 40,056 bytes, **138 data rows** (one per flagged pair, `flagged=1`)

**(e) Mock / simulated dispatch count: 0.** `stats.mock_dispatches = 0` — no red "N simulated" chips.
16 model calls total: 1 × OpenRouter/EXTERNAL (planner) + 15 × Fireworks/AMD_HOSTED.

**(f) Wall-clock per stage (from `job.created`, SSE timestamps):**

| Stage | Seat(s) | Duration |
|---|---|---|
| 0 Intake / boundary | trust | 55 s |
| 1 Planning (EXTERNAL) | planner | 43 s |
| 2 Plan completion + certification | certifier (10 calls) | 152 s |
| 3 Quote | — | ~0 s (deterministic) |
| 4′ Process fan-out (run over 138 candidates) | coder judge (2 batched calls) | 46 s |
| 7 Delivery / process registration | trust | 17 s |
| **Total** | | **313 s (~5 min 13 s)** |

**(g) Metered cost: $0.405643 total** (well under the $5.00 per-run cap).

| Seat | Calls | Zone | Cost |
|---|---|---|---|
| planner | 1 | EXTERNAL (OpenRouter) | $0.130445 |
| certifier | 10 | AMD_HOSTED (Fireworks) | $0.205959 |
| trust | 3 | AMD_HOSTED (Fireworks) | $0.049057 |
| coder (fan-out judge) | 2 | AMD_HOSTED (Fireworks) | $0.020182 |
| **Total** | **16** | | **$0.405643** |

Fireworks-billed portion ≈ **$0.275** (certifier + trust + coder); the $0.130 planner call is OpenRouter,
not Fireworks. Fan-out cost per unit: $0.000146.

## Demo surfaces — exact URLs for THIS run

Frontend (Vite) proxies `/api` → backend, so both `:5173` and `:8000` work for the API calls.

| Surface | URL |
|---|---|
| Build cockpit (the run) | http://localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV |
| Run map (fan-out grid) | http://localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV/map |
| Traces — planner seat (shows the one external call) | http://localhost:5173/traces?scope=job:job_01KXBWJB2Q4W05GYQP8Y94V4TV&seat=planner |
| Traces — all seats | http://localhost:5173/traces?scope=job:job_01KXBWJB2Q4W05GYQP8Y94V4TV |
| Egress ledger (host/zone/seat/bytes) | http://localhost:8000/api/egress?scope=job:job_01KXBWJB2Q4W05GYQP8Y94V4TV |
| Operations — registered process | http://localhost:5173/operations/prc_01KXBWVWH90X32B01BKS2BZPQV |
| Report (HTML) | http://localhost:8000/api/runs/run_01KXBWSZCC0XJP5ZP09431WSZR/report |
| Findings export (CSV) | http://localhost:8000/api/runs/run_01KXBWSZCC0XJP5ZP09431WSZR/export.csv |

## Servers — LEFT RUNNING

- **Backend** — port **8000**, `MODEL_MODE=auto`. Started from `backend/`:
  `MODEL_MODE=auto .venv/bin/uvicorn app.main:app --port 8000`
  (I restarted it in `auto`; it had been running in `mock`.) Log:
  `…/scratchpad/backend-auto.log`. Keys come from repo-root `.env` (loaded by `app/config.py`).
- **Frontend** — port **5173**, Vite dev server (`npm run dev` in `frontend/`). Was already running;
  I did not restart it. Proxies `/api` to `:8000`.

Health check: `curl http://localhost:8000/api/health` → `{"status":"ok","model_mode":"auto","corpus":"ok"}`.

## Caveats (say these if asked; none block the demo)

- **AMD_HOSTED, not the self-hosted MI300X.** All 15 non-planner calls served on **Fireworks
  (AMD-hosted, AMD silicon)**, badged `demo-exception` (raw synthetic data allowed on AMD_HOSTED for
  the demo; `ALLOW_RAW_ON_AMD_HOSTED=true`). The self-hosted MI300X fleet is not attached to this local
  backend, so zero calls hit it. The boundary invariant still holds: raw never went EXTERNAL, and the
  one external call carried only the sanitized brief. If you want the "even the fallback is AMD" line,
  that's accurate; don't claim the MI300X served this run.
- **Unit count 250 → 138.** The cockpit briefly shows `units: 250` at `run.started` (raw claims sample
  loaded) then settles to `138` — that's the candidate SQL narrowing the sample to 138 duplicate-pair
  candidates, all of which were judged and flagged. Expected, not a bug.
- **One live run used, one in reserve.** Budget: this run cost ~$0.28 against the Fireworks balance +
  $0.13 OpenRouter. A second live run is still available if a retake is needed.
- Fresh sandbox session (no cookie jar via curl) — did **not** consume the founders' in-browser 3/hr
  quota.

---

# V2 — full-architecture take (LOCAL / MI300X proof, weak numbers)

Second and final live run, after the MI300X fleet node (`A`, ready) was registered in the LOCAL
backend. Captured 2026-07-12 (job `created_at` ~20:22Z). Same insurer prompt, fresh session.

- **Job:** `job_01KXBZR3HPSQAV0K671XE9SBX4` · **Run:** `run_01KXC039YJ8HHYT5ZN5R03KY0G`
- **Registered process:** (delivery ran; not needed for the demo — use V1's `prc_…` for operations)

## What V2 proves — the full architecture is real

**Egress ledger now shows a LOCAL zone served by the self-hosted MI300X**, not just AMD_HOSTED
fallback. Rows by `(seat, zone, host)` for `scope=job:…`:

| seat | zone | host | calls |
|---|---|---|---|
| **trust** | **LOCAL** | **`fleet.local`** (MI300X) | **3** |
| planner | EXTERNAL | `openrouter.ai` | 1 |
| certifier | AMD_HOSTED | `api.fireworks.ai` | 11 |
| coder (judge) | AMD_HOSTED | `api.fireworks.ai` | 140 |

So: 1 EXTERNAL (planner, sanitized brief), 3 LOCAL (trust, on the MI300X), 151 AMD_HOSTED (Fireworks,
badged `demo-exception`). `mock_dispatches = 0`. This is the "raw-touching seat runs on hardware we
control" shot. **Ledger view:** http://localhost:5173/traces?scope=job:job_01KXBZR3HPSQAV0K671XE9SBX4
(filter `trust` to show the LOCAL rows).

## Why V2 is NOT the take for the run numbers

- **Flagged 39 / 138** (`needs_review=39, ok=99, error=0`) — v1 flagged all 138. Not a crash: this
  run's planner (gpt-5.6-sol is non-deterministic) emitted a different judge step,
  `judge-shared-loss-event`, that **reads the FNOL narratives** and dismisses structural matches whose
  stories describe separate incidents (e.g. "sideswipe on driver side" vs "falling limb through the
  roof"). Arguably higher-precision, but "we planted 138 and caught 39" reads on camera as missing
  duplicates. Do not show this count.
- The flagged count is **planner-topology-dependent** (138 in v1, 39 in v2) — a real non-determinism
  caveat, not a stable number.
- **Cost $1.408843**, **wall-clock 789 s (13 m 12 s)** — 3.4× the cost and 2.5× the time of v1, because
  the judge ran 140 per-unit coder calls (`deepseek-v4-pro` on Fireworks) instead of v1's 2 batched
  calls. Still under the $5 cap.
- Deliverables fine: `report.html` 200 (35,220 bytes), `export.csv` 200 (39 data rows).

## V2 stage timeline (from `job.created`)

| Stage | Duration |
|---|---|
| 0 Intake | 25 s |
| 1 Planning (EXTERNAL) | 68 s |
| 2 Certification | 274 s |
| 3 Quote | ~0 s |
| 4′ Fan-out (140 per-unit judge calls) | 411 s |
| 7 Delivery | 11 s |
| **Total** | **789 s (13 m 12 s)** |
