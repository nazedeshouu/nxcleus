import { Compass } from "@phosphor-icons/react";
import styles from "./Placeholder.module.css";

export function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <Compass weight="light" className={styles.icon} />
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.note}>{note}</p>
      </div>
    </div>
  );
}
