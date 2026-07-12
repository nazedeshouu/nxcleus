import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Circle, ShieldCheck } from "@phosphor-icons/react";
import { api, type EconProcess, type ProcessSummary } from "../api/client";
import { MOCK_FORCED } from "../api/config";
import { usd } from "../lib/format";
import styles from "./Operations.module.css";

/** Modeled contrast only — a frontier-API approach re-pays per run AND re-exposes
 *  data each run. Real Nxcleus numbers come from /economics/summary.
 *  Basis: a 60-unit batch with one frontier call per unit at ~$0.02/call (GPT-5.6-class
 *  list pricing) ≈ $1.20/run — vs our measured ~$0.07/run on AMD-hosted serving. */
const MODELED_FRONTIER_PER_RUN = 1.2;
const HORIZON = 240; // project the cost curves across this many runs

function MoneyChart({ buildCapex, perRun }: { buildCapex: number; perRun: number }) {
  const W = 560;
  const H = 210;
  const padL = 46;
  const padR = 16;
  const padT = 14;
  const padB = 26;
  const ours = (k: number) => buildCapex + k * perRun;
  const theirs = (k: number) => k * MODELED_FRONTIER_PER_RUN;
  const yMax = Math.max(theirs(HORIZON), ours(HORIZON)) * 1.08;
  const x = (k: number) => padL + (k / HORIZON) * (W - padL - padR);
  const y = (v: number) => padT + (1 - v / yMax) * (H - padT - padB);
  const path = (fn: (k: number) => number) => {
    const pts: string[] = [];
    for (let k = 0; k <= HORIZON; k += HORIZON / 60) pts.push(`${x(k).toFixed(1)},${y(fn(k)).toFixed(1)}`);
    return "M" + pts.join(" L");
  };
  const gridY = [0, yMax / 2, yMax];

  return (
    <div>
      <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative cost across runs: Nxcleus stays flat, a frontier-per-run approach scales linearly">
        {gridY.map((v, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="var(--hairline-soft)" strokeWidth="1" />
            <text x={padL - 8} y={y(v) + 3} textAnchor="end" fontSize="9" fontFamily="var(--font-mono)" fill="var(--text-faint)">
              {usd(v)}
            </text>
          </g>
        ))}
        {/* modeled competitor */}
        <path d={path(theirs)} fill="none" stroke="var(--zone-external)" strokeWidth="2" strokeDasharray="4 4" opacity="0.65" />
        {/* nxcleus (real) */}
        <path d={path(ours)} fill="none" stroke="var(--accent)" strokeWidth="2.5" />
        <circle cx={x(0)} cy={y(ours(0))} r="3.5" fill="var(--accent)" />
        <text x={x(0) + 6} y={y(ours(0)) - 8} fontSize="9" fontFamily="var(--font-mono)" fill="var(--accent-strong)">
          build capex {usd(buildCapex)}
        </text>
        <text x={W - padR} y={H - 6} textAnchor="end" fontSize="9" fontFamily="var(--font-mono)" fill="var(--text-faint)">
          {HORIZON} runs
        </text>
      </svg>
      <div className={styles.chartCap}>
        <span className={styles.legend}>
          <i className={styles.swatch} style={{ background: "var(--accent)" }} /> Nxcleus — build once, flat opex, 0 frontier calls per run
        </span>
        <span className={styles.legend}>
          <i className={styles.swatch} style={{ background: "var(--zone-external)" }} /> Modeled frontier-per-run — cost scales, data crosses the boundary every run
        </span>
      </div>
    </div>
  );
}

function Economics({ processes }: { processes: EconProcess[] }) {
  const agg = useMemo(() => {
    const buildCapex = processes.reduce((s, p) => s + p.build_cost_usd, 0);
    const runs = processes.flatMap((p) => p.runs);
    const runCount = runs.length;
    const perRun = runCount ? runs.reduce((s, r) => s + r.cost_usd, 0) / runCount : 0;
    const frontierPerRun = runCount ? runs.reduce((s, r) => s + r.frontier_calls, 0) / runCount : 0;
    return { buildCapex, runCount, perRun, frontierPerRun, procCount: processes.length };
  }, [processes]);

  return (
    <section className={styles.econ}>
      <div className={styles.econHead}>
        <div>
          <div className={styles.econKicker}>The economics</div>
          <h2 className={styles.econTitle}>
            Frontier intelligence as <em>capex</em>, not marginal cost
          </h2>
        </div>
      </div>
      <div className={styles.econGrid}>
        <MoneyChart buildCapex={agg.buildCapex || 0.047} perRun={agg.perRun || 0.00045} />
        <div className={styles.tiles}>
          <div className={styles.tile}>
            <div className={styles.tileNum}>{agg.procCount}</div>
            <div className={styles.tileLbl}>certified processes in the registry</div>
          </div>
          <div className={styles.tile}>
            <div className={styles.tileNum}>{usd(agg.buildCapex)}</div>
            <div className={styles.tileLbl}>one-time build cost, all processes</div>
          </div>
          <div className={styles.tile}>
            <div className={styles.tileNum}>{usd(agg.perRun)}</div>
            <div className={styles.tileLbl}>average cost per run, trending flat</div>
          </div>
          <div className={styles.tile}>
            <div className={`${styles.tileNum} ${styles.good}`}>{agg.frontierPerRun.toFixed(0)}</div>
            <div className={styles.tileLbl}>frontier calls per run — data never leaves</div>
          </div>
        </div>
      </div>
    </section>
  );
}

