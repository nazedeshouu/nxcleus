import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Plug, Lock, Trash, ShieldCheck, WifiHigh, WarningOctagon } from "@phosphor-icons/react";
import { api, type ConnectionInfo, type EgressRow, type ModelInfo } from "../api/client";
import { ZoneBadge } from "../components/ui/ZoneBadge";
import { useDemoToken } from "../api/useDemoToken";
import { MOCK_FORCED } from "../api/config";
import type { Seat, Zone } from "../lib/events";
import styles from "./Config.module.css";

const SEATS: { seat: Seat; zone: Zone }[] = [
  { seat: "trust", zone: "LOCAL" },
  { seat: "planner", zone: "EXTERNAL" },
  { seat: "certifier", zone: "LOCAL" },
  { seat: "conductor", zone: "LOCAL" },
  { seat: "coder", zone: "LOCAL" },
  { seat: "consolidator", zone: "LOCAL" },
  { seat: "oracle", zone: "LOCAL" },
  { seat: "inspector", zone: "LOCAL" },
];

function ModelRegistry({ models }: { models: ModelInfo[] }) {
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Model</th>
            <th>Provider</th>
            <th>Capability flags</th>
            <th>Serves</th>
            <th>License</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.key}>
              <td>
                <div className={styles.mkey}>{m.key}</div>
                {m.hf_id && <div className={styles.mhf}>{m.hf_id}</div>}
              </td>
              <td><span className={`${styles.provider} ${styles[m.provider] ?? styles.custom}`}>{m.provider}</span></td>
              <td>
                <div className={styles.flags}>
                  {(Array.isArray(m.flags) ? (m.flags as string[]).map((f) => [f, "ok"] as const) : Object.entries(m.flags ?? {})).map(([f, v]) => (
                    <span key={f} className={`${styles.flag} ${v === "strong" ? styles.strong : ""}`}>{f}</span>
                  ))}
                </div>
              </td>
              <td><span className={styles.serves}>{(m.serves ?? []).join(", ") || "—"}</span></td>
              <td><span className={styles.license}>{m.license ?? "—"}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Connections({ connections }: { connections: ConnectionInfo[] }) {
  const unlocked = useDemoToken();
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", base_url: "", api_key: "", data_class_ceiling: "SANITIZED", counts_as_local: false });
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = () => qc.invalidateQueries({ queryKey: ["connections"] });

  const add = async () => {
    if (!form.name || !form.base_url) return;
    setBusy(true);
    setFlash(null);
    try {
      await api.addConnection(form);
      setForm({ name: "", base_url: "", api_key: "", data_class_ceiling: "SANITIZED", counts_as_local: false });
      setFlash({ kind: "ok", msg: "Connection registered. The key is stored write-only and returned masked." });
      await refetch();
    } catch (e) {
      const status = (e as { status?: number }).status;
      setFlash({ kind: "err", msg: status === 401 ? "401 — presenter token required." : `Could not add: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.removeConnection(id);
      await refetch();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className={styles.body}>
      {connections.length === 0 && <div className={styles.empty}>No BYOK connections yet.</div>}
      {connections.map((c) => (
        <div key={c.id} className={styles.connRow}>
          <div>
            <div className={styles.connName}>{c.name}</div>
            <div className={styles.connUrl}>{c.base_url}</div>
          </div>
          <span className={styles.seatZone}>{c.zone}</span>
          <span className={styles.seatZone}>ceiling {c.data_class_ceiling ?? "SANITIZED"}</span>
          <span className={`${styles.spacer} ${styles.connKey}`}>{c.api_key}</span>
          <button className={styles.remove} disabled={!unlocked} onClick={() => remove(c.id)} title={unlocked ? "" : "Presenter mode required"}>
            <Trash weight="regular" style={{ width: 12, verticalAlign: "-2px" }} /> remove
          </button>
        </div>
      ))}

      <div className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label}>Name</label>
          <input className={styles.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Team GLM (Z.ai)" disabled={!unlocked} />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Base URL</label>
          <input className={styles.input} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.z.ai/v1" disabled={!unlocked} />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>API key (write-only)</label>
          <input className={styles.input} type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder="sk-…" disabled={!unlocked} />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Data-class ceiling</label>
          <select className={styles.input} value={form.data_class_ceiling} onChange={(e) => setForm({ ...form, data_class_ceiling: e.target.value })} disabled={!unlocked}>
            <option value="SANITIZED">SANITIZED — sanitized briefs only</option>
            <option value="RAW">RAW — raw data allowed (counts as local)</option>
          </select>
        </div>
        <label className={`${styles.field} ${styles.full} ${styles.checkbox}`}>
          <input type="checkbox" checked={form.counts_as_local} onChange={(e) => setForm({ ...form, counts_as_local: e.target.checked })} disabled={!unlocked} />
          Counts as local (inside the walls — raw data may be routed here)
        </label>
        {flash && <div className={`${styles.flash} ${flash.kind === "ok" ? styles.ok : styles.err}`}>{flash.msg}</div>}
        {unlocked ? (
          <button className={styles.submit} onClick={add} disabled={busy || !form.name || !form.base_url}>
            <Plug weight="fill" /> {busy ? "Registering…" : "Register connection"}
          </button>
        ) : (
          <span className={styles.locked}><Lock weight="regular" style={{ width: 11, verticalAlign: "-1px" }} /> Unlock Presenter mode to add a connection.</span>
        )}
      </div>
    </div>
  );
}

function SeatBindings({ models }: { models: ModelInfo[] }) {
  const unlocked = useDemoToken();
  const modelKeys = models.map((m) => m.key);
  const servedBy = (seat: Seat) => models.filter((m) => (m.serves ?? []).some((s) => s.startsWith(seat)));
  const [flash, setFlash] = useState<Record<string, { kind: "ok" | "err"; msg: string } | undefined>>({});

  const rebind = async (seat: Seat, model_key: string) => {
    try {
      await api.bindSeat(seat, { model_key });
      setFlash((f) => ({ ...f, [seat]: { kind: "ok", msg: "rebound" } }));
    } catch (e) {
      const status = (e as { status?: number }).status;
      setFlash((f) => ({ ...f, [seat]: { kind: "err", msg: status === 409 ? "ineligible (zone / data-class)" : status === 401 ? "presenter only" : "failed" } }));
    }
  };

  return (
    <div className={styles.body}>
      {SEATS.map(({ seat, zone }) => {
        const serving = servedBy(seat);
        return (
          <div key={seat} className={styles.seatRow}>
            <span className={styles.seatName}>{seat}</span>
            <span className={styles.seatZone}>{zone}</span>
            <span className={styles.seatServe}>{serving.length ? serving.map((m) => m.key).join(", ") : "default binding"}</span>
            {flash[seat] && <span className={`${styles.seatFlash} ${flash[seat]!.kind === "ok" ? styles.ok : styles.err}`}>{flash[seat]!.msg}</span>}
            <select
              className={styles.seatSelect}
              defaultValue=""
              disabled={!unlocked}
              onChange={(e) => e.target.value && rebind(seat, e.target.value)}
              title={unlocked ? "Rebind this seat" : "Presenter mode required"}
            >
              <option value="">rebind…</option>
              {modelKeys.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
        );
      })}
    </div>
  );
}

function EgressLedger() {
  const q = useQuery({ queryKey: ["egress"], queryFn: () => api.egress(), enabled: !MOCK_FORCED, retry: 0, refetchInterval: 5000 });
  const rows = (q.data?.egress ?? []).slice(0, 40);
  const violations = rows.filter((r) => r.sovereign_violation).length;
  const crossings = rows.filter((r) => r.zone === "EXTERNAL" && !r.sovereign_violation).length;

  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <WifiHigh weight="regular" style={{ width: 16, color: "var(--text-muted)" }} />
        <span className={styles.sectionTitle}>Egress ledger</span>
        <span className={styles.sectionNote}>
          {crossings} sanitized crossing{crossings === 1 ? "" : "s"}
          {violations > 0 && ` · ${violations} blocked`}
        </span>
      </div>
      <div className={styles.body}>
        {rows.length === 0 ? (
          <div className={styles.empty}>{q.isLoading ? "Loading ledger…" : "No egress recorded. Everything ran inside the walls."}</div>
        ) : (
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Host</th>
                  <th>Seat</th>
                  <th>Scope</th>
                  <th>Bytes</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r: EgressRow) => (
                  <tr key={r.id} style={r.sovereign_violation ? { background: "var(--danger-wash)" } : undefined}>
                    <td>
                      {r.sovereign_violation ? (
                        <span className={styles.provider} style={{ background: "var(--danger-wash)", color: "var(--danger-strong)" }}>
                          <WarningOctagon weight="fill" style={{ width: 11, verticalAlign: "-2px" }} /> blocked
                        </span>
                      ) : (
                        <ZoneBadge zone={r.zone as Zone} size="xs" />
                      )}
                    </td>
                    <td className={styles.connKey} style={{ letterSpacing: 0 }}>{r.host}</td>
                    <td className={styles.serves}>{r.seat ?? "—"}</td>
                    <td className={styles.mhf} style={{ marginTop: 0 }}>{r.scope}</td>
                    <td className={styles.serves}>{(r.bytes_out ?? 0) + (r.bytes_in ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export function Config() {
  const enabled = !MOCK_FORCED;
  const modelsQ = useQuery({ queryKey: ["models"], queryFn: api.listModels, enabled, retry: 0 });
  const connsQ = useQuery({ queryKey: ["connections"], queryFn: api.listConnections, enabled, retry: 0 });
  const models = useMemo(() => modelsQ.data?.models ?? [], [modelsQ.data]);
  const connections = connsQ.data?.connections ?? [];

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h1 className={styles.title}>Configuration</h1>
        <p className={styles.sub}>
          The routing substrate. Application code addresses seats, never models — bindings and BYOK endpoints live here, and every
          route is checked against the seat's zone and data-class ceiling before a single token moves.
        </p>
      </div>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <Cpu weight="regular" style={{ width: 16, color: "var(--text-muted)" }} />
          <span className={styles.sectionTitle}>Model registry</span>
          <span className={styles.sectionNote}>{models.length} models · builtin + BYOK, with capability flags</span>
        </div>
        <div className={styles.body}>
          {models.length ? <ModelRegistry models={models} /> : <div className={styles.empty}>{modelsQ.isLoading ? "Loading registry…" : "No models registered."}</div>}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <Plug weight="regular" style={{ width: 16, color: "var(--text-muted)" }} />
          <span className={styles.sectionTitle}>BYOK connections</span>
          <span className={styles.sectionNote}>keys stored write-only, returned masked</span>
        </div>
        <Connections connections={connections} />
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <ShieldCheck weight="regular" style={{ width: 16, color: "var(--text-muted)" }} />
          <span className={styles.sectionTitle}>Seat bindings</span>
          <span className={styles.sectionNote}>rebinding to an ineligible model is rejected (409)</span>
        </div>
        <SeatBindings models={models} />
      </section>

      <EgressLedger />
    </div>
  );
}
