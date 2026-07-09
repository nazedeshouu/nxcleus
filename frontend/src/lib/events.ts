/**
 * The UI contract, typed. Every event in docs/specs/06 §3 has an interface here.
 * The envelope carries seq/ts/scope/type; SSE `id:` == seq so reconnects resume.
 */

export type Zone = "LOCAL" | "AMD_HOSTED" | "CUSTOM" | "EXTERNAL";
export type DataClass = "RAW" | "SANITIZED";
export type Seat =
  | "trust"
  | "planner"
  | "certifier"
  | "conductor"
  | "coder"
  | "consolidator"
  | "oracle"
  | "inspector";
export type DeliveryMode = "build" | "process" | "semi-automated";
export type JobStatus =
  | "created"
  | "intake"
  | "planning"
  | "certifying"
  | "quoted"
  | "building"
  | "consolidating"
  | "qa"
  | "delivered"
  | "blocked"
  | "aborted"
  | "done";

/** Stages 0-7 (process mode skips 4/5). */
export type Stage = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;

export interface Envelope<Type extends string, Payload> {
  seq: number;
  ts: string;
  scope: string; // e.g. "job:job_01J..."
  type: Type;
  payload: Payload;
}

/* ---------- lifecycle ---------- */
export interface JobLifecyclePayload {
  status: JobStatus;
  stage: Stage;
  title?: string;
  mode?: DeliveryMode;
  reason?: string;
}

/* ---------- stage 0: intake + boundary ---------- */
export interface IntakeMessagePayload {
  role: "customer" | "system" | "trust";
  content: string;
}
export interface IntakeSpecUpdatedPayload {
  spec: { summary: string; acceptance?: string[] };
}
export interface IntakeClassifiedPayload {
  mode: DeliveryMode;
  rationale: string;
}
export interface PolicyRuleSplit {
  baseline: number; // always-on PII rules
  policy: number; // customer-supplied rules
}
export interface IntakePolicyRegisteredPayload {
  sources: Array<"document" | "typed" | "voice">;
  rule_count: number;
  split: PolicyRuleSplit;
  summary?: string;
}
export interface IntakeContextMappedPayload {
  files: number;
  symbols: number;
  tables: number;
  masked_identifiers: number;
}
export interface SensitivityFinding {
  rule_id: string; // cites a policy or baseline rule
  label: string;
  count: number;
  action: "masked" | "abstracted" | "dropped";
}
export interface BoundarySanitizedPayload {
  findings: SensitivityFinding[];
  never_leaves: string[]; // "what the frontier will never see"
  brief_tokens: number;
}

/* ---------- stage 1: planning ---------- */
export interface BomLine {
  seat: Seat;
  model: string; // display name, e.g. "Qwen3-Coder-Next"
  count: number;
  why: string; // capability flags / rationale
  zone: Zone;
}
export interface PlanStartedPayload {
  planner_model: string;
  zone: Zone;
}
export interface PlanDeltaPayload {
  text: string; // batched token delta
}
export type TopologyArchetype = "independent" | "interdependent";
export interface PlanCompletedPayload {
  summary: string;
  topology: TopologyArchetype;
  modules: number;
  bom: BomLine[];
}

/* ---------- stage 2: certify ---------- */
export interface CertifyCheckStartedPayload {
  check: string;
}
export interface CertifyFindingPayload {
  check: string;
  finding: string;
  severity: "minor" | "structural";
}
export interface AmendmentPayload {
  id: string;
  origin: "certifier" | "conductor";
  summary: string;
  hash: string; // hash-chained
  prev_hash: string;
  region?: string;
}
export interface ConsultOpenedPayload {
  id: string;
  scope: string;
  round: number;
  sanitization_receipt: { rules_applied: string[]; brief_tokens: number };
}
export interface ConsultResolvedPayload {
  id: string;
  round: number;
  resolution: string;
}
export interface GoalSetPayload {
  goal: string;
}
export interface CertifiedPayload {
  tests: number;
  vectors: number;
  identifiers_rehydrated: number;
}
export interface BlockedPayload {
  reason: string;
}

/* ---------- stage 3: quote ---------- */
export interface QuoteLine {
  label: string;
  detail: string;
  amount_usd: number;
}
export interface QuoteIssuedPayload {
  lines: QuoteLine[];
  low_usd: number;
  high_usd: number;
}
export interface QuoteApprovedPayload {
  approved_usd: number;
}

/* ---------- fleet ---------- */
export interface FleetProfileRequestedPayload {
  profile: string;
  nodes: number;
  seats: Seat[];
}
export interface FleetNodePayload {
  node: string;
  gpus: number;
  seats: Seat[];
}

