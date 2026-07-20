/** Typed REST client for 06 §2. Shapes match what the live backend returns. */
import { API_BASE, getDemoToken } from "./config";
import type { DeliveryMode, JobStatus, RunVerification, Stage, Zone } from "../lib/events";

export interface PublicConfig {
  sovereign: boolean;
  fallback_serving: boolean; // Fireworks badge
  profile: string;
  demo: boolean;
  trace_prompts?: boolean; // prompt/response tracing enabled (LOCAL-only store)
  signup_code_required?: boolean; // account creation gated behind an invite code
  keys?: { anthropic?: boolean; fireworks?: boolean };
  budgets?: { fireworks_daily_usd?: number; sandbox_run_usd?: number; sandbox_max_concurrent?: number };
}

export interface JobSummary {
  id: string;
  title: string;
  status: JobStatus;
  stage: Stage;
  mode?: DeliveryMode;
  origin?: string;
  created_at?: string;
  goal?: string;
}

/* ---------- processes / versions / economics ---------- */
export interface ProcessSummary {
  id: string;
  slug: string;
  name: string;
  mode: DeliveryMode;
  goal: string;
  status: string;
  current_version: number;
  created_from_job?: string;
  created_from?: string;
  created_at?: string;
}
export interface VersionDiff {
  triage: string;
  regions: string[];
  modules_rebuilt: string[];
  tests_added: number;
  frontier_consult: boolean;
}
export interface ProcessVersion {
  id: string;
  process_id: string;
  version: number;
  plan_id: string;
  package_path: string;
  image_tag?: string;
  diff_json?: string | null;
  certified_at?: string;
  status: string;
  diff?: VersionDiff | null;
}
export interface EconRun {
  run_id: string;
  ts: string | null;
  units: number | null;
  cost_usd: number | null;
  cost_per_unit: number | null;
  model_calls: number | null;
  frontier_calls: number | null;
  cost_verification: "passed" | "unverified";
  cost_reason: string | null;
  status: string;
  verification: RunVerification;
  verification_reasons: string[];
  demo: boolean;
  mock_dispatches?: number;
}
export interface EconProcess {
  process_id: string;
  slug: string;
  build_cost_usd: number;
  build_frontier_calls: number;
  runs: EconRun[];
  trend: string;
}

/* ---------- runs ---------- */
export interface RunStats {
  units?: number | null;
  ok?: number | null;
  needs_review?: number | null;
  error?: number | null;
  spot_checks?: number | null;
  discrepancies?: number | null;
  mock_dispatches?: number;
  verification?: RunVerification;
  verification_reasons?: string[];
  run_status?: string;
  demo?: boolean;
  corpus?: { kind?: string; company?: string | null; synthetic_demo?: boolean };
  artifact?: {
    verification?: "passed" | "unverified";
    degraded?: boolean;
    reason?: string | null;
    artifacts?: RunArtifactInfo[];
  };
}
export interface RunCost {
  total_usd?: number | null;
  cost_per_unit?: number | null;
  model_calls?: number | null;
  frontier_calls?: number | null;
  verification?: "passed" | "unverified";
  reason?: string | null;
}
export interface RunArtifactInfo {
  kind: string; // "report" | "csv"
  url: string;
}
export interface RunDetail {
  id: string;
  process_id: string;
  version: number;
  kind: string;
  status: string;
  verification?: RunVerification;
  verification_reasons?: string[];
  demo?: boolean;
  input_ref: string;
  started_at?: string;
  finished_at?: string;
  stats: RunStats;
  cost: RunCost;
  artifacts?: RunArtifactInfo[];
}
export interface NextStep {
  title: string;
  why: string;
  action: { kind: "refine" | "export" | "review" | "rerun"; params?: Record<string, unknown> };
}
export interface RunBatchRequest {
  version?: number;
  corpus?: { company: string };
  sample?: { mode?: "first" | "random"; n?: number };
  deliverable?: Record<string, unknown>;
  synthetic_demo?: boolean;
}
export interface RunUnit {
  id: string;
  run_id: string;
  unit_ref: string;
  status: string;
  result?: unknown;
  trace?: unknown;
  review_verdict?: string | null;
  review_note?: string | null;
  ts?: string;
}

/** Diff of a run's flagged units vs the corpus's planted ground truth (demo 5). */
export interface GroundTruthPair {
  claims: number[];
  policy_id: number;
  incident_date: string;
  amounts: number[];
  label: string;
}
export interface GroundTruthFalsePositive {
  unit_ref: string;
  candidate: Record<string, unknown>;
}
export interface GroundTruthCompare {
  company: string;
  pattern: string;
  ground_truth_basis: string;
  planted_total: number;
  flagged_total: number;
  true_positive_count: number;
  false_positive_count: number;
  missed_count: number;
  true_positives: GroundTruthPair[];
  false_positives: GroundTruthFalsePositive[];
  missed: GroundTruthPair[];
}

