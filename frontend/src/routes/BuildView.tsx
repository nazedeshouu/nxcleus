import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowCounterClockwise,
  ArrowRight,
  MagnifyingGlass,
  PencilSimple,
  Play,
  TreeStructure,
  Warning,
  WarningOctagon,
} from "@phosphor-icons/react";

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
import { PlanArtifact } from "../components/build/PlanArtifact";
import { CertifyPanel } from "../components/build/CertifyPanel";
import { AuditRail } from "../components/build/AuditRail";
import { WaveBoard } from "../components/build/WaveBoard";
import { ValidationWall, DefectBoard, DeliveryMoment } from "../components/build/QaPanels";
import { Telemetry } from "../components/build/Telemetry";
import { EgressMonitor } from "../components/build/EgressMonitor";
import { api } from "../api/client";
import { useDemoToken } from "../api/useDemoToken";

function BlockedRecovery({ jobId }: { jobId: string }) {
  const unlocked = useDemoToken();
  const [editing, setEditing] = useState(false);
  const [correction, setCorrection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function retry(value = "") {
    setBusy(true);
    setError("");
    try {
      await api.retryJob(jobId, value);
      setEditing(false);
    } catch (err) {
      setError((err as Error).message || "Could not restart this stage.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bv-recovery">
      <div className="bv-recovery-actions">
        <button type="button" disabled={!unlocked || busy} onClick={() => retry()}>
          <ArrowCounterClockwise weight="bold" /> Retry stage
        </button>
        <button type="button" disabled={!unlocked || busy} onClick={() => setEditing((value) => !value)}>
          <PencilSimple weight="bold" /> Edit request
        </button>
        <Link to="/build">Start over</Link>
      </div>
      {editing && (
        <form
          className="bv-recovery-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (correction.trim()) retry(correction.trim());
          }}
        >
          <label htmlFor="blocked-correction">What should the failed stage do differently?</label>
          <textarea
            id="blocked-correction"
            value={correction}
            maxLength={4000}
            rows={3}
            autoFocus
            onChange={(event) => setCorrection(event.target.value)}
            placeholder="Example: only review claims above 2,500 USD and return a CSV."
          />
          <button type="submit" disabled={busy || !correction.trim()}>Apply correction & retry</button>
        </form>
      )}
      {!unlocked && <p className="bv-recovery-note">Sign in to retry this job.</p>}
      {error && <p className="bv-recovery-error" role="alert">{error}</p>}
    </div>
  );
}

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
            {view.status === "blocked" && jobId && <BlockedRecovery jobId={jobId} />}
          </div>
          {view.status === "aborted" && <Link to="/build">Start over →</Link>}
        </div>
      )}

      {top}
      {jobId && (
        <Link
          to={`/build/${jobId}/map`}
          style={{
            display: "inline-flex", alignItems: "center", gap: 7, alignSelf: "flex-start",
            margin: "0 0 4px", padding: "8px 14px", borderRadius: "var(--r-pill)",
            border: "1px solid color-mix(in srgb, var(--accent) 38%, transparent)",
            background: "var(--accent-wash)", color: "var(--accent-strong)",
            fontSize: "var(--fs-xs)", fontWeight: 600, textDecoration: "none",
          }}
        >
          <TreeStructure weight="bold" style={{ width: 15, height: 15 }} /> View run map — live agent graph
        </Link>
      )}
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
          <PlanArtifact jobId={jobId} />
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