/* ---------- stage 4: workers + conductor ---------- */
export interface TaskStartedPayload {
  module: string;
  backend: string; // "local:B/qwen3-coder-next"
  seat: Seat;
  zone: Zone;
  wave: number;
  why: string; // routing rationale (capability flags)
}
export interface TaskOutputDeltaPayload {
  module: string;
  text: string;
}
export interface TaskTestsPayload {
  module: string;
  passed: number;
  failed: number;
}
export interface TaskDonePayload {
  module: string;
  ok: boolean;
  loc?: number;
  reason?: string;
}
export interface WaveStartedPayload {
  wave: number;
  of: number;
  modules: string[];
}
export interface WaveReviewPayload {
  wave: number;
  verdict: "green" | "amend" | "hold";
  goal_drift: number; // 0..1
  note: string;
}
export interface WaveGreenFlagPayload {
  wave: number;
}

/* ---------- stage 5: consolidate ---------- */
export interface ConsolidateStartedPayload {
  modules: number;
}
export interface ConsolidateTestRunPayload {
  passed: number;
  failed: number;
  total: number;
}
export interface ConsolidateCompletedPayload {
  passed: number;
  total: number;
}

/* ---------- stage 6: QA ---------- */
export interface InspectorStartedPayload {
  scenario: string;
  seat: Seat;
}
export interface QaProbePayload {
  scenario: string;
  probe: string;
}
export interface QaFindingPayload {
  scenario: string;
  result: "clear" | "flag";
  detail?: string;
}
export interface GoalCheckPayload {
  verdict: "fulfilled" | "partial" | "failed";
  gaps: string[];
}
export interface OracleCheckPayload {
  vector: string;
  verdict: "match" | "mismatch";
  model: string; // lineage-independent oracle
}
export interface QaPassedPayload {
  scenarios: number;
  probes: number;
  tickets_resolved: number;
}

/* ---------- tickets ---------- */
export type TicketStatus = "opened" | "in_fix" | "verified" | "human_review";
export type TicketSeverity = "low" | "medium" | "high";
export interface TicketPayload {
  id: string;
  title: string;
  status: TicketStatus;
  severity: TicketSeverity;
  source: "inspector" | "oracle" | "consolidation" | "warranty";
  scope?: string;
}

/* ---------- stage 7 + operate ---------- */
export interface DeliverRegisteredPayload {
  process_id: string;
  version: number;
  package: { plan: boolean; docs: boolean; qa_report: boolean; tests: number };
}
export interface RunStartedPayload {
  run_id: string;
  units: number;
}
export interface RunUnitCompletedPayload {
  unit: string;
  result: string;
}
export interface RunProgressPayload {
  done: number;
  total: number;
}
export interface RunSpotcheckPayload {
  unit: string;
  verdict: "match" | "mismatch";
}
export interface RunCompletedPayload {
  units: number;
  flagged: number;
  cost_usd: number;
  gpu_seconds: number;
}
export interface RefineTriagedPayload {
  verdict: "amend" | "consult";
  note: string;
}
export interface RefineVersionCreatedPayload {
  version: number;
  diff_summary: string;
}
export interface ReviewDecidedPayload {
  unit: string;
  verdict: "approve" | "reject";
}

/* ---------- router / meter / egress / telemetry ---------- */
export interface ModelCallPayload {
  seat: Seat;
  backend: string;
  zone: Zone;
  data_class: DataClass;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}
export interface MeterTickPayload {
  scope: string;
  cost_usd: number;
  tokens: number;
  gpu_seconds: number;
}
export interface EgressRequestPayload {
  host: string;
  zone: Zone;
  seat: Seat;
  data_class: DataClass;
  bytes: number;
}
export interface EgressViolationPayload {
  host: string;
  zone: Zone;
  detail: string;
}
export interface TelemetryGpuPayload {
  node: string;
  gpu: number;
  vram_used_gb: number;
  vram_total_gb: number;
  util: number; // 0..100
  power_w: number;
  toks_per_s: number;
}

/* ---------- sandbox + config + notices ---------- */
export interface SandboxQueuedPayload {
  position: number;
}
export interface SandboxStartedPayload {
  position: number;
}
export interface ConnectionAddedPayload {
  name: string;
  host: string; // never key material
  zone: Zone;
}
export interface ModelRegisteredPayload {
  model: string;
  flags: string[];
}
export interface SeatBoundPayload {
  seat: Seat;
  model_key: string;
  scope: string;
}
export interface SystemNoticePayload {
  text: string;
  level: "info" | "warn" | "error";
}

