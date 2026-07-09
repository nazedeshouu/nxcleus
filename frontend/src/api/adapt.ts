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
import type { NxEvent, Stage, Zone, DataClass, Seat } from "../lib/events";

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
  "certify.goal_set", "certify.certified", "certify.blocked",
  "quote.issued", "quote.approved",
  "fleet.profile_requested", "fleet.node_ready", "fleet.node_down",
  "task.started", "task.output_delta", "task.tests", "task.completed", "task.failed",
  "conductor.wave_started", "conductor.review", "conductor.amendment", "conductor.green_flag",
  "consolidate.started", "consolidate.test_run", "consolidate.completed",
  "qa.inspector_started", "qa.probe", "qa.finding", "qa.goal_check", "qa.oracle_check", "qa.passed",
  "ticket.opened", "ticket.in_fix", "ticket.verified", "ticket.human_review",
  "deliver.registered",
  "run.started", "run.unit_completed", "run.progress", "run.spotcheck", "run.completed",
  "warranty.ticket", "refine.triaged", "refine.version_created", "review.decided",
  "model.call", "meter.tick", "egress.request", "egress.violation", "telemetry.gpu",
  "sandbox.queued", "sandbox.started",
  "config.connection_added", "config.model_registered", "config.seat_bound",
  "system.notice",
];

/* backend sometimes sends a status-name where a numeric stage belongs */
const STAGE_BY_NAME: Record<string, Stage> = {
  created: 0, intake: 0,
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

/** Display model + zone per seat, sourced from infra/models.yaml semantics. */
const SEAT_INFO: Record<string, { model: string; zone: Zone }> = {
  trust: { model: "Gemma-4-26B", zone: "LOCAL" },
  planner: { model: "Frontier planner", zone: "EXTERNAL" },
  certifier: { model: "GLM-4.6", zone: "LOCAL" },
  conductor: { model: "GLM-4.6", zone: "LOCAL" },
  coder: { model: "Qwen3-Coder", zone: "LOCAL" },
  consolidator: { model: "GLM-4.6", zone: "LOCAL" },
  oracle: { model: "Gemma-4-31B", zone: "LOCAL" },
  inspector: { model: "Gemma-4-31B", zone: "LOCAL" },
};
const seatModel = (s: string) => SEAT_INFO[s]?.model ?? s;
const seatZone = (s: string): Zone => SEAT_INFO[s]?.zone ?? "LOCAL";

const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);
const arr = <T = unknown>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

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
        content: str(p.content) ?? "",
      });
    case "intake.spec_updated": {
      const spec = (p.spec ?? {}) as Record<string, unknown>;
      return env(raw, "intake.spec_updated", {
        spec: { summary: str(spec.summary) ?? str(p.title) ?? "", acceptance: arr<string>(spec.acceptance) },
      });
    }
    case "intake.classified":
      return env(raw, "intake.classified", {
        mode: (str(p.mode) as never) ?? "build",
        rationale: str(p.rationale) ?? "",
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

    /* ---------- stage 2 ---------- */
    case "certify.check_started":
      return env(raw, "certify.check_started", { check: str(p.check) ?? "check" });
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
    case "certify.goal_set":
      return env(raw, "certify.goal_set", { goal: str(p.goal) ?? "" });
    case "certify.certified":
      return env(raw, "certify.certified", {
        tests: num(p.tests) ?? 0,
        vectors: num(p.vectors) ?? 0,
        identifiers_rehydrated: num(p.identifiers_rehydrated) ?? 0,
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
      });
    case "consolidate.completed":
      return env(raw, "consolidate.completed", { passed: num(p.passed) ?? 0, total: num(p.total) ?? 0 });

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
    case "qa.finding":
      return env(raw, "qa.finding", {
        scenario: str(p.scenario) ?? "scenario",
        result: str(p.result) === "clear" ? "clear" : p.result === "flag" || p.severity ? "flag" : "clear",
        detail: str(p.detail) ?? str(p.severity),
      });
    case "qa.oracle_check":
      return env(raw, "qa.oracle_check", {
        vector: str(p.vector) ?? "V",
        verdict: str(p.verdict) === "mismatch" ? "mismatch" : "match",
        model: str(p.model) ?? "Gemma-4-31B (lineage-independent)",
      });
    case "qa.goal_check":
      return env(raw, "qa.goal_check", {
        verdict: (str(p.verdict) as never) ?? "fulfilled",
        gaps: arr<string>(p.gaps),
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
    case "ticket.verified":
    case "ticket.human_review":
    case "warranty.ticket": {
      const status =
        t === "ticket.in_fix" ? "in_fix"
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
      const pkg = (p.package ?? {}) as Record<string, unknown>;
      return env(raw, "deliver.registered", {
        process_id: str(p.process_id) ?? "",
        version: num(p.version) ?? 1,
        package: {
          plan: pkg.plan !== false,
          docs: pkg.docs !== false,
          qa_report: pkg.qa_report !== false,
          tests: num(pkg.tests) ?? 0,
        },
        frontier_calls: num(p.frontier_calls),
        invoice_total_usd: num(p.invoice_total_usd),
        goal_verdict: str(p.goal_verdict) as never,
      });
    }
    case "run.started":
      return env(raw, "run.started", {
        run_id: str(p.run_id) ?? scopeId(raw.scope),
        units: num(p.units) ?? num(p.total) ?? 0,
      });
    case "run.unit_completed":
      return env(raw, "run.unit_completed", {
        unit: str(p.unit) ?? "unit",
        result: str(p.result) ?? str(p.status) ?? "",
      });
    case "run.progress":
      return env(raw, "run.progress", { done: num(p.done) ?? 0, total: num(p.total) ?? 0 });
    case "run.spotcheck":
      return env(raw, "run.spotcheck", {
        unit: str(p.unit) ?? "unit",
        verdict: str(p.verdict) === "mismatch" ? "mismatch" : "match",
      });
    case "run.completed": {
      const stats = (p.stats ?? {}) as Record<string, unknown>;
      const cost = (p.cost ?? {}) as Record<string, unknown>;
      return env(raw, "run.completed", {
        units: num(p.units) ?? num(stats.units) ?? 0,
        flagged: num(p.flagged) ?? num(stats.needs_review) ?? 0,
        cost_usd: num(p.cost_usd) ?? num(cost.total_usd) ?? 0,
        gpu_seconds: num(p.gpu_seconds) ?? 0,
      });
    }
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
