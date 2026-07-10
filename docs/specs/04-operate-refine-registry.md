# 04 — Operate Phase, Refine Phase & Registry

Locked 2026-07-07. Upstream: design v2 §4–5. Siblings: 03 (how packages are born), 08 (continuous assurance), 10 (per-run metering).

## 1. Operations registry

`processes` + `process_versions` (05) back the Operations view: a table of the customer's automations with versions, run history, per-run cost trend, open warranty tickets, and three actions per process: **run batch**, **instantiate copy**, **request refinement**. Hackathon scope stays modest (design §4) — the KYC and Reg-Report demos exercise it naturally.

## 2. Process package format

One directory per version under `/data/packages/{process}/{version}/`, immutable after certification:

```
manifest.json      # name, version, mode, goal (D10), model_bom, connector bindings, entrypoint,
                   # runtime image tag (build mode), sampling rates, schemas (unit/result)
plan/
  plan.json        # certified plan (final version, rehydrated — package stays inside the boundary)
  amendments.jsonl # hash-chained amendment log (certifier + conductor origins)
  consults.jsonl   # consult history (sanitized payloads, as sent)
  goal.json        # goal statement + stage-6 goal-fulfillment verdict (08 §1.5)
src/               # build mode: generated modules + process.py entrypoint
topology.json      # process mode: executable topology (plan.topology extract)
tests/
  integration.json # stage-2 test specs
  vectors.json     # oracle vectors (inputs only)
docs/              # generated README, runbook, QA report
invoice.json       # final metered build invoice
```

The package is the "yours to run forever" artifact — the deck line is literal: repo-shaped, auditable, exportable.

## 3. Runtime contract (build mode)

Generated code implements one interface, executed inside the shared **process-runtime** container (01 §5):

```python
class Process(Protocol):
    input_schema: dict      # JSON Schema of a unit of work
    output_schema: dict     # JSON Schema of a unit result
    steps: list[StepMeta]   # names + kinds, for UI progress

    async def run_unit(self, unit: dict, ctx: ProcessContext) -> UnitResult
        # UnitResult.status: "ok" | "needs_review" | "error"
        # UnitResult.output: validated against output_schema
        # UnitResult.trace: per-step records (renders the audit trail)

class ProcessContext(Protocol):
    async def model(self, seat: str, messages, *, schema=None) -> Completion
        # → control-plane model-proxy; token scoped to manifest BoM seats
    def connector(self, name: str) -> Connector      # mock connectors from the seed kit
    def log(self, step: str, **fields) -> None       # → run_units trace
```

Rules enforced at consolidation review + runtime: no network besides `ctx.model` (container network is VM-internal only), no raw model names, deterministic logic in plain Python, judgment steps only via seats. **Semi-automated mode** is `status="needs_review"` + the review queue (§6) — a contract feature, not a separate topology.

The runtime container wraps `Process` with a standard FastAPI shim: `GET /health`, `GET /manifest`, `POST /run_unit`. The control plane's batch runner drives it; Caddy exposes it read-only at `/processes/{slug}` for inspector probes and judges.

## 4. Run execution (both modes)

`POST /api/processes/{id}/runs {version?, input: batch_ref | corpus_ref, kind: "batch"}`:

1. Resolve version → package; ensure runtime (build: container up; process: topology runner in-process).
2. Enqueue units from the input source (seed-kit dataset, sandbox corpus, or uploaded batch).
3. Fan out: build mode → `POST /run_unit` per unit with bounded concurrency; process mode → per-unit topology steps on fleet seats (one unit per worker slot, 07 §6).
4. Each unit: `run_units` row + `run.unit_completed` event; meter events accrue per seat call.
5. **Oracle spot-checks** sample `manifest.sampling` of completed units (08 §6); discrepancy → warranty ticket, never auto-fix.
6. Close: `runs.stats_json` = `{units, ok, needs_review, errors, spot_checks, discrepancies}`, `cost_json` from meter aggregation — the flat-and-small per-run cost line (10 §6).

**Zero frontier calls per run** is asserted, not narrated: the run view shows the egress ledger filtered to the run's scope — `EXTERNAL: 0 requests`.

## 5. Refine phase

`POST /api/processes/{id}/refine {request: "also flag adverse media in Spanish"}`:

