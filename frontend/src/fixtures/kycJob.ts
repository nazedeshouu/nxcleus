/**
 * A full KYC/AML onboarding job as an ordered event stream (06 §3).
 * Folds through the exact same store as live SSE, so the Build view renders a
 * complete stage-0→7 lifecycle from this alone. Doubles as the replay engine.
 */
import type { NxEvent } from "../lib/events";

export const KYC_JOB_ID = "job_01JKYCDEMO0000000000000001";
const SCOPE = `job:${KYC_JOB_ID}`;

let SEQ = 0;
let T = Date.parse("2026-07-09T14:00:00Z");
const EV: NxEvent[] = [];

function push<T extends NxEvent["type"]>(type: T, payload: Extract<NxEvent, { type: T }>["payload"], dtMs = 400) {
  T += dtMs;
  SEQ += 1;
  EV.push({ seq: SEQ, ts: new Date(T).toISOString(), scope: SCOPE, type, payload } as NxEvent);
}

// running cost accrual
let cost = 0;
let toks = 0;
let gpus = 0;
function meter(dc = 6, dt = 30, dg = 22) {
  cost = +(cost + dc / 100).toFixed(2);
  toks += dt * 137;
  gpus += dg;
  push("meter.tick", { scope: SCOPE, cost_usd: cost, tokens: toks, gpu_seconds: gpus }, 120);
}
function call(seat: any, backend: string, zone: any, dc: any, ti: number, to: number, usd: number) {
  push("model.call", { seat, backend, zone, data_class: dc, tokens_in: ti, tokens_out: to, cost_usd: usd }, 90);
}
let hprev = "genesis";
function amend(origin: "certifier" | "conductor", summary: string, region?: string) {
  const hash = ((SEQ * 2654435761) % 0xffffff).toString(16).padStart(6, "0");
  push(origin === "certifier" ? "certify.amendment" : "conductor.amendment", { id: `am_${SEQ}`, origin, summary, hash, prev_hash: hprev, region }, 260);
  hprev = hash;
}
// GPU telemetry pulse across the 8x MI300X droplet
const NODES = [
  { node: "amd-mi300x-A", gpu: 0 },
  { node: "amd-mi300x-A", gpu: 1 },
  { node: "amd-mi300x-B", gpu: 0 },
  { node: "amd-mi300x-B", gpu: 1 },
];
function tele(busy = 0.6) {
  for (const n of NODES) {
    const util = Math.min(99, Math.round(30 + busy * (52 + Math.random() * 16)));
    push("telemetry.gpu", {
      node: n.node, gpu: n.gpu,
      vram_used_gb: +(90 + busy * 80 + Math.random() * 12).toFixed(1),
      vram_total_gb: 192,
      util,
      power_w: Math.round(360 + busy * 340 + Math.random() * 60),
      toks_per_s: Math.round(700 + busy * 3200 + Math.random() * 400),
    }, 60);
  }
}

/* ---------- stage 0: intake, policy, boundary ---------- */
push("job.created", { status: "created", stage: 0, title: "KYC / AML customer onboarding", mode: "build" }, 0);
push("job.stage_changed", { status: "intake", stage: 0, title: "KYC / AML customer onboarding" }, 200);
push("intake.message", { role: "customer", content: "Onboard new retail customers: verify ID documents, screen against OFAC and EU sanctions, check PEP and adverse media, score risk, and produce an auditable case file per applicant." });
push("intake.message", { role: "trust", content: "Understood. I'll treat every raw document and identifier as confidential. Do you have a confidentiality policy I should apply on top of the standard PII baseline?" });
push("intake.message", { role: "customer", content: "Yes, attaching our data-handling policy. Customer PII and internal account IDs must never leave our infrastructure." });
tele(0.2);
push("intake.policy_registered", { sources: ["document", "typed"], rule_count: 14, split: { baseline: 9, policy: 5 }, summary: "PII baseline + 5 customer clauses: no raw identifiers, no account numbers, no document images off-box." });
push("intake.context_mapped", { files: 3, symbols: 0, tables: 4, masked_identifiers: 128 });
push("intake.spec_updated", { spec: { summary: "Document intake → OCR → sanctions + PEP + adverse-media screening → risk scoring → audited case file.", acceptance: ["Every applicant yields a case file with a decision and evidence trail", "Sanctions matches cite the list and entry", "No raw PII crosses the boundary"] } });
call("trust", "local:B/gemma-4-26b-a4b-it", "LOCAL", "RAW", 4200, 900, 0.0);
push("intake.classified", { mode: "build", rationale: "A reusable pipeline with typed stages and tests fits build mode; the process runs forever on new applicants." });
push("boundary.sanitized", {
  findings: [
    { rule_id: "PII-01", label: "Full names", count: 42, action: "masked" },
    { rule_id: "PII-04", label: "National ID numbers", count: 42, action: "abstracted" },
    { rule_id: "POL-02", label: "Internal account IDs", count: 44, action: "dropped" },
    { rule_id: "POL-05", label: "Document scans", count: 3, action: "dropped" },
  ],
  never_leaves: ["Applicant names & IDs", "Account numbers", "Document images", "Any raw record"],
  brief_tokens: 1840,
}, 500);
push("job.stage_changed", { status: "planning", stage: 1 }, 300);

