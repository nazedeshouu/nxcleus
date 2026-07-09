import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, Circle } from "@phosphor-icons/react";
import { api, type JobSummary } from "../api/client";
import { MOCK_FORCED } from "../api/config";
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
