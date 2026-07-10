import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bank, Heartbeat, Scales, LockKey, CaretLeft, CaretRight, ChartLineUp, Umbrella, Books, Truck, Storefront, Trash } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { api, companyPrompts, type CompanySummary } from "../api/client";
import { DataClassChip } from "../components/ui/DataClassChip";
import { OriginBadge } from "../components/ui/OriginBadge";
import { Composer, type ComposerSubmit } from "../components/build/Composer";
import { businessValueFor } from "../lib/businessValue";
import { useDemoToken } from "../api/useDemoToken";
import { compact } from "../lib/format";
import styles from "./Sandbox.module.css";

const PERSONA: Record<string, { icon: Icon; desc: string }> = {
  bank: { icon: Bank, desc: "Retail & commercial banking. Sanctions, AML, and fraud on customer, account, and transaction data." },
  clinic: { icon: Heartbeat, desc: "Outpatient care. Billing integrity, data-quality checks, and screening cohorts on protected health records." },
  lawfirm: { icon: Scales, desc: "Corporate law. Contract obligations, renewal windows, and billing review across the matter book." },
  exchange: { icon: ChartLineUp, desc: "Crypto exchange. Spoofing bursts, wash trades, and surveillance across the order book." },
  insurer: { icon: Umbrella, desc: "P&C insurance. Duplicate claims, staged rings, and coverage breaches across policies and payments." },
  ledger: { icon: Books, desc: "Group finance. Intercompany imbalances, journal anomalies, and close-cycle checks." },
  freight: { icon: Truck, desc: "Logistics. Denied-party screening of consignees and lanes against live watchlists." },
  market: { icon: Storefront, desc: "Online marketplace. Seller fraud, refund abuse, and listing-policy sweeps." },
};

// ponytail: static fallback so the sandbox renders (and screenshots) with no backend
const FALLBACK_COMPANIES: CompanySummary[] = Object.entries({
  bank: "Meridian Bank", clinic: "Cedarline Clinic", lawfirm: "Harwick & Voss",
  exchange: "Ashford Digital", insurer: "Cascadia Mutual", ledger: "Halden Group",
  freight: "Northgate Freight", market: "Bazarline",
}).map(([id, name]) => ({ id, name, prompts: [], origin: "builtin" as const }));

// Terms are constrained to #/## headings, paragraphs, "- " lists, and **bold** — render just those.
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

function Terms({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] | null = null;
  const flush = () => {
    if (list) blocks.push(<ul key={blocks.length} className={styles.mdList}>{list.map((li, i) => <li key={i}>{inline(li)}</li>)}</ul>);
    list = null;
  };
  for (const line of source.split("\n").map((l) => l.trimEnd())) {
    if (line.startsWith("- ")) (list ??= []).push(line.slice(2));
    else if (line.startsWith("## ")) { flush(); blocks.push(<h3 key={blocks.length} className={styles.mdH2}>{inline(line.slice(3))}</h3>); }
    else if (line.startsWith("# ")) { flush(); blocks.push(<h2 key={blocks.length} className={styles.mdH1}>{inline(line.slice(2))}</h2>); }
    else if (line === "") flush();
    else { flush(); blocks.push(<p key={blocks.length} className={styles.mdP}>{inline(line)}</p>); }
  }
  flush();
  return <div className={styles.terms}>{blocks}</div>;
}

