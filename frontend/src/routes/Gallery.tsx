import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play, CheckCircle, ArrowRight, Sparkle } from "@phosphor-icons/react";
import { api, type JobSummary } from "../api/client";
import { MOCK_FORCED } from "../api/config";
import { KYC_JOB_ID } from "../fixtures/kycJob";
import styles from "./Gallery.module.css";

const DONE = new Set(["done", "delivered"]);

/** The reference build always works — it plays from the bundled fixture. */
const FEATURE: JobSummary & { goal: string } = {
  id: KYC_JOB_ID,
  title: "KYC / AML customer onboarding",
  status: "done",
  stage: 7,
  mode: "build",
  goal: "The reference build, start to finish: intake and sanitization, a certified plan, three build waves, adversarial QA with the Numeric Oracle, and delivery to the registry.",
};

export function Gallery() {
  const q = useQuery({ queryKey: ["jobs"], queryFn: () => api.listJobs(), enabled: !MOCK_FORCED, retry: 0 });
  const live = (q.data?.jobs ?? []).filter((j) => DONE.has(j.status));

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h1 className={styles.title}>Gallery</h1>
        <p className={styles.sub}>
          Completed runs you can replay at your own pace — play, pause, scrub, and speed through the same live cockpit, at ×1, ×4, or ×16.
        </p>
      </div>

      <div className={styles.grid}>
        <div className={`${styles.card} ${styles.feature}`}>
          <div className={styles.top}>
            <span className={styles.tag}><Sparkle weight="fill" /> Reference build</span>
            <span className={styles.mode}>{FEATURE.mode} mode</span>
          </div>
          <h2 className={styles.name}>{FEATURE.title}</h2>
          <p className={styles.goal}>{FEATURE.goal}</p>
          <div className={styles.actions}>
            <Link to={`/build/${FEATURE.id}`} className={styles.watch}>
              <Play weight="fill" /> Watch the build
            </Link>
          </div>
        </div>

        {live.map((j) => (
          <div key={j.id} className={styles.card}>
            <div className={styles.top}>
              <span className={styles.tag}><CheckCircle weight="fill" /> {j.status}</span>
              {j.mode && <span className={styles.mode}>{j.mode} mode</span>}
            </div>
            <h2 className={styles.name}>{j.title}</h2>
            {j.goal && <p className={styles.goal}>{j.goal}</p>}
            <div className={styles.actions}>
              <Link to={`/replay/job/${j.id}`} className={styles.watch}>
                <Play weight="fill" /> Replay this build
              </Link>
              <Link to={`/build/${j.id}`} className={styles.secondary}>
                Open live <ArrowRight weight="bold" />
              </Link>
            </div>
          </div>
        ))}

        {live.length === 0 && !q.isLoading && (
          <p className={styles.empty}>No completed live jobs yet — the reference build above always works.</p>
        )}
      </div>
    </div>
  );
}
