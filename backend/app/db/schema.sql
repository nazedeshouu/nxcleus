-- Nxcleus control-plane schema (spec 05). SQLite (WAL), applied idempotently at startup.
-- `IF NOT EXISTS` everywhere so it re-runs harmlessly; additive changes only in-window.

-- 1. Event log (the spine — 06 §3 for the type catalog) -----------------------------------------
CREATE TABLE IF NOT EXISTS events (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,   -- global order
  ts         TEXT NOT NULL,
  scope      TEXT NOT NULL,        -- 'job:job_x' | 'run:run_x' | 'fleet' | 'sandbox' | 'system'
  type       TEXT NOT NULL,        -- catalog, 06 §3
  payload    TEXT NOT NULL         -- JSON
);
CREATE INDEX IF NOT EXISTS idx_events_scope ON events(scope, seq);

-- 2. Build phase ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
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
CREATE TABLE IF NOT EXISTS job_messages (
  id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id),
  role TEXT,                                      -- customer | trust
  content TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS boundary_vault (       -- raw->placeholder map; NEVER serialized outward
  job_id TEXT, placeholder TEXT, raw_value TEXT, kind TEXT,
  PRIMARY KEY (job_id, placeholder)
);
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id),
  version INTEGER, status TEXT,                   -- draft | certifying | certified | superseded
  body_json TEXT, certified_at TEXT
);
CREATE TABLE IF NOT EXISTS amendments (           -- hash-chained (03 §4)
  id TEXT PRIMARY KEY, plan_id TEXT REFERENCES plans(id), seq INTEGER,
  origin TEXT NOT NULL DEFAULT 'certifier',       -- certifier | conductor (D8) — one chain, one seq
  finding_id TEXT, check_name TEXT, plan_ref TEXT,
  patch_json TEXT, rationale TEXT, spec_ref TEXT,
  prev_hash TEXT, hash TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS consults (
  id TEXT PRIMARY KEY, plan_id TEXT, round INTEGER,
  scope_json TEXT, request_json TEXT, response_summary TEXT,
  status TEXT,                                    -- open | resolved | abandoned
  ts TEXT
);
CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY, job_id TEXT, plan_id TEXT,
  body_json TEXT,                                 -- itemized lines, 10 §4
  status TEXT,                                    -- issued | approved | superseded
  issued_at TEXT, approved_at TEXT
);
CREATE TABLE IF NOT EXISTS build_tasks (          -- stage-4 DAG tasks
  id TEXT PRIMARY KEY, job_id TEXT, module_id TEXT,
  wave INTEGER,                                   -- topological level (07 §3.1, D8)
  status TEXT,                                    -- pending|running|fixing|done|failed
  assigned_backend TEXT,                          -- which pool member built it (BoM panel)
  attempts INTEGER, workspace_path TEXT, ts TEXT
);

-- 3. Operate / refine ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processes (
  id TEXT PRIMARY KEY, slug TEXT UNIQUE, name TEXT, mode TEXT,
  goal TEXT,                                      -- carried from jobs.goal at delivery (D10)
  status TEXT,                                    -- active | archived
  current_version INTEGER, created_from_job TEXT, created_from TEXT,  -- lineage (instantiate)
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS process_versions (
  id TEXT PRIMARY KEY, process_id TEXT REFERENCES processes(id), version INTEGER,
  plan_id TEXT, package_path TEXT, image_tag TEXT,     -- image_tag null in process mode
  diff_json TEXT,                                      -- vs previous version (04 §5)
  certified_at TEXT, status TEXT,                      -- certified | superseded (still runnable)
  UNIQUE (process_id, version)
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, process_id TEXT, version INTEGER,
  kind TEXT,                                      -- batch | sandbox | spotcheck | probe
  status TEXT,                                    -- queued|running|done|failed|aborted
  input_ref TEXT, started_at TEXT, finished_at TEXT,
  stats_json TEXT, cost_json TEXT
);
CREATE TABLE IF NOT EXISTS run_units (
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), unit_ref TEXT,
  status TEXT,                                    -- ok | needs_review | error
  result_json TEXT, trace_json TEXT,
  review_verdict TEXT, review_note TEXT, ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_units_run ON run_units(run_id, status);

-- 4. QA & assurance ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  scope TEXT,                                     -- 'job:x' (stage 6) | 'process:x' (warranty)
  source TEXT,                                    -- inspector | oracle | consolidation | warranty
  severity TEXT,                                  -- blocker | major | minor | disagreement
  status TEXT,                                    -- open | in_fix | verified | human_review | wont_fix
  title TEXT, body_json TEXT,                     -- repro, expected/actual, plan/module refs
  fix_attempts INTEGER DEFAULT 0, ts TEXT
);
CREATE TABLE IF NOT EXISTS oracle_checks (
  id TEXT PRIMARY KEY, scope TEXT, vector_id TEXT, rule_id TEXT,
  inputs_json TEXT, expected_json TEXT,           -- oracle's blind computation (+ votes)
  actual_json TEXT, verdict TEXT,                 -- match | mismatch | oracle_uncertain
  votes_json TEXT, ts TEXT
);

