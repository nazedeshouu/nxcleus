import { BRAND } from "./brand";
import styles from "./Logo.module.css";

type Props = {
  /** hide the wordmark, mark only */
  markOnly?: boolean;
  /** tune size via font-size on the wrapper */
  size?: number;
  /** sovereign chrome inverts the colors */
  tone?: "default" | "invert";
  className?: string;
};

/**
 * The mark: sealed walls (rounded enclosure) with a single aperture on the
 * right edge, and a nucleus at the center. One boundary, one crossing.
 * This is a functional trademark, so it lives in the DOM as SVG.
 */
export function Logo({ markOnly = false, size = 20, tone = "default", className }: Props) {
  return (
    <span
      className={`${styles.logo} ${tone === "invert" ? styles.invert : ""} ${className ?? ""}`}
      style={{ fontSize: size }}
      aria-label={BRAND.name}
    >
      <svg className={styles.mark} viewBox="0 0 28 28" width="1.4em" height="1.4em" aria-hidden="true">
        {/* walls with an aperture gap on the right */}
        <path
          d="M18.5 4.2 A11 11 0 1 0 24.4 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinecap="round"
          className={styles.walls}
        />
        {/* nucleus */}
        <circle cx="14" cy="14" r="3.4" className={styles.nucleus} />
        {/* the single crossing: a sanitized mote leaving through the aperture */}
        <circle cx="23.2" cy="10.4" r="1.35" className={styles.mote} />
      </svg>
      {!markOnly && <span className={styles.word}>{BRAND.name}</span>}
    </span>
  );
}
