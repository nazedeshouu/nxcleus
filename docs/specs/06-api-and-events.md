# 06 — API & Event Catalog (the UI contract)

Locked 2026-07-07. This is the seam between backend and the (separately designed) frontend: the frontend session must be able to build against this doc alone. Base path `/api`. JSON everywhere. Errors: `{"error": {"code", "message", "detail?"}}` with proper HTTP status; `409` for state-machine violations (e.g. approving an unissued quote), `429` for guards/budgets.

## 1. Auth model (hackathon-grade, deliberate)

- **Public read:** all GET endpoints and SSE streams are unauthenticated — judges browse freely.
- **Sandbox writes:** anonymous session cookie (`sandbox_session`), rate limits per 09 §4.
- **Demo writes** (create job, approve quote, refine, toggle sovereign): require `X-Demo-Token` (env `ADMIN_TOKEN`) — presenter-only; the UI unlocks these controls when the token is stored.
- **Node/admin:** `X-Admin-Token` (same env var, distinct header semantics kept simple).

## 2. REST endpoints

### Jobs (build pipeline)
| Method | Path | Notes |
|---|---|---|
| POST | `/jobs` | `{title?, request, files?, repo?, db_schema?, policy_text?, sovereign?}` → `202 {job}`; starts stage 0. `repo` = archive upload or URL; `db_schema` = dump upload or connection ref (03 §2.2) |
| POST | `/jobs/{id}/policy` | add/extend the confidentiality policy: `{text}` \| multipart doc \| multipart audio (`kind=voice`, transcribed by local Whisper, O9) → updated RedactionPolicy summary (03 §2.1) |
| GET | `/jobs` · `/jobs/{id}` | list (filter `origin`, `status`) / detail incl. spec, **policy summary, goal**, current stage |
| POST | `/jobs/{id}/messages` | customer turn in the intake dialogue |
| POST | `/jobs/{id}/confirm-spec` | `{mode}` — confirms spec + mode → stage 1 |
| GET | `/jobs/{id}/plan` | current plan version + amendments (certifier + conductor) + consults |
| GET | `/jobs/{id}/quote` · POST `/jobs/{id}/approve-quote` | 🔒 demo token |
| POST | `/jobs/{id}/abort` | 🔒 |
| GET | `/jobs/{id}/events` | **SSE** — `?from_seq=N` replays then tails (see §3) |

### Processes, runs, refine (operate phase)
| Method | Path | Notes |
|---|---|---|
| GET | `/processes` · `/processes/{id}` | registry table / detail (versions, tickets, cost trend) |
| GET | `/processes/{id}/versions/{v}/diff` | human-readable diff payload (04 §5) |
| GET | `/processes/{id}/package/{v}/*` | serve package files (plan, docs, QA report) |
| POST | `/processes/{id}/runs` | `{version?, input_ref, kind:"batch"}` 🔒 → `202 {run}` |
| POST | `/processes/{id}/refine` | `{request}` 🔒 → creates refine job (lineage set) |
| POST | `/processes/{id}/instantiate` | `{connectors}` 🔒 → creates re-instantiation job |
| GET | `/runs/{id}` · `/runs/{id}/units` | detail / paginated units (`?status=needs_review`) |
| POST | `/units/{id}/review` | `{verdict, note}` 🔒 — semi-automated queue |
| GET | `/runs/{id}/events` | **SSE** |
| GET | `/tickets` | filter by scope/status/source |

### Platform & demo surfaces
| Method | Path | Notes |
|---|---|---|
| GET | `/fleet` | nodes + placements + profile |
| GET | `/fleet/telemetry` | **SSE** — `telemetry.gpu` events, all nodes |
| GET | `/egress?scope=&zone=` | ledger query (network monitor); `/egress/stream` **SSE** |
| POST | `/admin/sovereign` | `{enabled}` 🔒 — global toggle (the finale switch) |
| POST | `/admin/nodes/register` | node agent self-registration `{name, ip, gpus}` 🔒 |
| GET | `/models` | merged registry (builtin + custom) with capability flags — feeds the seat-config + routing UI |
| POST | `/connections` | 🔒 `{name, base_url, api_key, data_class_ceiling?, counts_as_local?}` — BYOK (02 §8); key write-only, returned masked |
| GET / DELETE | `/connections` · `/connections/{id}` | list (masked) / remove |
| POST | `/connections/{id}/models` | 🔒 `{provider_model_id, display_name, flags[], context_len}` — register + tag a model under the connection |
| PUT | `/seats/{seat}/binding` | 🔒 `{model_key, scope?}` — rebind a seat (global or `job:<id>`); `409` if zone/data-class ineligible (02 §8.2) |
| GET | `/economics/summary` | money-slide data: build cost vs per-run trend (10 §6) |
| GET | `/health` · `/config/public` | liveness; feature flags for the UI (sovereign state, fallback-serving badge, profile) |
| GET | `/replay/{scope}` | full ordered event dump for the replay player (09 §6) |

