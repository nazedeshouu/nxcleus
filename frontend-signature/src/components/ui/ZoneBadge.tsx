import type { Zone } from "../../lib/events";
import styles from "./ZoneBadge.module.css";

const LABEL: Record<Zone, string> = {
  LOCAL: "LOCAL",
  AMD_HOSTED: "AMD-HOSTED",
  CUSTOM: "CUSTOM",
  EXTERNAL: "EXTERNAL",
};

/** Zone = position relative to the wall. Temperature-coded per DESIGN.md §3. */
export function ZoneBadge({ zone, size = "sm" }: { zone: Zone; size?: "sm" | "xs" }) {
  return (
    <span className={`${styles.badge} ${styles[zone]} ${size === "xs" ? styles.xs : ""}`}>
      <span className={styles.dot} aria-hidden />
      {LABEL[zone]}
    </span>
  );
}
