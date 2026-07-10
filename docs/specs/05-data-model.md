# 05 — Data Model

Locked 2026-07-07. SQLite (WAL) at `SQLITE_PATH`, SQLAlchemy Core + aiosqlite, single writer (the API process). Schema lives in `backend/app/db/schema.sql`, applied idempotently at startup (no migration tool inside the window; additive changes only). IDs are ULIDs with type prefixes (`job_`, `pln_`, `prc_`, `run_`, `tkt_`…). Timestamps ISO-8601 UTC. `*_json` columns hold schema-validated payloads (pydantic models in `app/db/models.py` are the source of truth for their shapes; key shapes are specified in 03/04).

## 1. Event log (the spine — see 06 §3 for the type catalog)

```sql
CREATE TABLE events (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,   -- global order
  ts         TEXT NOT NULL,
  scope      TEXT NOT NULL,        -- 'job:job_x' | 'run:run_x' | 'fleet' | 'sandbox' | 'system'
  type       TEXT NOT NULL,        -- catalog, 06 §3
  payload    TEXT NOT NULL         -- JSON
);
CREATE INDEX idx_events_scope ON events(scope, seq);
```

Append-only; never updated. Drives: every SSE stream (tail by `scope` from a client-supplied `from_seq`), the replay feature (09 §6), resumability (07 §4), and the audit story. UI state for a job = fold of its events; DB rows below are the *materialized* current state for queries.

## 2. Build phase

```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY, created_at TEXT, title TEXT,
  origin TEXT NOT NULL DEFAULT 'customer',        -- customer | sandbox | reinstantiate | refine
  mode TEXT,                                      -- build | process | semi (null until classified)
  sovereign INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,                           -- intake|planning|certifying|quoted|building|
                                                  -- consolidating|qa|delivering|done|blocked|aborted
  current_stage INTEGER, spec_json TEXT,
  policy_json TEXT,                               -- RedactionPolicy (03 §2.1, D11); null = PII baseline only
  goal TEXT,                                      -- goal statement, set at stage 2 (03 §4.3, D10)
  sandbox_session_id TEXT, parent_process_id TEXT -- lineage for refine/instantiate jobs
);
CREATE TABLE job_messages (
  id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id),
  role TEXT,                                      -- customer | trust
  content TEXT, ts TEXT
);
CREATE TABLE boundary_vault (                     -- raw→placeholder map; NEVER serialized outward
  job_id TEXT, placeholder TEXT, raw_value TEXT, kind TEXT,
  PRIMARY KEY (job_id, placeholder)
);
CREATE TABLE plans (
  id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id),
  version INTEGER, status TEXT,                   -- draft | certifying | certified | superseded
  body_json TEXT, certified_at TEXT
);
CREATE TABLE amendments (                         -- hash-chained (03 §4)
  id TEXT PRIMARY KEY, plan_id TEXT REFERENCES plans(id), seq INTEGER,
  origin TEXT NOT NULL DEFAULT 'certifier',       -- certifier | conductor (D8) — one chain, one seq
  finding_id TEXT, check_name TEXT, plan_ref TEXT,
  patch_json TEXT, rationale TEXT, spec_ref TEXT,
  prev_hash TEXT, hash TEXT, ts TEXT
);
CREATE TABLE consults (
  id TEXT PRIMARY KEY, plan_id TEXT, round INTEGER,
  scope_json TEXT, request_json TEXT, response_summary TEXT,
  status TEXT,                                    -- open | resolved | abandoned
  ts TEXT
);
CREATE TABLE quotes (
  id TEXT PRIMARY KEY, job_id TEXT, plan_id TEXT,
  body_json TEXT,                                 -- itemized lines, 10 §4
  status TEXT,                                    -- issued | approved | superseded
  issued_at TEXT, approved_at TEXT
);
CREATE TABLE build_tasks (                        -- stage-4 DAG tasks
  id TEXT PRIMARY KEY, job_id TEXT, module_id TEXT,
  wave INTEGER,                                   -- topological level (07 §3.1, D8)
  status TEXT,                                    -- pending|running|fixing|done|failed
  assigned_backend TEXT,                          -- which pool member built it (BoM panel)
  attempts INTEGER, workspace_path TEXT, ts TEXT
);
```

## 3. Operate / refine

```sql
CREATE TABLE processes (
  id TEXT PRIMARY KEY, slug TEXT UNIQUE, name TEXT, mode TEXT,
  goal TEXT,                                      -- carried from jobs.goal at delivery (D10)
  status TEXT,                                    -- active | archived
  current_version INTEGER, created_from_job TEXT, created_from TEXT,  -- lineage (instantiate)
  created_at TEXT
);
CREATE TABLE process_versions (
  id TEXT PRIMARY KEY, process_id TEXT REFERENCES processes(id), version INTEGER,
  plan_id TEXT, package_path TEXT, image_tag TEXT,     -- image_tag null in process mode
  diff_json TEXT,                                      -- vs previous version (04 §5)
  certified_at TEXT, status TEXT,                      -- certified | superseded (still runnable)
  UNIQUE (process_id, version)
);
CREATE TABLE runs (
  id TEXT PRIMARY KEY, process_id TEXT, version INTEGER,
  kind TEXT,                                      -- batch | sandbox | spotcheck | probe
  status TEXT,                                    -- queued|running|done|failed|aborted
  input_ref TEXT, started_at TEXT, finished_at TEXT,
  stats_json TEXT, cost_json TEXT
);
CREATE TABLE run_units (
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), unit_ref TEXT,
  status TEXT,                                    -- ok | needs_review | error
  result_json TEXT, trace_json TEXT,
  review_verdict TEXT, review_note TEXT, ts TEXT
);
CREATE INDEX idx_run_units_run ON run_units(run_id, status);
```

