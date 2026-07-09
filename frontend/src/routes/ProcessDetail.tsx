import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Lightning, Copy, ArrowsClockwise, Lock, CaretDown, CaretRight,
  FileText, Receipt, CheckCircle, ShieldCheck, GitBranch,
} from "@phosphor-icons/react";
import { api, type EconProcess, type PackageInvoice, type PackageManifest, type ProcessVersion, type RunUnit, type VersionDiff } from "../api/client";
import { useDemoToken } from "../api/useDemoToken";
import { usd } from "../lib/format";
import styles from "./ProcessDetail.module.css";

type Flash = { kind: "ok" | "err"; msg: string } | null;

function ActionBar({ processId, version }: { processId: string; version: number }) {
  const unlocked = useDemoToken();
  const [flash, setFlash] = useState<Flash>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setFlash(null);
    try {
      await fn();
      setFlash({ kind: "ok", msg: `${label} accepted — a new job/run has started.` });
    } catch (e) {
      const status = (e as { status?: number }).status;
      const code = status === 401 ? "401 — presenter token required" : status === 409 ? "409 — not allowed in this state" : (e as Error).message;
      setFlash({ kind: "err", msg: `${label} rejected: ${code}` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <div className={styles.actions}>
        <button
          className={`${styles.action} ${styles.primary}`}
          disabled={!unlocked || busy != null}
          onClick={() => run("Run batch", () => api.runBatch(processId, { input_ref: "100", version }))}
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
          onClick={() => run("Refinement", () => api.refineProcess(processId, "Tighten the sanctions fuzzy-match threshold."))}
        >
          {unlocked ? <ArrowsClockwise weight="regular" /> : <Lock weight="regular" />} Request refinement
        </button>
      </div>
      {!unlocked && <div className={styles.hint}>Unlock Presenter mode (top-right) to run, instantiate, or refine.</div>}
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
              <div className={styles.verMetaSub}>{v.plan_id}</div>
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
            <span className={styles.invBadge}><ShieldCheck weight="fill" /> {inv.frontier_calls} frontier calls · sanitized brief only</span>
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

function RunRow({ run }: { run: EconProcess["runs"][number] }) {
  const [open, setOpen] = useState(false);
  const unlocked = useDemoToken();
  const qc = useQueryClient();
  const unitsQ = useQuery({
    queryKey: ["run-units", run.run_id],
    queryFn: () => api.getRunUnits(run.run_id),
    enabled: open,
    retry: 0,
  });
  const [reviewing, setReviewing] = useState<string | null>(null);

  const review = async (unitId: string, verdict: "approve" | "reject") => {
    setReviewing(unitId);
    try {
      await api.reviewUnit(unitId, verdict, verdict === "approve" ? "approved on review" : "returned for correction");
      await qc.invalidateQueries({ queryKey: ["run-units", run.run_id] });
    } catch {
      /* surfaced by the row staying un-reviewed */
    } finally {
      setReviewing(null);
    }
  };

  const units = unitsQ.data?.units ?? [];

  return (
    <div className={styles.runRow}>
      <div className={styles.runHead} onClick={() => setOpen((o) => !o)}>
        {open ? <CaretDown weight="bold" style={{ width: 13, color: "var(--accent)" }} /> : <CaretRight weight="bold" style={{ width: 13, color: "var(--text-faint)" }} />}
        <span className={styles.runId}>{run.run_id.replace(/^run_/, "run · ")}</span>
        <div className={styles.runStat}>
          <span><b>{run.units}</b> units</span>
          <span className="good"><b className="good">{usd(run.cost_usd)}</b></span>
          <span>{usd(run.cost_per_unit)}/unit</span>
          <span className={styles.frontierZero}><b className={styles.frontierZero}>{run.frontier_calls}</b> frontier</span>
        </div>
      </div>
      {open && (
        <div className={styles.runBody}>
          {unitsQ.isLoading ? (
            <p className={styles.diffNote}>Loading units…</p>
          ) : units.length === 0 ? (
            <p className={styles.diffNote}>No unit records for this run.</p>
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
                {units.map((u) => (
                  <tr key={u.id}>
                    <td>{u.unit_ref}</td>
                    <td><span className={`${styles.uStatus} ${styles[u.status] ?? ""}`}>{u.status.replace("_", " ")}</span></td>
                    <td>{scoreOf(u)}</td>
                    <td>
                      {u.review_verdict ? (
                        <span className={styles.verdictDone}>{u.review_verdict === "approve" ? "✓ approved" : "✗ rejected"}</span>
                      ) : (
                        <div className={styles.review}>
                          <button className={`${styles.reviewBtn} ${styles.approve}`} disabled={!unlocked || reviewing === u.id} onClick={() => review(u.id, "approve")} title={unlocked ? "" : "Presenter mode required"}>
                            approve
                          </button>
                          <button className={`${styles.reviewBtn} ${styles.reject}`} disabled={!unlocked || reviewing === u.id} onClick={() => review(u.id, "reject")} title={unlocked ? "" : "Presenter mode required"}>
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
        </div>
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
          </div>
          <p className={styles.goal}>{process.goal}</p>
        </div>
        <ActionBar processId={id} version={process.current_version} />
      </div>

      <div className={styles.cols}>
        <VersionsCard versions={versions} />
        <PackageCard processId={id} version={process.current_version} />
      </div>

      <div className={styles.runs}>
        <div className={styles.cardTitle}>Run history — batch operations under warranty</div>
        {runs.length === 0 ? (
          <p className={styles.diffNote}>No runs yet. Unlock Presenter mode and run a batch to see per-unit results and the semi-automated review queue.</p>
        ) : (
          runs.map((r) => <RunRow key={r.run_id} run={r} />)
        )}
      </div>
    </div>
  );
}
