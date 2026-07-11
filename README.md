# Nxcleus

**A plain-language request becomes a planned → certified → built → adversarially-QA'd → registered process automation — with your data never leaving hardware you control.**

Nxcleus is a sovereign automation platform for businesses that legally *cannot* send their data to an external AI. You describe what you need in plain language — attach files, a codebase, database schemas, a confidentiality policy — and the platform designs the work, completes and certifies the plan against your real data, builds it on a fleet of parallel agents, attacks it with adversarial QA, and registers a process that then runs forever with **zero further frontier calls**. Exactly one step ever talks to an outside model: a stage-1 planner that sees only a PII-sanitized brief. Everything else runs inside the boundary, on AMD silicon.

**Live:** https://nxcleus.tech

![Nxcleus landing](frontend/screenshots/redesign-landing-full.png)

Built for the **AMD Developer Hackathon: ACT II — Track 3 (Unicorn / Open Innovation)**. The hackathon reference material and our submission notes live in [`docs/hackathon/`](docs/hackathon/); the full engineering specs are in [`docs/specs/`](docs/specs/00-INDEX.md).

---

## What makes it different

- **The data boundary is enforced in code, not by policy.** A local trust model strips everything your confidentiality policy and the PII baseline forbid — *without losing the specification* — and composes a brief for the frontier planner. That brief is the only thing that ever crosses the line.
- **The frontier plans; local models do the real work.** After the planner drafts the topology, a strong local model completes and corrects it against the **full raw context the frontier never saw**, restores production specificity, and pins the goal the whole job is judged against. Build, review, consolidation, and adversarial QA are all local.
- **Sovereign Mode = zero external calls.** One toggle rebinds the planner onto the local fleet. Any outbound frontier call during a sovereign job raises `SovereignViolation` and paints the run red.
- **The boundary is auditable.** Every outbound request is logged to an egress ledger (`GET /api/egress`) with `(host, zone, seat, data_class, bytes)`, streamed live to the UI. Each job produces a receipt: "exactly N external calls, all sanitized."

---

## Built on AMD

> **Every token this platform generates is generated on AMD silicon — and everything except one planning conversation happens on GPUs we control.**

- **Self-hosted AMD Instinct MI300X (192 GB), running vLLM on ROCm.** This is the LOCAL zone. It hosts the trust layer, plan certification, the Numeric Oracle, and the adversarial QA inspectors — the seats that touch raw customer data. The MI300X's 192 GB of HBM is what lets these models sit resident and serve the pipeline without paging.
- **Fireworks AI (AMD-hosted serving) as the badged fallback.** Larger seats and availability failover route to Fireworks — which itself serves on AMD hardware — so the demo URL stays alive when the elastic fleet is powered down. Every Fireworks-served run is badged in the UI as fallback.
- **The one non-AMD call is the stage-1 planner (GPT-5.6, via OpenRouter),** and it only ever receives the sanitized brief. Turn on Sovereign Mode and even that moves on-fleet — the pipeline runs end-to-end on the MI300X, zero non-local calls.
- **The coordination VM runs zero LLM inference.** A small always-on host serves the UI, the SQLite ledger, and the scheduler. It's the receptionist, not the brain — all inference is on AMD.

This split *is* the product architecture, not a hackathon convenience: in production the thin control plane sits inside the customer's walls (or on dedicated AMD capacity we operate for them) and schedules work onto their GPUs, with fleet allocation justified line-by-line by each plan's model bill-of-materials.

### The zone model

The `ModelRouter` classifies every model backend into a zone and enforces where each data class may travel — this is a code path, not a convention:

| Zone | Runs on | RAW customer data | SANITIZED brief |
|---|---|---|---|
| **LOCAL** | Self-hosted MI300X (vLLM / ROCm) | ✅ | ✅ |
| **AMD_HOSTED** | Fireworks AI (AMD serving, badged fallback) | ⚠️ demo exception only (synthetic data, badged) | ✅ |
| **CUSTOM** | Customer BYOK endpoints (optional) | ⚠️ only if boundary-attested | ✅ |
| **EXTERNAL** | Frontier planner — GPT-5.6 via OpenRouter | ❌ hard error | ✅ (❌ in Sovereign Mode) |

**The boundary rule, in one sentence:** *`RAW` never leaves `LOCAL`; `EXTERNAL` only ever receives the sanitized planner brief and sanitized consults.*