## 4. QA & assurance

```sql
CREATE TABLE tickets (
  id TEXT PRIMARY KEY,
  scope TEXT,                                     -- 'job:x' (stage 6) | 'process:x' (warranty)
  source TEXT,                                    -- inspector | oracle | consolidation | warranty
  severity TEXT,                                  -- blocker | major | minor | disagreement
  status TEXT,                                    -- open | in_fix | verified | human_review | wont_fix
  title TEXT, body_json TEXT,                     -- repro, expected/actual, plan/module refs
  fix_attempts INTEGER DEFAULT 0, ts TEXT
);
CREATE TABLE oracle_checks (
  id TEXT PRIMARY KEY, scope TEXT, vector_id TEXT, rule_id TEXT,
  inputs_json TEXT, expected_json TEXT,           -- oracle's blind computation (+ votes)
  actual_json TEXT, verdict TEXT,                 -- match | mismatch | oracle_uncertain
  votes_json TEXT, ts TEXT
);
```

## 5. Platform

```sql
CREATE TABLE nodes (
  id TEXT PRIMARY KEY, name TEXT,                 -- 'A', 'B', 'C'...
  ip TEXT, status TEXT,                           -- provisioning|ready|draining|down
  gpus_json TEXT, seats_json TEXT,                -- current placements
  last_heartbeat TEXT, registered_at TEXT
);
CREATE TABLE meter_events (                       -- 10 §1
  id TEXT PRIMARY KEY, ts TEXT, scope TEXT,
  seat TEXT, backend TEXT, model_id TEXT,
  kind TEXT,                                      -- llm_call | gpu_sample
  tokens_in INTEGER, tokens_out INTEGER,
  gpu_seconds REAL, cost_usd REAL
);
CREATE INDEX idx_meter_scope ON meter_events(scope);
CREATE TABLE egress_log (
  id TEXT PRIMARY KEY, ts TEXT, scope TEXT,
  host TEXT, zone TEXT,                           -- LOCAL | AMD_HOSTED | EXTERNAL
  seat TEXT, bytes_out INTEGER, bytes_in INTEGER,
  sovereign_violation INTEGER DEFAULT 0
);
CREATE INDEX idx_egress_scope ON egress_log(scope);
CREATE TABLE sandbox_sessions (
  id TEXT PRIMARY KEY, company TEXT, created_at TEXT,
  client_hash TEXT, runs_used INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0
);
CREATE TABLE api_connections (                    -- BYOK custom endpoints (D13, 02 §8)
  id TEXT PRIMARY KEY, name TEXT, base_url TEXT,
  api_key_ref TEXT,                               -- pointer to encrypted secret; NEVER the key
  zone TEXT NOT NULL DEFAULT 'CUSTOM',
  data_class_ceiling TEXT NOT NULL DEFAULT 'SANITIZED',  -- RAW only via boundary attestation
  counts_as_local INTEGER NOT NULL DEFAULT 0,     -- attested on-prem endpoint (sovereign-eligible)
  created_at TEXT
);
CREATE TABLE custom_models (                      -- many models per connection
  id TEXT PRIMARY KEY, connection_id TEXT REFERENCES api_connections(id),
  provider_model_id TEXT, display_name TEXT,
  flags_json TEXT,                                -- capability flags, same vocabulary (02 §7.2)
  context_len INTEGER, notes TEXT, created_at TEXT
);
CREATE TABLE seat_overrides (                     -- user-configurable seat bindings (02 §8.2)
  id TEXT PRIMARY KEY, seat TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'global',           -- global | job:<id>
  model_key TEXT NOT NULL,                        -- models.yaml key or custom_models.id
  set_at TEXT, UNIQUE (seat, scope)
);
```

Sandbox company datasets are **separate read-only SQLite files** (`infra/seeds/out/{bank,clinic,lawfirm}.db`) — browsable via the sandbox API (09 §3), never mixed with platform state.

## 5b. Implementation additions (backend Wave 1, change protocol)

Two additive tables not in the original §2–5 list, added by the backend with the code that needs them:

- **`secrets`** (`ref` PK, `ciphertext`, `created_at`) — encrypted-at-rest store for BYOK keys; the
  `api_connections.api_key_ref` points here (never the key itself), Fernet-encrypted (D13, 02 §8).
- **`checkpoints`** (`scope`, `key`, `value_json`, `ts`; PK `(scope, key)`) — job/run-scoped scratch
  backing `StageContext.checkpoint()` for resumability (07 §1, §4). Stage 4 stores the certified
  plan id + test/vector sets here so a restart re-enters at the top of a stage cheaply.

Both are `CREATE TABLE IF NOT EXISTS` in `schema.sql`, applied idempotently at startup like the rest.

## 6. Retention & ops

- Everything fits SQLite for the window (events for a full build ≈ low thousands of rows). No deletes during the hackathon; `VACUUM` not needed.
- Nightly `sqlite3 .backup` to `/data/backups/` (cron on the VM) — cheap insurance before demo days.
- Postgres upgrade path (post-hackathon): schema is vanilla SQL; swap engine URL, replace AUTOINCREMENT seq with BIGSERIAL. Not in scope now.

### 2026-07-10 hardening wave (additive)

New columns: `jobs.request` (RAW original request — survives the intake spec overwrite), `processes.corpus_company` (default run corpus binding), `runs.params_json` (`{corpus, sample, deliverable}`), `runs.next_steps_json` (cached advisory). New table `model_traces` (per-dispatch prompt/response trace). `jobs.status` gains `awaiting_input`; `tickets.status` gains `fix_applied`. Applied via idempotent ALTERs in `db/engine.apply_schema` for pre-existing DBs.
