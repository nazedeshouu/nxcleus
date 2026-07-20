import { useRef, useState, type FormEvent } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Eye, EyeSlash, ArrowRight, CircleNotch, WarningCircle } from "@phosphor-icons/react";
import { Logo } from "../brand/Logo";
import { authApi } from "../api/client";
import { usePublicConfig } from "../components/shell/usePublicConfig";
import styles from "./Login.module.css";

type Mode = "signin" | "signup";
type FieldErrors = { username?: string; password?: string; invite?: string };

export function Login() {
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  const { config } = usePublicConfig();
  const codeRequired = !!config.signup_code_required;

  const [mode, setMode] = useState<Mode>("signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const userRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);
  const inviteRef = useRef<HTMLInputElement>(null);

  const from = (loc.state as { from?: string } | null)?.from ?? "/build";
  const isSignup = mode === "signup";

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    setMode(next);
    setErrors({});
    setFormError(null);
    requestAnimationFrame(() => userRef.current?.focus());
  };

  const focusFirst = (e: FieldErrors) => {
    if (e.username) userRef.current?.focus();
    else if (e.password) pwRef.current?.focus();
    else if (e.invite) inviteRef.current?.focus();
  };

  const validate = (): FieldErrors => {
    const e: FieldErrors = {};
    if (!username.trim()) e.username = "Enter your username.";
    if (!password) e.password = "Enter your password.";
    else if (isSignup && password.length < 8) e.password = "Use at least 8 characters.";
    if (isSignup && codeRequired && !invite.trim()) e.invite = "An invite code is required.";
    return e;
  };

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    if (busy) return;
    const found = validate();
    if (Object.keys(found).length) {
      setErrors(found);
      setFormError(null);
      focusFirst(found);
      return;
    }
    setErrors({});
    setFormError(null);
    setBusy(true);
    try {
      if (isSignup) await authApi.signup(username.trim(), password, codeRequired ? invite.trim() : undefined);
      else await authApi.login(username.trim(), password);
      await qc.invalidateQueries({ queryKey: ["auth", "me"] });
      nav(from, { replace: true });
    } catch (err) {
      // Map the contract's status codes to the field they belong to; focus it.
      const status = (err as { status?: number }).status;
      if (isSignup && status === 409) {
        setErrors({ username: "That username is already taken." });
        userRef.current?.focus();
      } else if (isSignup && status === 400) {
        setErrors({ password: "That password is too weak — use at least 8 characters." });
        pwRef.current?.focus();
      } else if (isSignup && status === 403 && codeRequired) {
        setErrors({ invite: "That invite code isn’t valid." });
        inviteRef.current?.focus();
      } else if (isSignup && status === 403) {
        setFormError("That invite code isn’t valid.");
      } else if (!isSignup && status === 401) {
        setFormError("Incorrect username or password.");
        pwRef.current?.focus();
      } else {
        setFormError((err as Error)?.message || (isSignup ? "Could not create your account." : "Sign-in failed."));
      }
      setBusy(false);
    }
  };

  return (
    <div className={styles.screen} data-temp="inside">
      <div className={styles.split} data-mode={mode}>
        {/* Brand panel — the sealed vault, quiet and atmospheric */}
        <aside className={styles.brandPanel}>
          <Link to="/" className={styles.brand} aria-label="Nxcleus home">
            <Logo size={22} tone="invert" />
          </Link>
          <div className={styles.brandCopy}>
            <h2 className={styles.brandHeadline}>Automation that never leaves your walls.</h2>
            <p className={styles.brandSub}>
              Nxcleus plans, certifies, builds, and verifies your regulated processes inside your own
              infrastructure. Raw data never crosses the boundary.
            </p>
          </div>
          <div className={styles.brandFoot}>
            <span className={styles.brandDot} aria-hidden="true" />
            Sovereign control plane
          </div>
        </aside>

        {/* Form panel */}
        <main className={styles.formPanel}>
          <div className={styles.formInner}>
            <Link to="/" className={styles.mobileBrand} aria-label="Nxcleus home">
              <Logo size={20} tone="invert" />
            </Link>

            <div className={styles.head}>
              <h1 className={styles.title}>{isSignup ? "Create your account" : "Welcome back"}</h1>
              <p className={styles.sub}>
                {isSignup ? "Set up access to the Nxcleus control plane." : "Sign in to the Nxcleus control plane."}
              </p>
            </div>

            <div className={styles.toggle} role="tablist" aria-label="Authentication mode">
              <button
                type="button"
                role="tab"
                aria-selected={!isSignup}
                className={styles.toggleBtn}
                onClick={() => switchMode("signin")}
              >
                Sign in
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={isSignup}
                className={styles.toggleBtn}
                onClick={() => switchMode("signup")}
              >
                Create account
              </button>
              <span className={styles.toggleThumb} aria-hidden="true" />
            </div>

            <form className={styles.form} onSubmit={submit} noValidate>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="auth-username">Username</label>
                <input
                  id="auth-username"
                  ref={userRef}
                  className={styles.input}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  autoFocus
                  aria-invalid={!!errors.username}
                  aria-describedby={errors.username ? "err-username" : undefined}
                />
                {errors.username && (
                  <p id="err-username" className={styles.err} role="alert">
                    <WarningCircle weight="fill" /> {errors.username}
                  </p>
                )}
              </div>

              <div className={styles.field}>
                <div className={styles.labelRow}>
                  <label className={styles.label} htmlFor="auth-password">Password</label>
                  {isSignup && !errors.password && <span className={styles.hint}>8+ characters</span>}
                </div>
                <div className={styles.inputWrap}>
                  <input
                    id="auth-password"
                    ref={pwRef}
                    className={`${styles.input} ${styles.hasToggle}`}
                    type={showPw ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete={isSignup ? "new-password" : "current-password"}
                    aria-invalid={!!errors.password}
                    aria-describedby={errors.password ? "err-password" : undefined}
                  />
                  <button
                    type="button"
                    className={styles.peek}
                    onClick={() => setShowPw((s) => !s)}
                    aria-label={showPw ? "Hide password" : "Show password"}
                    aria-pressed={showPw}
                    tabIndex={-1}
                  >
                    {showPw ? <EyeSlash weight="regular" /> : <Eye weight="regular" />}
                  </button>
                </div>
                {errors.password && (
                  <p id="err-password" className={styles.err} role="alert">
                    <WarningCircle weight="fill" /> {errors.password}
                  </p>
                )}
              </div>

              {isSignup && codeRequired && (
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="auth-invite">Invite code</label>
                  <input
                    id="auth-invite"
                    ref={inviteRef}
                    className={styles.input}
                    value={invite}
                    onChange={(e) => setInvite(e.target.value)}
                    autoComplete="off"
                    autoCapitalize="characters"
                    spellCheck={false}
                    aria-invalid={!!errors.invite}
                    aria-describedby={errors.invite ? "err-invite" : undefined}
                  />
                  {errors.invite && (
                    <p id="err-invite" className={styles.err} role="alert">
                      <WarningCircle weight="fill" /> {errors.invite}
                    </p>
                  )}
                </div>
              )}

              {formError && (
                <div className={styles.formError} role="alert">
                  <WarningCircle weight="fill" className={styles.formErrorIcon} />
                  <span>{formError}</span>
                </div>
              )}

              <button className={styles.submit} type="submit" disabled={busy}>
                {busy ? (
                  <>
                    <CircleNotch weight="bold" className={styles.spin} />
                    {isSignup ? "Creating account…" : "Signing in…"}
                  </>
                ) : (
                  <>
                    {isSignup ? "Create account" : "Sign in"}
                    <ArrowRight weight="bold" />
                  </>
                )}
              </button>
            </form>

            <p className={styles.switch}>
              {isSignup ? "Already have an account?" : "New to Nxcleus?"}{" "}
              <button type="button" className={styles.switchLink} onClick={() => switchMode(isSignup ? "signin" : "signup")}>
                {isSignup ? "Sign in" : "Create an account"}
              </button>
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
