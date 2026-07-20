import { ChatCircleDots, ShieldCheck, LockKey } from "@phosphor-icons/react";
import { Panel, type PanelStatus } from "./Panel";
import type { JobView } from "../../store/jobStore";

export function IntakePanel({ view }: { view: JobView }) {
  const { intake } = view;
  const status: PanelStatus = view.stage === 0 ? "active" : intake.boundary ? "ok" : "pending";
  const hasContent = intake.messages.length > 0 || intake.policy || intake.boundary;

  return (
    <Panel
      title="Intake & data boundary"
      icon={ChatCircleDots}
      status={status}
      tag={intake.classification ? `${intake.classification.mode} mode` : "stage 0"}
    >
      {!hasContent && <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>Awaiting the customer's request…</p>}

      {intake.messages.length > 0 && (
        <div className="bv-chat">
          {intake.messages.map((t, i) => (
            <div className={`bv-turn ${t.role}`} key={i}>
              <span className="bv-turn-role">{t.role}</span>
              <span className="bv-turn-text">{t.content}</span>
            </div>
          ))}
        </div>
      )}

      {intake.policy && (
        <div className="bv-policy">
          <div className="bv-policy-stat">
            <span className="bv-policy-num tnum">{intake.policy.rule_count}</span>
            <span className="bv-policy-lbl">policy rules</span>
          </div>
          <div className="bv-policy-stat">
            <span className="bv-policy-num tnum">{intake.policy.baseline}</span>
            <span className="bv-policy-lbl">PII baseline</span>
          </div>
          <div className="bv-policy-stat">
            <span className="bv-policy-num tnum">{intake.policy.policy}</span>
            <span className="bv-policy-lbl">customer clauses</span>
          </div>
          <div className="bv-policy-src">
            {intake.policy.sources.map((s) => (
              <span className="bv-src-chip" key={s}>{s}</span>
            ))}
          </div>
        </div>
      )}

      {intake.boundary && (
        <div className="bv-sanitize">
          <div className="bv-sanitize-head">
            <ShieldCheck weight="fill" />
            What the frontier will never see
          </div>
          {intake.boundary.findings.map((f) => (
            <div className="bv-finding" key={f.rule_id}>
              <span className="bv-finding-rule">{f.rule_id}</span>
              <span className="bv-finding-label">{f.label}</span>
              <span className="bv-finding-count tnum">×{f.count}</span>
              <span className="bv-finding-action">{f.action}</span>
            </div>
          ))}
          <div className="bv-never">
            <div className="bv-never-lbl">
              <LockKey weight="fill" /> Stays sealed in LOCAL
            </div>
            <div className="bv-never-items">
              {intake.boundary.never_leaves.map((n) => (
                <span className="bv-never-item" key={n}>{n}</span>
              ))}
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
