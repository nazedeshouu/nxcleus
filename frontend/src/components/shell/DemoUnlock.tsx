import { useState } from "react";
import { Key, Check } from "@phosphor-icons/react";
import { getDemoToken, setDemoToken, hasDemoToken } from "../../api/config";
import styles from "./DemoUnlock.module.css";

/** Stores X-Demo-Token; unlocking reveals presenter-only controls (06 §1). */
export function DemoUnlock() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState(getDemoToken() ?? "");
  const [unlocked, setUnlocked] = useState(hasDemoToken());

  const save = () => {
    setDemoToken(token.trim() || null);
    setUnlocked(!!token.trim());
    setOpen(false);
  };

  return (
    <div className={styles.wrap}>
      <button
        className={`${styles.trigger} ${unlocked ? styles.on : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {unlocked ? <Check weight="bold" /> : <Key weight="regular" />}
        {unlocked ? "Presenter" : "Presenter mode"}
      </button>
      {open && (
        <div className={styles.pop} role="dialog" aria-label="Presenter unlock">
          <label className={styles.label} htmlFor="demo-token">
            Demo token
          </label>
          <p className={styles.help}>Unlocks create, approve, refine, and the Sovereign Mode switch.</p>
          <input
            id="demo-token"
            className={styles.input}
            type="password"
            value={token}
            placeholder="X-Demo-Token"
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && save()}
            autoFocus
          />
          <div className={styles.row}>
            <button className={styles.primary} onClick={save}>
              {token.trim() ? "Unlock" : "Lock"}
            </button>
            <button className={styles.ghost} onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
