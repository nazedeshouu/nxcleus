import { useState } from "react";
import { FileText, Database, IdentificationCard, LockKey, ShieldCheck, ArrowLineUpRight, Cpu } from "@phosphor-icons/react";
import styles from "./BoundaryDiagram.module.css";

const RAW_ITEMS = [
  { icon: FileText, label: "Documents" },
  { icon: Database, label: "DB schemas" },
  { icon: IdentificationCard, label: "Customer PII" },
];

/**
 * The boundary made legible: RAW stays sealed in LOCAL; a single SANITIZED brief
 * crosses to the frontier planner. Sovereign Mode seals the aperture, planner
 * rebinds local, zero external calls. This is the landing's astonish beat.
 */
export function BoundaryDiagram() {
  const [sovereign, setSovereign] = useState(false);

  return (
    <div className={`${styles.wrap} ${sovereign ? styles.sov : ""}`}>
      <div className={styles.stage} data-sovereign={sovereign}>
        {/* LOCAL zone */}
        <div className={styles.zone}>
          <div className={styles.zoneHead}>
            <span className={`${styles.zoneTag} ${styles.local}`}>
              <span className={styles.tagDot} /> LOCAL
            </span>
            <span className={styles.zoneSub}>inside your walls · AMD MI300X</span>
          </div>
          <div className={styles.rawStack}>
            {RAW_ITEMS.map((r) => (
              <div className={styles.rawItem} key={r.label}>
                <r.icon weight="regular" />
                <span>{r.label}</span>
                <LockKey weight="fill" className={styles.rawLock} />
              </div>
            ))}
          </div>
          <div className={styles.trust}>
            <ShieldCheck weight="fill" />
            <div>
              <div className={styles.trustTitle}>Trust layer</div>
              <div className={styles.trustSub}>PII firewall + policy-governed masking</div>
            </div>
          </div>
          {sovereign && (
            <div className={styles.localPlanner}>
              <Cpu weight="fill" />
              <span>Planner runs local (GLM)</span>
            </div>
          )}
        </div>

        {/* the wall + crossing */}
        <div className={styles.wall}>
          <div className={styles.wallLine} />
          <div className={`${styles.aperture} ${sovereign ? styles.sealed : ""}`}>
            {sovereign ? <LockKey weight="fill" /> : null}
          </div>
          {!sovereign && (
            <div className={styles.brief} aria-hidden>
              <ArrowLineUpRight weight="bold" />
              <span>sanitized brief</span>
            </div>
          )}
          <div className={styles.wallLabel}>{sovereign ? "0 external calls" : "1 designed-in crossing"}</div>
        </div>

        {/* EXTERNAL zone */}
        <div className={`${styles.zone} ${styles.external}`}>
          <div className={styles.zoneHead}>
            <span className={`${styles.zoneTag} ${styles.ext}`}>
              <span className={styles.tagDot} /> EXTERNAL
            </span>
            <span className={styles.zoneSub}>frontier planner</span>
          </div>
          <div className={`${styles.frontier} ${sovereign ? styles.dim : ""}`}>
            <div className={styles.frontierModel}>Claude Fable 5</div>
            <div className={styles.frontierNote}>
              {sovereign ? "Not called in Sovereign Mode" : "Sees only the sanitized brief. Never your data."}
            </div>
          </div>
        </div>
      </div>

      <div className={styles.controls}>
        <div className={styles.controlText}>
          <strong>Sovereign Mode</strong>
          <span>Move planning on-fleet. Zero external calls.</span>
        </div>
        <button
          role="switch"
          aria-checked={sovereign}
          aria-label="Toggle Sovereign Mode"
          className={`${styles.switch} ${sovereign ? styles.switchOn : ""}`}
          onClick={() => setSovereign((s) => !s)}
        >
          <span className={styles.knob} />
        </button>
      </div>
    </div>
  );
}
