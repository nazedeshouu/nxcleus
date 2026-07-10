import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { WarningOctagon, Warning, Play, ArrowRight, MagnifyingGlass } from "@phosphor-icons/react";

import "../components/build/build.css";
import { useBreadcrumb } from "../components/shell/breadcrumbs";
import { useJobStream } from "../store/useJobStream";
import { sovereignViolationEvent } from "../fixtures/kycJob";
import type { JobView } from "../store/jobStore";
import type { ConnState } from "../api/sse";
import { TopStrip } from "../components/build/TopStrip";
import { IntakePanel } from "../components/build/IntakePanel";
import { ClarifyPanel } from "../components/build/ClarifyPanel";
import { StageGate } from "../components/build/StageGate";
import { PlanPanel } from "../components/build/PlanPanel";
import { CertifyPanel } from "../components/build/CertifyPanel";
import { AuditRail } from "../components/build/AuditRail";
import { WaveBoard } from "../components/build/WaveBoard";
import { ValidationWall, DefectBoard, DeliveryMoment } from "../components/build/QaPanels";
import { Telemetry } from "../components/build/Telemetry";
import { EgressMonitor } from "../components/build/EgressMonitor";

/** The cockpit chrome + panel grid, driven purely by a folded view. Shared by
 *  the live BuildView and the replay player — same fold, same panels. */
export function CockpitFrame({ view, top, jobId, completion }: { view: JobView; top: ReactNode; jobId?: string; completion?: ReactNode }) {
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
          <Link to="/build">Build another process →</Link>
        </div>
      )}

      {top}
      {completion}

      <div className="bv-grid">
        <div className="bv-col bv-col-left bv-col-side">
          <AuditRail view={view} />
        </div>

        <div className="bv-col bv-col-center">
          <ClarifyPanel view={view} jobId={jobId} />
          <StageGate view={view} jobId={jobId} />
          <IntakePanel view={view} />
          <PlanPanel view={view} />
          <CertifyPanel view={view} />
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

function CompletionBar({ jobId, processId }: { jobId: string; processId?: string }) {
  return (
    <div className="bv-complete-bar" role="status">
      <span className="bv-complete-lbl">Build complete.</span>
      <Link to={`/replay/job/${jobId}`} className="bv-complete-btn">
        <Play weight="fill" /> Replay this build
      </Link>
      <Link to={processId ? `/operations/${processId}` : "/operations"} className="bv-complete-btn">
        <ArrowRight weight="bold" /> View process
      </Link>
      <Link to={`/traces?scope=${encodeURIComponent(`job:${jobId}`)}`} className="bv-complete-btn bv-complete-ghost">
        <MagnifyingGlass weight="bold" /> Inspect prompts
      </Link>
    </div>
  );
}

function Cockpit({ jobId }: { jobId: string }) {
  const { view, conn, inject } = useJobStream(jobId, { speed: 16 });
  const simulateBreach = () => inject(sovereignViolationEvent(view.lastSeq + 1000));
  const done = view.status === "done" || view.status === "delivered";
  useBreadcrumb([{ label: "Build", to: "/build" }, { label: view.title ?? "Mission control" }]);

  const top = (
    <TopStrip
      view={view}
      conn={conn as ConnState}
      onSimulateBreach={simulateBreach}
      onRestart={() => location.reload()}
    />
  );
  const completion = done ? <CompletionBar jobId={jobId} processId={view.delivery?.process_id} /> : undefined;
  return <CockpitFrame view={view} top={top} jobId={jobId} completion={completion} />;
}

export function BuildView() {
  const { jobId = "" } = useParams();
  // key by jobId so switching jobs (or a hard replay) re-initializes the fold cleanly
  const [nonce] = useState(0);
  return <Cockpit key={`${jobId}:${nonce}`} jobId={jobId} />;
}