/* ---------- the union ---------- */
export type NxEvent =
  | Envelope<"job.created", JobLifecyclePayload>
  | Envelope<"job.stage_changed", JobLifecyclePayload>
  | Envelope<"job.blocked", JobLifecyclePayload>
  | Envelope<"job.done", JobLifecyclePayload>
  | Envelope<"job.aborted", JobLifecyclePayload>
  | Envelope<"intake.message", IntakeMessagePayload>
  | Envelope<"intake.spec_updated", IntakeSpecUpdatedPayload>
  | Envelope<"intake.classified", IntakeClassifiedPayload>
  | Envelope<"intake.policy_registered", IntakePolicyRegisteredPayload>
  | Envelope<"intake.context_mapped", IntakeContextMappedPayload>
  | Envelope<"boundary.sanitized", BoundarySanitizedPayload>
  | Envelope<"plan.started", PlanStartedPayload>
  | Envelope<"plan.delta", PlanDeltaPayload>
  | Envelope<"plan.completed", PlanCompletedPayload>
  | Envelope<"certify.check_started", CertifyCheckStartedPayload>
  | Envelope<"certify.finding", CertifyFindingPayload>
  | Envelope<"certify.amendment", AmendmentPayload>
  | Envelope<"certify.consult_opened", ConsultOpenedPayload>
  | Envelope<"certify.consult_resolved", ConsultResolvedPayload>
  | Envelope<"certify.goal_set", GoalSetPayload>
  | Envelope<"certify.certified", CertifiedPayload>
  | Envelope<"certify.blocked", BlockedPayload>
  | Envelope<"quote.issued", QuoteIssuedPayload>
  | Envelope<"quote.approved", QuoteApprovedPayload>
  | Envelope<"fleet.profile_requested", FleetProfileRequestedPayload>
  | Envelope<"fleet.node_ready", FleetNodePayload>
  | Envelope<"fleet.node_down", FleetNodePayload>
  | Envelope<"task.started", TaskStartedPayload>
  | Envelope<"task.output_delta", TaskOutputDeltaPayload>
  | Envelope<"task.tests", TaskTestsPayload>
  | Envelope<"task.completed", TaskDonePayload>
  | Envelope<"task.failed", TaskDonePayload>
  | Envelope<"conductor.wave_started", WaveStartedPayload>
  | Envelope<"conductor.review", WaveReviewPayload>
  | Envelope<"conductor.amendment", AmendmentPayload>
  | Envelope<"conductor.green_flag", WaveGreenFlagPayload>
  | Envelope<"consolidate.started", ConsolidateStartedPayload>
  | Envelope<"consolidate.test_run", ConsolidateTestRunPayload>
  | Envelope<"consolidate.completed", ConsolidateCompletedPayload>
  | Envelope<"qa.inspector_started", InspectorStartedPayload>
  | Envelope<"qa.probe", QaProbePayload>
  | Envelope<"qa.finding", QaFindingPayload>
  | Envelope<"qa.goal_check", GoalCheckPayload>
  | Envelope<"qa.oracle_check", OracleCheckPayload>
  | Envelope<"qa.passed", QaPassedPayload>
  | Envelope<"ticket.opened", TicketPayload>
  | Envelope<"ticket.in_fix", TicketPayload>
  | Envelope<"ticket.verified", TicketPayload>
  | Envelope<"ticket.human_review", TicketPayload>
  | Envelope<"deliver.registered", DeliverRegisteredPayload>
  | Envelope<"run.started", RunStartedPayload>
  | Envelope<"run.unit_completed", RunUnitCompletedPayload>
  | Envelope<"run.progress", RunProgressPayload>
  | Envelope<"run.spotcheck", RunSpotcheckPayload>
  | Envelope<"run.completed", RunCompletedPayload>
  | Envelope<"warranty.ticket", TicketPayload>
  | Envelope<"refine.triaged", RefineTriagedPayload>
  | Envelope<"refine.version_created", RefineVersionCreatedPayload>
  | Envelope<"review.decided", ReviewDecidedPayload>
  | Envelope<"model.call", ModelCallPayload>
  | Envelope<"meter.tick", MeterTickPayload>
  | Envelope<"egress.request", EgressRequestPayload>
  | Envelope<"egress.violation", EgressViolationPayload>
  | Envelope<"telemetry.gpu", TelemetryGpuPayload>
  | Envelope<"sandbox.queued", SandboxQueuedPayload>
  | Envelope<"sandbox.started", SandboxStartedPayload>
  | Envelope<"config.connection_added", ConnectionAddedPayload>
  | Envelope<"config.model_registered", ModelRegisteredPayload>
  | Envelope<"config.seat_bound", SeatBoundPayload>
  | Envelope<"system.notice", SystemNoticePayload>;

export type NxEventType = NxEvent["type"];

/** Narrow helper for the fold. */
export type EventOf<T extends NxEventType> = Extract<NxEvent, { type: T }>;
