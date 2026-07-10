import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Circle, Lightning, Lock, ShieldCheck } from "@phosphor-icons/react";
import { api, type JobSummary } from "../api/client";
import { MOCK_FORCED } from "../api/config";
import { useDemoToken } from "../api/useDemoToken";
import { KYC_JOB_ID } from "../fixtures/kycJob";
import styles from "./JobList.module.css";

const DEMO_JOB: JobSummary = {
  id: KYC_JOB_ID,
  title: "KYC / AML customer onboarding",
  status: "done",
  stage: 7,
  mode: "build",
  goal: "Auditable case file per applicant, no raw PII across the boundary.",
};

function NewProcess() {
  const navigate = useNavigate();
  const unlocked = useDemoToken();
  const [request, setRequest] = useState("");
  const [title, setTitle] = useState("");
  const [policy, setPolicy] = useState("");
  const [showPolicy, setShowPolicy] = useState(false);
  const [sovereign, setSovereign] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const create = async () => {
    if (!request.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.createJob({
        request: request.trim(),
        title: title.trim() || undefined,
        policy_text: policy.trim() || undefined,
        sovereign,
      });
      navigate(`/build/${res.job.id}`);
    } catch (e) {
      const status = (e as { status?: number }).status;
      setErr(status === 401 ? "Presenter token required — unlock top-right." : `Could not start: ${(e as Error).message}`);
      setBusy(false);
    }
  };

  return (
    <div className={styles.create}>
      <textarea
        className={styles.createText}
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        placeholder="Describe the process you need. e.g. Every month, flag duplicate claims and coverage breaches; the claims committee gets a case file per flagged entity and a CSV for recovery."
        rows={3}
      />
      {showPolicy && (
        <textarea
          className={styles.createText}
          value={policy}
          onChange={(e) => setPolicy(e.target.value)}
          placeholder="Confidentiality policy — what must never leave your walls, on top of the PII baseline."
          rows={2}
        />
      )}
      <div className={styles.createMeta}>
        <input
          className={styles.createTitle}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title (optional)"
        />
        <button className={`${styles.createOpt} ${showPolicy ? styles.on : ""}`} onClick={() => setShowPolicy((s) => !s)}>
          {showPolicy ? "Policy attached" : "Attach policy text"}
        </button>
        <label className={`${styles.createOpt} ${sovereign ? styles.on : ""}`} title="Zero external calls — even the sanitized planner brief stays inside">
          <input type="checkbox" checked={sovereign} onChange={(e) => setSovereign(e.target.checked)} hidden />
          <ShieldCheck weight={sovereign ? "fill" : "regular"} /> Sovereign
        </label>
        <button className={styles.createGo} disabled={busy || !request.trim()} onClick={create} title={unlocked ? "" : "May require Presenter mode"}>
          {unlocked ? <Lightning weight="fill" /> : <Lock weight="regular" />} {busy ? "Starting…" : "Start the build"}
        </button>
      </div>
      {err && <div className={styles.createErr}>{err}</div>}
    </div>
  );
}

export function JobList() {
  const q = useQuery({ queryKey: ["jobs"], queryFn: () => api.listJobs(), enabled: !MOCK_FORCED, retry: 0 });
  const live = q.data?.jobs ?? [];
  // Always surface the KYC demo job so the mission control view is reachable without a backend.
  const jobs = live.length ? live : [DEMO_JOB];

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <div>
          <h1 className={styles.title}>Build</h1>
          <p className={styles.sub}>
            Describe an internal process. Watch it get planned, certified, built, and verified inside the walls.
          </p>
        </div>
      </div>

      <NewProcess />

      <ul className={styles.grid}>
        {jobs.map((j) => (
          <li key={j.id}>
            <Link to={`/build/${j.id}`} className={styles.card}>
              <div className={styles.cardTop}>
                <span className={`${styles.status} ${styles[`s_${j.status}`] ?? ""}`}>
                  <Circle weight="fill" /> {j.status}
                </span>
                {j.mode && <span className={styles.mode}>{j.mode} mode</span>}
              </div>
              <h2 className={styles.jobTitle}>{j.title}</h2>
              {j.goal && <p className={styles.goal}>{j.goal}</p>}
              <span className={styles.enter}>
                Open mission control <ArrowRight weight="bold" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
