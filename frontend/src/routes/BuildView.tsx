import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { WarningOctagon, Warning } from "@phosphor-icons/react";

import "../components/build/build.css";
import { useJobStream } from "../store/useJobStream";
import { sovereignViolationEvent } from "../fixtures/kycJob";
import type { JobView } from "../store/jobStore";
import type { ConnState } from "../api/sse";
import { TopStrip } from "../components/build/TopStrip";
import { IntakePanel } from "../components/build/IntakePanel";
import { PlanPanel } from "../components/build/PlanPanel";
import { AuditRail } from "../components/build/AuditRail";
import { WaveBoard } from "../components/build/WaveBoard";
import { ValidationWall, DefectBoard, DeliveryMoment } from "../components/build/QaPanels";
import { Telemetry } from "../components/build/Telemetry";
import { EgressMonitor } from "../components/build/EgressMonitor";

/** The cockpit chrome + panel grid, driven purely by a folded view. Shared by
 *  the live BuildView and the replay player — same fold, same panels. */
export function CockpitFrame({ view, top }: { view: JobView; top: ReactNode }) {
  const blocked = view.status === "blocked" || view.status === "aborted";
  return (
    <div className="bv-root">
      {view.violation && (
        <div className="bv-violation-banner" role="alert">
          <WarningOctagon weight="fill" />
          <div>
            <b>Sovereign boundary held.</b>
            <p>{view.violation.detail}</p>
          </div>
        </div>
      )}

      {blocked && !view.violation && (
        <div className="bv-blocked-banner" role="status">
          <Warning weight="fill" />
          <div style={{ flex: 1 }}>
            <b>Run {view.status} at stage {view.stage}.</b>
            <p>{view.blockedReason ?? "The engine halted this run."}</p>
          </div>
          <Link to="/gallery">Watch a completed run →</Link>
        </div>
      )}

      {top}

      <div className="bv-grid">
        <div className="bv-col bv-col-left bv-col-side">
          <AuditRail view={view} />
        </div>

        <div className="bv-col bv-col-center">
          <IntakePanel view={view} />
          <PlanPanel view={view} />
          <WaveBoard view={view} />
          <ValidationWall view={view} />
          <DefectBoard view={view} />
          <DeliveryMoment view={view} />
        </div>

        <div className="bv-col bv-col-right bv-col-side">
          <Telemetry view={view} />
          <EgressMonitor view={view} />
        </div>
      </div>
    </div>
  );
}

function Cockpit({ jobId }: { jobId: string }) {
  const { view, conn, inject } = useJobStream(jobId, { speed: 16 });
  const simulateBreach = () => inject(sovereignViolationEvent(view.lastSeq + 1000));

  const top = (
    <TopStrip
      view={view}
      conn={conn as ConnState}
      onSimulateBreach={simulateBreach}
      onRestart={() => location.reload()}
    />
  );
  return <CockpitFrame view={view} top={top} />;
}

export function BuildView() {
  const { jobId = "" } = useParams();
  // key by jobId so switching jobs (or a hard replay) re-initializes the fold cleanly
  const [nonce] = useState(0);
  return <Cockpit key={`${jobId}:${nonce}`} jobId={jobId} />;
}
