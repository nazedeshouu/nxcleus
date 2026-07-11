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
 * The mark: a sealed enclosure (the walls) with a single aperture on the right
 * edge, a nucleus held at the center, and one sanitized mote crossing out.
 * One boundary, one crossing. Trademark, so it lives in the DOM as SVG.
 */
export function Logo({ markOnly = false, size = 20, tone = "default", className }: Props) {
  return (
    <span
      className={`${styles.logo} ${tone === "invert" ? styles.invert : ""} ${className ?? ""}`}
      style={{ fontSize: size }}
      aria-label={BRAND.name}
    >
      <svg className={styles.mark} viewBox="0 0 28 28" width="1.4em" height="1.4em" aria-hidden="true">
        {/* walls: a rounded enclosure broken by one aperture on the right edge */}
        <path
          d="M24 16.5 V18 A6 6 0 0 1 18 24 H10 A6 6 0 0 1 4 18 V10 A6 6 0 0 1 10 4 H18 A6 6 0 0 1 24 10 V11.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={styles.walls}
        />
        {/* nucleus: the data held inside the walls */}
        <circle cx="14" cy="14" r="3.2" className={styles.nucleus} />
        {/* the single crossing: a sanitized mote leaving through the aperture */}
        <circle cx="25.4" cy="14" r="1.5" className={styles.mote} />
      </svg>
      {!markOnly && <span className={styles.word}>{BRAND.name}</span>}
    </span>
  );
}
