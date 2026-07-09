# 10 — Metering, Quote & Economics

Locked 2026-07-07. Upstream: design v2 §8 ("frontier intelligence is a capital expense, not a marginal cost" — the money slide). Siblings: 02 §2 (router hooks), 05 §5 (tables), 06 (economics endpoints). Metering is not bookkeeping garnish here — it *is* the product claim, so it must be real numbers from real calls.

## 1. Meter events (written by the router on every dispatch)

`meter_events` row per LLM call: `(ts, scope, seat, backend, model_id, kind=llm_call, tokens_in, tokens_out, cost_usd)` — token counts from the provider/vLLM response `usage`, cost from the rates table (§3). GPU sampling rows (`kind=gpu_sample`, from telemetry 1-in-15 samples) record `(node → gpu_seconds at utilization)` for attribution.

## 2. GPU-second attribution (honest approximation, documented as such)

Exact per-request GPU accounting isn't feasible in the window; we use a defensible estimate, and we *say so* in the invoice footnote (regulated-enterprise honesty is on-brand):

- Per LLM call on a local backend: `gpu_seconds ≈ wall_clock_of_call × (1 / concurrent_requests_on_that_instance_avg)` — concurrency snapshot from vLLM `/metrics` at dispatch and completion.
- Per scope (job/run): sum of its calls' estimates, cross-checked against node-level utilization samples for the active window; if the sum exceeds measured node time, scale down pro-rata.
- `cost_usd = gpu_seconds × node_rate / 3600`.

## 3. Rates config (`infra/rates.yaml`)

```yaml
gpu:
  mi300x_hour_usd: 2.00          # confirm on portal (O5)
backends:
  anthropic:
    claude-fable-5: {in_per_mtok: X, out_per_mtok: Y}    # fill from price sheet Day 1
  fireworks:
    <model-id>: {in_per_mtok: ..., out_per_mtok: ...}     # from Fireworks catalog
  local:
    default: {in_per_mtok: 0, out_per_mtok: 0}            # local tokens are priced as GPU time, not per-token
margin: 0.0                       # hackathon: cost passthrough; product: pricing knob
```

## 4. Quote engine (stage 3 — deterministic, no LLM)

Input: plan `estimates` + `model_bom` + rates. Output `quotes.body_json`:

```jsonc
{
  "lines": [
    {"item": "Frontier planning & consults (sanitized brief only)", "qty": "≈120k tokens", "est_usd": [1.8, 3.6]},
    {"item": "Local certification, build waves & conductor review (GPU)", "qty": "≈1.9 GPU-h on 3× MI300X", "est_usd": [3.4, 5.1]},
    {"item": "Local consolidation (GPU)", "qty": "≈0.2 GPU-h", "est_usd": [0.3, 0.5]},
    {"item": "Adversarial QA incl. Numeric Oracle & goal check", "qty": "≈0.5 GPU-h", "est_usd": [0.9, 1.4]},
    {"item": "Projected per-run operating cost", "qty": "per 100 units", "est_usd": [0.06, 0.12]}
  ],
  "total_est_usd": [6.3, 10.7],
  "basis": "model BoM v1; ranges = ±50% on token estimates, ±30% on GPU time"
}
```

Estimation heuristics (config constants, tuned after first end-to-end run): tokens per module by complexity S/M/L; consult probability by findings-per-check history; GPU-h from BoM width × stage latency targets. **Quote is a range; the invoice is exact** (design §8) — reconciliation renders side-by-side at delivery.

## 5. Invoice (stage 7 + per refine)

Aggregate `meter_events` by scope → same line structure as the quote with actuals: real token counts per seat/backend/zone, estimated GPU-seconds (§2 footnote), delta vs quote. Stored in the package (`invoice.json`), rendered in Build view at delivery and downloadable. Refine invoices additionally show "frontier consult: $0.00" when triage stayed local — the receipt for the triage authority story.

## 6. Money-slide data (`GET /api/economics/summary`)

Per process: `{build_cost_usd, refine_costs[], runs: [{run_id, ts, units, cost_usd, cost_per_unit, frontier_calls: 0}], trend}` — the Operations view draws the capex-vs-flat-opex chart from this (frontend session decides the visual; this payload is the contract). The Reg-Report re-run beat and the sandbox both feed it live.

## 7. Budget guards (enforcement points)

- Router pre-dispatch check per 07 §5.4 (Fireworks daily cap, sandbox per-run cap).
- Per-job soft ceiling from the approved quote's upper bound ×1.5 → `system.notice` warning at 80%, park job at 100% (presenter may raise — never silently overrun a quoted price; that's a product behavior worth demoing if it ever triggers).
- All caps and current burn visible at `/api/config/public` for the UI's cost meter.
