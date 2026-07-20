/**
 * Event normalization: raw backend payloads (the shapes the running control
 * plane actually emits) -> the typed NxEvent catalog the fold + components
 * consume. Spec 06 §3 is the intended contract; the live backend diverged
 * across ~30 types, so we conform the frontend to reality here, at the SSE /
 * replay boundary. Fixtures already speak the typed shape and never pass
 * through this function.
 *
 * The adapter is tolerant: it prefers an already-typed field when present and
 * falls back to the backend field, so it keeps working whether or not the
 * backend is later reconciled to the spec.
 */
import type {
  NxEvent, Stage, Zone, DataClass, Seat, GoalVerdict, OracleVerdict,
  RunTerminalPayload, RunTerminalStatus, RunVerification,
} from "../lib/events";

type Raw = { seq: number; ts: string; scope: string; type: string; payload: Record<string, unknown> };

/**
 * Every event type the backend may emit. The backend sends NAMED SSE events
 * (`event: <type>`), so EventSource needs a listener registered per type —
 * `onmessage` alone (unnamed "message" events) never fires. Keep in sync with
 * the NxEvent union in events.ts.
 */
export const KNOWN_EVENT_TYPES: string[] = [
  "job.created", "job.stage_changed", "job.blocked", "job.done", "job.aborted",
  "intake.message", "intake.spec_updated", "intake.classified", "intake.policy_registered", "intake.context_mapped",
  "boundary.sanitized",
  "plan.started", "plan.delta", "plan.completed",
  "certify.check_started", "certify.finding", "certify.amendment", "certify.consult_opened", "certify.consult_resolved",
  "certify.consult_repaired", "certify.goal_set", "certify.certified", "certify.blocked", "plan.scope_violation",
  "quote.issued", "quote.approved",
  "fleet.profile_requested", "fleet.node_ready", "fleet.node_down",
  "task.started", "task.output_delta", "task.tests", "task.completed", "task.failed",
  "conductor.wave_started", "conductor.review", "conductor.amendment", "conductor.green_flag",
  "consolidate.started", "consolidate.test_run", "consolidate.completed",
  "qa.inspector_started", "qa.probe", "qa.finding", "qa.goal_check", "qa.oracle_check", "qa.completed", "qa.passed",
  "ticket.opened", "ticket.in_fix", "ticket.verified", "ticket.human_review",
  "deliver.registered",
  "run.started", "run.unit_completed", "run.progress", "run.spotcheck", "run.finished", "run.completed",
  "warranty.ticket", "refine.triaged", "refine.version_created", "review.decided",
  "model.call", "meter.tick", "egress.request", "egress.violation", "telemetry.gpu",
  "sandbox.queued", "sandbox.started",
  "config.connection_added", "config.model_registered", "config.seat_bound",
  "system.notice",
  // hardening wave: previously-dead named events (EventSource drops unregistered types)
  "qa.probe_started", "qa.probe_passed", "qa.probe_timeout", "qa.probe_exhausted", "qa.oracle_vote",
  "certify.consult_requested", "certify.scenarios_emitted", "certify.rehydrated", "certify.check_completed",
  "plan.replanned", "intake.turn", "intake.mode_classified", "task.fix_applied", "task.files_written",
  "conductor.goal_drift", "deliver.docs_generated", "boundary.sweep",
  "intake.clarification_requested", "intake.clarification_answered", "run.artifacts_ready", "model.trace",
  "ticket.fix_applied", "run.sql_step", "tool.created", "tool.invoked",
];

/* backend sometimes sends a status-name where a numeric stage belongs */
const STAGE_BY_NAME: Record<string, Stage> = {
  created: 0, intake: 0, awaiting_input: 0,
  planning: 1,
  certifying: 2, certify: 2,
  quoted: 3, quote: 3,
  building: 4, build: 4,
  consolidating: 5, consolidate: 5,
  qa: 6,
  delivered: 7, deliver: 7, done: 7,
};

function toStage(v: unknown, fallback: Stage = 0): Stage {
  if (typeof v === "number") return Math.max(0, Math.min(7, v)) as Stage;
  if (typeof v === "string" && v in STAGE_BY_NAME) return STAGE_BY_NAME[v];
  return fallback;
}

/**
 * Display model + zone per seat, sourced from infra/models.yaml semantics. `purpose` is the
 * one-line "why this seat dispatches", surfaced in the trace inspector so each row is legible.
 */
export const SEAT_INFO: Record<string, { model: string; zone: Zone; purpose?: string }> = {
  trust: { model: "Gemma-4-26B", zone: "LOCAL", purpose: "Runs intake, distills the policy, and masks PII at the boundary before anything leaves the box." },
  planner: { model: "Frontier planner", zone: "EXTERNAL", purpose: "The one external call: compiles the sanitized brief into a decomposed, certifiable plan." },
  certifier: { model: "GLM-4.6", zone: "LOCAL", purpose: "Certifies the plan — completes it, resolves findings, rehydrates identifiers, sets the goal." },
  conductor: { model: "GLM-4.6", zone: "LOCAL", purpose: "Reviews each build wave for goal drift and green-flags the next wave." },
  coder: { model: "Qwen3-Coder", zone: "LOCAL", purpose: "Writes one module's SQL/tool code and applies defect fixes." },
  consolidator: { model: "GLM-4.6", zone: "LOCAL", purpose: "Merges the built modules and runs the consolidated test suite." },
  oracle: { model: "Gemma-4-31B", zone: "LOCAL", purpose: "Independently recomputes each QA/run vector to score correctness (k-vote majority)." },
  inspector: { model: "Gemma-4-31B", zone: "LOCAL", purpose: "Runs adversarial QA probes and the goal-fulfillment check." },
};
const seatModel = (s: string) => SEAT_INFO[s]?.model ?? s;
const seatZone = (s: string): Zone => SEAT_INFO[s]?.zone ?? "LOCAL";

