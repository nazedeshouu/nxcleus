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
  ClarifyQuestion,
  RunArtifact,
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
  repaired?: boolean; // scope-lock was auto-repaired to a valid region
  requested?: boolean; // consult_requested seen, not yet opened (still sanitizing)
  reason?: string;
  seq: number;
}
export interface ProbeEntry {
  scenario: string;
  probe: string;
  status: "started" | "passed" | "timeout" | "exhausted";
  detail?: string;
  seq: number;
}
export interface ScopeViolationEntry {
  region?: string;
  detail?: string;
  wave?: number;
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
    replans: Array<{ note?: string; wave?: number; seq: number }>;
  };

  certify: {
    checks: CheckEntry[];
    amendments: AmendmentEntry[];
    consults: ConsultEntry[];
    goal?: string;
    certified?: { tests: number; vectors: number; identifiers_rehydrated: number };
    deferredConsults?: number;
    scopeViolations: ScopeViolationEntry[];
    scenariosEmitted?: number;
    rehydrated?: number;
  };

  quote: { lines: QuoteLine[]; low?: number; high?: number; approved?: number };

  fleet: { profile?: string; nodesRequested?: number; nodes: Record<string, { gpus: number; up: boolean }> };

  build: { waves: Record<number, WaveState>; tasks: Record<string, TaskState>; taskWave: Record<string, number> };

  consolidate: { modules?: number; testRuns: Array<{ passed: number; failed: number; total: number }>; completed?: { passed: number; total: number } };

  qa: {
    inspectors: Array<{ scenario: string; seat: string }>;
    probes: Array<{ scenario: string; probe: string }>;
    probeBoard: Record<string, ProbeEntry>; // key `${scenario}#${probe}` — live probe status
    findings: Array<{ scenario: string; result: "clear" | "flag"; detail?: string }>;
    oracleChecks: Array<{ vector: string; verdict: "match" | "mismatch"; model: string }>;
    votes: Array<{ vector: string; vote: string }>;
    goalCheck?: { verdict: "fulfilled" | "partial" | "failed"; gaps: string[] };
    passed?: { scenarios: number; probes: number; tickets_resolved: number };
  };

  fixes: Array<{ module: string; note?: string; seq: number }>;

  tickets: Record<string, TicketState>;

  delivery?: { process_id: string; version: number; package: { plan: boolean; docs: boolean; qa_report: boolean; tests: number } };
  deliveryDocs?: string[];

  boundarySweep?: { seq: number; clean: boolean; checked?: number; findings?: number };
  clarifications?: { questions: ClarifyQuestion[]; answered: boolean };
  runArtifacts?: RunArtifact[];
  traceCount: number;
  /** runtime-commissioned python tools (F7): created names + invocation count */
  tools: { created: Array<{ name: string; agent?: string }>; invocations: number };
  /** the "now" strip: one always-fresh line derived from the latest meaningful event */
  now?: { seq: number; text: string };

  cost: { cost_usd: number; tokens: number; gpu_seconds: number };
  modelCalls: Array<{ seq: number; seat: string; backend: string; zone: string; data_class: string; cost_usd: number; tokens: number }>;
  /** honesty counter: model calls that fell through to a simulated (mock) backend this run */
  mockDispatches: number;

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
    plan: { deltaText: "", bom: [], streaming: false, replans: [] },
    certify: { checks: [], amendments: [], consults: [], scopeViolations: [] },
    quote: { lines: [] },
    fleet: { nodes: {} },
    build: { waves: {}, tasks: {}, taskWave: {} },
    consolidate: { testRuns: [] },
    qa: { inspectors: [], probes: [], probeBoard: {}, findings: [], oracleChecks: [], votes: [] },
    fixes: [],
    tickets: {},
    traceCount: 0,
    tools: { created: [], invocations: 0 },
    cost: { cost_usd: 0, tokens: 0, gpu_seconds: 0 },
    modelCalls: [],
    mockDispatches: 0,
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
    case "boundary.sweep":
      v.boundarySweep = { seq: ev.seq, clean: ev.payload.clean, checked: ev.payload.checked, findings: ev.payload.findings };
      break;
    case "intake.clarification_requested":
      v.clarifications = { questions: ev.payload.questions, answered: false };
      if (v.stage === 0) v.status = "awaiting_input";
      break;
    case "intake.clarification_answered":
      if (v.clarifications) v.clarifications = { ...v.clarifications, answered: true };
      if (v.status === "awaiting_input") v.status = "intake";
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
    case "plan.replanned":
      v.plan = { ...v.plan, replans: [...v.plan.replans, { note: ev.payload.note, wave: ev.payload.wave, seq: ev.seq }] };
      break;

    /* stage 2 */
    case "certify.check_started":
      v.certify = { ...v.certify, checks: [...v.certify.checks, { check: ev.payload.check, status: "running" }] };
      break;
    case "certify.check_completed": {
      // upsert: sql-step validations can complete without a check_started
      const known = v.certify.checks.some((c) => c.check === ev.payload.check);
      v.certify = {
        ...v.certify,
        checks: known
          ? v.certify.checks.map((c) => (c.check === ev.payload.check && c.status === "running" ? { ...c, status: "done" } : c))
          : [...v.certify.checks, { check: ev.payload.check, status: "done" }],
      };
      break;
    }
    case "certify.scenarios_emitted":
      v.certify = { ...v.certify, scenariosEmitted: ev.payload.count };
      break;
    case "certify.rehydrated":
      v.certify = { ...v.certify, rehydrated: ev.payload.identifiers };
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
    case "certify.consult_requested": {
      // pre-open beat: shows as "requested · sanitizing" until consult_opened lands
      if (v.certify.consults.some((c) => c.id === ev.payload.id)) break;
      const entry: ConsultEntry = { id: ev.payload.id, scope: ev.payload.scope ?? "", round: 0, rules_applied: [], brief_tokens: 0, requested: true, reason: ev.payload.reason, seq: ev.seq };
      v.certify = { ...v.certify, consults: [...v.certify.consults, entry] };
      break;
    }
    case "certify.consult_opened": {
      const opened: ConsultEntry = { id: ev.payload.id, scope: ev.payload.scope, round: ev.payload.round, rules_applied: ev.payload.sanitization_receipt.rules_applied, brief_tokens: ev.payload.sanitization_receipt.brief_tokens, seq: ev.seq };
      const exists = v.certify.consults.some((c) => c.id === ev.payload.id);
      v.certify = {
        ...v.certify,
        consults: exists
          ? v.certify.consults.map((c) => (c.id === ev.payload.id ? { ...c, ...opened, requested: false, seq: c.seq } : c))
          : [...v.certify.consults, opened],
      };
      break;
    }
    case "certify.consult_resolved":
      v.certify = { ...v.certify, consults: v.certify.consults.map((c) => (c.id === ev.payload.id ? { ...c, resolution: ev.payload.resolution } : c)) };
      break;
    case "certify.consult_repaired":
      v.certify = { ...v.certify, consults: v.certify.consults.map((c) => (c.id === ev.payload.id ? { ...c, repaired: true } : c)) };
      break;
    case "plan.scope_violation":
      v.certify = { ...v.certify, scopeViolations: [...v.certify.scopeViolations, { region: ev.payload.region, detail: ev.payload.detail, wave: ev.payload.wave, seq: ev.seq }] };
      break;
    case "certify.goal_set":
      v.certify = { ...v.certify, goal: ev.payload.goal };
      break;
    case "certify.certified":
      v.certify = { ...v.certify, certified: { tests: ev.payload.tests, vectors: ev.payload.vectors, identifiers_rehydrated: ev.payload.identifiers_rehydrated }, deferredConsults: ev.payload.deferred_consults ?? v.certify.deferredConsults, checks: v.certify.checks.map((c) => ({ ...c, status: "done" })) };
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
    case "conductor.goal_drift": {
      const waveKeys = Object.keys(v.build.waves).map(Number);
      const wn = ev.payload.wave ?? (waveKeys.length ? Math.max(...waveKeys) : 1);
      const w = v.build.waves[wn] ?? { wave: wn, of: 0, modules: [], status: "running" as const };
      v.build = { ...v.build, waves: { ...v.build.waves, [wn]: { ...w, goal_drift: ev.payload.drift, note: ev.payload.note ?? w.note } } };
      break;
    }
    case "task.fix_applied":
      v.fixes = [...v.fixes, { module: ev.payload.module, note: ev.payload.note, seq: ev.seq }];
      break;
    case "task.files_written":
      break; // narrated by the "now" strip; the worker card shows tests/LOC from task.completed

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
    case "qa.probe_update": {
      const key = `${ev.payload.scenario}#${ev.payload.probe}`;
      v.qa = { ...v.qa, probeBoard: { ...v.qa.probeBoard, [key]: { scenario: ev.payload.scenario, probe: ev.payload.probe, status: ev.payload.status, detail: ev.payload.detail, seq: ev.seq } } };
      break;
    }
    case "qa.oracle_vote":
      v.qa = { ...v.qa, votes: [...v.qa.votes, { vector: ev.payload.vector, vote: ev.payload.vote }] };
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
    case "ticket.fix_applied":
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
    case "deliver.docs_generated":
      v.deliveryDocs = ev.payload.docs;
      break;
    case "run.started":
      v.runs = { ...v.runs, [ev.payload.run_id]: { units: ev.payload.units, done: 0, flagged: 0, status: "running" } };
      break;
    case "run.artifacts_ready":
      v.runArtifacts = ev.payload.artifacts;
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
      if (ev.payload.badge === "mock") v.mockDispatches = v.mockDispatches + 1;
      break;
    case "model.trace":
      v.traceCount = v.traceCount + 1; // full traces live in the /traces inspector
      break;
    case "run.sql_step":
      break; // narrated by the "now" strip
    case "tool.created":
      v.tools = { ...v.tools, created: [...v.tools.created, { name: ev.payload.name, agent: ev.payload.agent }] };
      break;
    case "tool.invoked":
      v.tools = { ...v.tools, invocations: v.tools.invocations + 1 };
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
  const line = nowText(ev);
  if (line) v.now = { seq: ev.seq, text: line };
  return v;
}