-- 5. Platform ------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, name TEXT,                 -- 'A', 'B', 'C'...
  ip TEXT, status TEXT,                           -- provisioning|ready|draining|down
  gpus_json TEXT, seats_json TEXT,                -- current placements
  last_heartbeat TEXT, registered_at TEXT
);
CREATE TABLE IF NOT EXISTS meter_events (         -- 10 §1
  id TEXT PRIMARY KEY, ts TEXT, scope TEXT,
  seat TEXT, backend TEXT, model_id TEXT,
  kind TEXT,                                      -- llm_call | gpu_sample
  tokens_in INTEGER, tokens_out INTEGER,
  gpu_seconds REAL, cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_meter_scope ON meter_events(scope);
CREATE TABLE IF NOT EXISTS egress_log (
  id TEXT PRIMARY KEY, ts TEXT, scope TEXT,
  host TEXT, zone TEXT,                           -- LOCAL | AMD_HOSTED | EXTERNAL | CUSTOM
  seat TEXT, bytes_out INTEGER, bytes_in INTEGER,
  sovereign_violation INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_egress_scope ON egress_log(scope);
CREATE TABLE IF NOT EXISTS sandbox_sessions (
  id TEXT PRIMARY KEY, company TEXT, created_at TEXT,
  client_hash TEXT, runs_used INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS api_connections (      -- BYOK custom endpoints (D13, 02 §8)
  id TEXT PRIMARY KEY, name TEXT, base_url TEXT,
  api_key_ref TEXT,                               -- pointer to encrypted secret; NEVER the key
  zone TEXT NOT NULL DEFAULT 'CUSTOM',
  data_class_ceiling TEXT NOT NULL DEFAULT 'SANITIZED',  -- RAW only via boundary attestation
  counts_as_local INTEGER NOT NULL DEFAULT 0,     -- attested on-prem endpoint (sovereign-eligible)
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS custom_models (        -- many models per connection
  id TEXT PRIMARY KEY, connection_id TEXT REFERENCES api_connections(id),
  provider_model_id TEXT, display_name TEXT,
  flags_json TEXT,                                -- capability flags, same vocabulary (02 §7.2)
  context_len INTEGER, notes TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS seat_overrides (       -- user-configurable seat bindings (02 §8.2)
  id TEXT PRIMARY KEY, seat TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'global',           -- global | job:<id>
  model_key TEXT NOT NULL,                        -- models.yaml key or custom_models.id
  set_at TEXT, UNIQUE (seat, scope)
);

-- encrypted secret store for BYOK keys — api_key_ref points here; value is Fernet ciphertext
CREATE TABLE IF NOT EXISTS secrets (
  ref TEXT PRIMARY KEY, ciphertext TEXT NOT NULL, created_at TEXT
);

-- job/run-scoped scratch backing StageContext.checkpoint() for resumability (07 §1, §4).
-- Additive to spec 05 (change protocol; noted in 05 §2 revision).
CREATE TABLE IF NOT EXISTS checkpoints (
  scope TEXT, key TEXT, value_json TEXT, ts TEXT,
  PRIMARY KEY (scope, key)
);