export interface Ticket {
  id: string;
  scope: string;
  source: string;
  severity: string;
  status: string;
  title: string;
  fix_attempts?: number;
  ts?: string;
  body?: unknown;
}

/* ---------- sandbox / datasets ---------- */
export type DatasetOrigin = "builtin" | "upload" | "connector" | "codebase";
export type DatasetKind = "rows" | "files";
export interface CompanySummary {
  id: string;
  name: string;
  prompts?: string[]; // older shape
  suggested_prompts?: string[]; // hardening-wave shape
  industry?: string;
  blurb?: string;
  origin?: DatasetOrigin; // custom datasets carry provenance; builtins are "builtin"
  kind?: DatasetKind; // "rows" (tabular) | "files" (codebase / documents)
  tables?: Array<{ table: string; row_count: number }>;
}
/** Result of registering a custom data source (upload / connector / codebase). */
export interface Dataset {
  id: string;
  name: string;
  blurb?: string;
  origin: DatasetOrigin;
  kind: DatasetKind;
  tables: Array<{ name: string; rows: number }>;
  meta?: Record<string, unknown>; // {snapshot_at,rows_copied,capped} | {files,code_map}
}
/** Tolerant accessor: the prompts field moved names across backend waves. */
export const companyPrompts = (c: CompanySummary): string[] => c.suggested_prompts ?? c.prompts ?? [];
export interface TablePage {
  rows: Array<Record<string, unknown>>;
  page?: number;
  total?: number;
}

/* ---------- models / connections / seats ---------- */
export interface ModelInfo {
  key: string;
  source: string;
  provider: string;
  hf_id?: string;
  flags: Record<string, string>;
  serves?: string[];
  license?: string;
  evidence?: string;
  serving?: Record<string, unknown>;
}
export type ApiStyle = "openai" | "anthropic";
export interface ConnectionInfo {
  id: string;
  name: string;
  base_url: string;
  zone: string;
  data_class_ceiling?: string;
  counts_as_local?: boolean;
  api_style?: ApiStyle; // wire dialect — how the router frames requests to this endpoint
  api_key: string; // masked by the backend
}
export interface ConnectionTest {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  error?: string;
}

/* ---------- egress ---------- */
/* ---------- traces (prompt inspector — LOCAL-only, contains RAW data) ---------- */
export interface TraceSummary {
  id: string;
  ts: string;
  scope: string;
  seat: string;
  backend: string;
  model?: string;
  zone: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  badge?: string; // e.g. "parsed_ok"
  messages_preview?: string;
  response_preview?: string;
}
export interface TraceDetail extends TraceSummary {
  messages?: Array<{ role?: string; content?: unknown }>; // authoritative: already parsed
  messages_json?: unknown; // raw string also on the row; prefer `messages`
  response_text?: string;
}

/* ---------- runtime-commissioned tools (F7) ---------- */
export interface ToolInfo {
  id: string;
  ts?: string;
  scope?: string;
  agent_dir?: string;
  name: string;
  description?: string;
  args_schema?: unknown;
  code?: string;
  self_test_passed?: boolean;
  created_by_seat?: string;
  model?: string;
}

/* ---------- plan artifact (persisted plan body_json, exposed by GET /jobs/{id}/plan) ---------- */
export interface PlanModule {
  id: string;
  name?: string;
  purpose?: string;
  algorithm?: string;
  complexity?: "S" | "M" | "L";
  consumes?: string[];
  provides?: string[];
  task_flags?: string[];
  assumptions?: string[];
  model?: string | null;
}
export interface PlanInterface {
  id: string;
  producer?: string;
  consumers?: string[];
  schema?: Record<string, unknown>;
}
export interface PlanStep {
  id: string;
  seat?: string | null;
  per_unit?: boolean;
  kind?: string | null; // "sql" | "analysis" | judgment (null)
  sql?: string | null;
  label?: string;
  purpose?: string | null;
  prompt_spec?: string;
  task_flags?: string[];
}
export interface PlanBomSeat {
  seat: string;
  count?: number;
  why?: string;
  sampling?: number | null;
}
export interface PlanBody {
  plan_id?: string;
  job_id?: string;
  version?: number;
  mode?: string; // build | process | semi
  modules?: PlanModule[];
  interfaces?: PlanInterface[];
  dag?: Array<{ task: string; module?: string; deps?: string[] }>;
  topology?: {
    unit?: { noun?: string; source?: string; schema?: Record<string, unknown> };
    steps?: PlanStep[];
  } | null;
  model_bom?: {
    seats?: PlanBomSeat[];
    fleet?: { profile?: string; nodes?: number; parallel_width?: number };
    conductor?: unknown;
  };
  estimates?: { frontier_tokens?: number; local_tokens?: number; gpu_hours?: number };
  risks?: string[];
}
export interface JobPlan {
  plan: PlanBody | null;
  amendments?: unknown[];
  consults?: unknown[];
}

