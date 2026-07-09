/** Typed REST client for 06 §2. Shapes match what the live backend returns. */
import { API_BASE, getDemoToken } from "./config";
import type { DeliveryMode, JobStatus, Stage, Zone } from "../lib/events";

export interface PublicConfig {
  sovereign: boolean;
  fallback_serving: boolean; // Fireworks badge
  profile: string;
  demo: boolean;
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
  ts: string;
  units: number;
  cost_usd: number;
  cost_per_unit: number;
  frontier_calls: number;
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
  units: number;
  ok: number;
  needs_review: number;
  error: number;
  spot_checks: number;
  discrepancies: number;
}
export interface RunCost {
  total_usd: number;
  cost_per_unit: number;
  frontier_calls: number;
}
export interface RunDetail {
  id: string;
  process_id: string;
  version: number;
  kind: string;
  status: string;
  input_ref: string;
  started_at?: string;
  finished_at?: string;
  stats: RunStats;
  cost: RunCost;
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

/* ---------- sandbox ---------- */
export interface CompanySummary {
  id: string;
  name: string;
  prompts: string[];
}
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
export interface ConnectionInfo {
  id: string;
  name: string;
  base_url: string;
  zone: string;
  data_class_ceiling?: string;
  counts_as_local?: boolean;
  api_key: string; // masked by the backend
}

/* ---------- egress ---------- */
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
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers as Record<string, string>) };
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
  createJob: (body: { title?: string; request: string; policy_text?: string; sovereign?: boolean }) =>
    req<{ job: JobSummary }>("/jobs", { method: "POST", body: JSON.stringify(body), demo: true }),
  postMessage: (id: string, content: string) =>
    req<unknown>(`/jobs/${id}/messages`, { method: "POST", body: JSON.stringify({ content }), demo: true }),
  confirmSpec: (id: string, mode: DeliveryMode) =>
    req<unknown>(`/jobs/${id}/confirm-spec`, { method: "POST", body: JSON.stringify({ mode }), demo: true }),
  getQuote: (id: string) => req<{ lines: unknown[] }>(`/jobs/${id}/quote`),
  approveQuote: (id: string) => req<unknown>(`/jobs/${id}/approve-quote`, { method: "POST", demo: true }),
  abort: (id: string) => req<unknown>(`/jobs/${id}/abort`, { method: "POST", demo: true }),

  /* processes / operate */
  listProcesses: () => req<{ processes: ProcessSummary[] }>("/processes"),
  getProcess: (id: string) => req<{ process: ProcessSummary; versions: ProcessVersion[] }>(`/processes/${id}`),
  getVersionDiff: (id: string, v: number) => req<{ diff: VersionDiff }>(`/processes/${id}/versions/${v}/diff`),
  runBatch: (id: string, body: { input_ref: string; version?: number }) =>
    req<{ run: RunDetail }>(`/processes/${id}/runs`, { method: "POST", body: JSON.stringify({ ...body, kind: "batch" }), demo: true }),
  refineProcess: (id: string, request: string) =>
    req<{ job: JobSummary }>(`/processes/${id}/refine`, { method: "POST", body: JSON.stringify({ request }), demo: true }),
  instantiateProcess: (id: string, connectors: Record<string, unknown>) =>
    req<{ job: JobSummary }>(`/processes/${id}/instantiate`, { method: "POST", body: JSON.stringify({ connectors }), demo: true }),

  /* runs */
  getRun: (id: string) => req<{ run: RunDetail }>(`/runs/${id}`),
  getRunUnits: (id: string, status?: string) => req<{ units: RunUnit[] }>(`/runs/${id}/units${qs({ status })}`),
  reviewUnit: (unitId: string, verdict: "approve" | "reject", note?: string) =>
    req<unknown>(`/units/${unitId}/review`, { method: "POST", body: JSON.stringify({ verdict, note }), demo: true }),

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
  addConnection: (body: { name: string; base_url: string; api_key: string; data_class_ceiling?: string; counts_as_local?: boolean }) =>
    req<{ connection: ConnectionInfo }>("/connections", { method: "POST", body: JSON.stringify(body), demo: true }),
  removeConnection: (id: string) => req<unknown>(`/connections/${id}`, { method: "DELETE", demo: true }),
  addConnectionModel: (id: string, body: { provider_model_id: string; display_name: string; flags: string[]; context_len?: number }) =>
    req<unknown>(`/connections/${id}/models`, { method: "POST", body: JSON.stringify(body), demo: true }),
  bindSeat: (seat: string, body: { model_key: string; scope?: string }) =>
    req<unknown>(`/seats/${seat}/binding`, { method: "PUT", body: JSON.stringify(body), demo: true }),

  /* sandbox */
  sandboxCompanies: () => req<{ companies: CompanySummary[] }>("/sandbox/companies"),
  sandboxTables: (companyId: string) => req<{ tables: string[]; seeded?: boolean }>(`/sandbox/companies/${companyId}/tables`),
  sandboxTable: (companyId: string, table: string, page = 1) =>
    req<TablePage>(`/sandbox/companies/${companyId}/tables/${table}${qs({ page })}`),
  sandboxRun: (body: { company: string; prompt: string }) =>
    req<{ job_id: string; queue_position?: number }>("/sandbox/runs", { method: "POST", body: JSON.stringify(body) }),
  sandboxQueue: () => req<{ pending: Array<{ job_id: string; company?: string; position?: number }>; max_concurrent: number }>("/sandbox/queue"),

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
