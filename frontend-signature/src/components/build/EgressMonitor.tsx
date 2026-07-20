import { WifiHigh, ShieldCheck, WarningOctagon, Scan } from "@phosphor-icons/react";
import { Panel } from "./Panel";
import { ZoneBadge } from "../ui/ZoneBadge";
import { DataClassChip } from "../ui/DataClassChip";
import type { JobView } from "../../store/jobStore";
import type { Zone, DataClass } from "../../lib/events";

export function EgressMonitor({ view }: { view: JobView }) {
  const rows = view.egress;
  const external = rows.filter((r) => r.zone === "EXTERNAL" && !r.violation).length;

  return (
    <Panel
      title="Egress / network monitor"
      icon={WifiHigh}
      status={view.violation ? "default" : "default"}
      tag={`${external} boundary crossing${external === 1 ? "" : "s"}`}
    >
      {rows.length === 0 ? (
        <p className="bv-egress-empty">No egress yet. Everything is running inside the walls.</p>
      ) : (
        <div className="bv-egress-list">
          {rows.map((r) => (
            <div className={`bv-egress-row ${r.violation ? "violation" : ""}`} key={r.seq}>
              {r.violation ? (
                <WarningOctagon weight="fill" style={{ width: 14, height: 14, color: "var(--danger)" }} />
              ) : (
                <ZoneBadge zone={r.zone as Zone} size="xs" />
              )}
              <span className="bv-egress-host">{r.host}</span>
              {r.data_class && !r.violation && <DataClassChip cls={r.data_class as DataClass} size="xs" />}
            </div>
          ))}
        </div>
      )}

      {view.boundarySweep && (
        <div className={`bv-sweep ${view.boundarySweep.clean ? "" : "dirty"}`}>
          <Scan weight="bold" />
          boundary sweep {view.boundarySweep.clean ? "clean" : `· ${view.boundarySweep.findings} finding${view.boundarySweep.findings === 1 ? "" : "s"}`}
          {view.boundarySweep.checked != null && ` · ${view.boundarySweep.checked} endpoints`}
        </div>
      )}

      <div className="bv-egress-note">
        <ShieldCheck weight="fill" />
        The only designed-in crossing is the sanitized planner brief. Everything else runs on the local fleet.
      </div>
    </Panel>
  );
}