const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);
const arr = <T = unknown>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const obj = (v: unknown): Record<string, unknown> =>
  (v != null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : {});

function readableText(v: unknown): string | undefined {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) {
    const parts = v.map(readableText).filter((item): item is string => Boolean(item));
    return parts.length ? parts.join(", ") : undefined;
  }
  if (v != null && typeof v === "object") {
    const value = v as Record<string, unknown>;
    for (const key of ["message", "detail", "description", "reason", "statement", "text", "title"]) {
      const preferred = readableText(value[key]);
      if (preferred) return preferred;
    }
    const parts = Object.entries(value)
      .map(([key, item]) => {
        const text = readableText(item);
        return text ? `${key}: ${text}` : undefined;
      })
      .filter((item): item is string => Boolean(item));
    return parts.length ? parts.join("; ") : undefined;
  }
  return undefined;
}

function textList(v: unknown): string[] {
  const values = Array.isArray(v) ? v : v == null ? [] : [v];
  return values.map(readableText).filter((item): item is string => Boolean(item));
}

function oracleVerdict(v: unknown): OracleVerdict {
  return ["match", "mismatch", "no_actual", "oracle_uncertain"].includes(str(v) ?? "")
    ? str(v) as OracleVerdict
    : "oracle_uncertain";
}

function goalVerdict(v: unknown): GoalVerdict {
  if (v === "failed") return "unfulfilled";
  return ["fulfilled", "partial", "unfulfilled"].includes(str(v) ?? "")
    ? str(v) as GoalVerdict
    : "unknown";
}

function runVerification(v: unknown): RunVerification {
  return ["passed", "failed", "unverified"].includes(str(v) ?? "")
    ? str(v) as RunVerification
    : "unverified";
}

/** Stringify a scope-ish value: backend consult scope is {only_regions:[...]}. */
function scopeText(v: unknown): string {
  if (typeof v === "string") return v;
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    if (Array.isArray(o.only_regions)) return (o.only_regions as string[]).join(", ");
    const vals = Object.values(o).filter((x) => typeof x === "string");
    if (vals.length) return vals.join(", ");
  }
  return "";
}

/** run:run_xyz -> run_xyz (for events that carry the id only in the scope). */
function scopeId(scope: string): string {
  const i = scope.indexOf(":");
  return i >= 0 ? scope.slice(i + 1) : scope;
}

function terminalPayload(raw: Raw, p: Record<string, unknown>, completed: boolean): RunTerminalPayload {
  const stats = obj(p.stats);
  const cost = obj(p.cost);
  const corpus = Object.keys(obj(p.corpus)).length ? obj(p.corpus) : obj(stats.corpus);
  let verification = runVerification(p.verification ?? stats.verification);
  const rawStatus = str(p.status) ?? str(stats.run_status);
  let status: RunTerminalStatus = ["done", "partial", "unverified", "failed"].includes(rawStatus ?? "")
    ? rawStatus as RunTerminalStatus
    : completed && verification === "passed" ? "done" : "unverified";
  if (status === "failed") verification = "failed";
  if (verification === "passed" && status !== "done") verification = "unverified";
  if (completed && verification !== "passed" && status === "done") status = "unverified";
  return {
    run_id: str(p.run_id) ?? scopeId(raw.scope),
    status,
    verification,
    reasons: textList(p.reasons ?? stats.verification_reasons),
    units: num(p.units) ?? num(stats.units) ?? 0,
    done: num(p.done) ?? num(stats.completed) ?? num(stats.processed_total) ?? num(stats.done) ?? 0,
    flagged: num(p.flagged) ?? num(stats.needs_review) ?? 0,
    cost_usd: num(p.cost_usd) ?? num(cost.total_usd) ?? null,
    gpu_seconds: num(p.gpu_seconds) ?? null,
    demo: p.demo === true || stats.demo === true || corpus.kind === "synthetic",
  };
}

const env = <T extends NxEvent>(raw: Raw, type: T["type"], payload: T["payload"]): T =>
  ({ seq: raw.seq, ts: raw.ts, scope: raw.scope, type, payload } as T);

/**
 * Normalize one raw backend event. Returns null for unknown types (the fold's
 * exhaustiveness guard would otherwise throw on a genuinely unknown event).
 */