const shortBackend = (b: string) => b.replace(/^local:[A-Z]\//, "").replace(/^anthropic:/, "");

/** One human line per meaningful event — feeds the mission-control "now" strip. */
function nowText(ev: NxEvent): string | null {
  switch (ev.type) {
    case "intake.message":
      return ev.payload.role === "trust" ? "intake: the trust seat is talking to the customer" : null;
    case "intake.classified":
      return `intake: classified as ${ev.payload.mode} mode`;
    case "intake.clarification_requested":
      return `intake: ${ev.payload.questions.length} question${ev.payload.questions.length === 1 ? "" : "s"} for you — parked until you answer`;
    case "intake.clarification_answered":
      return "intake: answers received, resuming";
    case "intake.policy_registered":
      return `intake: ${ev.payload.rule_count} policy rules registered`;
    case "intake.context_mapped":
      return `intake: mapped ${ev.payload.tables} tables, masked ${ev.payload.masked_identifiers} identifiers`;
    case "boundary.sanitized":
      return `boundary: brief sanitized — ${ev.payload.brief_tokens} tokens may cross`;
    case "boundary.sweep":
      return ev.payload.clean ? "boundary: sweep clean" : `boundary: sweep found ${ev.payload.findings} issue${ev.payload.findings === 1 ? "" : "s"}`;
    case "plan.started":
      return `planner: drafting on ${shortBackend(ev.payload.planner_model)}`;
    case "plan.completed":
      return `planner: ${ev.payload.modules} modules, ${ev.payload.topology} topology`;
    case "plan.replanned":
      return ev.payload.note ? `planner: revised — ${ev.payload.note}` : "planner: plan revised after review";
    case "certify.check_started":
      return `certifier: running ${ev.payload.check}`;
    case "certify.check_completed":
      return `certifier: ${ev.payload.check} complete`;
    case "certify.finding":
      return `certifier: ${ev.payload.severity} finding in ${ev.payload.check}`;
    case "certify.consult_requested":
      return "certifier: consult requested — sanitizing the brief";
    case "certify.consult_opened":
      return `certifier: consult ${ev.payload.round} sanitized → planner`;
    case "certify.consult_resolved":
      return `certifier: consult ${ev.payload.round} resolved`;
    case "certify.scenarios_emitted":
      return `certifier: ${ev.payload.count} adversarial scenarios emitted`;
    case "certify.rehydrated":
      return `certifier: ${ev.payload.identifiers} identifiers rehydrated inside the walls`;
    case "certify.certified":
      return `certified — ${ev.payload.tests} tests, ${ev.payload.vectors} oracle vectors`;
    case "quote.issued":
      return "quote issued — awaiting approval";
    case "quote.approved":
      return "quote approved, provisioning the fleet";
    case "fleet.node_ready":
      return `fleet: node ${ev.payload.node} up with ${ev.payload.gpus} GPUs`;
    case "conductor.wave_started":
      return `wave ${ev.payload.wave}/${ev.payload.of}: ${ev.payload.modules.length} modules dispatched`;
    case "task.started":
      return `wave ${ev.payload.wave}: building ${ev.payload.module} on ${shortBackend(ev.payload.backend)}`;
    case "task.tests":
      return `${ev.payload.module}: ${ev.payload.passed} tests passing${ev.payload.failed ? `, ${ev.payload.failed} failing` : ""}`;
    case "task.completed":
      return `${ev.payload.module} complete`;
    case "task.failed":
      return `${ev.payload.module} failed — conductor stepping in`;
    case "task.fix_applied":
      return `fix applied to ${ev.payload.module}`;
    case "task.files_written":
      return `${ev.payload.module}: ${ev.payload.files} files written`;
    case "conductor.review":
      return `conductor: reviewing wave ${ev.payload.wave}`;
    case "conductor.green_flag":
      return `conductor: wave ${ev.payload.wave} green-flagged`;
    case "conductor.goal_drift":
      return ev.payload.drift != null ? `conductor: goal drift ${(ev.payload.drift * 100).toFixed(0)}%` : "conductor: checking against the original goal";
    case "consolidate.started":
      return `consolidating ${ev.payload.modules} modules`;
    case "consolidate.test_run":
      return `validation wall: ${ev.payload.passed}/${ev.payload.total} tests passing`;
    case "qa.inspector_started":
      return `QA: ${ev.payload.scenario}`;
    case "qa.probe":
      return `QA: probing ${ev.payload.scenario}`;
    case "qa.probe_update":
      return ev.payload.status === "started"
        ? `QA: probing ${ev.payload.probe}`
        : `QA: probe ${ev.payload.status} — ${ev.payload.probe}`;
    case "qa.finding":
      return ev.payload.result === "flag" ? `QA: flagged ${ev.payload.scenario}` : `QA: ${ev.payload.scenario} clear`;
    case "qa.oracle_check":
      return `oracle: ${ev.payload.vector} ${ev.payload.verdict}`;
    case "qa.oracle_vote":
      return `oracle: vote on ${ev.payload.vector} — ${ev.payload.vote}`;
    case "qa.passed":
      return `QA passed — ${ev.payload.probes} probes across ${ev.payload.scenarios} scenarios`;
    case "ticket.opened":
      return `ticket opened: ${ev.payload.title}`;
    case "ticket.fix_applied":
      return `fix applied: ${ev.payload.title} (retest pending)`;
    case "ticket.verified":
      return `ticket verified: ${ev.payload.title}`;
    case "deliver.docs_generated":
      return "delivery: docs generated";
    case "deliver.registered":
      return "delivered to the operations registry";
    case "run.progress":
      return `run: ${ev.payload.done}/${ev.payload.total} units processed`;
    case "run.artifacts_ready":
      return "run: deliverables ready — report and CSV";
    case "run.sql_step":
      return `sql step: ${ev.payload.label} — ${ev.payload.rows.toLocaleString()} candidates`;
    case "tool.created":
      return `${ev.payload.agent ?? "agent"}: commissioned tool ${ev.payload.name}`;
    case "tool.invoked":
      return ev.payload.ok
        ? `tool ${ev.payload.name} ran${ev.payload.ms != null ? ` in ${ev.payload.ms}ms` : ""}`
        : `tool ${ev.payload.name} failed`;
    case "run.completed":
      return `run complete — ${ev.payload.units} units, ${ev.payload.flagged} flagged`;
    case "egress.violation":
      return "BLOCKED: external call stopped at the boundary";
    default:
      return null;
  }
}

export function foldEvents(events: NxEvent[], scope = ""): JobView {
  return events.reduce(foldEvent, initialJobView(scope));
}
