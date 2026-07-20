import { GitBranch, Cube, Stack } from "@phosphor-icons/react";
import { Panel, type PanelStatus } from "./Panel";
import { ZoneBadge } from "../ui/ZoneBadge";
import type { JobView } from "../../store/jobStore";

export function PlanPanel({ view }: { view: JobView }) {
  const { plan } = view;
  const status: PanelStatus = view.stage === 1 ? "active" : plan.summary ? "ok" : "pending";
  const showStream = plan.streaming || (!plan.summary && plan.deltaText);

  return (
    <Panel
      title="Plan"
      icon={GitBranch}
      status={status}
      tag={plan.plannerModel ? plan.plannerModel.replace(/^anthropic:/, "") : "stage 1"}
    >
      {!plan.deltaText && !plan.summary && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          The frontier planner sees only the sanitized brief.
        </p>
      )}

      {showStream && (
        <div className="bv-planstream">
          {plan.deltaText}
          {plan.streaming && <span className="bv-cursor" />}
        </div>
      )}

      {plan.summary && (
        <>
          <div className="bv-plan-meta">
            {plan.topology && (
              <span className="bv-topology">
                <GitBranch weight="bold" /> {plan.topology} parallelism
              </span>
            )}
            {plan.modules != null && (
              <span className="bv-topology" style={{ background: "var(--surface-sunk)", color: "var(--text-muted)" }}>
                <Cube weight="bold" /> {plan.modules} modules
              </span>
            )}
          </div>
          <p className="bv-plan-summary">{plan.summary}</p>
        </>
      )}

      {plan.bom.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="bv-panel-title" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <Stack weight="regular" style={{ width: 15, height: 15, color: "var(--text-muted)" }} />
            Model bill of materials
          </div>
          <div className="bv-bom">
            {plan.bom.map((b, i) => (
              <div className="bv-bom-row" key={i}>
                <span className="bv-bom-seat">{b.seat}</span>
                <div>
                  <div className="bv-bom-model">
                    {b.model} <ZoneBadge zone={b.zone} size="xs" />
                  </div>
                  <div className="bv-bom-why">{b.why}</div>
                </div>
                <span className="bv-bom-count tnum">×{b.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
