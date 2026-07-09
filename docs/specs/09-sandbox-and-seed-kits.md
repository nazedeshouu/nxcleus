# 09 — Judge Sandbox, Seed Kits & Demo Backend Requirements

Locked 2026-07-07. Upstream: design v2 §7. Siblings: 03 §8 (process mode = what sandbox runs), 07 §6 (queue), 10 (budget caps). Track rule anchor: **no hardcoded/canned answers** — every seed kit is *input* data; outputs are always computed live.

## 1. Judge sandbox = process mode, productized

The deployed site offers three synthetic companies with browsable data. A judge picks one, picks a suggested prompt or writes their own, and watches a **real** process-mode job run: trust → planner (topology + BoM) → certifier → fan-out → live dashboard → saved as a re-runnable workflow in the registry. Demo 4 and judge-run mode are the same work item (design §7.3).

## 2. The three companies (generators in `infra/seeds/`, fixed RNG seed, regenerate-able)

| Company | Tables (rows ~) | Planted patterns (so good prompts find real things) |
|---|---|---|
| **Meridian Bank** | customers (800), accounts (1,200), transactions (8,000) | dormant accounts with sudden reactivation; structuring-shaped deposit runs; a few sanctions-list-adjacent names |
| **Aurora Clinic** | patients (500), encounters (2,500), lab_results (4,000), prescriptions (1,500) | duplicate-billing shapes; impossible vitals (data-quality finds); overdue-screening cohorts |
| **Hale & Ostrom (law firm)** | contracts (200: metadata + full synthetic text 1–3 pages), parties (350), billing_entries (2,000) | auto-renew clauses with <60-day notice windows; missing signature blocks; fee-cap breaches |

Storage: one read-only SQLite per company + `contracts/*.txt` corpus (05 §5). Volumes tuned so fan-out is *visible* (a 200-unit contract sweep across 8 worker slots animates well) yet seedable in a day (O8).

**Suggested prompts** (config per company, 4–6 each) — e.g. bank: "Flag dormant accounts with unusual reactivation patterns and rank by risk"; law firm: "Extract renewal dates and auto-renew clauses across all contracts; flag notice windows under 60 days." Freeform prompts accepted; the sandbox planner's system prompt scopes topologies to the selected company's schema (injected) and refuses out-of-scope requests politely (`system.notice`).

## 3. Sandbox request flow

`POST /api/sandbox/runs {company, prompt}` → session cookie check → guards (§4) → FIFO queue (07 §6) → normal job with `origin=sandbox`: auto-confirmed spec (single-shot intake — no dialogue), auto-approved capped quote, process mode forced. The judge's screen is the standard Build view streaming their own job — the whole point.

## 4. Guards (design §10 risk: "sandbox fails live")

| Guard | Value (env, 01 §6) |
|---|---|
| Concurrency | 1 sandbox job at a time; live queue position |
| Per-run budget | ≤ `SANDBOX_RUN_BUDGET_USD` (0.50) — router hard stop, run aborts gracefully with partial dashboard |
| Per-run scope | ≤250 units, ≤10 min wall clock |
| Per-session | 3 runs/hour, cookie + IP-hash |
| Fleet state | prefer warm local seats; fall back to Fireworks seamlessly (badge on) — sandbox never requires a live droplet |
| Failure UX | any abort → completed-runs gallery + replay (§6) as the always-working surface |

## 5. Demo seed kits & per-demo backend requirements

| Demo | Seed kit (`infra/seeds/`) | Backend must support (beyond pipeline) |
|---|---|---|
| **1 — KYC hero** | synthetic identity docs (30 applicants: generated PDFs/images), **real public OFAC + EU consolidated lists** (downloaded at seed time), synthetic PEP/adverse-media fixtures | OCR path (03 §2); registry landing + live batch run (04 §4); **refinement beat**: rehearsed change request → triage → scoped rebuild → v2 diff view (04 §5); deterministic rehearsal = fixed seeds + temp 0.1 on demo path |
| **2 — Sovereign Surveillance finale** | synthetic order/trade blotters, planted spoofing + wash-trade sequences (deterministic generator) | global sovereign toggle (06); egress ledger panel proving `EXTERNAL: 0`; planted patterns must fire → validate detection in rehearsal, tune generator not the model |
| **3 — Regulatory Report Factory** | mock source systems (CSV/SQLite), one real public regulatory schema (O6 — pick a tractable XBRL/JSON schema Day 3), synthetic financials | validation wall = stage-5 gate rendered as N/143 counters (`consolidate.test_run`); **re-run beat**: Q3 batch on new data, per-run cost + zero-frontier ledger on screen |
| **4 — Sandbox** | §2 | §3–4 |
| **5 — Claims (pre-decided cut)** | 500 synthetic claims + policy fixtures | nothing new — "487/13" stat comes free from oracle flags (08 §4); graft onto KYC if cut |

## 6. Replay (event sourcing's free demo insurance)

`GET /api/replay/{scope}` returns the full ordered event list for any completed job/run; the frontend replay player re-drives the *same components* as live view at ×1/×4/×16. Uses: gallery entries ("watch this build"), rehearsal review, and the fallback if live GPU capacity dies mid-presentation. Replays are honestly labeled **Replay** in the UI — they are recordings of real runs, not canned outputs; the live path always exists alongside.

## 7. Pre-demo checklist (rehearsal gate, per demo)

- [ ] Seed regenerated from scratch on the VM (proves no hand-tuned state)
- [ ] Full live run green twice consecutively on target fleet profile
- [ ] Replay captured and spot-checked
- [ ] Budget burn per run recorded (10) — confirms judging-window credit math (02 §5)
- [ ] Fallback (P0) run green with badge visible