/* ---------- stage 1: planning (the one boundary crossing) ---------- */
push("plan.started", { planner_model: "anthropic:claude-fable-5", zone: "EXTERNAL" }, 200);
push("egress.request", { host: "api.anthropic.com", zone: "EXTERNAL", seat: "planner", data_class: "SANITIZED", bytes: 8420 });
const planChunks = [
  "Topology: interdependent build. ",
  "Six modules with typed interfaces. ",
  "1) document-intake (OCR + field extraction), ",
  "2) sanctions-screen (OFAC + EU consolidated list matcher), ",
  "3) pep-screen, 4) adverse-media, ",
  "5) risk-score (weighted model over screening signals), ",
  "6) case-file (assembles evidence + decision + audit trail). ",
  "Model BoM: coder pool ×3 for modules, ",
  "data-model seat for the list matcher, ",
  "oracle sampling at 5% on risk scores. ",
];
for (const c of planChunks) push("plan.delta", { text: c }, 130);
call("planner", "anthropic:claude-fable-5", "EXTERNAL", "SANITIZED", 1840, 2600, 0.21);
push("plan.completed", {
  summary: "Interdependent 6-module KYC pipeline with typed interfaces, list-matcher over public OFAC/EU data, and a weighted risk model.",
  topology: "interdependent",
  modules: 6,
  bom: [
    { seat: "coder", model: "Qwen3-Coder-Next", count: 3, why: "greenfield-codegen · typed module interfaces", zone: "LOCAL" },
    { seat: "coder", model: "Devstral-Small-2", count: 1, why: "sql-data · list-matcher over OFAC/EU tables", zone: "LOCAL" },
    { seat: "certifier", model: "GLM-4.6", count: 1, why: "plan completion + certification against raw context", zone: "LOCAL" },
    { seat: "conductor", model: "GLM-4.6", count: 1, why: "between-wave review vs. goal", zone: "LOCAL" },
    { seat: "oracle", model: "Gemma-4-31B", count: 1, why: "math · lineage-independent risk-score check", zone: "LOCAL" },
    { seat: "inspector", model: "Qwen3.6-35B-A3B", count: 2, why: "agentic adversarial QA", zone: "LOCAL" },
  ],
}, 400);
meter();
push("job.stage_changed", { status: "certifying", stage: 2 }, 300);

/* ---------- stage 2: certify (amendment log + consults + goal) ---------- */
push("certify.goal_set", { goal: "Given a batch of applicants, produce for each an auditable case file with an ID-verification result, sanctions/PEP/adverse-media findings that cite their source, a risk score, and an onboarding decision, without any raw PII leaving local infrastructure." }, 300);
for (const chk of ["Interfaces resolve against raw schemas", "OFAC/EU list fields present in mapped tables", "Risk weights sum to 1.0", "Every acceptance criterion has a test"]) {
  push("certify.check_started", { check: chk }, 220);
  call("certifier", "local:B/glm-4.6", "LOCAL", "RAW", 3100, 700, 0.0);
}
push("certify.finding", { check: "OFAC/EU list fields present in mapped tables", finding: "Planner assumed a single 'sanctions_list' table; raw schema splits OFAC and EU. Patchable locally.", severity: "minor" }, 260);
amend("certifier", "Split sanctions-screen input into ofac_entries + eu_consolidated; rehydrate real column names.", "sanctions-screen");
push("certify.finding", { check: "Risk weights sum to 1.0", finding: "Adverse-media weight missing; structural gap in the scoring contract.", severity: "structural" }, 260);
push("certify.consult_opened", { id: "cs_1", scope: "risk-score weighting", round: 1, sanitization_receipt: { rules_applied: ["PII-01", "POL-02"], brief_tokens: 240 } }, 300);
push("egress.request", { host: "api.anthropic.com", zone: "EXTERNAL", seat: "planner", data_class: "SANITIZED", bytes: 1120 });
call("planner", "anthropic:claude-fable-5", "EXTERNAL", "SANITIZED", 240, 180, 0.02);
push("certify.consult_resolved", { id: "cs_1", round: 1, resolution: "Add adverse-media weight 0.15; renormalize the other four weights." }, 320);
amend("certifier", "Insert adverse-media into risk-score with weight 0.15; renormalize to sum 1.0.", "risk-score");
meter();
push("certify.certified", { tests: 34, vectors: 12, identifiers_rehydrated: 128 }, 400);
push("job.stage_changed", { status: "quoted", stage: 3 }, 300);

