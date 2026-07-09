# Nxcleus — control plane (backend)

The FastAPI control plane + event-sourced orchestrator for the adaptive sovereign process platform.
It hosts the API + SSE event streams, the SQLite ledger, and the asyncio pipeline engine. **It runs
zero LLM inference** — all model calls go out to the MI300X fleet (vLLM/ROCm), the Fireworks fallback
(AMD-hosted), or the Anthropic planner; only the sanitized planner brief ever leaves the boundary.

Specs are the source of truth: `../docs/specs/` (start at `00-INDEX.md`).

## Stack

- Python **3.12** (pinned via `.python-version`), managed with **uv** (project rooted here).
- FastAPI + Uvicorn, SQLAlchemy Core over aiosqlite (SQLite WAL, single writer), Pydantic v2.
- Anthropic SDK + OpenAI-compatible httpx clients for vLLM/Fireworks; a deterministic `MockClient`
  backs dev/CI so the whole pipeline runs with zero keys.

## Boot (zero config)

```bash
cd backend
uv sync --extra dev            # creates .venv, installs deps (downloads CPython 3.12 if needed)
uv run uvicorn app.main:app    # boots with no env vars: SQLite in ./data/, mock model backends
```

- Health: `GET /api/health` · feature flags: `GET /api/config/public` · OpenAPI: `/docs`.
- A gitignored `.env` at the repo root is read automatically when present (real keys, real backends).
- `MODEL_MODE`: `mock` (default, deterministic) · `auto` (real backend when reachable, else mock) ·
  `live` (real only).

## Seed the demo feed

```bash
uv run --project backend python scripts/dev_seed.py     # from repo root
```

Runs a KYC/AML job stages 0→7 in mock mode, registers a process + a batch run, exercises
refine / BYOK / sandbox / sovereign-enforcement, and prints event-catalog coverage. Idempotent.

## Tests / lint

```bash
uv run pytest        # boundary enforcement, state machine, resumability, structured-output repair
uv run ruff check .
```

## Live smoke (manual — needs real keys, never in CI)

```bash
uv run --project backend python scripts/live_smoke.py   # ≤10-token calls to Anthropic + Fireworks
```

## Layout (spec 01 §4)

```
app/
  main.py         app factory + lifespan (engine start, node poll)
  config.py       pydantic-settings — every env var, all defaulted
  db/             schema.sql (05), engine (WAL/single-writer), dao, models.py (artifact shapes)
  events.py       envelope + typed catalog (06 §3) + in-process SSE bus (replay/tail/heartbeat)
  boundary/       stage 0 + egress ledger, boundary vault, PII mask, consult gate, whisper, secrets
  models/         router (boundary enforced here) + clients (vLLM/Fireworks/Anthropic/Mock) + registry
  seats/          base.py (the seam) + _placeholder.py (backend) + <seat>.py (AI engineer)
  orchestrator/   engine + StageContext, seat resolver, code-exec stub
  planning/ certify/ quote/ fleet/ conduct/ consolidate/ qa/ delivery/   stages 1–7
  runtime/        operate-phase run execution + process package/workspace layout
  refine/ sandbox/ metering/ api/
```
