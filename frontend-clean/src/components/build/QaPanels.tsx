import { TestTube, Bug, Scales, Target, SealCheck, ArrowRight, Wrench } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { Panel, type PanelStatus } from "./Panel";
import { ShortId } from "../ui/ShortId";
import type { JobView } from "../../store/jobStore";
import { countEvidenceState } from "../../lib/evidenceTruth";

const ORACLE_LABELS = {
  match: "match",
  mismatch: "mismatch",
  no_actual: "no actual result",
  oracle_uncertain: "oracle uncertain",
} as const;

const EMPTY_GOAL_COPY = {
  fulfilled: "Verified against the original ask, not the drifted plan.",
  partial: "Goal evidence is partial; no specific gaps were reported.",
  unfulfilled: "The original goal is not fulfilled; no specific gaps were reported.",
  unknown: "Goal fulfillment evidence was not reported.",
} as const;

export function ValidationWall({ view }: { view: JobView }) {
  const { consolidate } = view;
  const last = consolidate.testRuns[consolidate.testRuns.length - 1];
  const completedEvidence = consolidate.completed && {
    ...consolidate.completed,
    failed: Math.max(consolidate.completed.total - consolidate.completed.passed, 0),
  };
  const wallState = completedEvidence
    ? countEvidenceState(completedEvidence)
    : last ? countEvidenceState(last) : null;
  const status: PanelStatus = view.stage === 5
    ? "active"
    : wallState === "passed" ? "ok"
      : wallState === "failed" ? "error"
        : wallState === "unverified" ? "warn" : "pending";
  if (view.mode === "process") return null;

  return (
    <Panel
      title="Validation wall"
      icon={TestTube}
      status={status}
      tag={consolidate.completed ? consolidate.completed.verification : "stage 5"}
    >
      {!last && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          Consolidation is gated by objective tests.
        </p>
      )}
      {last && (
        <>
          {wallState !== "passed" && (
            <div className={`bv-qa-truth ${wallState ?? "unverified"}`}>
              <strong>Integration {wallState ?? "unverified"}</strong>
              <p>{last.reason || (last.total === 0
                ? "No executed test evidence is available."
                : "The integration suite did not produce fully passing verified evidence.")}</p>
            </div>
          )}
          <div className="bv-wall-nums">
            <span className={`bv-wall-pass ${wallState ?? "unverified"} tnum`}>{last.passed}</span>
            <span className="bv-wall-total tnum">/ {last.total} passing</span>
            {last.failed > 0 && <span className="bv-wall-fail tnum">{last.failed} failing</span>}
          </div>
          <div className="bv-wall-track">
            <div
              className={`bv-wall-fill ${wallState ?? "unverified"}`}
              style={{ width: `${last.total > 0 ? (last.passed / last.total) * 100 : 0}%` }}
            />
          </div>
          <div className="bv-wall-runs">
            {consolidate.testRuns.map((r, i) => {
              const state = countEvidenceState(r);
              return <div className={`bv-wall-run ${state}`} key={i} title={`${state}: ${r.passed}/${r.total}`} />;
            })}
          </div>
        </>
      )}
    </Panel>
  );
}