export function normalizeEvent(raw: Raw): NxEvent | null {
  const p = (raw.payload ?? {}) as Record<string, unknown>;
  const t = raw.type;

  switch (t) {
    /* ---------- lifecycle ---------- */
    case "job.created":
      return env(raw, "job.created", {
        status: (str(p.status) as never) ?? "created",
        stage: toStage(p.stage, 0),
        title: str(p.title),
        mode: str(p.mode) as never,
      });
    case "job.stage_changed":
      return env(raw, "job.stage_changed", {
        status: (str(p.status) as never) ?? "planning",
        stage: toStage(p.stage, 0),
        title: str(p.title),
        mode: str(p.mode) as never,
      });
    case "job.blocked":
      return env(raw, "job.blocked", {
        status: "blocked",
        stage: toStage(p.stage, 0),
        reason: str(p.reason) ?? "blocked",
      });
    case "job.done":
      return env(raw, "job.done", {
        status: (str(p.status) as never) ?? "done",
        stage: toStage(p.stage, 7),
      });
    case "job.aborted":
      return env(raw, "job.aborted", {
        status: "aborted",
        stage: toStage(p.stage, 0),
        reason: str(p.reason) ?? "aborted",
      });

    /* ---------- stage 0 ---------- */
    case "intake.message":
      return env(raw, "intake.message", {
        role: (str(p.role) as never) ?? "customer",
        content: str(p.content) ?? str(p.text) ?? "",
      });
    case "intake.turn": {
      // backend shape: {ready: bool, missing: string[]} — voice it as a trust line
      const missing = arr<string>(p.missing);
      const content =
        str(p.content) ??
        (p.ready === true
          ? "Spec is complete — moving on."
          : missing.length
            ? `Still need: ${missing.join(", ")}.`
            : "Working through the spec with you.");
      return env(raw, "intake.message", { role: (str(p.role) as never) ?? "trust", content });
    }
    case "intake.spec_updated": {
      const spec = (p.spec ?? {}) as Record<string, unknown>;
      return env(raw, "intake.spec_updated", {
        spec: { summary: str(spec.summary) ?? str(p.title) ?? "", acceptance: arr<string>(spec.acceptance) },
      });
    }
    case "intake.classified":
    case "intake.mode_classified": // backend alias; carries {recommended}
      return env(raw, "intake.classified", {
        mode: (str(p.mode) as never) ?? (str(p.recommended) as never) ?? "build",
        rationale: str(p.rationale) ?? str(p.reason) ?? "",
      });
    case "intake.clarification_requested": {
      const KINDS = ["delivery", "threshold", "population", "scope"];
      const qs = arr<Record<string, unknown>>(p.questions).length
        ? arr<Record<string, unknown>>(p.questions)
        : arr<Record<string, unknown>>(p.clarifications);
      return env(raw, "intake.clarification_requested", {
        questions: qs.map((q, i) => ({
          id: str(q.id) ?? `q${i}`,
          question: str(q.question) ?? str(q.text) ?? "",
          kind: (KINDS.includes(str(q.kind) ?? "") ? str(q.kind) : "scope") as never,
          options: arr<string>(q.options).length ? arr<string>(q.options) : undefined,
          required: q.required !== false,
        })),
      });
    }
    case "intake.clarification_answered":
      return env(raw, "intake.clarification_answered", {
        answers: num(p.answers) ?? (arr(p.answers).length || undefined),
      });
    case "intake.policy_registered": {
      const split = (p.split ?? {}) as Record<string, unknown>;
      return env(raw, "intake.policy_registered", {
        sources: arr<never>(p.sources),
        rule_count: num(p.rule_count) ?? 0,
        split: {
          baseline: num(split.baseline) ?? num(p.baseline_rules) ?? 0,
          policy: num(split.policy) ?? num(p.policy_rules) ?? 0,
        },
        summary: str(p.summary),
      });
    }
    case "intake.context_mapped":
      return env(raw, "intake.context_mapped", {
        files: num(p.files) ?? 0,
        symbols: num(p.symbols) ?? 0,
        tables: num(p.tables) ?? 0,
        masked_identifiers: num(p.masked_identifiers) ?? 0,
      });
    case "boundary.sanitized": {
      const rules = arr<string>(p.policy_rules_applied);
      const pii = num(p.pii_fields_masked) ?? 0;
      const idg = num(p.identifiers_generalized) ?? 0;
      const vault = num(p.vault_size) ?? 0;
      const findings = (arr(p.findings) as never[]).length
        ? (p.findings as never[])
        : ([
            pii > 0 && { rule_id: rules[0] ?? "PII", label: "PII fields masked", count: pii, action: "masked" },
            idg > 0 && { rule_id: rules[1] ?? rules[0] ?? "RP", label: "Identifiers generalized", count: idg, action: "abstracted" },
          ].filter(Boolean) as never[]);
      const never_leaves = arr<string>(p.never_leaves).length
        ? arr<string>(p.never_leaves)
        : ([
            vault > 0 && `${vault} raw values sealed in vault`,
            pii > 0 && `${pii} PII fields`,
            idg > 0 && `${idg} generalized identifiers`,
          ].filter(Boolean) as string[]);
      return env(raw, "boundary.sanitized", {
        findings,
        never_leaves,
        brief_tokens: num(p.brief_tokens) ?? 0,
      });
    }

    case "boundary.sweep":
      // backend shape: {clean, residuals} (residuals = count)
      return env(raw, "boundary.sweep", {
        clean: p.clean !== false && !(num(p.findings) ?? num(p.residuals) ?? 0),
        checked: num(p.checked) ?? num(p.hosts) ?? num(p.endpoints),
        findings: num(p.findings) ?? num(p.residuals),
      });

    /* ---------- stage 1 ---------- */
    case "plan.started": {
      const sovereign = p.sovereign === true;
      return env(raw, "plan.started", {
        planner_model: str(p.planner_model) ?? (sovereign ? "GLM-4.6 (sovereign)" : "Frontier planner"),
        zone: (str(p.zone) as Zone) ?? (sovereign ? "LOCAL" : "EXTERNAL"),
      });
    }
    case "plan.delta":
      return env(raw, "plan.delta", { text: str(p.text) ?? str(p.delta) ?? "" });
    case "plan.completed": {
      const bomSeats = arr<Record<string, unknown>>(((p.bom ?? {}) as Record<string, unknown>).seats);
      const modules = num(p.modules) ?? 0;
      const topology = (str(p.topology) ?? str(p.topology_archetype) ?? "interdependent") as never;
      const bom = arr(p.bom).length
        ? (p.bom as never[])
        : (bomSeats.map((s) => ({
            seat: (str(s.seat) ?? "coder") as Seat,
            model: str(s.model) ?? seatModel(str(s.seat) ?? ""),
            count: num(s.count) ?? 1,
            why: str(s.why) ?? "",
            zone: (str(s.zone) as Zone) ?? seatZone(str(s.seat) ?? ""),
          })) as never[]);
      return env(raw, "plan.completed", {
        summary: str(p.summary) ?? `Decomposed into ${modules} modules with ${topology} topology.`,
        topology,
        modules,
        bom,
      });
    }

    case "plan.replanned": {
      // backend shape: {only_regions, added_regions} (string arrays)
      const only = arr<string>(p.only_regions);
      const added = arr<string>(p.added_regions);
      const built = [
        only.length ? `scoped to ${only.join(", ")}` : "",
        added.length ? `added ${added.join(", ")}` : "",
      ].filter(Boolean).join(" · ");
      return env(raw, "plan.replanned", {
        note: str(p.note) ?? str(p.summary) ?? str(p.reason) ?? (built || undefined),
        wave: num(p.wave),
      });
    }

    /* ---------- stage 2 ---------- */
    case "certify.check_started":
      return env(raw, "certify.check_started", { check: str(p.check) ?? "check" });
    case "certify.check_completed":
      return env(raw, "certify.check_completed", { check: str(p.check) ?? "check" });
    case "certify.scenarios_emitted":
      return env(raw, "certify.scenarios_emitted", {
        count: num(p.count) ?? num(p.scenarios) ?? arr(p.scenarios).length,
      });
    case "certify.rehydrated":
      return env(raw, "certify.rehydrated", {
        identifiers: num(p.identifiers) ?? num(p.identifiers_rehydrated) ?? num(p.count) ?? 0,
      });
    case "certify.consult_requested":
      // backend shape: {finding_id, only_regions}
      return env(raw, "certify.consult_requested", {
        id: str(p.id) ?? str(p.consult_id) ?? str(p.finding_id) ?? `cns_${raw.seq}`,
        scope: scopeText(p.scope) || (Array.isArray(p.only_regions) ? (p.only_regions as string[]).join(", ") : undefined),
        reason: str(p.reason) ?? str(p.why) ?? str(p.question) ?? str(p.finding_id),
      });
    case "certify.finding":
      return env(raw, "certify.finding", {
        check: str(p.check) ?? "check",
        finding: str(p.finding) ?? [str(p.finding_id), str(p.triage)].filter(Boolean).join(" · ") ?? "",
        severity: str(p.severity) === "minor" ? "minor" : "structural",
      });
    case "certify.amendment":
      return env(raw, "certify.amendment", {
        id: str(p.id) ?? `amd_${raw.seq}`,
        origin: "certifier",
        summary: str(p.summary) ?? str(p.rationale) ?? "",
        hash: str(p.hash) ?? "",
        prev_hash: str(p.prev_hash) ?? "",
        region: str(p.region) ?? str(p.plan_ref),
      });
    case "conductor.amendment":
      return env(raw, "conductor.amendment", {
        id: str(p.id) ?? `amd_${raw.seq}`,
        origin: "conductor",
        summary: str(p.summary) ?? str(p.rationale) ?? "",
        hash: str(p.hash) ?? "",
        prev_hash: str(p.prev_hash) ?? "",
        region: str(p.region) ?? str(p.plan_ref),
      });
    case "certify.consult_opened": {
      const r = (p.sanitization_receipt ?? {}) as Record<string, unknown>;
      const rules = arr<string>(r.rules_applied).length
        ? arr<string>(r.rules_applied)
        : ([
            str(r.data_class) ?? "SANITIZED",
            num(r.known_values_remasked) ? `${num(r.known_values_remasked)} remasked` : undefined,
          ].filter(Boolean) as string[]);
      return env(raw, "certify.consult_opened", {
        id: str(p.id) ?? str(p.consult_id) ?? `cns_${raw.seq}`,
        scope: scopeText(p.scope),
        round: num(p.round) ?? 1,
        sanitization_receipt: { rules_applied: rules, brief_tokens: num(r.brief_tokens) ?? 0 },
      });
    }
    case "certify.consult_resolved":
      return env(raw, "certify.consult_resolved", {
        id: str(p.id) ?? str(p.consult_id) ?? `cns_${raw.seq}`,
        round: num(p.round) ?? 1,
        resolution: str(p.resolution) ?? "resolved",
      });
    case "certify.consult_repaired":
      return env(raw, "certify.consult_repaired", {
        id: str(p.id) ?? str(p.consult_id) ?? `cns_${raw.seq}`,
        round: num(p.round),
        note: str(p.note) ?? str(p.detail) ?? "scope-lock auto-repaired to a valid region",
      });
    case "plan.scope_violation":
      return env(raw, "plan.scope_violation", {
        region: str(p.region) ?? (Array.isArray(p.only_regions) ? (p.only_regions as string[]).join(", ") : undefined),
        detail: str(p.detail) ?? str(p.reason) ?? "out-of-scope re-plan edit rejected",
        wave: num(p.wave),
      });
    case "certify.goal_set":
      return env(raw, "certify.goal_set", { goal: str(p.goal) ?? "" });
    case "certify.certified":
      return env(raw, "certify.certified", {
        tests: num(p.tests) ?? 0,
        vectors: num(p.vectors) ?? 0,
        identifiers_rehydrated: num(p.identifiers_rehydrated) ?? 0,
        deferred_consults: num(p.deferred_consults),
      });
    case "certify.blocked":
      return env(raw, "certify.blocked", { reason: str(p.reason) ?? "blocked at certification" });

    /* ---------- stage 3 ---------- */
    case "quote.issued": {
      const lines = arr<Record<string, unknown>>(p.lines).map((l) => ({
        label: str(l.label) ?? str(l.item) ?? "",
        detail: str(l.detail) ?? str(l.qty) ?? "",
        amount_usd: num(l.amount_usd) ?? (Array.isArray(l.est_usd) ? num((l.est_usd as unknown[])[1]) ?? 0 : 0),
      }));
      const total = p.total_est_usd as unknown[] | undefined;
      return env(raw, "quote.issued", {
        lines,
        low_usd: num(p.low_usd) ?? (total ? num(total[0]) ?? 0 : 0),
        high_usd: num(p.high_usd) ?? (total ? num(total[1]) ?? 0 : 0),
      });
    }
    case "quote.approved":
      return env(raw, "quote.approved", { approved_usd: num(p.approved_usd) ?? num(p.total) ?? 0 });

    /* ---------- fleet ---------- */
    case "fleet.profile_requested":
      return env(raw, "fleet.profile_requested", {
        profile: str(p.profile) ?? "P1",
        nodes: num(p.nodes) ?? 1,
        seats: arr<never>(p.seats),
      });
    case "fleet.node_ready":
      return env(raw, "fleet.node_ready", {
        node: str(p.node) ?? "A",
        gpus: num(p.gpus) ?? 8,
        seats: arr<never>(p.seats),
      });
    case "fleet.node_down":
      return env(raw, "fleet.node_down", {
        node: str(p.node) ?? "A",
        gpus: num(p.gpus) ?? 8,
        seats: arr<never>(p.seats),
      });

    /* ---------- stage 4 ---------- */
    case "task.started": {
      const routing = (p.routing ?? {}) as Record<string, unknown>;
      const flags = arr<string>(routing.flags);
      const seat = (str(p.seat) ?? "coder") as Seat;
      return env(raw, "task.started", {
        module: str(p.module) ?? str(p.task) ?? "module",
        backend: str(p.backend) ?? str(routing.chosen) ?? "local",
        seat,
        zone: (str(p.zone) as Zone) ?? "LOCAL",
        wave: num(p.wave) ?? 0,
        why: str(p.why) ?? (flags.length ? `${flags.join(", ")} · ${str(routing.reason) ?? "capability match"}` : str(routing.reason) ?? ""),
        task: str(p.task),
      });
    }
    case "task.output_delta":
      return env(raw, "task.output_delta", {
        module: str(p.module) ?? "module",
        text: str(p.text) ?? str(p.delta) ?? "",
      });
    case "task.tests":
      return env(raw, "task.tests", {
        module: str(p.module) ?? "module",
        passed: num(p.passed) ?? 0,
        failed: num(p.failed) ?? 0,
        total: num(p.total) ?? (num(p.passed) ?? 0) + (num(p.failed) ?? 0),
        verification: runVerification(p.verification),
        sandboxed: p.sandboxed === true,
        reason: readableText(p.reason) ?? null,
      });
    case "task.completed":
      return env(raw, "task.completed", {
        module: str(p.module) ?? "module",
        ok: p.ok !== false,
        loc: num(p.loc) ?? (arr(p.files).length ? arr(p.files).length : undefined),
        reason: str(p.notes) ?? str(p.reason),
      });
    case "task.failed":
      return env(raw, "task.failed", {
        module: str(p.module) ?? "module",
        ok: false,
        reason: str(p.reason) ?? str(p.notes),
      });
    case "task.fix_applied": {
      // backend shape: {ticket: title string, files: paths[]}
      const ticket = str(p.ticket);
      const files = arr<string>(p.files);
      const module = str(p.module) ?? str(p.task) ?? ticket ?? "module";
      return env(raw, "task.fix_applied", {
        module,
        note:
          str(p.note) ?? str(p.fix) ?? str(p.summary) ??
          (ticket && ticket !== module ? ticket : undefined) ??
          (files.length ? `${files.length} file${files.length === 1 ? "" : "s"} touched` : undefined),
      });
    }
    case "task.files_written":
      return env(raw, "task.files_written", {
        module: str(p.module) ?? str(p.task) ?? "module",
        files: num(p.files) ?? num(p.count) ?? arr(p.files).length,
      });
    case "conductor.goal_drift":
      // backend shape: {description}
      return env(raw, "conductor.goal_drift", {
        wave: num(p.wave),
        drift: num(p.drift) ?? num(p.goal_drift) ?? null,
        note: str(p.note) ?? str(p.description) ?? str(p.assessment) ?? str(p.detail),
      });
    case "conductor.wave_started":
      return env(raw, "conductor.wave_started", {
        wave: num(p.wave) ?? 1,
        of: num(p.of) ?? 1,
        modules: arr<string>(p.modules).length ? arr<string>(p.modules) : arr<string>(p.tasks),
        tasks: arr<string>(p.tasks),
      });
    case "conductor.review":
      return env(raw, "conductor.review", {
        wave: num(p.wave) ?? 1,
        verdict: (str(p.verdict) as never) ?? "green",
        goal_drift: num(p.goal_drift) ?? null,
        note: str(p.note) ?? str(p.assessment) ?? "",
      });
    case "conductor.green_flag":
      return env(raw, "conductor.green_flag", { wave: num(p.wave) ?? 1 });

    /* ---------- stage 5 ---------- */
    case "consolidate.started":
      return env(raw, "consolidate.started", { modules: num(p.modules) ?? 0 });
    case "consolidate.test_run":
      return env(raw, "consolidate.test_run", {
        passed: num(p.passed) ?? 0,
        failed: num(p.failed) ?? 0,
        total: num(p.total) ?? (num(p.passed) ?? 0) + (num(p.failed) ?? 0),
        verification: runVerification(p.verification),
        sandboxed: p.sandboxed === true,
        reason: readableText(p.reason) ?? null,
      });
    case "consolidate.completed":
      return env(raw, "consolidate.completed", {
        passed: num(p.passed) ?? 0,
        total: num(p.total) ?? 0,
        verification: runVerification(p.verification),
        sandboxed: p.sandboxed === true,
      });

    /* ---------- stage 6 ---------- */
    case "qa.inspector_started":
      return env(raw, "qa.inspector_started", {
        scenario: str(p.scenario) ?? (num(p.agents) ? `${num(p.agents)} inspectors staged` : "inspectors staged"),
        seat: "inspector",
      });
    case "qa.probe":
      return env(raw, "qa.probe", {
        scenario: str(p.scenario) ?? "scenario",
        probe: str(p.probe) ?? (p.found === true ? "found" : "clear"),
      });
    case "qa.probe_started":
    case "qa.probe_passed":
    case "qa.probe_timeout":
    case "qa.probe_exhausted":
      // backend shapes: started {scenario, source}; others {scenario, steps}
      return env(raw, "qa.probe_update", {
        scenario: str(p.scenario) ?? str(p.check) ?? "scenario",
        probe: str(p.probe) ?? str(p.name) ?? str(p.scenario) ?? "probe",
        status: t.slice("qa.probe_".length) as never,
        detail:
          str(p.detail) ?? str(p.reason) ??
          (num(p.steps) != null ? `${num(p.steps)} steps` : str(p.source)),
      });
    case "qa.oracle_vote": {
      // backend shape: {vector, votes: array, expected, uncertain: bool}
      const votes = arr(p.votes);
      return env(raw, "qa.oracle_vote", {
        vector: str(p.vector) ?? "V",
        vote:
          p.uncertain === true ? "uncertain"
          : votes.length ? votes.map(String).join("/")
          : str(p.vote) ?? str(p.verdict) ?? "vote",
        round: num(p.round) ?? num(p.k),
      });
    }
    case "qa.finding":
      return env(raw, "qa.finding", {
        scenario: str(p.scenario) ?? "scenario",
        result: str(p.result) === "clear" ? "clear" : p.result === "flag" || p.severity ? "flag" : "clear",
        detail: str(p.detail) ?? str(p.severity),
      });
    case "qa.oracle_check":
      return env(raw, "qa.oracle_check", {
        vector: str(p.vector) ?? "V",
        verdict: oracleVerdict(p.verdict),
        model: str(p.model) ?? "not reported",
      });
    case "qa.goal_check":
      return env(raw, "qa.goal_check", {
        verdict: goalVerdict(p.verdict),
        gaps: textList(p.gaps),
      });
    case "qa.completed":
      return env(raw, "qa.completed", {
        verification: runVerification(p.verification),
        reasons: textList(p.reasons),
        demo_override: p.demo_override === true,
      });
    case "qa.passed":
      return env(raw, "qa.passed", {
        scenarios: num(p.scenarios) ?? num(p.vectors) ?? 0,
        probes: num(p.probes) ?? 0,
        tickets_resolved: num(p.tickets_resolved) ?? num(p.flagged_for_review) ?? 0,
      });

    /* ---------- tickets ---------- */
    case "ticket.opened":
    case "ticket.in_fix":
    case "ticket.fix_applied": // {ticket_id, retested:false} — fix landed, not yet retested
    case "ticket.verified":
    case "ticket.human_review":
    case "warranty.ticket": {
      const status =
        t === "ticket.in_fix" ? "in_fix"
        : t === "ticket.fix_applied" ? "fix_applied"
        : t === "ticket.verified" ? "verified"
        : t === "ticket.human_review" ? "human_review"
        : "opened";
      const source = (str(p.source) ?? (t === "warranty.ticket" ? "warranty" : "inspector")) as never;
      const title =
        str(p.title) ??
        (str(p.unit) ? `warranty: ${str(p.unit)}` : undefined) ??
        (str(p.reason) ? `${source}: ${str(p.reason)}` : undefined) ??
        `${source} finding`;
      return env(raw, t, {
        id: str(p.id) ?? str(p.ticket_id) ?? `tkt_${raw.seq}`,
        title,
        status,
        severity: (str(p.severity) as never) ?? "medium",
        source,
        scope: str(p.scope) ?? raw.scope,
      });
    }

    /* ---------- stage 7 + operate ---------- */
    case "deliver.registered": {
      const pkg = Object.keys(obj(p.package)).length ? obj(p.package) : obj(p.package_summary);
      const verification = p.verification === "passed" ? "passed" : "unverified";
      const demoOverride = p.demo_override === true;
      const rawLabel = str(p.delivery_label);
      return env(raw, "deliver.registered", {
        process_id: str(p.process_id) ?? "",
        version: num(p.version) ?? 1,
        package: {
          plan: pkg.plan === true,
          docs: pkg.docs === true,
          qa_report: pkg.qa_report === true,
          tests: num(pkg.tests) ?? num(pkg.test_specs) ?? 0,
        },
        frontier_calls: num(p.frontier_calls),
        invoice_total_usd: num(p.invoice_total_usd),
        goal_verdict: p.goal_verdict == null ? undefined : goalVerdict(p.goal_verdict),
        verification,
        verification_reasons: textList(p.verification_reasons ?? p.reasons),
        demo_override: demoOverride,
        delivery_label: verification === "passed"
          ? rawLabel ?? "VERIFIED"
          : rawLabel && rawLabel !== "VERIFIED" ? rawLabel : demoOverride ? "UNVERIFIED DEMO" : "UNVERIFIED",
      });
    }
    case "deliver.docs_generated": {
      // backend shape: {readme_chars, runbook_chars}
      const named = arr<string>(p.docs).length ? arr<string>(p.docs) : arr<string>(p.files);
      const docs = named.length
        ? named
        : ([num(p.readme_chars) && "README", num(p.runbook_chars) && "runbook"].filter(Boolean) as string[]);
      return env(raw, "deliver.docs_generated", { docs });
    }
    case "run.started": {
      const corpus = obj(p.corpus);
      return env(raw, "run.started", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        units: num(p.units) ?? num(p.total) ?? 0,
        demo: p.demo === true || p.synthetic === true || corpus.kind === "synthetic",
      });
    }
    case "run.artifacts_ready":
      return env(raw, "run.artifacts_ready", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        verification: p.verification === "passed" ? "passed" : "unverified",
        degraded: p.degraded === true || p.verification !== "passed",
        reason: readableText(p.reason) ?? null,
        artifacts: arr<Record<string, unknown>>(p.artifacts).map((a) => ({
          kind: str(a.kind) ?? "report",
          url: str(a.url) ?? "",
        })),
      });
    case "run.sql_step":
      return env(raw, "run.sql_step", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        step: str(p.step),
        label: str(p.label) ?? str(p.step) ?? "sql step",
        rows: num(p.rows) ?? 0,
      });
    case "tool.created":
      return env(raw, "tool.created", {
        name: str(p.name) ?? "tool",
        description: str(p.description),
        agent: str(p.agent) ?? str(p.created_by_seat),
      });
    case "tool.invoked":
      return env(raw, "tool.invoked", {
        name: str(p.name) ?? "tool",
        ms: num(p.ms) ?? num(p.latency_ms),
        ok: p.ok !== false,
      });
    case "run.unit_completed":
      return env(raw, "run.unit_completed", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        unit: str(p.unit) ?? (num(p.unit_index) != null ? String(num(p.unit_index)) : "unit"),
        result: str(p.result) ?? str(p.status) ?? "",
      });
    case "run.progress":
      return env(raw, "run.progress", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        done: num(p.done) ?? 0,
        total: num(p.total) ?? 0,
      });
    case "run.spotcheck":
      return env(raw, "run.spotcheck", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        unit: str(p.unit) ?? (num(p.unit_index) != null ? String(num(p.unit_index)) : "unit"),
        verdict: ["match", "mismatch", "inconclusive"].includes(str(p.verdict) ?? "")
          ? str(p.verdict) as "match" | "mismatch" | "inconclusive"
          : "inconclusive",
      });
    case "run.finished":
      return env(raw, "run.finished", terminalPayload(raw, p, false));
    case "run.completed":
      return env(raw, "run.completed", terminalPayload(raw, p, true));
    case "refine.triaged":
      return env(raw, "refine.triaged", {
        verdict: str(p.verdict) === "consult" ? "consult" : "amend",
        note: str(p.note) ?? str(p.rationale) ?? "",
      });
    case "refine.version_created":
      return env(raw, "refine.version_created", {
        version: num(p.version) ?? 1,
        diff_summary: str(p.diff_summary) ?? str(p.triage) ?? "",
      });
    case "review.decided":
      return env(raw, "review.decided", {
        unit: str(p.unit) ?? "unit",
        verdict: str(p.verdict) === "reject" ? "reject" : "approve",
      });

    /* ---------- router / meter / egress / telemetry ---------- */
    case "model.call": {
      const zone = (str(p.zone) as Zone) ?? "LOCAL";
      return env(raw, "model.call", {
        seat: (str(p.seat) ?? "coder") as Seat,
        backend: str(p.backend) ?? str(p.model) ?? "local",
        zone,
        data_class: (str(p.data_class) as DataClass) ?? (zone === "EXTERNAL" ? "SANITIZED" : "RAW"),
        tokens_in: num(p.tokens_in) ?? 0,
        tokens_out: num(p.tokens_out) ?? 0,
        cost_usd: num(p.cost_usd) ?? 0,
      });
    }
    case "model.trace": {
      const zone = (str(p.zone) as Zone) ?? "LOCAL";
      return env(raw, "model.trace", {
        id: str(p.id) ?? str(p.trace_id),
        seat: (str(p.seat) ?? "coder") as Seat,
        backend: str(p.backend) ?? str(p.model) ?? "local",
        zone,
        tokens_in: num(p.tokens_in) ?? 0,
        tokens_out: num(p.tokens_out) ?? 0,
        cost_usd: num(p.cost_usd) ?? 0,
        latency_ms: num(p.latency_ms),
        badge: str(p.badge),
      });
    }
    case "meter.tick":
      return env(raw, "meter.tick", {
        scope: raw.scope,
        cost_usd: num(p.cost_usd) ?? 0,
        tokens: num(p.tokens) ?? (num(p.tokens_in) ?? 0) + (num(p.tokens_out) ?? 0),
        gpu_seconds: num(p.gpu_seconds) ?? 0,
      });
    case "egress.request": {
      const zone = (str(p.zone) as Zone) ?? "LOCAL";
      return env(raw, "egress.request", {
        host: str(p.host) ?? "fleet.local",
        zone,
        seat: (str(p.seat) ?? "trust") as Seat,
        // only tag the designed-in crossing so the monitor stays legible
        data_class: (zone === "EXTERNAL" ? "SANITIZED" : (str(p.data_class) as DataClass)) as never,
        bytes: num(p.bytes) ?? num(p.bytes_out) ?? 0,
      });
    }
    case "egress.violation":
      return env(raw, "egress.violation", {
        host: str(p.host) ?? "external.endpoint",
        zone: (str(p.zone) as Zone) ?? "EXTERNAL",
        detail: str(p.detail) ?? str(p.reason) ?? "External call blocked under Sovereign Mode.",
      });
    case "telemetry.gpu":
      return env(raw, "telemetry.gpu", {
        node: str(p.node) ?? "A",
        gpu: num(p.gpu) ?? 0,
        vram_used_gb: num(p.vram_used_gb) ?? 0,
        vram_total_gb: num(p.vram_total_gb) ?? 1,
        util: num(p.util) ?? 0,
        power_w: num(p.power_w) ?? 0,
        toks_per_s: num(p.toks_per_s) ?? num(p.tokens_per_s) ?? 0,
        gpus: num(p.gpus),
      });

    /* ---------- sandbox / config / notices ---------- */
    case "sandbox.queued":
      return env(raw, "sandbox.queued", { position: num(p.position) ?? 0 });
    case "sandbox.started":
      return env(raw, "sandbox.started", { position: num(p.position) ?? 0 });
    case "config.connection_added":
      return env(raw, "config.connection_added", {
        name: str(p.name) ?? "connection",
        host: str(p.host) ?? str(p.base_url) ?? "",
        zone: (str(p.zone) as Zone) ?? "CUSTOM",
      });
    case "config.model_registered":
      return env(raw, "config.model_registered", {
        model: str(p.model) ?? str(p.display_name) ?? "model",
        flags: arr<string>(p.flags),
      });
    case "config.seat_bound":
      return env(raw, "config.seat_bound", {
        seat: (str(p.seat) ?? "coder") as Seat,
        model_key: str(p.model_key) ?? "",
        scope: str(p.scope) ?? "global",
      });
    case "system.notice":
      return env(raw, "system.notice", {
        text: str(p.text) ?? "",
        level: (str(p.level) as never) ?? "info",
      });

    default:
      return null;
  }
}
