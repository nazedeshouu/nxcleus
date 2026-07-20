import type { DatasetOrigin } from "../../api/client";
import styles from "./OriginBadge.module.css";

const LABEL: Record<DatasetOrigin, string> = {
  builtin: "built-in",
  upload: "upload",
  connector: "connected",
  codebase: "codebase",
};

/** Provenance of a data source, temperature-coded like zones. */
export function OriginBadge({ origin, size = "sm" }: { origin: DatasetOrigin; size?: "sm" | "xs" }) {
  return (
    <span className={`${styles.badge} ${styles[origin]} ${size === "xs" ? styles.xs : ""}`}>
      {LABEL[origin]}
    </span>
  );
}
