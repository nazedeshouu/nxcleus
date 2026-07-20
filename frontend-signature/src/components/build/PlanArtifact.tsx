import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Blueprint,
  MagnifyingGlass,
  Cube,
  Plugs,
  ListChecks,
  Stack,
  Warning,
  CaretDown,
  CaretRight,
  UsersThree,
} from "@phosphor-icons/react";
import { Panel } from "./Panel";
import { ZoneBadge } from "../ui/ZoneBadge";
import { SEAT_INFO } from "../../api/adapt";
import { api, type PlanBody, type PlanStep, type PlanModule } from "../../api/client";
import { MOCK_FORCED } from "../../api/config";
import type { Zone } from "../../lib/events";
import styles from "./PlanArtifact.module.css";

/** Kind badge for a topology (process-mode) step: sql / analysis / judgment. */
function stepKind(s: PlanStep): { label: string; cls: string } {
  if (s.kind === "sql") return { label: "sql", cls: styles.kSql };
  if (s.kind === "analysis") return { label: "analysis", cls: styles.kAnalysis };
  return { label: "judgment", cls: styles.kJudge };
}

function Flags({ flags }: { flags?: string[] }) {
  if (!flags?.length) return null;
  return (
    <div className={styles.flags}>
      {flags.map((f) => (
        <span key={f} className={styles.flag}>{f}</span>
      ))}
    </div>
  );
}