### Judge sandbox (09)
| Method | Path | Notes |
|---|---|---|
| GET | `/sandbox/companies` | the three companies + suggested prompts |
| GET | `/sandbox/companies/{id}/tables` · `/tables/{t}?page=` | browse mock data read-only |
| POST | `/sandbox/runs` | `{company, prompt}` → `202 {job, queue_position}` (guards → `429`) |
| GET | `/sandbox/queue` | live queue state |

## 3. Event catalog

Envelope (SSE `data:` payload, one per event; `id:` = `seq` so `Last-Event-ID` reconnects resume automatically):

```json
{"seq": 4211, "ts": "2026-07-09T14:02:11Z", "scope": "job:job_01J...", "type": "certify.amendment", "payload": {...}}
```

| Type | Payload core | Emitted |
|---|---|---|
| `job.created` / `job.stage_changed` / `job.blocked` / `job.done` / `job.aborted` | status, stage | lifecycle |
| `intake.message` | role, content | each dialogue turn |
| `intake.spec_updated` / `intake.classified` | spec, mode+rationale | stage 0 |
| `intake.policy_registered` | sources, rule count, baseline+policy split | policy intake (03 §2.1) |
| `intake.context_mapped` | files, symbols, tables, masked identifiers | codebase/DB intake (03 §2.2) |
| `boundary.sanitized` | sensitivity report (cites policy rule IDs) | stage 0 gate |
| `plan.started` / `plan.delta` / `plan.completed` | text delta / plan summary + **BoM** + topology archetype | stage 1, streamed |
| `certify.check_started` / `certify.finding` | check, finding | stage 2 |
| `certify.amendment` | amendment (+hash, origin) | the amendment-log ticker |
| `certify.consult_opened` / `certify.consult_resolved` | scope, round, sanitization receipt | escalations (03 §4.2) |
| `certify.goal_set` | goal text | stage 2 (D10) — pinned in Build view |
| `certify.certified` / `certify.blocked` | test/vector counts, identifiers rehydrated | stage 2 gate |
| `quote.issued` / `quote.approved` | itemized lines | stage 3 |
| `fleet.profile_requested` / `fleet.node_ready` / `fleet.node_down` | node, seats | provisioning (07 §5) |
| `task.started` / `task.output_delta` / `task.tests` / `task.completed` / `task.failed` | module, backend, wave, delta/results | stage 4 worker panels |
| `conductor.wave_started` / `conductor.review` / `conductor.amendment` / `conductor.green_flag` | wave n/of, verdict, goal_drift, amendment (+hash) | stage 4 wave rhythm (D8) |
| `consolidate.started` / `consolidate.test_run` / `consolidate.completed` | pass/fail counts | stage 5 + validation wall |
| `qa.inspector_started` / `qa.probe` / `qa.finding` | scenario, probe, result | stage 6 |
| `qa.goal_check` | verdict (fulfilled/partial), gaps | stage 6 final gate (D10) |
| `qa.oracle_check` | vector, verdict | oracle beats |
| `ticket.opened` / `ticket.in_fix` / `ticket.verified` / `ticket.human_review` | ticket | defect board |
| `qa.passed` | stats | stage 6 gate |
| `deliver.registered` | process id, package summary | stage 7 |
| `run.started` / `run.unit_completed` / `run.progress` / `run.spotcheck` / `run.completed` | unit result / counts / verdict / stats+cost | operate phase |
| `warranty.ticket` | ticket | continuous assurance |
| `refine.triaged` / `refine.version_created` | amend-vs-consult verdict / diff summary | refine beats |
| `review.decided` | unit, verdict | semi-automated queue |
| `model.call` | seat, backend, zone, tokens, cost | every router dispatch (BoM panel + cost meter) |
| `meter.tick` | scope totals | throttled 1/s during activity |
| `egress.request` | host, zone, seat | network monitor |
| `egress.violation` | detail | Sovereign red banner |
| `telemetry.gpu` | node, vram, util, power, tok/s | fleet panel, 2 s cadence |
| `sandbox.queued` / `sandbox.started` | position | sandbox UX |
| `config.connection_added` / `config.model_registered` / `config.seat_bound` | name+host (never key material), model+flags, seat+model_key+scope | BYOK + seat-config UI (02 §8) |
| `system.notice` | text, level | fallback-serving badge, budget warnings |

Rules: payloads are additive-only after the UI session starts building; token-level deltas (`plan.delta`, `task.output_delta`) are throttled to ≤10 events/s per scope with batched text; every SSE stream sends `: heartbeat` comments every 10 s.

## 4. Model-proxy (process-runtime → control plane)

`POST /proxy/complete` — body `{seat, messages, schema?}`, header `X-Process-Token` (minted per process at delivery; claims: process id, allowed seats from manifest BoM). Router enforces seat allowlist + data class + budgets exactly as internal calls; meter scope = the active run. This is the only network egress a process container has (01 §5).
