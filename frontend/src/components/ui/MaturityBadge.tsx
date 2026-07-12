import styles from "./MaturityBadge.module.css";

/** Quiet "Preview" pill for surfaces that are fixture-backed, stubbed, or otherwise not
 * production-ready. Native title tooltip — no popover machinery. Place at the section/page title. */
export function MaturityBadge({
  label = "Preview",
  tip = "Not production-ready — demo build",
  size = "sm",
}: { label?: string; tip?: string; size?: "sm" | "xs" }) {
  return (
    <span
      className={`${styles.badge} ${size === "xs" ? styles.xs : ""}`}
      title={tip}
      aria-label={`${label} — ${tip}`}
    >
      {label}
    </span>
  );
}
