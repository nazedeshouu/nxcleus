import { useState } from "react";
import { useParams } from "react-router-dom";
import { WarningOctagon } from "@phosphor-icons/react";

import "../components/build/build.css";
import { useJobStream } from "../store/useJobStream";
import { sovereignViolationEvent } from "../fixtures/kycJob";
import { TopStrip } from "../components/build/TopStrip";
import { IntakePanel } from "../components/build/IntakePanel";
import { PlanPanel } from "../components/build/PlanPanel";
import { AuditRail } from "../components/build/AuditRail";
import { WaveBoard } from "../components/build/WaveBoard";
import { ValidationWall, DefectBoard, DeliveryMoment } from "../components/build/QaPanels";
import { Telemetry } from "../components/build/Telemetry";
import { EgressMonitor } from "../components/build/EgressMonitor";

function Cockpit({ jobId }: { jobId: string }) {
  const { view, conn, inject } = useJobStream(jobId, { speed: 16 });

  const simulateBreach = () => inject(sovereignViolationEvent(view.lastSeq + 1000));

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

      <TopStrip view={view} conn={conn} onSimulateBreach={simulateBreach} onRestart={() => location.reload()} />

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

export function BuildView() {
  const { jobId = "" } = useParams();
  // key by jobId so switching jobs (or a hard replay) re-initializes the fold cleanly
  const [nonce] = useState(0);
  return <Cockpit key={`${jobId}:${nonce}`} jobId={jobId} />;
}
