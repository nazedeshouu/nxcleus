/**
 * The UI state for a job IS a fold of its events (06 §3, 05 §1):
 *   reduce(events) -> JobView
 * The same fold serves live SSE, VITE_MOCK fixtures, and the replay player.
 * Every event type in the catalog has a case here (some minimal, flagged for wave 2).
 */
import type {
  NxEvent,
  Stage,
  JobStatus,
  DeliveryMode,
  TopologyArchetype,
  BomLine,
  SensitivityFinding,
  QuoteLine,
  TelemetryGpuPayload,
  TicketStatus,
  TicketSeverity,
} from "../lib/events";

export interface ChatTurn {
  role: "customer" | "system" | "trust";
  content: string;
}
export interface AmendmentEntry {
  id: string;
  origin: "certifier" | "conductor";
  summary: string;
  hash: string;
  prev_hash: string;
  region?: string;
  seq: number;
}
export interface ConsultEntry {
  id: string;
  scope: string;
  round: number;
  rules_applied: string[];
  brief_tokens: number;
  resolution?: string;
  seq: number;
}
export interface CheckEntry {
  check: string;
  status: "running" | "finding" | "done";
  finding?: string;
  severity?: "minor" | "structural";
}
export interface TaskState {
  module: string;
  backend: string;
  seat: string;
  zone: string;
  wave: number;
  why: string;
  output: string;
  tests?: { passed: number; failed: number };
  status: "running" | "completed" | "failed";
  loc?: number;
  reason?: string;
}
export interface WaveState {
  wave: number;
  of: number;
  modules: string[];
  status: "running" | "reviewing" | "green";
  verdict?: "green" | "amend" | "hold";
  goal_drift?: number | null;
  note?: string;
}
export interface TicketState {
  id: string;
  title: string;
  status: TicketStatus;
  severity: TicketSeverity;
  source: string;
  scope?: string;
}
export interface EgressEntry {
  seq: number;
  host: string;
  zone: string;
  seat?: string;
  data_class?: string;
  bytes?: number;
  violation?: boolean;
  detail?: string;
}
export interface NoticeEntry {
  seq: number;
  text: string;
  level: "info" | "warn" | "error";
}

export interface JobView {
  scope: string;
  title?: string;
  status: JobStatus;
  stage: Stage;
  mode?: DeliveryMode;
  blockedReason?: string;

  intake: {
    messages: ChatTurn[];
    specSummary?: string;
    acceptance: string[];
    classification?: { mode: DeliveryMode; rationale: string };
    policy?: {
      sources: string[];
      rule_count: number;
      baseline: number;
      policy: number;
      summary?: string;
    };
    context?: { files: number; symbols: number; tables: number; masked: number };
    boundary?: {
      findings: SensitivityFinding[];
      never_leaves: string[];
      brief_tokens: number;
    };
  };

  plan: {
    plannerModel?: string;
    plannerZone?: string;
    deltaText: string;
    summary?: string;
    topology?: TopologyArchetype;
    modules?: number;
    bom: BomLine[];
    streaming: boolean;
  };

  certify: {
    checks: CheckEntry[];
    amendments: AmendmentEntry[];
    consults: ConsultEntry[];
    goal?: string;
    certified?: { tests: number; vectors: number; identifiers_rehydrated: number };
  };

  quote: { lines: QuoteLine[]; low?: number; high?: number; approved?: number };

  fleet: { profile?: string; nodesRequested?: number; nodes: Record<string, { gpus: number; up: boolean }> };

  build: { waves: Record<number, WaveState>; tasks: Record<string, TaskState>; taskWave: Record<string, number> };

  consolidate: { modules?: number; testRuns: Array<{ passed: number; failed: number; total: number }>; completed?: { passed: number; total: number } };

  qa: {
    inspectors: Array<{ scenario: string; seat: string }>;
    probes: Array<{ scenario: string; probe: string }>;
    findings: Array<{ scenario: string; result: "clear" | "flag"; detail?: string }>;
    oracleChecks: Array<{ vector: string; verdict: "match" | "mismatch"; model: string }>;
    goalCheck?: { verdict: "fulfilled" | "partial" | "failed"; gaps: string[] };
    passed?: { scenarios: number; probes: number; tickets_resolved: number };
  };

  tickets: Record<string, TicketState>;

  delivery?: { process_id: string; version: number; package: { plan: boolean; docs: boolean; qa_report: boolean; tests: number } };