1. **Triage** (`certifier`): delta vs. certified plan → `amend` (mechanical: new field, threshold, schema data point) or `consult` (structural) — same triage schema as stage 2 (03 §4).
2. Amend path: certifier patches plan locally → affected modules/steps identified from the DAG → only those rebuild (stage 4 scoped) → scoped re-certification (affected checks + new tests).
3. Consult path: constrained re-plan (scope-locked, 03 §3) — planner sees sanitized plan + delta only, never accumulated data — then as above.
4. New `process_versions` row v(n+1): `diff_json` = plan JSON-diff + modules rebuilt + tests added + re-certification findings (renders the human-readable diff view). **Old versions stay runnable** — packages are immutable, `runs.version` pins.
5. Mini-quote → mini-invoice; frontier tokens itemized only if a consult fired (the "~2% of original build" receipt).

**Re-instantiation** (`POST .../instantiate {connectors}`): re-enters the pipeline at stage 4 with the certified plan as-is and new connector bindings — no stage-1 planner call. New process entry, `created_from` lineage.

## 6. Continuous assurance ("operating with a warranty")

Beyond per-run spot-checks: a scheduler tick (asyncio, hourly by default, config) runs (a) oracle re-checks on a sample of recent live outputs, (b) one short inspector probe suite against each registered process's runtime. Findings file **warranty tickets** into the process queue (visible in Operations view) and feed Refine. Language rule everywhere (UI copy, docs, deck): *operating with a warranty* — never unattended magic.

**Review queue:** `run_units` with `needs_review` render as a per-process queue; a human verdict (`approve`/`reject` + note) closes the unit and is recorded in the trace — the semi-automated mode demo beat.

---

## Wave-2 backend deviations (live integration, 2026-07-09)

Flagged per the change protocol; implemented in `backend/`.

- **Code-exec sandbox is real (§3).** `orchestrator/codeexec.py` now runs the workspace in a throwaway `python:3.12-slim` container with `--network none`, CPU/memory/PID caps, and the workspace copied into a container-private tmpfs (host mount read-only). It runs the workspace's pytest suite when one exists, else an import/compile smoke of every source file. Degrades to the Wave-1 deterministic behaviour (flagged `sandboxed:false`) when Docker is absent (dev/CI), so mock mode never hard-depends on a daemon.
- **Stage-6 staging deploy is an in-process FastAPI shim (§3), not a per-job container image on the live path.** `runtime/staging.py` serves the assembled process over REAL HTTP on an ephemeral `127.0.0.1` port (`GET /health`, `GET /manifest`, `POST /run_unit`) — the inspector swarm probes a live endpoint, and the shim imports the process's `run_unit` entrypoint when present. Rationale: an in-process uvicorn shim gives the inspector a genuine HTTP surface without a ~per-job docker build/pull in the demo window; the container image build/tag stays as the delivery-time step. Same shim contract either way.
- **Per-process proxy token implemented (§3).** `boundary/proxy_token.py` mints a compact HMAC token (key derived from `ADMIN_TOKEN`) scoped to `{process, seats, exp}`; the staging shim's `/run_unit` enforces it, so a token minted for process A is refused on process B (the inspector's wrong-tenant probe hits a real 401). Wiring into the model-proxy endpoint (`api/proxy.py`) is the remaining step.

### 2026-07-10 hardening wave

`drive_run` is now REAL: the simulated unit-{i} / i%7 path is deleted. A shared `execute_topology` (runtime/operate.py) serves both the stage-4 fan-out and registered-process runs: topology-mode runs load the version package's `topology.json` and sweep real corpus units metered on `run:<id>`; build-mode runs (entrypoint process.py) drive every unit through the staging shim over real HTTP. Topologies may carry `kind:"sql"` candidate steps — a single read-only SELECT against the bound corpus whose result rows replace the unit set for the per-unit judgment steps (cross-row detections: pairs, clusters, sums-vs-limits, window bursts); sql-only topologies land their rows directly as findings. Corpus binding: `processes.corpus_company` is stored at delivery; `POST /processes/{id}/runs` accepts `{corpus:{company}, sample:{mode:first|random,n}, deliverable:{...}}` (run `params_json`). Warranty spot-checks are honest — K random completed units re-run and compared (no rehearsed discrepancy). Every completed run writes deliverables (`findings.csv` + self-contained print-ready `report.html`) served at `GET /runs/{id}/report` and `/runs/{id}/export.csv`, announced via `run.artifacts_ready`.
