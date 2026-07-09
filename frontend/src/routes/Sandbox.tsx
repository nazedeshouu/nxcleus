import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bank, Heartbeat, Scales, LockKey, ShieldCheck, Lightning, CaretLeft, CaretRight } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { api, type CompanySummary } from "../api/client";
import { DataClassChip } from "../components/ui/DataClassChip";
import styles from "./Sandbox.module.css";

const PERSONA: Record<string, { icon: Icon; desc: string }> = {
  bank: { icon: Bank, desc: "Retail & commercial banking. Sanctions, AML, and fraud on customer, account, and transaction data." },
  clinic: { icon: Heartbeat, desc: "Outpatient care. Billing integrity, data-quality checks, and screening cohorts on protected health records." },
  lawfirm: { icon: Scales, desc: "Corporate law. Contract obligations, renewal windows, and billing review across the matter book." },
};

function DataBrowser({ companyId }: { companyId: string }) {
  const tablesQ = useQuery({ queryKey: ["sb-tables", companyId], queryFn: () => api.sandboxTables(companyId), retry: 0 });
  const tables = tablesQ.data?.tables ?? [];
  const [table, setTable] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const active = table ?? tables[0] ?? null;
  useEffect(() => {
    setTable(null);
    setPage(1);
  }, [companyId]);

  const rowsQ = useQuery({
    queryKey: ["sb-rows", companyId, active, page],
    queryFn: () => api.sandboxTable(companyId, active as string, page),
    enabled: !!active,
    retry: 0,
  });
  const rows = rowsQ.data?.rows ?? [];
  const columns = rows.length ? Object.keys(rows[0]) : [];

  return (
    <div className={styles.panel}>
      <div className={styles.panelHead}>
        <span className={styles.panelTitle}>Private data · read-only</span>
        <span className={styles.rawNote}>
          <DataClassChip cls="RAW" size="xs" /> never leaves LOCAL
        </span>
      </div>
      <div className={styles.tabs}>
        {tables.map((t) => (
          <button key={t} className={`${styles.tab} ${active === t ? styles.on : ""}`} onClick={() => { setTable(t); setPage(1); }}>
            {t}
          </button>
        ))}
      </div>
      <div className={styles.tableScroll}>
        {rows.length === 0 ? (
          <div className={styles.empty}>{rowsQ.isLoading ? "Loading rows…" : "No rows."}</div>
        ) : (
          <table className={styles.dataTable}>
            <thead>
              <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {columns.map((c) => <td key={c}>{String(r[c] ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className={styles.pager}>
        <button className={styles.pagerBtn} disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          <CaretLeft weight="bold" style={{ width: 11, verticalAlign: "-1px" }} /> prev
        </button>
        <span className={styles.pagerInfo}>page {page}</span>
        <button className={styles.pagerBtn} disabled={rows.length < 25} onClick={() => setPage((p) => p + 1)}>
          next <CaretRight weight="bold" style={{ width: 11, verticalAlign: "-1px" }} />
        </button>
      </div>
    </div>
  );
}

function AskPanel({ company }: { company: CompanySummary }) {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const launch = async () => {
    const text = prompt.trim();
    if (!text) return;
    setBusy(true);
    setFlash(null);
    try {
      const res = await api.sandboxRun({ company: company.id, prompt: text });
      navigate(`/build/${res.job_id}`);
    } catch (e) {
      const status = (e as { status?: number }).status;
      setFlash(
        status === 429
          ? "The sandbox is at its budget or concurrency cap. Watch a completed run in the Gallery instead."
          : `Could not start the run: ${(e as Error).message}`,
      );
      setBusy(false);
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.panelHead}>
        <span className={styles.panelTitle}>Ask {company.name} to build a process</span>
      </div>
      <div className={styles.ask}>
        <div className={styles.askLabel}>Start from a suggested process</div>
        <div className={styles.chips}>
          {company.prompts.map((p) => (
            <button key={p} className={styles.chip} onClick={() => setPrompt(p)}>
              {p}
            </button>
          ))}
        </div>
        <div className={styles.askLabel}>or describe your own</div>
        <textarea
          className={styles.textarea}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={`e.g. ${company.prompts[0]}`}
        />
        <button className={styles.run} disabled={busy || !prompt.trim()} onClick={launch}>
          <Lightning weight="fill" /> {busy ? "Starting the run…" : "Run it inside the walls"}
        </button>
        {flash && <div className={styles.flash}>{flash}</div>}
        <div className={styles.boundaryNote}>
          <ShieldCheck weight="fill" />
          <span>
            Your data stays in {company.name}'s zone. Only a sanitized brief — no names, no account numbers — ever crosses to the frontier planner.
          </span>
        </div>
      </div>
    </div>
  );
}

export function Sandbox() {
  const companiesQ = useQuery({ queryKey: ["sb-companies"], queryFn: api.sandboxCompanies, retry: 0 });
  const companies = useMemo(() => companiesQ.data?.companies ?? [], [companiesQ.data]);
  const [selId, setSelId] = useState<string | null>(null);
  const selected = companies.find((c) => c.id === (selId ?? companies[0]?.id));

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h1 className={styles.title}>Judge sandbox</h1>
        <p className={styles.sub}>
          Pick a company, browse its private data, then ask for a process. Every run is a real job — planned, certified, and built inside the walls.
          The frontier only ever sees a <b>sanitized brief</b>.
        </p>
      </div>

      <div className={styles.companies}>
        {companies.map((c) => {
          const persona = PERSONA[c.id] ?? { icon: LockKey, desc: "Synthetic enterprise dataset." };
          const Ico = persona.icon;
          const on = selected?.id === c.id;
          return (
            <button key={c.id} className={`${styles.company} ${on ? styles.sel : ""}`} onClick={() => setSelId(c.id)}>
              <div className={styles.companyIcon}><Ico weight="fill" /></div>
              <div className={styles.companyName}>{c.name}</div>
              <div className={styles.companyDesc}>{persona.desc}</div>
            </button>
          );
        })}
      </div>

      {selected ? (
        <div className={styles.split}>
          <DataBrowser companyId={selected.id} />
          <AskPanel company={selected} />
        </div>
      ) : (
        <div className={styles.empty}>{companiesQ.isLoading ? "Loading companies…" : "No sandbox companies available."}</div>
      )}
    </div>
  );
}
