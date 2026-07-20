import { useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import {
  TreeStructure, ArrowLeft, X, Brain, MagnifyingGlass,
  ArrowUpRight, CheckCircle, Cube, Circle,
} from "@phosphor-icons/react";
import { useJobStream } from "../store/useJobStream";
import { useBreadcrumb } from "../components/shell/breadcrumbs";
import { ZoneBadge } from "../components/ui/ZoneBadge";
import { SEAT_INFO } from "../api/adapt";
import type { JobView, TaskState, WaveState } from "../store/jobStore";
import type { Zone } from "../lib/events";
import {
  deliveryNodeStatus,
  runNodeStatus,
  taskNodeStatus,
  type EvidenceNodeStatus,
} from "../lib/evidenceTruth";
import styles from "./RunMap.module.css";

/* ---------- graph model ---------- */
type NodeKind = "boundary" | "planner" | "certify" | "conductor" | "worker" | "review" | "run" | "deliverable";
type NodeStatus = EvidenceNodeStatus | "pending" | "active" | "reviewing" | "green" | "blocked";

interface MapNode {
  id: string;
  kind: NodeKind;
  title: string;
  role: string;
  seat?: string;
  zone?: Zone;
  status: NodeStatus;
  stat?: { text: string; tone?: "ok" | "warn" };
  wave?: number;
  module?: string;
  col: number;
  left: number; top: number; w: number; h: number;
}
interface Edge { id: string; from: string; to: string; cross?: boolean; }

const COL_W = 244, NODE_W = 190, ROW_PITCH = 112, PAD_X = 52, PAD_TOP = 96, PAD_BOTTOM = 76;
const H: Record<NodeKind, number> = {
  boundary: 88, planner: 88, certify: 88, conductor: 88, worker: 88, review: 62, run: 88, deliverable: 96,
};

const isActive = (s: NodeStatus) => s === "running" || s === "active" || s === "reviewing";
const isDone = (s: NodeStatus) => s === "done" || s === "green";

function reviewStatus(w: WaveState): NodeStatus {
  return w.status === "green" ? "green" : w.status === "reviewing" ? "reviewing" : "pending";
}

/** Derive the pipeline graph from the folded view. Columns are laid out
 *  deterministically so the SVG edges and the node boxes share one grid. */
function buildGraph(view: JobView) {
  const columns: MapNode[][] = [];
  const push = (col: MapNode[]) => { columns.push(col); return columns.length - 1; };
  const stage = view.stage;

  // col 0 — intake / boundary (always present)
  const b = view.intake.boundary;
  const boundaryStat = b
    ? { text: `${b.brief_tokens} tok cross` }
    : view.mode
      ? { text: view.mode }
      : undefined;
  push([{
    id: "boundary", kind: "boundary", title: "Intake · Boundary", role: "sanitizes the brief",
    seat: "trust", zone: "LOCAL",
    status: stage > 0 ? "done" : "active",
    stat: boundaryStat, col: 0, left: 0, top: 0, w: NODE_W, h: H.boundary,
  }]);

  // col 1 — planner (the one external hop), appears once planning starts
  const hasPlanner = stage >= 1 || !!view.plan.plannerModel || view.plan.streaming || !!view.plan.summary;
  if (hasPlanner) {
    const p = view.plan;
    const status: NodeStatus = p.streaming ? "running" : p.summary ? "done" : stage === 1 ? "active" : "pending";
    push([{
      id: "planner", kind: "planner", title: "Planner", role: "the one external hop",
      seat: "planner", zone: "EXTERNAL", status,
      stat: p.modules ? { text: `${p.modules} modules` } : p.topology ? { text: p.topology } : undefined,
      col: 0, left: 0, top: 0, w: NODE_W, h: H.planner,
    }]);
  }

  // col 2 — certifier
  const c = view.certify;
  const hasCertify = stage >= 2 || c.checks.length > 0 || !!c.goal || !!c.certified;
  if (hasCertify) {
    const status: NodeStatus = c.certified ? "done" : stage === 2 ? "active" : c.checks.length ? "running" : "pending";
    push([{
      id: "certify", kind: "certify", title: "Certifier", role: "completes & certifies the plan",
      seat: "certifier", zone: "LOCAL", status,
      stat: c.certified ? { text: `${c.certified.tests} tests`, tone: "ok" } : c.goal ? { text: "goal set" } : c.checks.length ? { text: `${c.checks.length} checks` } : undefined,
      col: 0, left: 0, top: 0, w: NODE_W, h: H.certify,
    }]);
  }

  // The middle is one of two shapes: a BUILD (conductor fans out to coder waves)
  // or a process/detection RUN (no fan-out — a single corpus scan). KYC is build;
  // the insurer/lawfirm/bank sandbox jobs are runs.
  const waves = Object.values(view.build.waves).sort((a, b) => a.wave - b.wave);
  const tasks = Object.values(view.build.tasks);
  const runs = Object.values(view.runs);
  const hasBuild = waves.length > 0 || stage === 4;
  const hasRun = !hasBuild && runs.length > 0;

  // col 3 — conductor (the fan-out hub), build shape only
  if (hasBuild) {
    const anyRunning = waves.some((w) => w.status === "running" || w.status === "reviewing");
    const status: NodeStatus = view.delivery ? "done"
      : anyRunning ? "running"
        : waves.length && waves.every((w) => w.status === "green") ? "done"
          : waves.length ? "running" : stage >= 4 ? "active" : "pending";
    push([{
      id: "conductor", kind: "conductor", title: "Conductor", role: "fans out & reviews each wave",
      seat: "conductor", zone: "LOCAL", status,
      stat: waves.length ? { text: `${waves.length} wave${waves.length > 1 ? "s" : ""}` } : undefined,
      col: 0, left: 0, top: 0, w: NODE_W, h: H.conductor,
    }]);
  }

  // per-wave: a workers column then a review column
  for (const w of waves) {
    const workers = tasks.filter((t) => t.wave === w.wave)
      // stable order = the order the conductor named them
      .sort((a, b) => w.modules.indexOf(a.module) - w.modules.indexOf(b.module));
    const workerNodes: MapNode[] = (workers.length ? workers : w.modules.map((m) => ({ module: m } as TaskState))).map((t) => {
      const known = "status" in t && t.status;
      const st: NodeStatus = known ? taskNodeStatus(t) : "pending";
      return {
        id: `w${w.wave}:${t.module}`, kind: "worker", title: t.module, role: "coder",
        seat: "coder", zone: (t.zone as Zone) ?? "LOCAL", status: st, wave: w.wave, module: t.module,
        stat: t.tests ? {
          text: t.tests.verification === "passed"
            ? `✓ ${t.tests.passed}/${t.tests.total}`
            : `${t.tests.verification} · ${t.tests.passed}/${t.tests.total}`,
          tone: st === "done" ? "ok" : "warn",
        }
          : t.loc != null ? { text: `${t.loc} LOC` } : undefined,
        col: 0, left: 0, top: 0, w: NODE_W, h: H.worker,
      };
    });
    push(workerNodes);
    push([{
      id: `review${w.wave}`, kind: "review", title: `Wave ${w.wave} review`, role: "conductor",
      seat: "conductor", zone: "LOCAL", status: reviewStatus(w), wave: w.wave,
      stat: w.goal_drift != null ? { text: `drift ${(w.goal_drift * 100).toFixed(0)}%`, tone: w.goal_drift > 0.15 ? "warn" : "ok" } : w.verdict ? { text: w.verdict } : undefined,
      col: 0, left: 0, top: 0, w: NODE_W, h: H.review,
    }]);
  }

  // process/detection RUN — one corpus-scan node instead of a build fan-out
  if (hasRun) {
    const r = runs[runs.length - 1];
    const status = runNodeStatus(r);
    push([{
      id: "run", kind: "run", title: "Detection run", role: "scans the corpus & flags",
      zone: "LOCAL", status,
      stat: status === "running"
        ? { text: `${r.done}/${r.units}` }
        : { text: `${r.verification} · ${r.flagged} flagged`, tone: status === "done" && !r.flagged ? "ok" : "warn" },
      col: 0, left: 0, top: 0, w: NODE_W, h: H.run,
    }]);
  }

  // terminal — deliverable
  if (hasBuild || hasRun || view.delivery || stage >= 7) {
    const d = view.delivery;
    push([{
      id: "deliverable", kind: "deliverable", title: "Deliverable", role: "registered process",
      zone: "LOCAL", status: d ? deliveryNodeStatus(d) : stage >= 7 ? "active" : "pending",
      stat: d ? {
        text: `v${d.version} · ${d.delivery_label}`,
        tone: d.verification === "passed" ? "ok" : "warn",
      } : undefined,
      col: 0, left: 0, top: 0, w: NODE_W, h: H.deliverable,
    }]);
  }

  // ---- layout: assign x per column, stack y centered on the spine ----
  const maxRows = Math.max(1, ...columns.map((c) => c.length));
  const contentH = maxRows * ROW_PITCH;
  const centerY = PAD_TOP + contentH / 2;
  columns.forEach((colNodes, ci) => {
    const cx = PAD_X + NODE_W / 2 + ci * COL_W;
    const n = colNodes.length;
    colNodes.forEach((node, j) => {
      const cy = centerY + (j - (n - 1) / 2) * ROW_PITCH;
      node.col = ci;
      node.left = cx - NODE_W / 2;
      node.top = cy - node.h / 2;
    });
  });

  const nodes = columns.flat();
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const has = (id: string) => byId.has(id);

  // ---- edges along the pipeline ----
  const edges: Edge[] = [];
  const link = (from: string, to: string, cross = false) => { if (has(from) && has(to)) edges.push({ id: `${from}->${to}`, from, to, cross }); };
  link("boundary", "planner", true);
  link("planner", "certify", true);
  link("certify", "conductor");
  // conductor also reaches certify's slot even if certify missing (early)
  if (!has("certify")) link("planner", "conductor");
  if (!has("planner")) link("boundary", "conductor");

  if (waves.length) {
    for (let i = 0; i < waves.length; i++) {
      const w = waves[i];
      const workerIds = nodes.filter((n) => n.kind === "worker" && n.wave === w.wave).map((n) => n.id);
      const src = i === 0 ? "conductor" : `review${waves[i - 1].wave}`;
      for (const wid of workerIds) link(src, wid);
      for (const wid of workerIds) link(wid, `review${w.wave}`);
    }
    link(`review${waves[waves.length - 1].wave}`, "deliverable");
  } else if (has("conductor")) {
    link("conductor", "deliverable");
  }

  // run shape (process/detection): spine → run → deliverable
  const spineTail = has("certify") ? "certify" : has("planner") ? "planner" : "boundary";
  if (has("run")) {
    link(spineTail, "run");
    link("run", "deliverable");
  } else if (has("deliverable") && !has("conductor")) {
    // thin delivery-only job: don't leave the deliverable orphaned
    link(spineTail, "deliverable");
  }

  // ---- boundary wall around the planner column ----
  const planner = byId.get("planner");
  let wall: { x1: number; x2: number } | null = null;
  if (planner) {
    const boundary = byId.get("boundary")!;
    const after = byId.get("certify") ?? byId.get("conductor");
    const x1 = (boundary.left + boundary.w + planner.left) / 2;
    const x2 = after ? (planner.left + planner.w + after.left) / 2 : planner.left + planner.w + (COL_W - NODE_W) / 2;
    wall = { x1, x2 };
  }

  const width = PAD_X * 2 + (columns.length - 1) * COL_W + NODE_W;
  const height = PAD_TOP + contentH + PAD_BOTTOM;
  return { nodes, edges, byId, wall, width, height, centerY };
}

function edgeState(from: MapNode, to: MapNode): "live" | "done" | "pending" {
  if (isActive(from.status) || isActive(to.status)) return "live";
  if (isDone(from.status) && isDone(to.status)) return "done";
  return "pending";
}

function edgePath(from: MapNode, to: MapNode): string {
  const x1 = from.left + from.w, y1 = from.top + from.h / 2;
  const x2 = to.left, y2 = to.top + to.h / 2;
  const dx = Math.max(28, (x2 - x1) * 0.45);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

/* ---------- transcript primitives (Claude-Code style, mono, quiet) ---------- */
function splitReasoning(text: string): { reasoning: string[]; body: string } {
  const reasoning: string[] = [];
  const body = text.replace(/<(think|reasoning|thinking)>([\s\S]*?)<\/\1>/gi, (_a, _t, inner: string) => {
    const t = inner.trim(); if (t) reasoning.push(t); return "";
  }).trim();
  return { reasoning, body };
}
function Sect({ children }: { children: ReactNode }) { return <div className={styles.sect}>{children}</div>; }
function Field({ k, children }: { k: string; children: ReactNode }) {
  return <div className={styles.field}><span className={styles.fieldK}>{k}</span><span className={styles.fieldV}>{children}</span></div>;
}
function Out({ label, text }: { label?: string; text: string }) {
  return <pre className={styles.out}>{label && <span className={styles.outLabel}>{label}</span>}{text}</pre>;
}
function Reason({ text }: { text: string }) {
  return <div className={styles.reason}><span className={styles.reasonTag}><Brain weight="fill" /> reasoning</span>{text}</div>;
}
function Msg({ role, content }: { role: string; content: string }) {
  const { reasoning, body } = splitReasoning(content);
  return (
    <div className={styles.msg}>
      <span className={styles.msgRole} data-r={role}>{role}</span>
      {reasoning.map((r, i) => <Reason key={i} text={r} />)}
      <div className={styles.msgBody}>{body || content}</div>
    </div>
  );
}

/* ---------- per-node transcript ---------- */
function Transcript({ view, node }: { view: JobView; node: MapNode }) {
  switch (node.kind) {
    case "boundary": {
      const iv = view.intake;
      return (
        <>
          {iv.classification && <Field k="classified">{iv.classification.mode} — {iv.classification.rationale}</Field>}
          {iv.policy && <Field k="policy">{iv.policy.rule_count} rules from {iv.policy.sources.join(", ") || "baseline"}</Field>}
          {iv.context && <Field k="context">{iv.context.tables} tables · {iv.context.masked} identifiers masked</Field>}
          <Sect>conversation</Sect>
          {iv.messages.length === 0 && <div className={styles.empty}>No intake messages folded yet.</div>}
          {iv.messages.map((m, i) => <Msg key={i} role={m.role} content={m.content} />)}
          {iv.boundary && (
            <>
              <Sect>boundary receipt — what may cross</Sect>
              <Field k="brief"><b>{iv.boundary.brief_tokens}</b> sanitized tokens leave the box</Field>
              {iv.boundary.findings?.length > 0 && <Field k="masked">{iv.boundary.findings.length} sensitive spans held back</Field>}
              {iv.boundary.never_leaves?.length > 0 && (
                <div className={styles.chips}>
                  {iv.boundary.never_leaves.map((n, i) => <span key={i} className={styles.chip} data-tone="never">{n}</span>)}
                </div>
              )}
            </>
          )}
        </>
      );
    }
    case "planner": {
      const p = view.plan;
      return (
        <>
          <Field k="model">{p.plannerModel ?? "frontier planner"}</Field>
          <Field k="zone">the only dispatch that leaves the sovereign boundary</Field>
          {view.intake.boundary && <Field k="input">only <b>{view.intake.boundary.brief_tokens}</b> sanitized tokens — no raw PII</Field>}
          {p.deltaText && (<><Sect>plan (streamed)</Sect><Msg role="planner" content={p.deltaText} /></>)}
          {p.summary && <><Sect>result</Sect><Field k="summary">{p.summary}</Field></>}
          {p.topology && <Field k="topology">{p.topology}</Field>}
          {p.bom.length > 0 && (
            <>
              <Sect>bill of materials</Sect>
              {p.bom.map((l, i) => <Field key={i} k={`${l.count}× ${l.seat}`}>{l.model} — {l.why}</Field>)}
            </>
          )}
        </>
      );
    }
    case "certify": {
      const c = view.certify;
      return (
        <>
          {c.goal && <Field k="goal"><b>{c.goal}</b></Field>}
          {c.certified && (
            <><Sect>certified</Sect>
              <Field k="tests">{c.certified.tests} tests emitted</Field>
              <Field k="vectors">{c.certified.vectors} oracle vectors</Field>
              <Field k="rehydrated">{c.certified.identifiers_rehydrated} identifiers restored inside the walls</Field>
            </>
          )}
          {c.checks.length > 0 && (
            <><Sect>checks</Sect>
              {c.checks.map((ch, i) => (
                <div key={i} className={styles.rowLine}>
                  <span className={styles.rowIcon}>{ch.status === "done" ? <CheckCircle weight="fill" color="var(--ok)" /> : ch.status === "finding" ? "!" : <Circle weight="bold" />}</span>
                  <span className={styles.rowText}>{ch.check}</span>
                  {ch.finding && <span className={styles.rowNote}>{ch.finding}</span>}
                </div>
              ))}
            </>
          )}
          {c.consults.length > 0 && (
            <><Sect>consults with the planner</Sect>
              {c.consults.map((cs, i) => <Field key={i} k={`round ${cs.round || "?"}`}>{cs.resolution ?? cs.reason ?? cs.scope ?? "sanitized re-consult"}</Field>)}
            </>
          )}
        </>
      );
    }
    case "conductor": {
      const waves = Object.values(view.build.waves).sort((a, b) => a.wave - b.wave);
      return (
        <>
          <Field k="role">runs the DAG in topological waves, reviewing between each</Field>
          <Sect>waves</Sect>
          {waves.length === 0 && <div className={styles.empty}>No waves dispatched yet.</div>}
          {waves.map((w) => (
            <div key={w.wave} className={styles.rowLine}>
              <span className={styles.rowIcon}>{w.status === "green" ? <CheckCircle weight="fill" color="var(--ok)" /> : <Circle weight="bold" />}</span>
              <span className={styles.rowText}>Wave {w.wave}/{w.of} — {w.modules.join(", ")}</span>
              {w.goal_drift != null && <span className={styles.rowNote}>drift {(w.goal_drift * 100).toFixed(0)}%</span>}
            </div>
          ))}
        </>
      );
    }
    case "worker": {
      const t = view.build.tasks[node.module ?? ""];
      if (!t) return <div className={styles.empty}>This module hasn’t started yet — the conductor named it for wave {node.wave}.</div>;
      return (
        <>
          <Msg role="system" content={t.why} />
          {t.output && <Out label="streamed output" text={t.output} />}
          <Sect>result</Sect>
          <Field k="status">{t.status}{t.reason ? ` — ${t.reason}` : ""}</Field>
          {t.tests && (
            <>
              <Field k="tests">{t.tests.passed}/{t.tests.total} · {t.tests.verification}</Field>
              {t.tests.reason && <Field k="evidence">{t.tests.reason}</Field>}
            </>
          )}
          {t.loc != null && <Field k="size">{t.loc} LOC</Field>}
          <Field k="backend">{t.backend.replace(/^local:/, "")}</Field>
        </>
      );
    }
    case "review": {
      const w = view.build.waves[node.wave ?? 0];
      if (!w) return <div className={styles.empty}>No review yet.</div>;
      return (
        <>
          <Field k="verdict"><b>{w.verdict ?? w.status}</b></Field>
          {w.note && <Msg role="conductor" content={w.note} />}
          {w.goal_drift != null && <Field k="goal drift">{(w.goal_drift * 100).toFixed(0)}% — 0% means still exactly on the certified promise</Field>}
          <Field k="modules">{w.modules.join(", ")}</Field>
        </>
      );
    }
    case "run": {
      const r = Object.values(view.runs).slice(-1)[0];
      return (
        <>
          <Field k="role">runs the certified detection over the full corpus — inside the sovereign boundary, no external hop</Field>
          {r && (
            <>
              <Sect>run</Sect>
              <Field k="processed">{r.done.toLocaleString()} / {r.units.toLocaleString()} units</Field>
              <Field k="flagged"><b>{r.flagged.toLocaleString()}</b> flagged</Field>
              {r.cost_usd != null && <Field k="cost">${r.cost_usd.toFixed(3)}</Field>}
              {r.gpu_seconds != null && <Field k="gpu">{r.gpu_seconds}s</Field>}
              <Field k="status">{r.status}</Field>
              <Field k="verification"><b>{r.verification}</b>{r.demo ? " · demo" : ""}</Field>
              {r.reasons.length > 0 && <Field k="reasons">{r.reasons.join("; ")}</Field>}
              {r.artifactVerification && (
                <Field k="artifacts">{r.artifactVerification}{r.artifactReason ? ` · ${r.artifactReason}` : ""}</Field>
              )}
            </>
          )}
          {view.runArtifacts && view.runArtifacts.length > 0 && (
            <><Sect>artifacts</Sect>{view.runArtifacts.map((a, i) => <Field key={i} k={a.kind}>{a.url}</Field>)}</>
          )}
        </>
      );
    }
    case "deliverable": {
      const d = view.delivery;
      if (!d) return <div className={styles.empty}>The run hasn’t reached delivery yet. This is where the certified process, docs, and run artifacts land.</div>;
      return (
        <>
          <Field k="process"><b>{d.process_id}</b> · v{d.version}</Field>
          <Field k="verification"><b>{d.delivery_label}</b></Field>
          {d.verification_reasons.length > 0 && <Field k="reasons">{d.verification_reasons.join("; ")}</Field>}
          <Sect>package</Sect>
          <div className={styles.chips}>
            {d.package.plan && <span className={styles.chip} data-tone={d.verification === "passed" ? "ok" : "warn"}>plan</span>}
            {d.package.docs && <span className={styles.chip} data-tone={d.verification === "passed" ? "ok" : "warn"}>docs</span>}
            {d.package.qa_report && <span className={styles.chip} data-tone={d.verification === "passed" ? "ok" : "warn"}>qa report</span>}
            <span className={styles.chip} data-tone={d.verification === "passed" ? "ok" : "warn"}>{d.package.tests} tests</span>
          </div>
          {view.deliveryDocs && view.deliveryDocs.length > 0 && (
            <><Sect>documents</Sect><div className={styles.chips}>{view.deliveryDocs.map((doc, i) => <span key={i} className={styles.chip}>{doc}</span>)}</div></>
          )}
          {view.runArtifacts && view.runArtifacts.length > 0 && (
            <><Sect>run artifacts</Sect>{view.runArtifacts.map((a, i) => <Field key={i} k={a.kind}>{a.url}</Field>)}</>
          )}
        </>
      );
    }
  }
}

function Panel({ view, node, jobId, onClose }: { view: JobView; node: MapNode | null; jobId: string; onClose: () => void }) {
  const seatInfo = node?.seat ? SEAT_INFO[node.seat] : undefined;
  return (
    <aside className={styles.panel} data-open={node ? "true" : "false"} aria-hidden={!node}>
      {node && (
        <div className={styles.panelInner}>
          <div className={styles.panelHead}>
            <div className={styles.panelHeadTop}>
              <span className={styles.panelSeat}>{node.seat ?? node.kind} {seatInfo && <>→ <b>{seatInfo.model}</b></>}</span>
              {node.zone && <ZoneBadge zone={node.zone} size="xs" />}
              <button className={styles.panelClose} onClick={onClose} aria-label="Close transcript"><X weight="bold" /></button>
            </div>
            <div className={styles.panelSeat} style={{ fontWeight: 400, color: "var(--text)" }}>{node.title}</div>
            {seatInfo?.purpose && <p className={styles.panelPurpose}>{seatInfo.purpose}</p>}
          </div>
          <div className={styles.term}>
            <Transcript view={view} node={node} />
            {node.seat && (
              <Link className={styles.tracesLink} to={`/traces?scope=${encodeURIComponent(`job:${jobId}`)}&seat=${node.seat}`}>
                <MagnifyingGlass weight="bold" /> Inspect full prompts &amp; responses for this seat
              </Link>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

/* ---------- node box ---------- */
function Node({ n, selected, onClick }: { n: MapNode; selected: boolean; onClick: () => void }) {
  const running = isActive(n.status);
  return (
    <button
      className={styles.node}
      data-kind={n.kind} data-status={n.status} data-sel={selected}
      style={{ left: n.left, top: n.top, width: n.w, height: n.h }}
      onClick={onClick}
    >
      <div className={styles.nodeTop}>
        <span className={styles.dot} />
        <span className={styles.nodeTitle}>{n.title}</span>
        {running && n.kind !== "review" && <span className={styles.spin} />}
        {n.kind === "deliverable" && <Cube weight="bold" style={{ width: 13, marginLeft: "auto", color: "var(--text-faint)" }} />}
      </div>
      <div className={styles.nodeRole}>{n.role}</div>
      {n.h > 70 && (
        <div className={styles.nodeMeta}>
          {n.zone && <ZoneBadge zone={n.zone} size="xs" />}
          {n.stat && <span className={n.stat.tone === "ok" ? styles.nodeStatOk : n.stat.tone === "warn" ? styles.nodeStatWarn : styles.nodeStat}>{n.stat.text}</span>}
        </div>
      )}
    </button>
  );
}

export function RunMap() {
  const { jobId = "" } = useParams();
  const { view, conn } = useJobStream(jobId, { speed: 16 });
  const [selId, setSelId] = useState<string | null>(null);
  useBreadcrumb([{ label: "Build", to: "/build" }, { label: view.title ?? "Run", to: `/build/${jobId}` }, { label: "Run map" }]);

  const g = useMemo(() => buildGraph(view), [view]);
  const selected = selId ? g.byId.get(selId) ?? null : null;
  const started = g.nodes.length > 1;

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <Link to={`/build/${jobId}`} className={styles.back}><ArrowLeft weight="bold" /> Cockpit</Link>
        <div className={styles.headMain}>
          <h1 className={styles.title}><TreeStructure weight="bold" /> Run map</h1>
          <p className={styles.sub}>The multi-agent pipeline, live — one external hop, everything else sealed. Click any agent to read its transcript.</p>
        </div>
        <span className={styles.live} data-conn={conn}>
          <span className={styles.liveDot} />{conn === "closed" ? "complete" : conn === "open" ? "live" : conn}
        </span>
        <Link to={`/build/${jobId}`} className={styles.cockpitLink}><ArrowUpRight weight="bold" /> Open cockpit</Link>
      </div>

      <div className={styles.board}>
        <div className={styles.canvasScroll}>
          {!started ? (
            <div className={styles.boardEmpty}>
              <TreeStructure weight="bold" />
              <div>The map draws itself as the run advances — intake first, then the planner crosses the boundary, then the conductor fans out.</div>
            </div>
          ) : (
            <div className={styles.canvas} style={{ width: g.width, height: g.height }}>
              <svg className={styles.svg} width={g.width} height={g.height}>
                {g.wall && (
                  <g>
                    <rect className={styles.wallBand} x={g.wall.x1} y={0} width={g.wall.x2 - g.wall.x1} height={g.height} />
                    <line className={styles.wallSeam} x1={g.wall.x1} y1={0} x2={g.wall.x1} y2={g.height} />
                    <line className={styles.wallSeam} x1={g.wall.x2} y1={0} x2={g.wall.x2} y2={g.height} />
                    <text className={styles.wallLabel} x={(g.wall.x1 + g.wall.x2) / 2} y={22} textAnchor="middle">sovereign boundary</text>
                  </g>
                )}
                {g.edges.map((e) => {
                  const from = g.byId.get(e.from)!, to = g.byId.get(e.to)!;
                  return <path key={e.id} className={styles.edge} data-state={edgeState(from, to)} data-cross={e.cross} d={edgePath(from, to)} />;
                })}
              </svg>
              {g.nodes.map((n) => (
                <Node key={n.id} n={n} selected={selId === n.id} onClick={() => setSelId((cur) => (cur === n.id ? null : n.id))} />
              ))}
            </div>
          )}
        </div>
        <Panel view={view} node={selected} jobId={jobId} onClose={() => setSelId(null)} />
      </div>

      <div className={styles.legend}>
        <span className={styles.legItem}><span className={styles.legDot} style={{ background: "var(--accent)" }} /> running</span>
        <span className={styles.legItem}><span className={styles.legDot} style={{ background: "var(--ok)" }} /> done</span>
        <span className={styles.legItem}><span className={styles.legDot} style={{ background: "var(--text-faint)" }} /> pending</span>
        <span className={styles.legItem}><span className={styles.legLine} style={{ borderColor: "var(--accent)" }} /> energized edge</span>
        <span className={styles.legItem} style={{ marginLeft: "auto" }}>planner is the only node beyond the sovereign boundary</span>
      </div>
    </div>
  );
}