Architecture detail: [`docs/specs/01-system-architecture.md`](docs/specs/01-system-architecture.md) · seats & routing: [`docs/specs/02-model-seats-and-routing.md`](docs/specs/02-model-seats-and-routing.md).

---

## The pipeline (stages 0 → 7)

A job flows through eight stages. Only stage 1 leaves the boundary — and only with the sanitized brief.

| # | Stage | Seat(s) | Zone |
|---|---|---|---|
| 0 | Intake, policy distillation, classification & data boundary | `trust` | LOCAL |
| 1 | Planning (work topology + bill-of-materials) | `planner` | **EXTERNAL** / LOCAL (sovereign) |
| 2 | Plan completion, rehydration & certification against raw context | `certifier` (+ sanitized planner consults) | LOCAL |
| 3 | Quote (deterministic, from the plan's BoM) | — | LOCAL |
| 4 | Parallel code generation in waves, with between-wave review | `coder` pool + `conductor` | LOCAL (fleet) |
| 5 | Consolidation — merge modules, run the full integration suite | `consolidator` | LOCAL |
| 6 | Adversarial QA + goal check | `inspector`, `oracle`, `coder` | LOCAL |
| 7 | Delivery → operations registry | `trust` (docs) | LOCAL |

Process-mode jobs (corpus fan-out over many units instead of code generation) run stages 4′/5′ in place of 4/5. Full contracts: [`docs/specs/03-build-pipeline.md`](docs/specs/03-build-pipeline.md).

---

## Run it locally

Everything runs from a clean clone **with no API keys** in mock mode — a deterministic `MockClient` backs the whole pipeline end to end. Requires [`uv`](https://docs.astral.sh/uv/) and Node 20+.

### Backend (zero config)

```bash
cd backend
uv sync --extra dev            # creates .venv, installs deps (fetches CPython 3.12 if needed)
uv run uvicorn app.main:app    # boots with no env vars: SQLite in ./data/, mock model backends
```

- Health: `GET /api/health` · public feature flags: `GET /api/config/public` · OpenAPI: `/docs`.
- `MODEL_MODE` controls dispatch: `mock` (default, deterministic) · `auto` (real backend when reachable, else mock) · `live` (real only).

### Run a full job 0 → 7 in mock mode

```bash
# from the repo root
uv run --project backend python scripts/dev_seed.py
```

This drives a KYC/AML job through all eight stages, registers a process and a batch run, and exercises the refine / BYOK / sandbox / sovereign-enforcement paths — every event the pipeline can emit appears at least once. Idempotent and re-runnable.

### Frontend

```bash
cd frontend
npm install
npm run dev                    # Vite dev server; proxies /api to the backend
```

### Tests

```bash
cd backend && uv run pytest    # boundary enforcement, state machine, resumability, structured-output repair
```

### Live mode (optional — real models)

Copy your keys into a gitignored `.env` at the repo root and set `MODEL_MODE=live` (or `auto`). Every variable has a safe default, so only set what you use. Canonical names (full surface in [`backend/app/config.py`](backend/app/config.py)):

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Flagship stage-1 planner (`openai/gpt-5.6-sol`) |
| `FIREWORKS_API_KEY` / `FIREWORKS_BASE_URL` | AMD-hosted fallback serving |
| `HF_TOKEN` | Gated model downloads on the droplet (Gemma repos) |
| `DIGITALOCEAN_ACCESS_TOKEN` | Elastic MI300X fleet automation |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Optional BYOK / planner fallbacks |
| `SOVEREIGN_DEFAULT` | Boot every job with zero external calls |
| `ALLOW_RAW_ON_AMD_HOSTED` | Toggle the AMD-hosted demo exception (set `false` to show hard enforcement) |
| `ADMIN_TOKEN` / `APP_BASE_URL` | Admin endpoints · public URL |

---

## Repository layout

```
backend/     FastAPI control plane + event-sourced orchestrator (runs zero LLM inference)
  app/models/    ModelRouter (boundary enforced here) + vLLM / Fireworks / OpenRouter / Mock clients
  app/boundary/  stage 0: PII masking, policy distillation, consult gate, egress ledger
frontend/    React + Vite UI (Build cockpit, Traces, egress ledger, replay gallery)
infra/       droplet ROCm/vLLM bootstrap, node agent, seats.yaml / fleet.yaml / rates.yaml, seed kits
docs/        specs/ (engineering source of truth) · hackathon/ (event reference)
scripts/     dev_seed.py (mock E2E) · live_smoke.py
```

---

## License

MIT — see [`LICENSE`](LICENSE).