function DataBrowser({ companyId }: { companyId: string }) {
  const [view, setView] = useState<"data" | "terms">("data");
  const tablesQ = useQuery({ queryKey: ["sb-tables", companyId], queryFn: () => api.sandboxTables(companyId), retry: 0 });
  const tables = tablesQ.data?.tables ?? [];
  const [table, setTable] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const active = table ?? tables[0] ?? null;
  useEffect(() => {
    setTable(null);
    setPage(1);
    setView("data");
  }, [companyId]);

  const rowsQ = useQuery({
    queryKey: ["sb-rows", companyId, active, page],
    queryFn: () => api.sandboxTable(companyId, active as string, page),
    enabled: view === "data" && !!active,
    retry: 0,
  });
  const termsQ = useQuery({
    queryKey: ["sb-terms", companyId],
    queryFn: () => api.sandboxTerms(companyId),
    enabled: view === "terms",
    retry: 0,
  });
  const rows = rowsQ.data?.rows ?? [];
  const columns = rows.length ? Object.keys(rows[0]) : [];

  return (
    <div className={styles.panel}>
      <div className={styles.panelHead}>
        <div className={styles.seg}>
          <button className={`${styles.segBtn} ${view === "data" ? styles.on : ""}`} onClick={() => setView("data")}>Tables</button>
          <button className={`${styles.segBtn} ${view === "terms" ? styles.on : ""}`} onClick={() => setView("terms")}>Terms</button>
        </div>
        <span className={styles.rawNote}>
          <DataClassChip cls="RAW" size="xs" /> never leaves LOCAL
        </span>
      </div>

      {view === "terms" ? (
        <div className={styles.termsScroll}>
          {termsQ.isLoading ? (
            <div className={styles.empty}>Loading terms…</div>
          ) : termsQ.data?.seeded ? (
            <Terms source={termsQ.data.markdown} />
          ) : (
            <div className={styles.empty}>This company hasn't published its terms of data use yet.</div>
          )}
        </div>
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}

function AskPanel({ company }: { company: CompanySummary }) {
  const navigate = useNavigate();
  const suggestions = useMemo(
    () => companyPrompts(company).map((p) => ({ prompt: p, value: businessValueFor(company.id, p) })),
    [company],
  );

  const run = async (p: ComposerSubmit) => {
    const res = await api.sandboxRun({ company: company.id, prompt: p.request });
    navigate(`/build/${res.job_id}`);
  };

  return (
    <div className={styles.askCol}>
      <div className={styles.askHeading}>Ask {company.name} to build a process</div>
      <Composer
        variant="sandbox"
        boundCompany={company}
        suggestions={suggestions}
        placeholder={`e.g. ${companyPrompts(company)[0] ?? "Flag duplicate claims every month"}`}
        submitLabel="Run it inside the walls"
        onSubmit={run}
      />
    </div>
  );
}

function CompanyCard({ company, selected, onSelect, onDelete }: {
  company: CompanySummary;
  selected: boolean;
  onSelect: () => void;
  onDelete?: () => void;
}) {
  const persona = PERSONA[company.id] ?? { icon: LockKey, desc: "Custom enterprise dataset." };
  const Ico = persona.icon;
  const rows = (company.tables ?? []).reduce((n, t) => n + (t.row_count ?? 0), 0);
  const custom = !!company.origin && company.origin !== "builtin";
  return (
    <div className={styles.companyWrap}>
      <button className={`${styles.company} ${selected ? styles.sel : ""}`} onClick={onSelect}>
        <div className={styles.companyIcon}><Ico weight="fill" /></div>
        <div className={styles.companyNameRow}>
          <span className={styles.companyName}>{company.name}</span>
          {custom && <OriginBadge origin={company.origin!} size="xs" />}
        </div>
        <div className={styles.companyDesc}>{company.blurb ?? company.industry ?? persona.desc}</div>
        {(company.tables?.length ?? 0) > 0 && (
          <div className={styles.companyStats}>
            {company.tables!.length} tables · {compact(rows)} rows
          </div>
        )}
      </button>
      {custom && onDelete && (
        <button className={styles.del} onClick={onDelete} title="Delete this data source" aria-label={`Delete ${company.name}`}>
          <Trash weight="regular" />
        </button>
      )}
    </div>
  );
}

export function Sandbox() {
  const unlocked = useDemoToken();
  const qc = useQueryClient();
  const companiesQ = useQuery({ queryKey: ["sb-companies"], queryFn: api.sandboxCompanies, retry: 0 });
  const companies = useMemo(() => {
    const live = companiesQ.data?.companies ?? [];
    return live.length ? live : companiesQ.isError ? FALLBACK_COMPANIES : [];
  }, [companiesQ.data, companiesQ.isError]);
  const [selId, setSelId] = useState<string | null>(null);
  const selected = companies.find((c) => c.id === (selId ?? companies[0]?.id));

  const del = async (id: string) => {
    try {
      await api.deleteDataset(id);
      if (selId === id) setSelId(null);
      await qc.invalidateQueries({ queryKey: ["sb-companies"] });
    } catch {
      /* builtin refuses (400) or presenter required — leave the card in place */
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h1 className={styles.title}>Judge sandbox</h1>
        <p className={styles.sub}>
          Pick a company, browse its private data, then ask for a process. Every run is a real job — planned, certified, and built inside the walls.
          The frontier only ever sees a <b>sanitized brief</b>.
        </p>
      </div>

      {companiesQ.isLoading && companies.length === 0 ? (
        <div className={styles.companies}>
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className={styles.skeleton} />)}
        </div>
      ) : (
        <div className={styles.companies}>
          {companies.map((c) => (
            <CompanyCard
              key={c.id}
              company={c}
              selected={selected?.id === c.id}
              onSelect={() => setSelId(c.id)}
              onDelete={unlocked ? () => del(c.id) : undefined}
            />
          ))}
        </div>
      )}

      {selected ? (
        <div className={styles.split}>
          <DataBrowser companyId={selected.id} />
          <AskPanel company={selected} />
        </div>
      ) : (
        <div className={styles.empty}>
          {companiesQ.isLoading ? "Loading companies…" : "No sandbox companies available."}
        </div>
      )}
    </div>
  );
}