export interface EgressRow {
  id: string;
  ts: string;
  scope: string;
  host: string;
  zone: string;
  seat?: string;
  bytes_out?: number;
  bytes_in?: number;
  sovereign_violation?: number;
}

export interface FleetNodeInfo {
  name: string;
  ip?: string;
  gpus: number;
  seats: string[];
  up: boolean;
}
export interface FleetInfo {
  profile: string;
  nodes: FleetNodeInfo[];
}

export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

async function req<T>(path: string, init?: RequestInit & { demo?: boolean }): Promise<T> {
  // FormData must set its own multipart boundary — never force a JSON content-type on it.
  const isForm = init?.body instanceof FormData;
  const headers: Record<string, string> = { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(init?.headers as Record<string, string>) };
  if (init?.demo) {
    const t = getDemoToken();
    if (t) headers["X-Demo-Token"] = t;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let body: { error?: ApiError } = {};
    try {
      body = await res.json();
    } catch {
      /* non-json error */
    }
    throw Object.assign(new Error(body.error?.message ?? `HTTP ${res.status}`), { status: res.status, api: body.error });
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const qs = (params?: Record<string, string | number | undefined>) => {
  if (!params) return "";
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]));
  const s = new URLSearchParams(clean).toString();
  return s ? `?${s}` : "";
};

/** Map the backend's /config/public shape to the UI's feature flags. */
function mapPublicConfig(raw: Record<string, unknown>): PublicConfig {
  const keys = (raw.keys_present ?? {}) as Record<string, boolean>;
  return {
    sovereign: (raw.sovereign as boolean) ?? (raw.sovereign_default as boolean) ?? false,
    fallback_serving: (raw.fallback_serving as boolean) ?? (raw.model_mode === "fireworks"),
    profile: (raw.profile as string) ?? (raw.model_mode as string) ?? "demo",
    demo: (raw.demo as boolean) ?? !(raw.admin_required as boolean),
    trace_prompts: raw.trace_prompts as boolean | undefined,
    signup_code_required: (raw.signup_code_required as boolean) ?? false,
    keys: { anthropic: keys.anthropic, fireworks: keys.fireworks },
    budgets: raw.budgets as PublicConfig["budgets"],
  };
}