/* ---------- stage 3: quote ---------- */
push("quote.issued", {
  lines: [
    { label: "Planning (frontier, sanitized)", detail: "claude-fable-5 · 1 plan + 1 consult", amount_usd: 0.23 },
    { label: "Certification (local)", detail: "GLM-4.6 · 4 checks + 2 amendments", amount_usd: 0.08 },
    { label: "Build fleet (local MI300X)", detail: "Qwen/Devstral ×4 · ~2 waves", amount_usd: 1.10 },
    { label: "Adversarial QA (local)", detail: "2 inspectors + oracle 5%", amount_usd: 0.34 },
  ],
  low_usd: 1.55, high_usd: 2.20,
}, 400);
push("quote.approved", { approved_usd: 1.85 }, 500);
push("job.stage_changed", { status: "building", stage: 4 }, 300);

/* ---------- fleet provisioning ---------- */
push("fleet.profile_requested", { profile: "kyc-build-8x", nodes: 2, seats: ["coder", "certifier", "conductor", "oracle", "inspector"] }, 200);
push("fleet.node_ready", { node: "amd-mi300x-A", gpus: 4, seats: ["coder", "certifier", "conductor"] }, 300);
push("fleet.node_ready", { node: "amd-mi300x-B", gpus: 4, seats: ["coder", "oracle", "inspector"] }, 300);
tele(0.9);

/* ---------- stage 4: waves + worker panels ---------- */
// wave 1: three independent modules
push("conductor.wave_started", { wave: 1, of: 2, modules: ["document-intake", "sanctions-screen", "pep-screen"] }, 300);
const wave1 = [
  { m: "document-intake", b: "local:B/qwen3-coder-next", why: "greenfield-codegen · OCR field extraction", loc: 214 },
  { m: "sanctions-screen", b: "local:B/devstral-small-2", why: "sql-data · matcher over ofac/eu tables", loc: 188 },
  { m: "pep-screen", b: "local:A/qwen3-coder-next", why: "greenfield-codegen · list lookup", loc: 96 },
];
for (const t of wave1) push("task.started", { module: t.m, backend: t.b, seat: "coder", zone: "LOCAL", wave: 1, why: t.why }, 220);
tele(1);
for (const chunk of ["def extract_fields(doc):", "\n    text = ocr(doc)", "\n    return parse(text)"]) push("task.output_delta", { module: "document-intake", text: chunk }, 110);
for (const chunk of ["def screen(name):", "\n    return match(name, ofac) or match(name, eu)"]) push("task.output_delta", { module: "sanctions-screen", text: chunk }, 110);
for (const t of wave1) { call("coder", t.b, "LOCAL", "RAW", 2600, 1400, 0.0); }
meter(9, 60, 55);
for (const t of wave1) push("task.tests", { module: t.m, passed: t.m === "sanctions-screen" ? 11 : 8, failed: 0 }, 140);
for (const t of wave1) push("task.completed", { module: t.m, ok: true, loc: t.loc }, 160);
push("conductor.review", { wave: 1, verdict: "green", goal_drift: 0.02, note: "All three modules meet their interface contracts; goal alignment strong." }, 320);
push("conductor.green_flag", { wave: 1 }, 200);
tele(0.7);

// wave 2: dependent modules
push("conductor.wave_started", { wave: 2, of: 2, modules: ["adverse-media", "risk-score", "case-file"] }, 300);
const wave2 = [
  { m: "adverse-media", b: "local:A/qwen3-coder-next", why: "greenfield-codegen · media search adapter", loc: 142 },
  { m: "risk-score", b: "local:B/qwen3-coder-next", why: "greenfield-codegen · weighted model", loc: 120 },
  { m: "case-file", b: "local:A/devstral-small-2", why: "docs-writing · evidence + audit assembly", loc: 176 },
];
for (const t of wave2) push("task.started", { module: t.m, backend: t.b, seat: "coder", zone: "LOCAL", wave: 2, why: t.why }, 220);
tele(1);
for (const chunk of ["def score(sig):", "\n    w = WEIGHTS  # sums to 1.0", "\n    return dot(w, sig)"]) push("task.output_delta", { module: "risk-score", text: chunk }, 110);
for (const t of wave2) call("coder", t.b, "LOCAL", "RAW", 2400, 1300, 0.0);
meter(11, 60, 60);
// one module needs a fix -> ticket
push("task.tests", { module: "adverse-media", passed: 6, failed: 2 }, 150);
push("ticket.opened", { id: "tk_1", title: "adverse-media: pagination drops results past page 1", status: "opened", severity: "medium", source: "consolidation" }, 220);
push("ticket.in_fix", { id: "tk_1", title: "adverse-media: pagination drops results past page 1", status: "in_fix", severity: "medium", source: "consolidation" }, 260);
push("task.tests", { module: "adverse-media", passed: 8, failed: 0 }, 200);
push("ticket.verified", { id: "tk_1", title: "adverse-media: pagination drops results past page 1", status: "verified", severity: "medium", source: "consolidation" }, 200);
push("task.tests", { module: "risk-score", passed: 9, failed: 0 }, 140);
push("task.tests", { module: "case-file", passed: 12, failed: 0 }, 140);
for (const t of wave2) push("task.completed", { module: t.m, ok: true, loc: t.loc }, 150);
push("conductor.amendment", { id: "am_wave2", origin: "conductor", summary: "Tighten case-file audit schema to include the sanctions list version used.", hash: "9c1a4f", prev_hash: hprev, region: "case-file" } as any, 260);
hprev = "9c1a4f";
push("conductor.review", { wave: 2, verdict: "green", goal_drift: 0.04, note: "Pipeline complete end-to-end; audit trail satisfies the goal statement." }, 320);
push("conductor.green_flag", { wave: 2 }, 200);
tele(0.6);
push("job.stage_changed", { status: "consolidating", stage: 5 }, 300);