export function DefectBoard({ view }: { view: JobView }) {
  const tickets = Object.values(view.tickets);
  const { qa } = view;
  const probes = Object.values(qa.probeBoard).sort((a, b) => a.seq - b.seq);
  const status: PanelStatus = view.stage === 6
    ? "active"
    : qa.completed?.verification === "passed"
      ? "ok"
      : qa.completed ? "default" : tickets.length ? "default" : "pending";

  return (
    <Panel
      title="Adversarial QA & defect board"
      icon={Bug}
      status={status}
      tag={qa.passed ? `${qa.passed.tickets_resolved} resolved` : "stage 6"}
    >
      {tickets.length === 0 && qa.oracleChecks.length === 0 && probes.length === 0 && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          Inspectors probe adversarially; the Numeric Oracle checks independently.
        </p>
      )}

      {qa.completed && qa.completed.verification !== "passed" && (
        <div className={`bv-qa-truth ${qa.completed.verification}`}>
          <strong>QA {qa.completed.verification}</strong>
          {qa.completed.demo_override && <span>demo override</span>}
          <p>{qa.completed.reasons.length ? qa.completed.reasons.join("; ") : "Verification evidence is incomplete."}</p>
        </div>
      )}

      {view.tools.created.length > 0 && (
        <div className="bv-cert-stats" style={{ marginTop: 0, marginBottom: 10 }}>
          <span className="bv-cert-stat" title={view.tools.created.map((t) => t.name).join(", ")}>
            <Wrench weight="bold" style={{ width: 10, verticalAlign: "-1px", marginRight: 3 }} />
            {view.tools.created.length} tool{view.tools.created.length === 1 ? "" : "s"} commissioned
            {view.tools.invocations > 0 && ` · ${view.tools.invocations} runs`}
          </span>
        </div>
      )}

      {probes.length > 0 && (
        <div className="bv-probes">
          {probes.map((p) => (
            <div className={`bv-probe ${p.status}`} key={`${p.scenario}#${p.probe}`} title={p.detail}>
              <i className="bv-probe-dot" />
              <div style={{ minWidth: 0 }}>
                <div className="bv-probe-name">{p.probe}</div>
                {p.probe !== p.scenario && <div className="bv-probe-scenario">{p.scenario}</div>}
              </div>
              <span className="bv-probe-status">{p.status}</span>
            </div>
          ))}
        </div>
      )}

      {tickets.length > 0 && (
        <div className="bv-tickets">
          {tickets.map((t) => (
            <div className="bv-ticket" key={t.id}>
              <span className={`bv-ticket-sev ${t.severity}`} />
              <div>
                <div className="bv-ticket-title">{t.title}</div>
                <div className="bv-ticket-src">{t.source}</div>
              </div>
              <span className={`bv-ticket-status ${t.status}`}>{t.status.replace("_", " ")}</span>
            </div>
          ))}
        </div>
      )}

      {view.fixes.length > 0 && (
        <div>
          {view.fixes.map((f) => (
            <div className="bv-fixline" key={f.seq}>
              <Wrench weight="bold" /> fix applied · {f.module}{f.note ? ` — ${f.note}` : ""}
            </div>
          ))}
        </div>
      )}

      {(qa.oracleChecks.length > 0 || qa.votes.length > 0) && (
        <div className="bv-oracle">
          <div className="bv-oracle-head" title="An independent model from a different lineage re-computes the certifier's numeric test vectors, so it can't share the builder's blind spots">
            <Scales weight="fill" /> Numeric Oracle
            <span className="bv-oracle-model">{qa.oracleChecks[0]?.model ?? "lineage-independent"}</span>
          </div>
          {qa.oracleChecks.map((o, i) => (
            <div className="bv-oracle-row" key={i}>
              <span className="bv-oracle-v">{o.vector}</span>
              <span className={`bv-oracle-verdict ${o.verdict}`}>{ORACLE_LABELS[o.verdict]}</span>
            </div>
          ))}
          {qa.votes.length > 0 && (
            <div className="bv-votes">
              {qa.votes.slice(-9).map((vt, i) => (
                <span className="bv-vote" key={i}>{vt.vector} · {vt.vote}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {qa.goalCheck && (
        <div className={`bv-goalcheck ${qa.goalCheck.verdict}`}>
          <Target weight="fill" />
          <div>
            <div className="bv-goalcheck-lbl">Goal fulfillment: {qa.goalCheck.verdict}</div>
            <div className="bv-goalcheck-sub">
              {qa.goalCheck.gaps.length
                ? qa.goalCheck.gaps.join("; ")
                : EMPTY_GOAL_COPY[qa.goalCheck.verdict]}
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

export function DeliveryMoment({ view }: { view: JobView }) {
  if (!view.delivery) return null;
  const d = view.delivery;
  const verified = d.verification === "passed";
  return (
    <Panel title="Delivered to registry" icon={SealCheck} status={verified ? "ok" : "default"} tag={d.delivery_label}>
      <div className={`bv-deliver ${verified ? "verified" : "unverified"}`}>
        <SealCheck weight="fill" className="bv-deliver-icon" />
        <div className="bv-deliver-title">
          <ShortId id={d.process_id} /> · v{d.version} · {verified ? "VERIFIED" : d.delivery_label}
        </div>
        {!verified && (
          <div className="bv-deliver-reasons">
            {d.verification_reasons.length
              ? d.verification_reasons.join("; ")
              : "Verification evidence is incomplete."}
          </div>
        )}
        <div className="bv-deliver-pkg">
          {d.package.plan && <span className="bv-deliver-item">plan</span>}
          {d.package.docs && <span className="bv-deliver-item">docs</span>}
          {d.package.qa_report && <span className="bv-deliver-item">QA report</span>}
          <span className="bv-deliver-item">{d.package.tests} tests</span>
          {(view.deliveryDocs ?? []).map((doc) => (
            <span className="bv-deliver-item" key={doc}>{doc}</span>
          ))}
        </div>
        <Link to="/operations" className="bv-deliver-link">
          Open in operations registry <ArrowRight weight="bold" />
        </Link>
      </div>
    </Panel>
  );
}