  cost: { cost_usd: number; tokens: number; gpu_seconds: number };
  modelCalls: Array<{ seq: number; seat: string; backend: string; zone: string; data_class: string; cost_usd: number; tokens: number }>;

  egress: EgressEntry[];
  violation?: EgressEntry;

  telemetry: Record<string, TelemetryGpuPayload>; // key: `${node}#${gpu}`

  notices: NoticeEntry[];

  // wave-2 surfaces, folded minimally so nothing is a total no-op
  runs: Record<string, { units: number; done: number; flagged: number; cost_usd?: number; gpu_seconds?: number; status: string }>;
  refine?: { verdict?: "amend" | "consult"; note?: string; version?: number; diff_summary?: string };
  sandbox?: { position: number; started: boolean };
  config: { connections: string[]; models: string[]; seatBindings: Array<{ seat: string; model_key: string; scope: string }> };

  lastSeq: number;
  seenSeqs: Set<number>;
}

export function initialJobView(scope = ""): JobView {
  return {
    scope,
    status: "created",
    stage: 0,
    intake: { messages: [], acceptance: [] },
    plan: { deltaText: "", bom: [], streaming: false },
    certify: { checks: [], amendments: [], consults: [] },
    quote: { lines: [] },
    fleet: { nodes: {} },
    build: { waves: {}, tasks: {}, taskWave: {} },
    consolidate: { testRuns: [] },
    qa: { inspectors: [], probes: [], findings: [], oracleChecks: [] },
    tickets: {},
    cost: { cost_usd: 0, tokens: 0, gpu_seconds: 0 },
    modelCalls: [],
    egress: [],
    telemetry: {},
    notices: [],
    runs: {},
    config: { connections: [], models: [], seatBindings: [] },
    lastSeq: 0,
    seenSeqs: new Set(),
  };
}

const MAX_EGRESS = 40;
const MAX_CALLS = 30;

