import { useState, type FormEvent } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Logo } from "../brand/Logo";
import { authApi } from "../api/client";
import styles from "./Login.module.css";

export function Login() {
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (loc.state as { from?: string } | null)?.from ?? "/build";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await authApi.login(username.trim(), password);
      await qc.invalidateQueries({ queryKey: ["auth", "me"] });
      nav(from, { replace: true });
    } catch (err) {
      setError((err as Error)?.message || "Sign-in failed");
      setBusy(false);
    }
  };

  return (
    <div className={styles.screen} data-temp="inside">
      <form className={styles.card} onSubmit={submit}>
        <Link to="/" className={styles.brand} aria-label="Nxcleus home">
          <Logo size={22} tone="invert" />
        </Link>
        <div className={styles.head}>
          <h1 className={styles.title}>Sign in</h1>
          <p className={styles.sub}>Access the Nxcleus control plane.</p>
        </div>

        <label className={styles.field}>
          <span className={styles.label}>Username</span>
          <input
            className={styles.input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Password</span>
          <input
            className={styles.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && <div className={styles.error} role="alert">{error}</div>}

        <button className={styles.submit} type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
