import { useParams } from "react-router-dom";
import { Play, Pause } from "@phosphor-icons/react";
import "../components/build/build.css";
import { useReplay, type ReplaySpeed } from "../store/useReplay";
import { CockpitFrame } from "./BuildView";
import { TopStrip } from "../components/build/TopStrip";
import styles from "./Replay.module.css";

const SPEEDS: ReplaySpeed[] = [1, 4, 16];

function TransportBar(r: ReturnType<typeof useReplay>) {
  const current = r.cursor > 0 ? r.events[r.cursor - 1]?.type : undefined;
  return (
    <div className={styles.bar}>
      <button className={styles.play} onClick={r.toggle} aria-label={r.playing ? "Pause" : "Play"}>
        {r.playing ? <Pause weight="fill" /> : <Play weight="fill" />}
      </button>
      <div className={styles.track}>
        <input
          className={styles.range}
          type="range"
          min={0}
          max={r.events.length}
          value={r.cursor}
          onChange={(e) => r.seek(Number(e.target.value))}
          aria-label="Seek"
        />
        <span className={styles.counter}>{r.cursor} / {r.events.length}</span>
      </div>
      {current && <span className={styles.now}>{current}</span>}
      <div className={styles.speeds}>
        {SPEEDS.map((s) => (
          <button key={s} className={`${styles.speed} ${r.speed === s ? styles.on : ""}`} onClick={() => r.setSpeed(s)}>
            ×{s}
          </button>
        ))}
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
  if (r.error || r.events.length === 0) {
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
      <TransportBar {...r} />
    </>
  );

  return <CockpitFrame view={r.view} top={top} />;
}