export const api = {
  health: () => req<{ ok: boolean }>("/health"),
  publicConfig: async () => mapPublicConfig((await req<Record<string, unknown>>("/config/public")) ?? {}),

  /* jobs */
  listJobs: (params?: { origin?: string; status?: string }) =>
    req<{ jobs: JobSummary[] }>(`/jobs${qs(params)}`),
  getJob: (id: string) => req<JobSummary>(`/jobs/${id}`),
  /** Raw job payload — clarification questions ride on the job (field name varies). */
  getJobFull: (id: string) => req<Record<string, unknown>>(`/jobs/${id}`),
  answerJob: (id: string, answers: Array<{ id: string; answer: string }>) =>
    req<unknown>(`/jobs/${id}/answers`, { method: "POST", body: JSON.stringify({ answers }), demo: true }),
  createJob: (body: { title?: string; request: string; policy_text?: string; sovereign?: boolean; company?: string }) =>
    req<{ job: JobSummary }>("/jobs", { method: "POST", body: JSON.stringify(body), demo: true }),
  postMessage: (id: string, content: string) =>
    req<unknown>(`/jobs/${id}/messages`, { method: "POST", body: JSON.stringify({ content }), demo: true }),
  retryJob: (id: string, correction = "") =>
    req<{ retried: boolean; target_stage: string }>(`/jobs/${id}/retry`, {
      method: "POST", body: JSON.stringify({ correction }), demo: true,
    }),
  confirmSpec: (id: string, mode: DeliveryMode) =>
    req<unknown>(`/jobs/${id}/confirm-spec`, { method: "POST", body: JSON.stringify({ mode }), demo: true }),
  getQuote: (id: string) => req<{ lines: unknown[] }>(`/jobs/${id}/quote`),
  approveQuote: (id: string) => req<unknown>(`/jobs/${id}/approve-quote`, { method: "POST", demo: true }),
  abort: (id: string) => req<unknown>(`/jobs/${id}/abort`, { method: "POST", demo: true }),

  /* processes / operate */
  listProcesses: () => req<{ processes: ProcessSummary[] }>("/processes"),
  getProcess: (id: string) => req<{ process: ProcessSummary; versions: ProcessVersion[] }>(`/processes/${id}`),
  getVersionDiff: (id: string, v: number) => req<{ diff: VersionDiff }>(`/processes/${id}/versions/${v}/diff`),
  // extra keys (budget, …) pass through opaquely — next-steps rerun params ride here
  runBatch: (id: string, body: RunBatchRequest & Record<string, unknown>) =>
    req<{ run: RunDetail }>(`/processes/${id}/runs`, { method: "POST", body: JSON.stringify({ ...body, kind: "batch" }), demo: true }),
  refineProcess: (id: string, request: string) =>
    req<{ job: JobSummary }>(`/processes/${id}/refine`, { method: "POST", body: JSON.stringify({ request }), demo: true }),
  instantiateProcess: (id: string, connectors: Record<string, unknown>) =>
    req<{ job: JobSummary }>(`/processes/${id}/instantiate`, { method: "POST", body: JSON.stringify({ connectors }), demo: true }),

  /* runs */
  getRun: (id: string) => req<{ run: RunDetail }>(`/runs/${id}`),
  getRunUnits: (id: string, status?: string) => req<{ units: RunUnit[] }>(`/runs/${id}/units${qs({ status })}`),
  groundTruthCompare: (id: string) => req<GroundTruthCompare>(`/runs/${id}/ground-truth-compare`),
  reviewUnit: (unitId: string, verdict: "approve" | "reject", note?: string) =>
    req<unknown>(`/units/${unitId}/review`, { method: "POST", body: JSON.stringify({ verdict, note }), demo: true }),
  /** POST generates (idempotent on the backend), GET reads; tolerate either failing. */
  nextSteps: async (runId: string): Promise<NextStep[]> => {
    await req(`/runs/${runId}/next-steps`, { method: "POST", demo: true }).catch(() => undefined);
    const res = await req<{ next_steps: NextStep[] }>(`/runs/${runId}/next-steps`);
    return res?.next_steps ?? [];
  },

  /* traces (prompt inspector) */
  traces: (params?: { scope?: string; seat?: string; limit?: number; offset?: number }) =>
    req<{ traces: TraceSummary[] }>(`/traces${qs(params)}`),
  trace: (id: string) => req<{ trace: TraceDetail }>(`/traces/${id}`).then((r) => r.trace),
  /** Persisted plan body (body_json) + amendments/consults — 404 until stage 1 certifies a plan. */
  plan: (jobId: string) => req<JobPlan>(`/jobs/${jobId}/plan`),

  /* runtime-commissioned tools (F7) */
  tools: (scope?: string) => req<{ tools: ToolInfo[] }>(`/tools${qs({ scope })}`),

  /* economics + tickets */
  economics: () => req<{ processes: EconProcess[] }>("/economics/summary"),
  listTickets: (params?: { scope?: string; status?: string; source?: string }) =>
    req<{ tickets: Ticket[] }>(`/tickets${qs(params)}`),

  /* fleet + egress */
  fleet: () => req<FleetInfo>("/fleet"),
  egress: (params?: { scope?: string; zone?: string }) => req<{ egress: EgressRow[] }>(`/egress${qs(params)}`),
  setSovereign: (enabled: boolean) => req<unknown>("/admin/sovereign", { method: "POST", body: JSON.stringify({ enabled }), demo: true }),

  /* models + connections + seats */
  listModels: () => req<{ models: ModelInfo[] }>("/models"),
  listConnections: () => req<{ connections: ConnectionInfo[] }>("/connections"),
  addConnection: (body: { name: string; base_url: string; api_key: string; data_class_ceiling?: string; counts_as_local?: boolean; api_style?: ApiStyle }) =>
    req<{ connection: ConnectionInfo }>("/connections", { method: "POST", body: JSON.stringify(body), demo: true }),
  removeConnection: (id: string) => req<unknown>(`/connections/${id}`, { method: "DELETE", demo: true }),
  testConnection: (id: string) => req<ConnectionTest>(`/connections/${id}/test`, { method: "POST", demo: true }),
  addConnectionModel: (id: string, body: { provider_model_id: string; display_name: string; flags: string[]; context_len?: number }) =>
    req<unknown>(`/connections/${id}/models`, { method: "POST", body: JSON.stringify(body), demo: true }),
  bindSeat: (seat: string, body: { model_key: string; scope?: string }) =>
    req<unknown>(`/seats/${seat}/binding`, { method: "PUT", body: JSON.stringify(body), demo: true }),
  unbindSeat: (seat: string, scope = "global") =>
    req<unknown>(`/seats/${seat}/binding?scope=${encodeURIComponent(scope)}`, { method: "DELETE", demo: true }),
  /** Extract editable policy text from an uploaded PDF/image (feeds the composer's policy_text). */
  extractPolicy: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<{ text: string; kind: string; name: string; chars: number }>("/policies/extract", { method: "POST", body: fd, demo: true });
  },

  /* sandbox */
  sandboxCompanies: () => req<{ companies: CompanySummary[] }>("/sandbox/companies"),
  sandboxTables: (companyId: string) => req<{ tables: string[]; seeded?: boolean }>(`/sandbox/companies/${companyId}/tables`),
  sandboxTerms: (companyId: string) => req<{ markdown: string; seeded: boolean }>(`/sandbox/companies/${companyId}/terms`),
  sandboxTable: (companyId: string, table: string, page = 1) =>
    req<TablePage>(`/sandbox/companies/${companyId}/tables/${table}${qs({ page })}`),
  sandboxRun: (body: { company: string; prompt: string }) =>
    req<{ job_id: string; queue_position?: number }>("/sandbox/runs", { method: "POST", body: JSON.stringify(body) }),
  sandboxQueue: () => req<{ pending: Array<{ job_id: string; company?: string; position?: number }>; max_concurrent: number }>("/sandbox/queue"),

  /* custom data sources (F-datasets): upload files, connect a live DB, or point at a codebase */
  addDataset: (files: File[], meta?: { name?: string; blurb?: string }) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    if (meta?.name) fd.append("name", meta.name);
    if (meta?.blurb) fd.append("blurb", meta.blurb);
    return req<Dataset>("/datasets", { method: "POST", body: fd, demo: true });
  },
  connectDataset: (body: { url: string; name?: string }) =>
    req<Dataset>("/datasets/connect", { method: "POST", body: JSON.stringify(body), demo: true }),
  codebaseDataset: (body: { path?: string; git_url?: string; name?: string }) =>
    req<Dataset>("/datasets/codebase", { method: "POST", body: JSON.stringify(body), demo: true }),
  deleteDataset: (id: string) => req<unknown>(`/datasets/${id}`, { method: "DELETE", demo: true }),

  /* replay */
  replay: (scope: string) => req<{ scope: string; events: unknown[] }>(`/replay/${scope}`),

  /* package artifacts (plan/manifest/invoice/qa served as files) */
  packageFile: <T = unknown>(id: string, v: number, file: string) =>
    req<T>(`/processes/${id}/package/${v}/${file}`),
};

