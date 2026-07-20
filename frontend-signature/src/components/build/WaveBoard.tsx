import { Stack, Cpu, ClipboardText, CheckCircle } from "@phosphor-icons/react";
import { Panel, type PanelStatus } from "./Panel";
import { ZoneBadge } from "../ui/ZoneBadge";
import type { JobView, TaskState } from "../../store/jobStore";
import type { Zone } from "../../lib/events";
import { countEvidenceState, taskNodeStatus } from "../../lib/evidenceTruth";

function Worker({ t }: { t: TaskState }) {
  const evidenceStatus = taskNodeStatus(t);
  return (
    <div className={`bv-worker ${evidenceStatus}`}>
      <div className="bv-worker-head">
        <span className="bv-worker-name">{t.module}</span>
        {t.status === "running" && <span className="bv-worker-spin" />}
        {evidenceStatus === "done" && <CheckCircle weight="fill" style={{ width: 14, height: 14, color: "var(--ok)", marginLeft: "auto" }} />}
      </div>
      <div className="bv-worker-backend">
        <Cpu weight="bold" />
        {t.backend.replace(/^local:/, "")}
        <span style={{ marginLeft: "auto" }}>
          <ZoneBadge zone={t.zone as Zone} size="xs" />
        </span>
      </div>
      <div className="bv-worker-why">{t.why}</div>
      {t.output && <pre className="bv-worker-out">{t.output.slice(-160)}</pre>}
      <div className="bv-worker-foot">
        {t.tests ? (
          <>
            <span className={countEvidenceState(t.tests) === "passed" ? "bv-worker-tests-ok" : "bv-worker-tests-warn"}>
              {t.tests.verification} · {t.tests.passed}/{t.tests.total}
            </span>
            {t.tests.failed > 0 && <span className="bv-worker-tests-fail">✗ {t.tests.failed}</span>}
          </>
        ) : (
          <span style={{ color: "var(--text-faint)" }}>building…</span>
        )}
        {t.loc != null && <span className="bv-worker-loc">{t.loc} LOC</span>}
      </div>
    </div>
  );
}

export function WaveBoard({ view }: { view: JobView }) {
  const waves = Object.values(view.build.waves).sort((a, b) => a.wave - b.wave);
  const tasks = Object.values(view.build.tasks);
  const taskStates = tasks.map(taskNodeStatus);
  const status: PanelStatus = view.stage === 4 ? "active"
    : taskStates.some((state) => state === "failed") ? "error"
      : taskStates.some((state) => state === "unverified") ? "warn"
        : waves.length && taskStates.length && taskStates.every((state) => state === "done")
          ? "ok" : waves.length ? "default" : "pending";

  return (
    <Panel
      title="Build fleet — waves"
      icon={Stack}
      status={status}
      tag={waves.length ? `${waves.length} wave${waves.length > 1 ? "s" : ""}` : "stage 4"}
    >
      {waves.length === 0 && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          The conductor runs the DAG in topological waves, reviewing between each.
        </p>
      )}

      {waves.map((w) => {
        const workers = tasks.filter((t) => t.wave === w.wave);
        return (
          <div className="bv-wave" key={w.wave}>
            <div className="bv-wave-head">
              <span className="bv-wave-n">Wave {w.wave} / {w.of}</span>
              <span className={`bv-wave-status ${w.status}`}>{w.status}</span>
            </div>
            <div className="bv-workers">
              {workers.map((t) => (
                <Worker key={t.module} t={t} />
              ))}
            </div>
            {w.verdict && (
              <div className={`bv-review ${w.verdict}`}>
                {w.verdict === "green" ? <CheckCircle weight="fill" /> : <ClipboardText weight="fill" />}
                <div>
                  <div>{w.note}</div>
                  {w.goal_drift != null && <div className="bv-review-drift" title="How far the built system has wandered from the goal pinned at certification — 0% means still exactly on promise">goal drift {(w.goal_drift * 100).toFixed(0)}%</div>}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </Panel>
  );
}
