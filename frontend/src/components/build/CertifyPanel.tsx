import { ListChecks, ArrowsLeftRight } from "@phosphor-icons/react";
import { Panel, type PanelStatus } from "./Panel";
import type { JobView } from "../../store/jobStore";

/** Stage-2 live surface: checks as they run, adversarial scenarios, consult
 *  beats. The full consult receipts live in the audit rail; this is the pulse. */
export function CertifyPanel({ view }: { view: JobView }) {
  const { certify, plan } = view;
  const status: PanelStatus = view.stage === 2 ? "active" : certify.certified ? "ok" : "pending";
  const consultsOpen = certify.consults.filter((c) => !c.resolution).length;
  const empty = !certify.checks.length && !certify.scenariosEmitted && !certify.certified && !certify.consults.length;

  return (
    <Panel
      title="Certification"
      icon={ListChecks}
      status={status}
      tag={certify.certified ? `${certify.certified.tests} tests · ${certify.certified.vectors} vectors` : "stage 2"}
    >
      {empty && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          The certifier hardens the plan: independent checks, adversarial scenarios, scope locks.
        </p>
      )}

      {certify.checks.length > 0 && (
        <div className="bv-cert-checks">
          {certify.checks.map((c) => (
            <div className={`bv-cert-check ${c.status}`} key={c.check}>
              <i className="bv-cert-dot" />
              <span className="bv-cert-name">{c.check}</span>
              {c.finding && <span className="bv-cert-finding">{c.finding}</span>}
            </div>
          ))}
        </div>
      )}

      {(certify.scenariosEmitted != null || certify.rehydrated != null || consultsOpen > 0 || certify.consults.length > 0) && (
        <div className="bv-cert-stats">
          {certify.scenariosEmitted != null && (
            <span className="bv-cert-stat">{certify.scenariosEmitted} adversarial scenarios</span>
          )}
          {certify.rehydrated != null && (
            <span className="bv-cert-stat ok">{certify.rehydrated} identifiers rehydrated locally</span>
          )}
          {certify.consults.length > 0 && (
            <span className="bv-cert-stat">
              <ArrowsLeftRight weight="bold" style={{ width: 10, verticalAlign: "-1px", marginRight: 3 }} />
              {consultsOpen > 0
                ? `consult in flight (${consultsOpen})`
                : `${certify.consults.length} consult${certify.consults.length === 1 ? "" : "s"} resolved`}
            </span>
          )}
        </div>
      )}

      {plan.replans.map((r) => (
        <div className="bv-replan" key={r.seq}>
          Plan revised{r.wave != null ? ` after wave ${r.wave}` : ""}{r.note ? ` — ${r.note}` : ", scope lock enforced."}
        </div>
      ))}
    </Panel>
  );
}