/* ---------- stage 5: consolidation (validation wall) ---------- */
push("consolidate.started", { modules: 6 }, 250);
push("consolidate.test_run", { passed: 58, failed: 4, total: 62 }, 300);
call("consolidator", "local:B/glm-4.6", "LOCAL", "RAW", 5200, 900, 0.0);
push("consolidate.test_run", { passed: 61, failed: 1, total: 62 }, 320);
push("consolidate.test_run", { passed: 62, failed: 0, total: 62 }, 320);
push("consolidate.completed", { passed: 62, total: 62 }, 300);
meter(8, 40, 40);
push("job.stage_changed", { status: "qa", stage: 6 }, 300);

/* ---------- stage 6: adversarial QA + oracle + goal check ---------- */
push("qa.inspector_started", { scenario: "Sanctions evasion via transliterated name", seat: "inspector" }, 250);
push("qa.probe", { scenario: "Sanctions evasion via transliterated name", probe: "Submit 'Vladimir' vs 'Wladimir' spelling variants" }, 240);
call("inspector", "local:B/qwen3.6-35b-a3b", "LOCAL", "RAW", 3400, 1600, 0.0);
push("qa.finding", { scenario: "Sanctions evasion via transliterated name", result: "flag", detail: "Fuzzy matcher missed one transliteration; opened ticket." }, 260);
push("ticket.opened", { id: "tk_2", title: "sanctions-screen: add transliteration normalization", status: "opened", severity: "high", source: "inspector" }, 220);
push("ticket.in_fix", { id: "tk_2", title: "sanctions-screen: add transliteration normalization", status: "in_fix", severity: "high", source: "inspector" }, 240);
push("ticket.verified", { id: "tk_2", title: "sanctions-screen: add transliteration normalization", status: "verified", severity: "high", source: "inspector" }, 260);
push("qa.inspector_started", { scenario: "Risk-score boundary conditions", seat: "inspector" }, 250);
for (const v of ["all-clear applicant → low", "sanctions hit → auto high", "PEP + adverse media → elevated"]) {
  push("qa.oracle_check", { vector: v, verdict: "match", model: "Gemma-4-31B (lineage-independent)" }, 220);
}
call("oracle", "local:B/gemma-4-31b-it", "LOCAL", "RAW", 1800, 400, 0.0);
push("qa.finding", { scenario: "Risk-score boundary conditions", result: "clear" }, 220);
push("qa.goal_check", { verdict: "fulfilled", gaps: [] }, 320);
push("qa.passed", { scenarios: 2, probes: 6, tickets_resolved: 2 }, 300);
meter(7, 30, 30);
push("job.stage_changed", { status: "delivered", stage: 7 }, 300);

/* ---------- stage 7: delivery ---------- */
push("deliver.registered", { process_id: "proc_kyc_onboarding", version: 1, package: { plan: true, docs: true, qa_report: true, tests: 62 } }, 300);
push("job.done", { status: "done", stage: 7 }, 300);
push("system.notice", { text: "Process registered. Ready to run on new applicants — zero frontier calls from here.", level: "info" }, 200);

export const KYC_EVENTS: NxEvent[] = EV;

/** Presenter control: a would-be external call under Sovereign Mode, blocked at the boundary. */
export function sovereignViolationEvent(seq: number): NxEvent {
  return {
    seq,
    ts: new Date().toISOString(),
    scope: SCOPE,
    type: "egress.violation",
    payload: { host: "api.anthropic.com", zone: "EXTERNAL", detail: "Sovereign Mode active: an external planner call was requested and blocked at the boundary. Zero data left the fleet." },
  } as NxEvent;
}
