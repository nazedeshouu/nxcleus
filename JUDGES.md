# For judges — hands-on in 2 minutes

Everything below runs on our hosted demo with **platform keys already provided** — you do **not** need your own API key to sign in or run a job.

- **App:** https://amdplatform.nxcleus.tech (sign-in wall) → lands on the `/build` cockpit
- **Landing / story:** https://amd.nxcleus.tech
- **Sign in:** username `judge` · password `nx-61027a2d5f5ce492f3`
- **Create your own account (optional):** invite code `amd-judge-2026` on the sign-up form

(These credentials are intentionally public for judging.)

---

## The 2-minute path

**Option A — run a detection on planted data (fastest).**
1. Sign in, open **Sandbox**.
2. Pick the **insurer** corpus → the **"Audit duplicate claims"** suggestion.
3. Run it. When it finishes, open the run and hit **Compare with planted patterns** — it diffs what the pipeline flagged against the ground truth we planted in the seed corpus (true positives / misses, side by side).

**Option B — describe any process (the real product).**
1. Go to **/build**, type a plain-language automation ("review these contracts and flag ones that contradict themselves", attach files or point at a sandbox company).
2. The planner drafts the work; you get a **priced quote** — approve it (this is the human-in-the-loop gate).
3. It builds on the fleet, runs adversarial QA, and registers a process you can re-run.

> Sandbox runs are rate-limited to **3 runs/hour per session** — if you hit the wall, sign up with the invite code for a fresh session, or open an already-completed run.

---

## What to look at

- **Run map** — the live fan-out of the job across stages and parallel agents.
- **/traces → egress ledger** — every outbound request with `(host, zone, seat, data_class, bytes)`. This is the boundary, auditable. The **prompts** for each seat are inspectable here too.
- **Compare with planted patterns** — flags vs. the corpus's known ground truth (the honesty check on detection quality).
- **Judge-readable report** — per-run report written for a human reviewer, not a log dump.

---

## The architecture, in five lines

1. You describe work in plain language against your own data.
2. **Exactly one** step leaves the boundary: a stage-1 planner (GPT-5.6 via OpenRouter) that sees **only a PII-sanitized brief** — never raw data.
3. Everything else — plan certification, build, review, adversarial QA — runs on **local AMD MI300X** (vLLM/ROCm), with Fireworks (AMD-hosted) as a badged fallback.
4. Every outbound call is logged to the egress ledger; each job produces a receipt: "exactly N external calls, all sanitized."
5. Flip **Sovereign Mode** and even the planner moves on-fleet — zero external calls, enforced in code (any leak paints the run red).

## Measured on our runs

- **~$0.54** to design + build a process · **~$0.025** per batch run afterward.
- **138/138** planted patterns caught on the insurer duplicate-claims corpus.
- After a process is registered it runs **forever with zero further frontier calls**.

---

## Run it yourself locally (no keys needed)

Mock mode backs the whole pipeline end-to-end with a deterministic client — no API keys, no GPU. Requires [`uv`](https://docs.astral.sh/uv/) and Node 20+.

```bash
# backend (zero config — SQLite in ./data/, mock model backends)
cd backend && uv sync --extra dev && uv run uvicorn app.main:app

# drive a full job 0 → 7 in mock mode (from repo root)
uv run --project backend python scripts/dev_seed.py

# frontend
cd frontend && npm install && npm run dev
```

`MODEL_MODE=mock` is the default (deterministic). Set `MODEL_MODE=auto` (or `live`) with keys in a gitignored `.env` to use real models — see the [README](README.md#live-mode-optional--real-models).
