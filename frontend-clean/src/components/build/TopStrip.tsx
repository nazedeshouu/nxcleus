import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Target, WarningOctagon, ArrowClockwise, MagnifyingGlass } from "@phosphor-icons/react";
import type { JobView } from "../../store/jobStore";
import type { ConnState } from "../../api/sse";
import { ShortId } from "../ui/ShortId";
import { MaturityBadge } from "../ui/MaturityBadge";
import { usd } from "../../lib/format";

const STAGES: { n: number; name: string }[] = [
  { n: 0, name: "Intake & boundary" },
  { n: 1, name: "Planning" },
  { n: 2, name: "Certify" },
  { n: 3, name: "Quote" },
  { n: 4, name: "Build" },
  { n: 5, name: "Consolidate" },
  { n: 6, name: "QA" },
  { n: 7, name: "Deliver" },
];

function stageClass(view: JobView, n: number): string {
  const processMode = view.mode === "process";
  if (processMode && (n === 4 || n === 5)) return "skipped";
  if (view.stage > n || view.status === "done" || view.status === "delivered") return "done";
  if (view.stage === n) return "active";
  return "";
}

export function TopStrip({
  view,
  conn,
  onSimulateBreach,
  onRestart,
  controls,
  connLabel,
}: {
  view: JobView;
  conn: ConnState;
  onSimulateBreach?: () => void;
  onRestart?: () => void;
  controls?: ReactNode; // replaces the presenter buttons (e.g. replay transport)
  connLabel?: string; // override the connection pill text (e.g. "replay")
}) {
  const cost = view.cost.cost_usd;
  const high = view.quote.high;
  const fillPct = high ? Math.min(100, (cost / high) * 100) : 0;

  return (
    <div className="bv-top">
      <div className="bv-title-row">
        <div>
          <h1 className="bv-title">{view.title ?? "Build job"}</h1>
          <div className="bv-title-sub"><ShortId id={view.scope.replace(/^job:/, "")} /></div>
        </div>
        <div className="bv-title-meta">
          {view.mockDispatches > 0 && (
            <span className="bv-simchip" title="Some model calls fell through to a simulated (mock) backend under load — this run is not fully live.">
              <i /> {view.mockDispatches} simulated
            </span>
          )}
          <span className={`bv-conn ${conn}`}>
            <i /> {connLabel ?? (conn === "open" ? "streaming" : conn)}
          </span>
          <Link className="bv-inspect" to={`/traces?scope=${encodeURIComponent(view.scope)}`} title="Per-dispatch prompts, tokens, and costs — LOCAL-only">
            <MagnifyingGlass weight="bold" /> Model activity
          </Link>
          {controls ?? (
            <div className="bv-presenter">
              <MaturityBadge label="Demo" tip="Injects a simulated boundary violation — a scripted demonstration, not a live event" size="xs" />
              <button className="danger" onClick={onSimulateBreach} title="Demo: inject a simulated blocked external call to show the boundary catching a violation">
                <WarningOctagon weight="regular" /> Simulate breach
              </button>
              <button onClick={onRestart} title="Replay from the first event">
                <ArrowClockwise weight="regular" /> Replay
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="bv-stagerail" role="list" aria-label="Pipeline stages">
        {STAGES.map((s) => (
          <div className={`bv-stage ${stageClass(view, s.n)}`} key={s.n} role="listitem">
            <div className="bv-stage-num">STAGE {s.n}</div>
            <div className="bv-stage-name">{s.name}</div>
          </div>
        ))}
      </div>

      {view.now && (
        <div className={`bv-now ${view.status === "done" || view.status === "delivered" ? "settled" : ""}`} role="status" aria-live="polite">
          <i className="bv-now-dot" />
          <span className="bv-now-stage">{STAGES[view.stage]?.name ?? `stage ${view.stage}`}</span>
          <span className="bv-now-text" key={view.now.seq}>{view.now.text}</span>
        </div>
      )}

      <div className="bv-strip">
        <div className="bv-goal">
          <Target weight="fill" className="bv-goal-icon" />
          <div>
            <div className="bv-goal-label">Goal — what we promised</div>
            {view.certify.goal ? (
              <p className="bv-goal-text">{view.certify.goal}</p>
            ) : (
              <p className="bv-goal-text bv-goal-pending">Pinned at certification (stage 2).</p>
            )}
          </div>
        </div>

        <div className="bv-meter">
          <div className="bv-meter-top">
            <span className="bv-meter-cost">{usd(cost)}</span>
            <span className="bv-meter-quote">
              {high ? `quote ${usd(view.quote.low ?? 0)}–${usd(high)}` : "metering…"}
            </span>
          </div>
          <div className="bv-meter-track">
            <div className="bv-meter-fill" style={{ width: `${fillPct}%` }} />
          </div>
          <div className="bv-meter-sub">
            <span>{(view.cost.tokens / 1000).toFixed(1)}k tok</span>
            <span>{view.cost.gpu_seconds}s GPU</span>
            {view.quote.approved != null && <span>approved {usd(view.quote.approved)}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
