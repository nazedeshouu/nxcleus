import { useState, type ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Lightning, Copy, ArrowsClockwise, Lock, CaretDown, CaretRight,
  FileText, Receipt, CheckCircle, ShieldCheck, GitBranch, X, Printer,
  DownloadSimple, ArrowSquareOut, MagnifyingGlass, Compass, Play, Target, WarningCircle,
} from "@phosphor-icons/react";
import { api, type EconProcess, type GroundTruthCompare, type NextStep, type PackageInvoice, type PackageManifest, type ProcessSummary, type ProcessVersion, type RunUnit, type VersionDiff } from "../api/client";
import { useDemoToken } from "../api/useDemoToken";
import { useBreadcrumb } from "../components/shell/breadcrumbs";
import { ShortId } from "../components/ui/ShortId";
import { usd, whenLabel } from "../lib/format";
import styles from "./ProcessDetail.module.css";

type Flash = { kind: "ok" | "err"; msg: string } | null;

const finite = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value);
const moneyOrDash = (value: number | null | undefined): string => finite(value) ? usd(value) : "—";
const numberOrDash = (value: number | null | undefined): string => finite(value) ? String(value) : "—";

/** The process may carry its corpus binding under a couple of names. */
function boundCompany(process: ProcessSummary): string {
  const raw = process as unknown as Record<string, unknown>;
  // authoritative: flat corpus_company; older nested shapes tolerated
  const corpus = raw.corpus as Record<string, unknown> | undefined;
  return (raw.corpus_company as string) ?? (corpus?.company as string) ?? (raw.company as string) ?? "";
}

