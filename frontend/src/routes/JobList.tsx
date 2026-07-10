import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Circle, Play, Sparkle } from "@phosphor-icons/react";
import { api, type JobSummary } from "../api/client";
import { MOCK_FORCED } from "../api/config";
import { KYC_JOB_ID } from "../fixtures/kycJob";
import { Composer, type ComposerSubmit } from "../components/build/Composer";
import styles from "./JobList.module.css";

const DONE = new Set(["done", "delivered"]);

// The reference build always works — it plays from the bundled KYC fixture. (Merged from the former Gallery feature card.)
const DEMO_JOB: JobSummary = {
  id: KYC_JOB_ID,
  title: "KYC / AML customer onboarding",
  status: "done",
  stage: 7,
  mode: "build",
  goal: "The reference build, start to finish: intake and sanitization, a certified plan, three build waves, adversarial QA with the Numeric Oracle, and delivery to the registry — an auditable case file per applicant, no raw PII across the boundary.",
};

function JobCard({ job }: { job: JobSummary }) {
  const done = DONE.has(job.status);
  const isRef = job.id === KYC_JOB_ID;
  return (
    <li className={styles.card}>
      <Link to={`/build/${job.id}`} className={styles.cardMain}>
        <div className={styles.cardTop}>
          <span className={`${styles.status} ${styles[`s_${job.status}`] ?? ""}`}>
            <Circle weight="fill" /> {job.status}
          </span>
          {isRef ? (
            <span className={styles.refTag}><Sparkle weight="fill" /> Reference build</span>
          ) : (
            job.mode && <span className={styles.mode}>{job.mode} mode</span>
          )}
        </div>
        <h2 className={styles.jobTitle}>{job.title}</h2>
        {job.goal && <p className={styles.goal}>{job.goal}</p>}
      </Link>
      <div className={styles.cardActions}>
        <Link to={`/build/${job.id}`} className={styles.enter}>
          Open mission control <ArrowRight weight="bold" />
        </Link>
        {done && (
          <Link to={`/replay/job/${job.id}`} className={styles.replay} title="Replay this build at your own pace">
            <Play weight="fill" /> Replay
          </Link>
        )}
      </div>
    </li>
  );
}

export function JobList() {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["jobs"], queryFn: () => api.listJobs(), enabled: !MOCK_FORCED, retry: 0 });
  const live = q.data?.jobs ?? [];
  // Always surface the KYC demo job so mission control is reachable without a backend.
  const jobs = live.length ? live : [DEMO_JOB];

  const create = async (p: ComposerSubmit) => {
    const res = await api.createJob({
      request: p.request,
      title: p.title,
      policy_text: p.policy_text,
      sovereign: p.sovereign,
      company: p.company,
    });
    navigate(`/build/${res.job.id}`);
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h1 className={styles.title}>Build</h1>
        <p className={styles.sub}>
          Describe an internal process. Attach your policy and data, then watch it get planned, certified, built, and verified inside the walls.
        </p>
      </div>

      <Composer variant="build" submitLabel="Start the build" onSubmit={create} />

      <ul className={styles.grid}>
        {jobs.map((j) => <JobCard key={j.id} job={j} />)}
      </ul>
    </div>
  );
}
