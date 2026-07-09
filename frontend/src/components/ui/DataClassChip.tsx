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
    <span className={`${styles.chip} ${raw ? styles.raw : styles.san} ${size === "xs" ? styles.xs : ""}`}>
      {raw ? <LockKey weight="fill" /> : <ArrowLineUpRight weight="bold" />}
      {cls}
    </span>
  );
}