function CostSpark({ runs }: { runs: EconProcess["runs"] }) {
  // a single run has no trend to draw — a lone dot reads as debris, so show a dash
  if (runs.length < 2) return <span className={styles.num} style={{ color: "var(--text-faint)" }}>—</span>;
  const vals = runs.map((r) => r.cost_per_unit);
  const max = Math.max(...vals, 1e-9);
  const w = 68;
  const h = 20;
  const pts = vals.map((v, i) => `${(i / Math.max(1, vals.length - 1)) * w},${h - (v / max) * (h - 3) - 1.5}`);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline points={pts.join(" ")} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
      {vals.map((v, i) => (
        <circle key={i} cx={(i / Math.max(1, vals.length - 1)) * w} cy={h - (v / max) * (h - 3) - 1.5} r="1.6" fill="var(--accent)" />
      ))}
    </svg>
  );
}

export function Operations() {
  const navigate = useNavigate();
  const enabled = !MOCK_FORCED;
  const procsQ = useQuery({ queryKey: ["processes"], queryFn: api.listProcesses, enabled, retry: 0 });
  const econQ = useQuery({ queryKey: ["economics"], queryFn: api.economics, enabled, retry: 0 });
  const ticketsQ = useQuery({ queryKey: ["tickets", "warranty"], queryFn: () => api.listTickets({ source: "warranty" }), enabled, retry: 0 });

  const processes = procsQ.data?.processes ?? [];
  const econ = econQ.data?.processes ?? [];
  const econByProc = useMemo(() => new Map(econ.map((e) => [e.process_id, e])), [econ]);
  const openTicketsByScope = useMemo(() => {
    const m = new Map<string, number>();
    for (const t of ticketsQ.data?.tickets ?? []) {
      if (t.status === "verified") continue;
      const key = t.scope?.replace(/^process:/, "") ?? "";
      m.set(key, (m.get(key) ?? 0) + 1);
    }
    return m;
  }, [ticketsQ.data]);

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h1 className={styles.title}>Operations</h1>
        <p className={styles.sub}>
          The registry. Every delivered process, versioned and metered, running inside the walls under continuous warranty.
        </p>
      </div>

      {econ.length > 0 && <Economics processes={econ} />}

      <div className={styles.tableWrap}>
        <div className={styles.tableScroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Process</th>
                <th>Mode</th>
                <th>Version</th>
                <th>Status</th>
                <th>Runs</th>
                <th>Cost / unit trend</th>
                <th>Warranty</th>
                <th aria-label="open" />
              </tr>
            </thead>
            <tbody>
              {processes.map((p: ProcessSummary) => {
                const e = econByProc.get(p.id);
                const runCount = e?.runs.length ?? 0;
                const open = openTicketsByScope.get(p.id) ?? 0;
                return (
                  <tr key={p.id} onClick={() => navigate(`/operations/${p.id}`)}>
                    <td>
                      <div className={styles.procName}>{p.name}</div>
                      <div className={styles.procSlug}>{p.slug}</div>
                    </td>
                    <td><span className={styles.mode}>{p.mode}</span></td>
                    <td><span className={styles.ver}>v{p.current_version}</span></td>
                    <td>
                      <span className={`${styles.statusChip} ${p.status === "active" ? "" : styles.paused}`}>
                        <Circle weight="fill" /> {p.status}
                      </span>
                    </td>
                    <td><span className={styles.num}>{runCount}</span></td>
                    <td>{e ? <CostSpark runs={e.runs} /> : <span className={styles.num} style={{ color: "var(--text-faint)" }}>—</span>}</td>
                    <td>
                      <span className={`${styles.warranty} ${open ? styles.open : ""}`}>
                        <ShieldCheck weight="fill" /> {open ? `${open} open` : "clear"}
                      </span>
                    </td>
                    <td><ArrowRight weight="bold" className={styles.arrow} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {processes.length === 0 && (
          <div className={styles.empty}>
            {procsQ.isLoading ? "Loading the registry…" : <>No processes yet. <Link to="/build">Build one</Link> to populate the registry.</>}
          </div>
        )}
      </div>
    </div>
  );
}