/** Fold one event into a fresh view reference (so React re-renders). */
export function foldEvent(prev: JobView, ev: NxEvent): JobView {
  if (prev.seenSeqs.has(ev.seq)) return prev; // idempotent replay/reconnect
  const v: JobView = { ...prev, seenSeqs: new Set(prev.seenSeqs).add(ev.seq) };
  v.lastSeq = Math.max(prev.lastSeq, ev.seq);

  switch (ev.type) {
    case "job.created":
    case "job.stage_changed":
    case "job.done": {
      v.status = ev.payload.status;
      v.stage = ev.payload.stage;
      if (ev.payload.title) v.title = ev.payload.title;
      if (ev.payload.mode) v.mode = ev.payload.mode;
      break;
    }
    case "job.blocked": {
      v.status = ev.payload.status;
      v.stage = ev.payload.stage;
      v.blockedReason = ev.payload.reason;
      break;
    }
    case "job.aborted": {
      v.status = "aborted";
      v.blockedReason = ev.payload.reason;
      break;
    }

    /* stage 0 */
    case "intake.message":
      v.intake = { ...v.intake, messages: [...v.intake.messages, { role: ev.payload.role, content: ev.payload.content }] };
      break;
    case "intake.spec_updated":
      v.intake = { ...v.intake, specSummary: ev.payload.spec.summary, acceptance: ev.payload.spec.acceptance ?? v.intake.acceptance };
      break;
    case "intake.classified":
      v.intake = { ...v.intake, classification: { mode: ev.payload.mode, rationale: ev.payload.rationale } };
      v.mode = ev.payload.mode;
      break;
    case "intake.policy_registered":
      v.intake = { ...v.intake, policy: { sources: ev.payload.sources, rule_count: ev.payload.rule_count, baseline: ev.payload.split.baseline, policy: ev.payload.split.policy, summary: ev.payload.summary } };
      break;
    case "intake.context_mapped":
      v.intake = { ...v.intake, context: { files: ev.payload.files, symbols: ev.payload.symbols, tables: ev.payload.tables, masked: ev.payload.masked_identifiers } };
      break;
    case "boundary.sanitized":
      v.intake = { ...v.intake, boundary: { findings: ev.payload.findings, never_leaves: ev.payload.never_leaves, brief_tokens: ev.payload.brief_tokens } };
      break;

    /* stage 1 */
    case "plan.started":
      v.plan = { ...v.plan, plannerModel: ev.payload.planner_model, plannerZone: ev.payload.zone, streaming: true, deltaText: "" };
      break;
    case "plan.delta":
      v.plan = { ...v.plan, deltaText: v.plan.deltaText + ev.payload.text };
      break;
    case "plan.completed":
      v.plan = { ...v.plan, summary: ev.payload.summary, topology: ev.payload.topology, modules: ev.payload.modules, bom: ev.payload.bom, streaming: false };
      break;

    /* stage 2 */
    case "certify.check_started":
      v.certify = { ...v.certify, checks: [...v.certify.checks, { check: ev.payload.check, status: "running" }] };
      break;
    case "certify.finding":
      v.certify = { ...v.certify, checks: v.certify.checks.map((c) => (c.check === ev.payload.check ? { ...c, status: "finding", finding: ev.payload.finding, severity: ev.payload.severity } : c)) };
      break;
    case "certify.amendment":
    case "conductor.amendment": {
      // reconstruct the hash chain in display order when the backend omits prev_hash
      const last = v.certify.amendments[v.certify.amendments.length - 1];
      const prev_hash = ev.payload.prev_hash || last?.hash || "genesis";
      v.certify = { ...v.certify, amendments: [...v.certify.amendments, { id: ev.payload.id, origin: ev.payload.origin, summary: ev.payload.summary, hash: ev.payload.hash, prev_hash, region: ev.payload.region, seq: ev.seq }] };
      break;
    }
    case "certify.consult_opened":
      v.certify = { ...v.certify, consults: [...v.certify.consults, { id: ev.payload.id, scope: ev.payload.scope, round: ev.payload.round, rules_applied: ev.payload.sanitization_receipt.rules_applied, brief_tokens: ev.payload.sanitization_receipt.brief_tokens, seq: ev.seq }] };
      break;
    case "certify.consult_resolved":
      v.certify = { ...v.certify, consults: v.certify.consults.map((c) => (c.id === ev.payload.id ? { ...c, resolution: ev.payload.resolution } : c)) };
      break;
    case "certify.goal_set":
      v.certify = { ...v.certify, goal: ev.payload.goal };
      break;
    case "certify.certified":
      v.certify = { ...v.certify, certified: { tests: ev.payload.tests, vectors: ev.payload.vectors, identifiers_rehydrated: ev.payload.identifiers_rehydrated }, checks: v.certify.checks.map((c) => ({ ...c, status: "done" })) };
      break;
    case "certify.blocked":
      v.blockedReason = ev.payload.reason;
      break;

    /* stage 3 */
    case "quote.issued":
      v.quote = { ...v.quote, lines: ev.payload.lines, low: ev.payload.low_usd, high: ev.payload.high_usd };
      break;
    case "quote.approved":
      v.quote = { ...v.quote, approved: ev.payload.approved_usd };
      break;

    /* fleet */
    case "fleet.profile_requested":
      v.fleet = { ...v.fleet, profile: ev.payload.profile, nodesRequested: ev.payload.nodes };
      break;
    case "fleet.node_ready":
      v.fleet = { ...v.fleet, nodes: { ...v.fleet.nodes, [ev.payload.node]: { gpus: ev.payload.gpus, up: true } } };
      break;
    case "fleet.node_down":
      v.fleet = { ...v.fleet, nodes: { ...v.fleet.nodes, [ev.payload.node]: { gpus: ev.payload.gpus, up: false } } };
      break;

    /* stage 4 */
    case "task.started": {
      // resolve wave membership: the backend carries it in conductor.wave_started.tasks
      const waveKeys = Object.keys(v.build.waves).map(Number);
      const resolvedWave =
        (ev.payload.task ? v.build.taskWave[ev.payload.task] : undefined) ??
        (ev.payload.wave || (waveKeys.length ? Math.max(...waveKeys) : 1));
      v.build = { ...v.build, tasks: { ...v.build.tasks, [ev.payload.module]: { module: ev.payload.module, backend: ev.payload.backend, seat: ev.payload.seat, zone: ev.payload.zone, wave: resolvedWave, why: ev.payload.why, output: "", status: "running" } } };
      break;
    }
    case "task.output_delta": {
      const t = v.build.tasks[ev.payload.module];
      if (t) v.build = { ...v.build, tasks: { ...v.build.tasks, [ev.payload.module]: { ...t, output: t.output + ev.payload.text } } };
      break;
    }
    case "task.tests": {
      const t = v.build.tasks[ev.payload.module];
      if (t) v.build = { ...v.build, tasks: { ...v.build.tasks, [ev.payload.module]: { ...t, tests: { passed: ev.payload.passed, failed: ev.payload.failed } } } };
      break;
    }
    case "task.completed": {
      const t = v.build.tasks[ev.payload.module];
      if (t) v.build = { ...v.build, tasks: { ...v.build.tasks, [ev.payload.module]: { ...t, status: "completed", loc: ev.payload.loc } } };
      break;
    }
    case "task.failed": {
      const t = v.build.tasks[ev.payload.module];
      if (t) v.build = { ...v.build, tasks: { ...v.build.tasks, [ev.payload.module]: { ...t, status: "failed", reason: ev.payload.reason } } };
      break;
    }
    case "conductor.wave_started": {
      const taskWave = { ...v.build.taskWave };
      for (const tid of ev.payload.tasks ?? []) taskWave[tid] = ev.payload.wave;
      v.build = { ...v.build, taskWave, waves: { ...v.build.waves, [ev.payload.wave]: { wave: ev.payload.wave, of: ev.payload.of, modules: ev.payload.modules, status: "running" } } };
      break;
    }
    case "conductor.review": {
      const w = v.build.waves[ev.payload.wave];
      v.build = { ...v.build, waves: { ...v.build.waves, [ev.payload.wave]: { ...(w ?? { wave: ev.payload.wave, of: 0, modules: [] }), status: "reviewing", verdict: ev.payload.verdict, goal_drift: ev.payload.goal_drift, note: ev.payload.note } } };
      break;
    }
    case "conductor.green_flag": {
      const w = v.build.waves[ev.payload.wave];
      if (w) v.build = { ...v.build, waves: { ...v.build.waves, [ev.payload.wave]: { ...w, status: "green" } } };
      break;
    }

    /* stage 5 */
    case "consolidate.started":
      v.consolidate = { ...v.consolidate, modules: ev.payload.modules };
      break;
    case "consolidate.test_run":
      v.consolidate = { ...v.consolidate, testRuns: [...v.consolidate.testRuns, { passed: ev.payload.passed, failed: ev.payload.failed, total: ev.payload.total }] };
      break;
    case "consolidate.completed":
      v.consolidate = { ...v.consolidate, completed: { passed: ev.payload.passed, total: ev.payload.total } };
      break;

    /* stage 6 */
    case "qa.inspector_started":
      v.qa = { ...v.qa, inspectors: [...v.qa.inspectors, { scenario: ev.payload.scenario, seat: ev.payload.seat }] };
      break;
    case "qa.probe":
      v.qa = { ...v.qa, probes: [...v.qa.probes, { scenario: ev.payload.scenario, probe: ev.payload.probe }] };
      break;
    case "qa.finding":
      v.qa = { ...v.qa, findings: [...v.qa.findings, { scenario: ev.payload.scenario, result: ev.payload.result, detail: ev.payload.detail }] };
      break;
    case "qa.oracle_check":
      v.qa = { ...v.qa, oracleChecks: [...v.qa.oracleChecks, { vector: ev.payload.vector, verdict: ev.payload.verdict, model: ev.payload.model }] };
      break;
    case "qa.goal_check":
      v.qa = { ...v.qa, goalCheck: { verdict: ev.payload.verdict, gaps: ev.payload.gaps } };
      break;
    case "qa.passed":
      v.qa = { ...v.qa, passed: { scenarios: ev.payload.scenarios, probes: ev.payload.probes, tickets_resolved: ev.payload.tickets_resolved } };
      break;

    /* tickets */
    case "ticket.opened":
    case "warranty.ticket":
      v.tickets = { ...v.tickets, [ev.payload.id]: { id: ev.payload.id, title: ev.payload.title, status: ev.payload.status, severity: ev.payload.severity, source: ev.payload.source, scope: ev.payload.scope } };
      break;
    case "ticket.in_fix":
    case "ticket.verified":
    case "ticket.human_review": {
      // status transition: keep the ticket's opened metadata, only advance status
      const ex = v.tickets[ev.payload.id];
      v.tickets = { ...v.tickets, [ev.payload.id]: { ...(ex ?? { id: ev.payload.id, title: ev.payload.title, severity: ev.payload.severity, source: ev.payload.source, scope: ev.payload.scope }), status: ev.payload.status } };
      break;
    }

    /* stage 7 + operate */
    case "deliver.registered": {
      const tests = ev.payload.package.tests || v.certify.certified?.tests || v.consolidate.completed?.total || 0;
      v.delivery = { process_id: ev.payload.process_id, version: ev.payload.version, package: { ...ev.payload.package, tests } };
      v.status = "delivered";
      v.stage = 7;
      break;
    }
    case "run.started":
      v.runs = { ...v.runs, [ev.payload.run_id]: { units: ev.payload.units, done: 0, flagged: 0, status: "running" } };
      break;
    case "run.progress": {
      const anyKey = Object.keys(v.runs)[Object.keys(v.runs).length - 1];
      if (anyKey) v.runs = { ...v.runs, [anyKey]: { ...v.runs[anyKey], done: ev.payload.done } };
      break;
    }
    case "run.unit_completed":
      break; // wave-2 unit table; folded via run.progress for the meter
    case "run.spotcheck":
      break; // wave-2 warranty strip
    case "run.completed": {
      const anyKey = Object.keys(v.runs)[Object.keys(v.runs).length - 1];
      if (anyKey) v.runs = { ...v.runs, [anyKey]: { ...v.runs[anyKey], done: ev.payload.units, flagged: ev.payload.flagged, cost_usd: ev.payload.cost_usd, gpu_seconds: ev.payload.gpu_seconds, status: "done" } };
      break;
    }
    case "refine.triaged":
      v.refine = { ...v.refine, verdict: ev.payload.verdict, note: ev.payload.note };
      break;
    case "refine.version_created":
      v.refine = { ...v.refine, version: ev.payload.version, diff_summary: ev.payload.diff_summary };
      break;
    case "review.decided":
      break; // wave-2 semi-automated queue

    /* router / meter / egress / telemetry */
    case "model.call":
      v.modelCalls = [{ seq: ev.seq, seat: ev.payload.seat, backend: ev.payload.backend, zone: ev.payload.zone, data_class: ev.payload.data_class, cost_usd: ev.payload.cost_usd, tokens: ev.payload.tokens_in + ev.payload.tokens_out }, ...v.modelCalls].slice(0, MAX_CALLS);
      break;
    case "meter.tick":
      v.cost = { cost_usd: ev.payload.cost_usd, tokens: ev.payload.tokens, gpu_seconds: ev.payload.gpu_seconds };
      break;
    case "egress.request":
      v.egress = [{ seq: ev.seq, host: ev.payload.host, zone: ev.payload.zone, seat: ev.payload.seat, data_class: ev.payload.data_class, bytes: ev.payload.bytes }, ...v.egress].slice(0, MAX_EGRESS);
      break;
    case "egress.violation": {
      const entry: EgressEntry = { seq: ev.seq, host: ev.payload.host, zone: ev.payload.zone, violation: true, detail: ev.payload.detail };
      v.violation = entry;
      v.egress = [entry, ...v.egress].slice(0, MAX_EGRESS);
      break;
    }
    case "telemetry.gpu":
      v.telemetry = { ...v.telemetry, [`${ev.payload.node}#${ev.payload.gpu}`]: ev.payload };
      break;

    /* sandbox / config / notices */
    case "sandbox.queued":
      v.sandbox = { position: ev.payload.position, started: false };
      break;
    case "sandbox.started":
      v.sandbox = { position: ev.payload.position, started: true };
      break;
    case "config.connection_added":
      v.config = { ...v.config, connections: [...v.config.connections, ev.payload.name] };
      break;
    case "config.model_registered":
      v.config = { ...v.config, models: [...v.config.models, ev.payload.model] };
      break;
    case "config.seat_bound":
      v.config = { ...v.config, seatBindings: [...v.config.seatBindings, { seat: ev.payload.seat, model_key: ev.payload.model_key, scope: ev.payload.scope }] };
      break;
    case "system.notice":
      v.notices = [...v.notices, { seq: ev.seq, text: ev.payload.text, level: ev.payload.level }].slice(-8);
      break;

    default: {
      // exhaustiveness guard: if a new event type is added to the catalog,
      // TypeScript errors here until it gets a fold case.
      const _never: never = ev;
      return _never;
    }
  }
  return v;
}

export function foldEvents(events: NxEvent[], scope = ""): JobView {
  return events.reduce(foldEvent, initialJobView(scope));
}