function ActionBar({ processId, version, process }: { processId: string; version: number; process: ProcessSummary }) {
  const unlocked = useDemoToken();
  const [flash, setFlash] = useState<Flash>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [company, setCompany] = useState(() => boundCompany(process));
  const [refineOpen, setRefineOpen] = useState(false);
  const [refineText, setRefineText] = useState("Tighten the sanctions fuzzy-match threshold.");
  const companiesQ = useQuery({ queryKey: ["sb-companies"], queryFn: api.sandboxCompanies, retry: 0, staleTime: 60_000 });
  const companies = companiesQ.data?.companies ?? [];

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setFlash(null);
    try {
      await fn();
      setFlash({ kind: "ok", msg: `${label} accepted — a new job/run has started.` });
    } catch (e) {
      const status = (e as { status?: number }).status;
      const code = status === 401 ? "401 — sign in required" : status === 409 ? "409 — not allowed in this state" : (e as Error).message;
      setFlash({ kind: "err", msg: `${label} rejected: ${code}` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      {companies.length > 0 && (
        <div className={styles.corpusRow}>
          <label className={styles.corpusLbl}>Corpus</label>
          <select className={styles.corpusSelect} value={company} onChange={(e) => setCompany(e.target.value)} disabled={!unlocked}>
            <option value="">process binding</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      )}
      <div className={styles.actions}>
        <button
          className={`${styles.action} ${styles.primary}`}
          disabled={!unlocked || busy != null}
          onClick={() => run("Run batch", () => api.runBatch(processId, {
            version,
            sample: { mode: "first", n: 100 },
            ...(company ? { corpus: { company } } : {}),
          }))}
        >
          {unlocked ? <Lightning weight="fill" /> : <Lock weight="regular" />} Run a batch
        </button>
        <button
          className={styles.action}
          disabled={!unlocked || busy != null}
          onClick={() => run("Instantiate", () => api.instantiateProcess(processId, {}))}
        >
          {unlocked ? <Copy weight="regular" /> : <Lock weight="regular" />} Instantiate copy
        </button>
        <button
          className={styles.action}
          disabled={!unlocked || busy != null}
          onClick={() => setRefineOpen((o) => !o)}
        >
          {unlocked ? <ArrowsClockwise weight="regular" /> : <Lock weight="regular" />} Request refinement
        </button>
      </div>
      {refineOpen && (
        <div className={styles.refineRow}>
          <input
            className={styles.noteInput}
            value={refineText}
            onChange={(e) => setRefineText(e.target.value)}
            placeholder="What should change? e.g. Tighten the sanctions fuzzy-match threshold."
            disabled={!unlocked}
          />
          <button
            className={`${styles.action} ${styles.primary}`}
            disabled={!unlocked || busy != null || !refineText.trim()}
            onClick={() => run("Refinement", () => api.refineProcess(processId, refineText.trim()))}
          >
            Send
          </button>
        </div>
      )}
      {!unlocked && <div className={styles.hint}>Sign in to run, instantiate, or refine.</div>}
      {flash && <div className={`${styles.flash} ${flash.kind === "ok" ? styles.ok : styles.err}`}>{flash.msg}</div>}
    </div>
  );
}

function DiffView({ diff }: { diff: VersionDiff }) {
  return (
    <div className={styles.diff}>
      <div className={styles.diffGrid}>
        <div className={styles.diffItem}>
          <span className={styles.diffLbl}>Triage</span>
          <span className={styles.triage}>{diff.triage}</span>
        </div>
        <div className={styles.diffItem}>
          <span className={styles.diffLbl}>Frontier consult</span>
          <span className={styles.diffVal}>{diff.frontier_consult ? "yes" : "no — local only"}</span>
        </div>
        <div className={styles.diffItem}>
          <span className={styles.diffLbl}>Modules rebuilt</span>
          <span className={styles.diffVal}>{diff.modules_rebuilt.length ? diff.modules_rebuilt.join(", ") : "none"}</span>
        </div>
        <div className={styles.diffItem}>
          <span className={styles.diffLbl}>Tests added</span>
          <span className={styles.diffVal}>{diff.tests_added}</span>
        </div>
      </div>
      <p className={styles.diffNote} style={{ marginTop: 12 }}>
        {diff.triage === "amend"
          ? "Amended in place — a scoped patch, re-certified against the same goal. No full rebuild, no new frontier consult."
          : "Regions touched: " + (diff.regions.length ? diff.regions.join(", ") : "none") + "."}
      </p>
    </div>
  );
}

function VersionsCard({ versions }: { versions: ProcessVersion[] }) {
  const [sel, setSel] = useState<number>(versions[versions.length - 1]?.version ?? 1);
  const selVer = versions.find((v) => v.version === sel);
  const diff: VersionDiff | null = selVer?.diff ?? null;

  return (
    <div className={styles.card}>
      <div className={styles.cardTitle}>Version history</div>
      <div className={styles.verList}>
        {[...versions].reverse().map((v) => (
          <div key={v.version} className={`${styles.verRow} ${v.version === sel ? styles.sel : ""}`} onClick={() => setSel(v.version)}>
            <span className={styles.verTag}>v{v.version}</span>
            <div className={styles.verMeta}>
              <div className={styles.verMetaTop}>
                {v.diff?.triage === "amend" ? "Amendment" : v.version === 1 ? "Initial certification" : "Revision"}
                {v.status === "certified" && " · certified"}
              </div>
              <div className={styles.verMetaSub}><ShortId id={v.plan_id} /></div>
            </div>
            {v.version === sel ? <CaretDown weight="bold" style={{ width: 12, color: "var(--accent)" }} /> : <CaretRight weight="bold" style={{ width: 12, color: "var(--text-faint)" }} />}
          </div>
        ))}
      </div>
      {diff ? <DiffView diff={diff} /> : (
        <div className={styles.diff}>
          <p className={styles.diffNote}>
            <GitBranch weight="bold" style={{ width: 12, verticalAlign: "-2px", marginRight: 4 }} />
            v{sel} is the initial certification — the baseline plan, goal, and test vectors. Later versions carry a human-readable diff.
          </p>
        </div>
      )}
    </div>
  );
}

function PackageCard({ processId, version }: { processId: string; version: number }) {
  const invQ = useQuery({ queryKey: ["pkg", processId, version, "invoice"], queryFn: () => api.packageFile<PackageInvoice>(processId, version, "invoice.json"), retry: 0 });
  const manQ = useQuery({ queryKey: ["pkg", processId, version, "manifest"], queryFn: () => api.packageFile<PackageManifest>(processId, version, "manifest.json"), retry: 0 });
  const inv = invQ.data;
  const man = manQ.data;
  const under = inv?.delta_vs_quote != null && inv.delta_vs_quote < 0;

  return (
    <div className={styles.card}>
      <div className={styles.cardTitle}>Delivered package · invoice</div>
      {inv ? (
        <>
          {inv.lines.map((l, i) => (
            <div key={i} className={styles.invLine}>
              <div>
                <div className={styles.invItem}>{l.item}</div>
                <div className={styles.invQty}>{l.qty}{l.zone ? ` · ${l.zone}` : ""}</div>
              </div>
              <span className={styles.invAmt}>{usd(l.actual_usd)}</span>
            </div>
          ))}
          <div className={styles.invTotal}>
            <span className={styles.invItem} style={{ color: "var(--text-muted)" }}>Total, this build</span>
            <span className={styles.invTotalNum}>{usd(inv.total_usd)}</span>
          </div>
          <div className={styles.invMeta}>
            <span className={styles.invBadge}><ShieldCheck weight="fill" /> {inv.frontier_calls} measured frontier calls</span>
            {under && <span className={styles.invBadge}><CheckCircle weight="fill" /> {usd(Math.abs(inv.delta_vs_quote!))} under quote</span>}
          </div>
        </>
      ) : (
        <p className={styles.diffNote}>{invQ.isLoading ? "Loading invoice…" : "Invoice not available for this version."}</p>
      )}

      <div className={styles.artifacts}>
        <a className={styles.artifact} href={`/api/processes/${processId}/package/${version}/manifest.json`} target="_blank" rel="noreferrer">
          <FileText weight="regular" /> manifest.json
        </a>
        <a className={styles.artifact} href={`/api/processes/${processId}/package/${version}/invoice.json`} target="_blank" rel="noreferrer">
          <Receipt weight="regular" /> invoice.json
        </a>
        {man?.image_tag && <span className={styles.artifact}><GitBranch weight="regular" /> {man.image_tag}</span>}
      </div>
    </div>
  );
}

function scoreOf(u: RunUnit): string {
  const r = u.result as { score?: number } | undefined;
  return r?.score != null ? r.score.toFixed(2) : "—";
}

/** Render arbitrary result JSON as a readable definition list, not a dump. */
function DefList({ data }: { data: unknown }): ReactNode {
  if (data == null || data === "") return <span className={styles.dlEmpty}>—</span>;
  if (Array.isArray(data)) {
    if (data.length === 0) return <span className={styles.dlEmpty}>none</span>;
    if (data.every((x) => typeof x !== "object" || x == null)) {
      return <span className={styles.dlVal}>{data.map(String).join(", ")}</span>;
    }
    const rows = data as Array<Record<string, unknown>>;
    const cols = [...new Set(rows.flatMap((r) => Object.keys(r ?? {})))].slice(0, 8);
    return (
      <div className={styles.dlTableWrap}>
        <table className={styles.dlTable}>
          <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{cols.map((c) => <td key={c}><DefList data={r?.[c]} /></td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (typeof data === "object") {
    return (
      <dl className={styles.dl}>
        {Object.entries(data as Record<string, unknown>).map(([k, val]) => (
          <div className={styles.dlRow} key={k}>
            <dt className={styles.dlKey}>{k.replace(/_/g, " ")}</dt>
            <dd className={styles.dlVal}><DefList data={val} /></dd>
          </div>
        ))}
      </dl>
    );
  }
  if (typeof data === "boolean") return <span className={styles.dlVal}>{data ? "yes" : "no"}</span>;
  return <span className={styles.dlVal}>{String(data)}</span>;
}

function TraceSteps({ trace }: { trace: unknown }) {
  const steps = Array.isArray(trace) ? trace : null;
  if (!steps?.length) return null;
  return (
    <div className={styles.traceSteps}>
      <div className={styles.drawerSub}>Trace</div>
      <ol>
        {steps.map((s, i) => (
          <li key={i}>{typeof s === "string" ? s : typeof s === "object" && s ? Object.values(s as Record<string, unknown>).filter((x) => typeof x === "string").join(" · ") || JSON.stringify(s) : String(s)}</li>
        ))}
      </ol>
    </div>
  );
}

/** Evidence drawer: the unit's full result + trace + review controls. */
function EvidenceDrawer({ unit, onClose, onReview, busy }: {
  unit: RunUnit;
  onClose: () => void;
  onReview: (verdict: "approve" | "reject", note: string) => void;
  busy: boolean;
}) {
  const unlocked = useDemoToken();
  const [note, setNote] = useState("");
  return (
    <>
      <div className={styles.drawerScrim} onClick={onClose} />
      <aside className={styles.drawer} role="dialog" aria-label={`Evidence for ${unit.unit_ref}`}>
        <header className={styles.drawerHead}>
          <div>
            <div className={styles.drawerRef}>{unit.unit_ref}</div>
            <span className={`${styles.uStatus} ${styles[unit.status] ?? ""}`}>{unit.status.replace("_", " ")}</span>
          </div>
          <button className={styles.drawerClose} onClick={onClose} aria-label="Close"><X weight="bold" /></button>
        </header>

        <div className={styles.drawerBody}>
          <div className={styles.drawerSub}>Result</div>
          <DefList data={unit.result} />
          <TraceSteps trace={unit.trace} />
        </div>

        <footer className={styles.drawerFoot}>
          {unit.review_verdict ? (
            <div className={styles.verdictDone}>
              {unit.review_verdict === "approve" ? "✓ approved" : "✗ rejected"}
              {unit.review_note ? ` — ${unit.review_note}` : ""}
            </div>
          ) : (
            <>
              <input
                className={styles.noteInput}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Review note (who/why — lands in the audit trail)"
                disabled={!unlocked}
              />
              <div className={styles.review}>
                <button className={`${styles.reviewBtn} ${styles.approve}`} disabled={!unlocked || busy} onClick={() => onReview("approve", note)}>approve</button>
                <button className={`${styles.reviewBtn} ${styles.reject}`} disabled={!unlocked || busy} onClick={() => onReview("reject", note)}>reject</button>
              </div>
              {!unlocked && <span className={styles.hint}>Sign in to review.</span>}
            </>
          )}
        </footer>
      </aside>
    </>
  );
}

const NEXT_ICON: Record<NextStep["action"]["kind"], typeof Compass> = {
  refine: ArrowsClockwise,
  export: DownloadSimple,
  review: MagnifyingGlass,
  rerun: Lightning,
};

function GroundTruthPanel({ q }: { q: { data?: GroundTruthCompare; isLoading: boolean; error: unknown } }) {
  if (q.isLoading) return <p className={styles.diffNote}>Checking flagged units against the planted ground truth…</p>;
  if (q.error || !q.data) {
    const msg = (q.error as { message?: string })?.message ?? "comparison unavailable for this run";
    return <p className={styles.diffNote}>Ground-truth comparison unavailable — {msg}</p>;
  }
  const c = q.data;
  const perfect = c.false_positive_count === 0 && c.missed_count === 0;
  return (
    <div className={styles.gtPanel}>
      <div className={styles.gtHead}><Target weight="bold" /> Planted vs flagged — {c.pattern}</div>
      <div className={styles.gtStats}>
        <div className={styles.gtStat}>
          <b className="good">{c.true_positive_count}</b>
          <span>caught of {c.planted_total} planted</span>
        </div>
        <div className={`${styles.gtStat} ${c.false_positive_count ? styles.gtBad : ""}`}>
          <b>{c.false_positive_count}</b><span>flagged, not planted</span>
        </div>
        <div className={`${styles.gtStat} ${c.missed_count ? styles.gtBad : ""}`}>
          <b>{c.missed_count}</b><span>planted, not flagged</span>
        </div>
      </div>
      {perfect ? (
        <p className={styles.gtPerfect}>
          <CheckCircle weight="fill" /> All {c.planted_total} planted patterns flagged — zero false positives, zero misses.
        </p>
      ) : (
        <>
          {c.missed.length > 0 && (
            <div className={styles.gtList}>
              <div className={styles.gtListHead}><WarningCircle weight="bold" /> Planted but not flagged ({c.missed_count})</div>
              {c.missed.slice(0, 20).map((m, i) => <div key={i} className={styles.gtItem}>{m.label}</div>)}
              {c.missed_count > 20 && <div className={styles.gtMore}>+{c.missed_count - 20} more</div>}
            </div>
          )}
          {c.false_positives.length > 0 && (
            <div className={styles.gtList}>
              <div className={styles.gtListHead}><WarningCircle weight="bold" /> Flagged but not planted ({c.false_positive_count})</div>
              {c.false_positives.slice(0, 20).map((f, i) => <div key={i} className={styles.gtItem}>{f.unit_ref}</div>)}
              {c.false_positive_count > 20 && <div className={styles.gtMore}>+{c.false_positive_count - 20} more</div>}
            </div>
          )}
        </>
      )}
      <p className={styles.gtBasis}>Ground truth: {c.ground_truth_basis}.</p>
    </div>
  );
}

function RunRow({ run, processId, version }: { run: EconProcess["runs"][number]; processId: string; version: number }) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const [sel, setSel] = useState<RunUnit | null>(null);
  const [artGlow, setArtGlow] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);
  const unlocked = useDemoToken();
  const qc = useQueryClient();
  const unitsQ = useQuery({
    queryKey: ["run-units", run.run_id],
    queryFn: () => api.getRunUnits(run.run_id),
    enabled: open,
    retry: 0,
  });
  const runQ = useQuery({ queryKey: ["run", run.run_id], queryFn: () => api.getRun(run.run_id), enabled: open, retry: 0 });
  const nextQ = useQuery({ queryKey: ["next-steps", run.run_id], queryFn: () => api.nextSteps(run.run_id), enabled: open, retry: 0 });
  const [compareOn, setCompareOn] = useState(false);
  const compareQ = useQuery({ queryKey: ["gt-compare", run.run_id], queryFn: () => api.groundTruthCompare(run.run_id), enabled: open && compareOn, retry: 0 });
  const [reviewing, setReviewing] = useState<string | null>(null);

  const review = async (unitId: string, verdict: "approve" | "reject", note?: string) => {
    setReviewing(unitId);
    try {
      await api.reviewUnit(unitId, verdict, note?.trim() || (verdict === "approve" ? "approved on review" : "returned for correction"));
      await qc.invalidateQueries({ queryKey: ["run-units", run.run_id] });
      setSel(null);
    } catch {
      /* surfaced by the row staying un-reviewed */
    } finally {
      setReviewing(null);
    }
  };

  const units = unitsQ.data?.units ?? [];
  const statuses = [...new Set(units.map((u) => u.status))];
  const shown = filter ? units.filter((u) => u.status === filter) : units;
  const artifacts = runQ.data?.run.artifacts ?? [];
  const artifactEvidence = runQ.data?.run.stats?.artifact;
  const artifactVerification = artifactEvidence?.verification;
  const artifactLabel = artifactVerification === "passed"
    ? "verified"
    : artifactVerification === "unverified" ? "unverified" : "verification unavailable";
  const reportUrl = artifacts.find((a) => a.kind === "report")?.url ?? `/api/runs/${run.run_id}/report`;
  const csvUrl = artifacts.find((a) => a.kind === "csv")?.url ?? `/api/runs/${run.run_id}/export.csv`;

  const printReport = () => {
    const w = window.open(reportUrl, "_blank");
    w?.addEventListener("load", () => w.print());
  };

  const flashRun = (kind: "ok" | "err", msg: string) => setFlash({ kind, msg });

  const doAction = async (step: NextStep) => {
    const params = step.action.params ?? {};
    try {
      switch (step.action.kind) {
        case "refine": {
          const request = (params.request as string) ?? step.title;
          await api.refineProcess(processId, request);
          flashRun("ok", "Refinement accepted — a new build job has started.");
          break;
        }
        case "review":
          setFilter("needs_review");
          break;
        case "export":
          // params: {format: "report"|"csv"} — open the artifact and light the card
          window.open(params.format === "csv" ? csvUrl : reportUrl, "_blank");
          setArtGlow(true);
          setTimeout(() => setArtGlow(false), 1600);
          break;
        case "rerun":
          // params like {sample:{mode,n}} / {budget} pass through opaquely
          {
          const rerunParams = { ...(params as Record<string, unknown>) };
          delete rerunParams.input_ref;
          const requested = params.sample as Record<string, unknown> | undefined;
          const sample = requested
            && (requested.mode === "first" || requested.mode === "random")
            && Number.isInteger(requested.n) && Number(requested.n) > 0
              ? { mode: requested.mode as "first" | "random", n: Number(requested.n) }
              : { mode: "first" as const, n: 100 };
          await api.runBatch(processId, {
            ...rerunParams,
            sample,
            version,
          });
          flashRun("ok", "Re-run accepted — watch the run history.");
          break;
          }
      }
    } catch (e) {
      const status = (e as { status?: number }).status;
      flashRun("err", status === 401 ? "Sign in required." : `Action failed: ${(e as Error).message}`);
    }
  };

  return (
    <div className={styles.runRow}>
      <div className={styles.runHead} onClick={() => setOpen((o) => !o)}>
        {open ? <CaretDown weight="bold" style={{ width: 13, color: "var(--accent)" }} /> : <CaretRight weight="bold" style={{ width: 13, color: "var(--text-faint)" }} />}
        <ShortId id={run.run_id} />
        <div className={styles.runStat}>
          <span><b>{numberOrDash(run.units)}</b> units</span>
          <span className={run.cost_verification === "passed" && finite(run.cost_usd) ? styles.runMetricGood : styles.runMetricMuted}>
            <b>{moneyOrDash(run.cost_usd)}</b>
          </span>
          <span>{moneyOrDash(run.cost_per_unit)}/unit</span>
          <span className={run.cost_verification === "passed" && finite(run.frontier_calls) ? styles.runMetricGood : styles.runMetricMuted}>
            <b>{numberOrDash(run.frontier_calls)}</b> {run.cost_verification === "passed" ? "measured frontier" : "frontier (unverified)"}
          </span>
          {(run.mock_dispatches ?? 0) > 0 && (
            <span className={styles.simChip} title="Some model calls fell through to a simulated (mock) backend — not a clean live run.">
              {run.mock_dispatches} simulated
            </span>
          )}
        </div>
      </div>
      <div className={styles.runTruth}>
        <span className={styles.truthChip}>status: {run.status || "unknown"}</span>
        <span className={`${styles.truthChip} ${styles[`truth_${run.verification}`] ?? ""}`}>
          verification: {run.verification}
        </span>
        <span className={`${styles.truthChip} ${run.demo ? styles.truthDemo : ""}`}>demo: {run.demo ? "yes" : "no"}</span>
        {run.verification_reasons.length > 0 ? (
          <span className={styles.truthReason}>{run.verification_reasons.join("; ")}</span>
        ) : run.verification !== "passed" ? (
          <span className={styles.truthReason}>No verification reason was recorded.</span>
        ) : null}
        {run.cost_verification !== "passed" && run.cost_reason && (
          <span className={styles.truthReason}>Cost: {run.cost_reason}</span>
        )}
      </div>
      {open && (
        <div className={styles.runBody}>
          {(artifacts.length > 0) && (
            <div className={`${styles.artCard} ${artifactVerification === "passed" ? "" : styles.artUnverified} ${artGlow ? styles.artGlow : ""}`}>
              <div>
                <div className={styles.artTitle}>Deliverables · {artifactLabel}</div>
                {artifactEvidence?.reason && <div className={styles.artReason}>{artifactEvidence.reason}</div>}
              </div>
              <div className={styles.artBtns}>
                <a className={styles.artBtn} href={reportUrl} target="_blank" rel="noreferrer">
                  <ArrowSquareOut weight="bold" /> Open report
                </a>
                <a className={styles.artBtn} href={csvUrl} download>
                  <DownloadSimple weight="bold" /> Download CSV
                </a>
                <button className={styles.artBtn} onClick={printReport}>
                  <Printer weight="bold" /> Print → PDF
                </button>
              </div>
            </div>
          )}

          <div className={styles.findingsBar}>
            <span className={styles.findingsTitle}>Findings</span>
            {statuses.length > 1 && (
              <div className={styles.filterChips}>
                <button className={`${styles.filterChip} ${filter == null ? styles.on : ""}`} onClick={() => setFilter(null)}>
                  all · {units.length}
                </button>
                {statuses.map((s) => (
                  <button key={s} className={`${styles.filterChip} ${filter === s ? styles.on : ""}`} onClick={() => setFilter(s)}>
                    {s.replace("_", " ")} · {units.filter((u) => u.status === s).length}
                  </button>
                ))}
              </div>
            )}
            {run.ts && <span className={styles.chip}>{whenLabel(run.ts)}</span>}
            <button className={`${styles.inspectLink} ${styles.compareBtn}`} onClick={() => setCompareOn((v) => !v)}>
              <Target weight="bold" /> {compareOn ? "Hide comparison" : "Compare with planted patterns"}
            </button>
            <Link className={styles.inspectLink} to={`/replay/run/${run.run_id}`}>
              <Play weight="fill" /> Replay
            </Link>
            <Link className={styles.inspectLink} to={`/traces?scope=${encodeURIComponent(`run:${run.run_id}`)}`}>
              <MagnifyingGlass weight="bold" /> Inspect prompts
            </Link>
          </div>

          {compareOn && <GroundTruthPanel q={compareQ} />}

          {unitsQ.isLoading ? (
            <p className={styles.diffNote}>Loading units…</p>
          ) : shown.length === 0 ? (
            <p className={styles.diffNote}>{filter ? "No units with this status." : "No unit records for this run."}</p>
          ) : (
            <table className={styles.unitTable}>
              <thead>
                <tr>
                  <th>Unit</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((u) => (
                  <tr key={u.id} className={styles.unitRow} onClick={() => setSel(u)}>
                    <td>{u.unit_ref}</td>
                    <td><span className={`${styles.uStatus} ${styles[u.status] ?? ""}`}>{u.status.replace("_", " ")}</span></td>
                    <td>{scoreOf(u)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {u.review_verdict ? (
                        <span className={styles.verdictDone}>{u.review_verdict === "approve" ? "✓ approved" : "✗ rejected"}</span>
                      ) : (
                        <div className={styles.review}>
                          <button className={`${styles.reviewBtn} ${styles.approve}`} disabled={!unlocked || reviewing === u.id} onClick={() => review(u.id, "approve")} title={unlocked ? "" : "Sign in required"}>
                            approve
                          </button>
                          <button className={`${styles.reviewBtn} ${styles.reject}`} disabled={!unlocked || reviewing === u.id} onClick={() => review(u.id, "reject")} title={unlocked ? "" : "Sign in required"}>
                            reject
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {(nextQ.data?.length ?? 0) > 0 && (
            <div className={styles.nextSteps}>
              <div className={styles.artTitle}><Compass weight="bold" style={{ width: 13, verticalAlign: "-2px", marginRight: 5 }} />What next</div>
              <div className={styles.nextGrid}>
                {nextQ.data!.slice(0, 5).map((s, i) => {
                  const Ico = NEXT_ICON[s.action.kind] ?? Compass;
                  return (
                    <button key={i} className={styles.nextCard} onClick={() => doAction(s)} disabled={!unlocked && (s.action.kind === "refine" || s.action.kind === "rerun")}>
                      <div className={styles.nextTop}><Ico weight="bold" /><span>{s.title}</span></div>
                      <p className={styles.nextWhy}>{s.why}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {flash && <div className={`${styles.flash} ${flash.kind === "ok" ? styles.ok : styles.err}`}>{flash.msg}</div>}
        </div>
      )}

      {sel && (
        <EvidenceDrawer
          unit={sel}
          onClose={() => setSel(null)}
          onReview={(verdict, note) => review(sel.id, verdict, note)}
          busy={reviewing === sel.id}
        />
      )}
    </div>
  );
}

export function ProcessDetail() {
  const { id = "" } = useParams();
  const procQ = useQuery({ queryKey: ["process", id], queryFn: () => api.getProcess(id), retry: 0 });
  const econQ = useQuery({ queryKey: ["economics"], queryFn: api.economics, retry: 0 });

  const process = procQ.data?.process;
  const versions = procQ.data?.versions ?? [];
  const econ = econQ.data?.processes.find((p) => p.process_id === id);
  const runs = econ?.runs ?? [];

  useBreadcrumb([{ label: "Operations", to: "/operations" }, { label: process?.name ?? "Process" }]);

  if (procQ.isLoading) return <div className={styles.wrap}><div className={styles.loading}>Loading process…</div></div>;
  if (!process) return <div className={styles.wrap}><Link to="/operations" className={styles.back}><ArrowLeft weight="bold" /> Operations</Link><div className={styles.loading}>Process not found.</div></div>;

  return (
    <div className={styles.wrap}>
      <Link to="/operations" className={styles.back}><ArrowLeft weight="bold" /> Operations</Link>

      <div className={styles.head}>
        <div>
          <h1 className={styles.title}>{process.name}</h1>
          <div className={styles.metaRow}>
            <span className={`${styles.chip} ${styles.accent}`}>{process.mode} mode</span>
            <span className={styles.chip}>v{process.current_version}</span>
            <span className={`${styles.chip} ${process.status === "active" ? styles.ok : ""}`}>{process.status}</span>
            <span className={styles.chip}>{process.slug}</span>
            {whenLabel(process.created_at) && <span className={styles.chip}>{whenLabel(process.created_at)}</span>}
          </div>
          <p className={styles.goal}>{process.goal}</p>
        </div>
        <ActionBar processId={id} version={process.current_version} process={process} />
      </div>

      <div className={styles.cols}>
        <VersionsCard versions={versions} />
        <PackageCard processId={id} version={process.current_version} />
      </div>

      <div className={styles.runs}>
        <div className={styles.cardTitle}>Run history — batch operations under warranty</div>
        {runs.length === 0 ? (
          <p className={styles.diffNote}>No runs yet. Run a batch to see per-unit results and the semi-automated review queue.</p>
        ) : (
          runs.map((r) => <RunRow key={r.run_id} run={r} processId={id} version={process.current_version} />)
        )}
      </div>
    </div>
  );
}
