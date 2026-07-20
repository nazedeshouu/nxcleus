import { useState, type MouseEvent } from "react";
import styles from "./ShortId.module.css";

/** Display-only short form of a long prefixed-ULID id: first `chars` glyphs in muted mono,
 *  full id in the title, copied on click. Never changes what is sent to the API. */
export function ShortId({ id, chars = 8 }: { id: string; chars?: number }) {
  const [copied, setCopied] = useState(false);
  if (!id) return null;
  const truncated = id.length > chars;
  const copy = (e: MouseEvent) => {
    e.stopPropagation(); // ids often sit inside clickable rows — copy, don't trigger the row
    e.preventDefault();
    navigator.clipboard?.writeText(id).catch(() => undefined);
    setCopied(true);
    setTimeout(() => setCopied(false), 1000);
  };
  return (
    <button type="button" className={styles.id} title={id} onClick={copy}>
      {copied ? "copied" : truncated ? `${id.slice(0, chars)}…` : id}
    </button>
  );
}
