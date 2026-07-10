import type { DataClass } from "../../lib/events";
import { LockKey, ArrowLineUpRight } from "@phosphor-icons/react";
import styles from "./DataClassChip.module.css";

/**
 * RAW = sealed (filled ink chip, lock). Never leaves LOCAL.
 * SANITIZED = outlined cool. The only thing that crosses the wall.
 */
export function DataClassChip({ cls, size = "sm" }: { cls: DataClass; size?: "sm" | "xs" }) {
  const raw = cls === "RAW";
  return (
    <span
      className={`${styles.chip} ${raw ? styles.raw : styles.san} ${size === "xs" ? styles.xs : ""}`}
      title={raw
        ? "Raw customer data — sealed inside LOCAL, never crosses the boundary"
        : "Sanitized brief — names and identifiers stripped; the only thing allowed to cross the wall"}
    >
      {raw ? <LockKey weight="fill" /> : <ArrowLineUpRight weight="bold" />}
      {cls}
    </span>
  );
}