function ModuleCard({ m }: { m: PlanModule }) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(m.algorithm || m.assumptions?.length || m.consumes?.length || m.provides?.length);
  return (
    <div className={styles.item}>
      <button className={styles.itemHead} onClick={() => setOpen((o) => !o)} disabled={!hasDetail}>
        {hasDetail ? (open ? <CaretDown weight="bold" /> : <CaretRight weight="bold" />) : <span className={styles.dot} />}
        <span className={styles.itemName}>{m.name ?? m.id}</span>
        {m.complexity && <span className={styles.cx}>{m.complexity}</span>}
        <Flags flags={m.task_flags} />
      </button>
      {m.purpose && <p className={styles.itemPurpose}>{m.purpose}</p>}
      {open && (
        <div className={styles.itemBody}>
          {(m.consumes?.length || m.provides?.length) && (
            <div className={styles.wires}>
              {m.consumes?.length ? <span><b>consumes</b> {m.consumes.join(", ")}</span> : null}
              {m.provides?.length ? <span><b>provides</b> {m.provides.join(", ")}</span> : null}
            </div>
          )}
          {m.algorithm && <pre className={styles.code}>{m.algorithm}</pre>}
          {m.assumptions?.length ? (
            <ul className={styles.assume}>
              {m.assumptions.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}

function StepCard({ s }: { s: PlanStep }) {
  const [open, setOpen] = useState(false);
  const k = stepKind(s);
  const detail = s.sql || s.prompt_spec || s.purpose;
  return (
    <div className={styles.item}>
      <button className={styles.itemHead} onClick={() => setOpen((o) => !o)} disabled={!detail}>
        {detail ? (open ? <CaretDown weight="bold" /> : <CaretRight weight="bold" />) : <span className={styles.dot} />}
        <span className={`${styles.kind} ${k.cls}`}>{k.label}</span>
        <span className={styles.itemName}>{s.label ?? s.id}</span>
        {s.per_unit && <span className={styles.perUnit}>per-unit</span>}
        <Flags flags={s.task_flags} />
      </button>
      {open && (
        <div className={styles.itemBody}>
          {s.purpose && <p className={styles.itemPurpose}>{s.purpose}</p>}
          {s.prompt_spec && (
            <div className={styles.subLabelWrap}>
              <span className={styles.subLabel}>prompt spec</span>
              <pre className={styles.code}>{s.prompt_spec}</pre>
            </div>
          )}
          {s.sql && (
            <div className={styles.subLabelWrap}>
              <span className={styles.subLabel}>generated sql</span>
              <pre className={styles.code}>{s.sql}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** The persisted plan as a first-class build artifact: what the frontier planner authored,
 *  read back from body_json (richer than the live plan.completed event) with a deep-link to the
 *  exact planner transcript. Renders nothing until stage 1 has certified a plan (404 → null). */
export function PlanArtifact({ jobId }: { jobId?: string }) {
  const [showAll, setShowAll] = useState(false);
  const q = useQuery({
    queryKey: ["plan", jobId],
    queryFn: () => api.plan(jobId as string),
    enabled: Boolean(jobId) && !MOCK_FORCED,
    retry: 0,
  });
  const plan: PlanBody | null = q.data?.plan ?? null;

  const bom = plan?.model_bom;
  const seats = bom?.seats ?? [];
  const parallelAgents = seats.reduce((n, s) => n + (s.count ?? 1), 0);
  const width = bom?.fleet?.parallel_width;
  const modules = plan?.modules ?? [];
  const steps = plan?.topology?.steps ?? [];
  const interfaces = plan?.interfaces ?? [];
  const risks = plan?.risks ?? [];
  const isProcess = steps.length > 0 || plan?.mode === "process";

  if (!plan) return null; // loading / 404 / mock — stay quiet inside the cockpit

  const CAP = 6;
  const shownModules = showAll ? modules : modules.slice(0, CAP);
  const shownSteps = showAll ? steps : steps.slice(0, CAP);
  const overflow = Math.max(modules.length - CAP, steps.length - CAP, 0);

  return (
    <Panel
      title="Plan artifact"
      icon={Blueprint}
      status="ok"
      tag={
        <span className={styles.tag}>
          {plan.mode ?? "build"}{plan.version ? ` · v${plan.version}` : ""}
        </span>
      }
    >
      {/* fan-out summary — how wide the fleet ran (Task 3: parallel-agent count) */}
      <div className={styles.stats}>
        <span className={styles.stat}>
          <UsersThree weight="bold" /> {parallelAgents} parallel {parallelAgents === 1 ? "agent" : "agents"}
          {width ? <em> · width {width}</em> : null}
        </span>
        {isProcess ? (
          <span className={styles.stat}><ListChecks weight="bold" /> {steps.length} topology steps</span>
        ) : (
          <span className={styles.stat}><Cube weight="bold" /> {modules.length} modules</span>
        )}
        {interfaces.length > 0 && (
          <span className={styles.stat}><Plugs weight="bold" /> {interfaces.length} interfaces</span>
        )}
      </div>

      {/* the actual work order */}
      {isProcess ? (
        <section className={styles.section}>
          {plan.topology?.unit?.noun && (
            <p className={styles.unitLine}>
              One worker per <b>{plan.topology.unit.noun}</b>
              {plan.topology.unit.source ? ` from ${plan.topology.unit.source}` : ""}.
            </p>
          )}
          <div className={styles.list}>
            {shownSteps.map((s) => <StepCard key={s.id} s={s} />)}
          </div>
        </section>
      ) : (
        <section className={styles.section}>
          <div className={styles.list}>
            {shownModules.map((m) => <ModuleCard key={m.id} m={m} />)}
          </div>
          {interfaces.length > 0 && (
            <div className={styles.ifaces}>
              <span className={styles.subLabel}><Plugs weight="bold" /> typed interfaces</span>
              <div className={styles.ifaceRow}>
                {interfaces.map((i) => <code key={i.id} className={styles.iface} title={i.id}>{i.id}</code>)}
              </div>
            </div>
          )}
        </section>
      )}

      {overflow > 0 && (
        <button className={styles.more} onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show less" : `Show all — ${overflow} more`}
        </button>
      )}

      {/* model bill of materials — the seats + fan-out the planner ordered */}
      {seats.length > 0 && (
        <div className={styles.bom}>
          <span className={styles.subLabel}><Stack weight="bold" /> model bill of materials</span>
          {seats.map((b, i) => {
            const info = SEAT_INFO[b.seat];
            return (
              <div className={styles.bomRow} key={i}>
                <span className={styles.bomSeat}>{b.seat}</span>
                <div className={styles.bomMid}>
                  <div className={styles.bomModel}>
                    {info?.model ?? b.seat}
                    {info && <ZoneBadge zone={info.zone as Zone} size="xs" />}
                  </div>
                  {b.why && <div className={styles.bomWhy}>{b.why}</div>}
                </div>
                <span className={styles.bomCount}>×{b.count ?? 1}</span>
              </div>
            );
          })}
        </div>
      )}

      {risks.length > 0 && (
        <ul className={styles.risks}>
          {risks.map((r, i) => (
            <li key={i}><Warning weight="fill" /> {r}</li>
          ))}
        </ul>
      )}

      {jobId && (
        <Link className={styles.transcript} to={`/traces?scope=${encodeURIComponent(`job:${jobId}`)}&seat=planner`}>
          <MagnifyingGlass weight="bold" /> View planner transcript
        </Link>
      )}
    </Panel>
  );
}
