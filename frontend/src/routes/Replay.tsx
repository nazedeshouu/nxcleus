import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Play, Pause } from "@phosphor-icons/react";
import "../components/build/build.css";
import { useReplay, type ReplaySpeed, type UseReplay } from "../store/useReplay";
import { whenLabel } from "../lib/format";
import { CockpitFrame } from "./BuildView";
import { TopStrip } from "../components/build/TopStrip";
import styles from "./Replay.module.css";

const SPEEDS: ReplaySpeed[] = [1, 4, 16];

/** MM:SS (or H:MM:SS past an hour) for the elapsed/total time axis. */
function mmss(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** "6m 12s" / "45s" / "1h 03m" for the recorded-duration caption. */
function ran(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${String(m % 60).padStart(2, "0")}m`;
  const rs = s % 60;
  return rs ? `${m}m ${rs}s` : `${m}m`;
}

const wallTime = (epoch: number) =>
  new Date(epoch).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function TransportBar({ r }: { r: UseReplay }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; label: string } | null>(null);
  const end = r.playbackEnd || 1;
  const pct = Math.min(100, (r.clockMs / end) * 100);

  const onMove = (e: React.MouseEvent) => {
    const el = trackRef.current;
    if (!el || r.playbackEnd === 0) return;
    const rect = el.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setHover({ x: frac * rect.width, label: wallTime(r.wallClockAt(frac * r.playbackEnd)) });
  };

  return (
    <div className={styles.bar}>
      <div className={styles.meta}>
        <span className={styles.recorded}>Recorded {whenLabel(new Date(r.startEpoch).toISOString())}</span>
        <span className={styles.dot} />
        <span>ran {ran(r.totalRealMs)}</span>
        <span className={styles.dot} />
        <span className={styles.wall}>{wallTime(r.wallClockAt(r.clockMs))}</span>
      </div>
      <div className={styles.transport}>
        <button className={styles.play} onClick={r.toggle} aria-label={r.playing ? "Pause" : "Play"}>
          {r.playing ? <Pause weight="fill" /> : <Play weight="fill" />}
        </button>
        <div className={styles.track} ref={trackRef} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          <input
            className={styles.range}
            style={{ background: `linear-gradient(to right, var(--accent) ${pct}%, var(--surface-sunk) ${pct}%)` }}
            type="range"
            min={0}
            max={r.playbackEnd}
            step={Math.max(1, Math.round(r.playbackEnd / 600))}
            value={r.clockMs}
            onChange={(e) => r.seek(Number(e.target.value))}
            aria-label="Seek timeline"
          />
          {hover && (
            <span className={styles.tip} style={{ left: hover.x }}>
              {hover.label}
            </span>
          )}
        </div>
        <span className={styles.counter}>
          {mmss(r.elapsedRealMs)} <i>/</i> {mmss(r.totalRealMs)}
        </span>
        <div className={styles.speeds}>
          {SPEEDS.map((s) => (
            <button key={s} className={`${styles.speed} ${r.speed === s ? styles.on : ""}`} onClick={() => r.setSpeed(s)}>
              ×{s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Replay() {
  const { kind = "job", id = "" } = useParams();
  const scope = `${kind}:${id}`;
  const r = useReplay(scope);

  if (r.loading) {
    return (
      <div className="bv-root">
        <div className={styles.loading}>Loading replay…</div>
      </div>
    );
  }
  if (r.error || !r.hasTimeline) {
    return (
      <div className="bv-root">
        <div className={styles.loading}>{r.error ? `Could not load replay: ${r.error}` : "No events to replay for this scope."}</div>
      </div>
    );
  }

  const badge = <span className={styles.badge}><i /> Replay</span>;
  const top = (
    <>
      <TopStrip view={r.view} conn="open" controls={badge} connLabel="replay" />
      <TransportBar r={r} />
    </>
  );

  return <CockpitFrame view={r.view} top={top} jobId={kind === "job" ? id : undefined} />;
}
