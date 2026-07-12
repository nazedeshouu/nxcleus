import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Circle, Play } from "@phosphor-icons/react";
import { api, type JobSummary } from "../api/client";
import { MOCK_FORCED } from "../api/config";
import { ShortId } from "../components/ui/ShortId";
import { whenLabel } from "../lib/format";
import { Composer, type ComposerSubmit } from "../components/build/Composer";
import styles from "./JobList.module.css";

const DONE = new Set(["done", "delivered"]);

function jobLabel(job: JobSummary): string {
  return job.title?.trim() || job.goal?.trim().split(/[.\n]/)[0] || "Untitled build";
}

function JobCard({ job }: { job: JobSummary }) {
  const done = DONE.has(job.status);
  const when = whenLabel(job.created_at);
  return (
    <li className={styles.card}>
      <Link to={`/build/${job.id}`} className={styles.cardMain}>
        <div className={styles.cardTop}>
          <span className={`${styles.status} ${styles[`s_${job.status}`] ?? ""}`}>
            <Circle weight="fill" /> {job.status}
          </span>
          {job.mode && <span className={styles.mode}>{job.mode} mode</span>}
        </div>
        <h2 className={styles.jobTitle}>{jobLabel(job)}</h2>
        {job.goal ? (
          <p className={styles.goal}>{job.goal}</p>
        ) : (
          <p className={styles.goalEmpty}>No description recorded.</p>
        )}
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
      <div className={styles.cardMeta}>
        {when && <span>{when}</span>}
        <ShortId id={job.id} />
      </div>
    </li>
  );
}

export function JobList() {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["jobs"], queryFn: () => api.listJobs(), enabled: !MOCK_FORCED, retry: 0 });
  const jobs = q.data?.jobs ?? [];

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

      {jobs.length > 0 ? (
        <ul className={styles.grid}>
          {jobs.map((j) => <JobCard key={j.id} job={j} />)}
        </ul>
      ) : (
        <div className={styles.empty}>
          <p className={styles.emptyLead}>Start your first build</p>
          <p className={styles.emptySub}>Describe a process above. Once it runs, every build lands here — planned, certified, and verified inside the walls.</p>
        </div>
      )}
    </div>
  );
}
