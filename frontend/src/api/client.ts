/** Typed REST client for 06 §2. Lean: the endpoints wave-1 surfaces need. */
import { API_BASE, getDemoToken } from "./config";
import type { DeliveryMode, JobStatus, Stage, Zone } from "../lib/events";

export interface PublicConfig {
  sovereign: boolean;
  fallback_serving: boolean; // Fireworks badge
  profile: string;
  demo: boolean;
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

export const api = {
  health: () => req<{ ok: boolean }>("/health"),
  publicConfig: () => req<PublicConfig>("/config/public"),
  listJobs: (params?: { origin?: string; status?: string }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return req<{ jobs: JobSummary[] }>(`/jobs${q ? `?${q}` : ""}`);
  },
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
  fleet: () => req<FleetInfo>("/fleet"),
  setSovereign: (enabled: boolean) => req<unknown>("/admin/sovereign", { method: "POST", body: JSON.stringify({ enabled }), demo: true }),
};

export type { Zone };