export interface PackageManifest {
  name: string;
  slug: string;
  version: number;
  mode: string;
  goal: string;
  model_bom?: { seats: Array<{ seat: string; count?: number; why?: string; sampling?: number }>; fleet?: Record<string, unknown> };
  connectors?: Array<{ name: string; kind: string; mock?: boolean }>;
  entrypoint?: string;
  image_tag?: string;
  seats?: string[];
  goal_verdict?: string;
}
export interface PackageInvoice {
  lines: Array<{ item: string; qty: string; actual_usd: number; zone?: string; backend?: string; tokens_in?: number; tokens_out?: number }>;
  total_usd: number;
  footnote?: string;
  frontier_calls: number;
  quote_total_est_usd?: [number, number];
  delta_vs_quote?: number;
}

export type { Zone };

/* ---------- auth (cookie session; same-origin so the browser carries the cookie) ---------- */
export interface AuthSession {
  username: string;
  role: "admin" | "judge" | string;
  auth_enabled: boolean; // false => dev mode (synthetic session, no login wall)
}
export const authApi = {
  me: () => req<AuthSession>("/auth/me"),
  login: (username: string, password: string) =>
    req<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  // Account creation. Auto-logs-in on success (sets the same cookie as login).
  // Errors surface via req()'s thrown Error.status: 409 taken, 400 weak, 403 bad invite code.
  signup: (username: string, password: string, invite_code?: string) =>
    req<AuthSession>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(invite_code ? { username, password, invite_code } : { username, password }),
    }),
  logout: () => req<{ ok: boolean }>("/auth/logout", { method: "POST" }),
};
