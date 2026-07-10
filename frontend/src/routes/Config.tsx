import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Plug, Lock, Trash, ShieldCheck, WifiHigh, WarningOctagon, Warning, CheckCircle, XCircle, Pulse } from "@phosphor-icons/react";
import { api, type ApiStyle, type ConnectionInfo, type ConnectionTest, type EgressRow, type ModelInfo } from "../api/client";
import { ZoneBadge } from "../components/ui/ZoneBadge";
import { DataClassChip } from "../components/ui/DataClassChip";
import { useDemoToken } from "../api/useDemoToken";
import { MOCK_FORCED } from "../api/config";
import { SEAT_INFO } from "../api/adapt";
import type { Seat, Zone } from "../lib/events";
import styles from "./Config.module.css";

// Provider presets prefill the base URL + wire dialect; "Custom" leaves them blank.
const PRESETS: { label: string; base_url: string; api_style: ApiStyle }[] = [
  { label: "OpenAI", base_url: "https://api.openai.com/v1", api_style: "openai" },
  { label: "Anthropic", base_url: "https://api.anthropic.com", api_style: "anthropic" },
  { label: "Fireworks", base_url: "https://api.fireworks.ai/inference/v1", api_style: "openai" },
  { label: "AMD local fleet", base_url: "http://localhost:8000/v1", api_style: "openai" },
  { label: "Custom", base_url: "", api_style: "openai" },
];

// ponytail: static seat→zone/role map mirrors infra/seats.yaml; fetch /seats if bindings go dynamic
const SEATS: { seat: Seat; zone: Zone; role: string }[] = [
  { seat: "trust", zone: "LOCAL", role: "Front door — intake dialogue, policy capture, sanitization" },
  { seat: "planner", zone: "EXTERNAL", role: "Frontier architect — sees only the sanitized brief" },
  { seat: "certifier", zone: "LOCAL", role: "Hardens the plan into checks, tests, and scope locks" },
  { seat: "conductor", zone: "LOCAL", role: "Runs the build waves, reviews between each" },
  { seat: "coder", zone: "LOCAL", role: "Writes the modules, fleet-parallel" },
  { seat: "consolidator", zone: "LOCAL", role: "Merges modules behind the validation wall" },
  { seat: "oracle", zone: "LOCAL", role: "Lineage-independent numeric verification" },
  { seat: "inspector", zone: "LOCAL", role: "Adversarial QA probes" },
];

const FLAG_PRESETS = ["code", "json", "long_context", "reasoning", "cheap"];

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
  const [form, setForm] = useState<{ name: string; base_url: string; api_key: string; data_class_ceiling: string; counts_as_local: boolean; api_style: ApiStyle }>(
    { name: "", base_url: "", api_key: "", data_class_ceiling: "SANITIZED", counts_as_local: false, api_style: "openai" },
  );
  const [modelId, setModelId] = useState("");
  const [flags, setFlags] = useState<string[]>([]);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [tests, setTests] = useState<Record<string, ConnectionTest | "busy">>({});

  const refetch = () => qc.invalidateQueries({ queryKey: ["connections"] });
  const toggleFlag = (f: string) => setFlags((fs) => (fs.includes(f) ? fs.filter((x) => x !== f) : [...fs, f]));

  const applyPreset = (p: (typeof PRESETS)[number]) =>
    setForm((f) => ({ ...f, base_url: p.base_url, api_style: p.api_style, name: f.name || (p.label === "Custom" ? "" : p.label) }));

  const test = async (id: string) => {
    setTests((t) => ({ ...t, [id]: "busy" }));
    try {
      const res = await api.testConnection(id);
      setTests((t) => ({ ...t, [id]: res }));
    } catch (e) {
      setTests((t) => ({ ...t, [id]: { ok: false, error: (e as Error).message } }));
    }
  };

  const add = async () => {
    if (!form.name || !form.base_url) return;
    setBusy(true);
    setFlash(null);
    try {
      const res = await api.addConnection(form);
      // register the first model with its capability flags in the same gesture
      if (modelId.trim() && res?.connection?.id) {
        await api
          .addConnectionModel(res.connection.id, { provider_model_id: modelId.trim(), display_name: modelId.trim(), flags })
          .catch(() => setFlash({ kind: "err", msg: "Connection saved, but the model registration failed — add it again below." }));
      }
      setForm({ name: "", base_url: "", api_key: "", data_class_ceiling: "SANITIZED", counts_as_local: false, api_style: "openai" });
      setModelId("");
      setFlags([]);
      setFlash((f) => f ?? { kind: "ok", msg: "Connection registered. The key is stored write-only and returned masked." });
      await refetch();
      await qc.invalidateQueries({ queryKey: ["models"] });
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
      {connections.length === 0 && <div className={styles.empty}>No BYOK connections yet — add one below, or the built-in local fleet serves every seat.</div>}
      {connections.map((c) => {
        const t = tests[c.id];
        return (
          <div key={c.id} className={styles.connRow}>
            <div className={styles.connLead}>
              <div className={styles.connName}>{c.name}</div>
              <div className={styles.connUrl}>{c.base_url}</div>
            </div>
            {c.api_style && <span className={styles.apiStyle}>{c.api_style}</span>}
            <span className={styles.seatZone}>{c.zone}</span>
            <span className={styles.seatZone}>ceiling {c.data_class_ceiling ?? "SANITIZED"}</span>
            {c.counts_as_local && (
              <span className={styles.attest} title="Attested by you: this endpoint is treated as inside the walls — RAW data may route here">
                <Warning weight="fill" /> counts as LOCAL
              </span>
            )}
            <span className={`${styles.spacer} ${styles.connKey}`}>{c.api_key}</span>
            {t && t !== "busy" && (
              t.ok
                ? <span className={styles.testOk}><CheckCircle weight="fill" /> {t.latency_ms != null ? `${t.latency_ms} ms` : "ok"}{t.model ? ` · ${t.model}` : ""}</span>
                : <span className={styles.testErr} title={t.error}><XCircle weight="fill" /> {t.error ?? "failed"}</span>
            )}
            <button className={styles.testBtn} disabled={!unlocked || t === "busy"} onClick={() => test(c.id)} title={unlocked ? "Ping this endpoint" : "Presenter mode required"}>
              <Pulse weight="bold" style={{ width: 12, verticalAlign: "-2px" }} /> {t === "busy" ? "Testing…" : "Test"}
            </button>
            <button className={styles.remove} disabled={!unlocked} onClick={() => remove(c.id)} title={unlocked ? "" : "Presenter mode required"}>
              <Trash weight="regular" style={{ width: 12, verticalAlign: "-2px" }} /> remove
            </button>
          </div>
        );
      })}

      <div className={styles.form}>
        <div className={`${styles.field} ${styles.full}`}>
          <label className={styles.label}>Provider preset</label>
          <div className={styles.flagPick}>
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className={`${styles.flagChip} ${form.base_url === p.base_url && form.api_style === p.api_style && p.label !== "Custom" ? styles.on : ""}`}
                onClick={() => applyPreset(p)}
                disabled={!unlocked}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Name</label>
          <input className={styles.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Team GLM (Z.ai)" disabled={!unlocked} />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Base URL</label>
          <input className={styles.input} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.z.ai/v1" disabled={!unlocked} />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>API style</label>
          <select className={styles.input} value={form.api_style} onChange={(e) => setForm({ ...form, api_style: e.target.value as ApiStyle })} disabled={!unlocked}>
            <option value="openai">OpenAI-compatible</option>
            <option value="anthropic">Anthropic</option>
          </select>
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
        <div className={styles.field}>
          <label className={styles.label}>First model id (optional)</label>
          <input className={styles.input} value={modelId} onChange={(e) => setModelId(e.target.value)} placeholder="glm-4.6" disabled={!unlocked} />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Capability flags</label>
          <div className={styles.flagPick}>
            {FLAG_PRESETS.map((f) => (
              <button key={f} type="button" className={`${styles.flagChip} ${flags.includes(f) ? styles.on : ""}`} onClick={() => toggleFlag(f)} disabled={!unlocked}>
                {f}
              </button>
            ))}
          </div>
        </div>
        <label className={`${styles.field} ${styles.full} ${styles.checkbox}`}>
          <input type="checkbox" checked={form.counts_as_local} onChange={(e) => setForm({ ...form, counts_as_local: e.target.checked })} disabled={!unlocked} />
          Counts as local (inside the walls — raw data may be routed here)
        </label>
        {form.counts_as_local && (
          <div className={`${styles.full} ${styles.warnNote}`}>
            <Warning weight="fill" />
            You are attesting that this endpoint sits inside your boundary. RAW customer data may be routed to it,
            and the egress ledger will record it as a LOCAL zone. Only attest infrastructure you control.
          </div>
        )}
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

function SeatCards({ models, connections }: { models: ModelInfo[]; connections: ConnectionInfo[] }) {
  const unlocked = useDemoToken();
  const modelKeys = models.map((m) => m.key);
  const servedBy = (seat: Seat) => models.filter((m) => (m.serves ?? []).some((s) => s.startsWith(seat)));
  const openaiModel = models.find((m) => /gpt-5\.6-sol/i.test(m.key) || /gpt-5\.6-sol/i.test(m.hf_id ?? ""));
  const openaiConfigured = !!openaiModel || connections.some((c) => c.api_style === "openai");
  const [flash, setFlash] = useState<Record<string, { kind: "ok" | "err"; msg: string } | undefined>>({});
  const [bound, setBound] = useState<Record<string, string>>({}); // optimistic override display

  const rebind = async (seat: Seat, model_key: string) => {
    try {
      await api.bindSeat(seat, { model_key });
      setBound((b) => ({ ...b, [seat]: model_key }));
      setFlash((f) => ({ ...f, [seat]: { kind: "ok", msg: "rebound" } }));
    } catch (e) {
      const status = (e as { status?: number }).status;
      setFlash((f) => ({ ...f, [seat]: { kind: "err", msg: status === 409 ? "ineligible (zone / data-class)" : status === 401 ? "presenter only" : "failed" } }));
    }
  };

  return (
    <div className={styles.seatGrid}>
      {SEATS.map(({ seat, zone, role }) => {
        const serving = servedBy(seat);
        const overridden = !!bound[seat];
        const prefersOpenai = seat === "planner" && !overridden && openaiConfigured;
        const binding = bound[seat] ?? (prefersOpenai ? (openaiModel?.key ?? "openai/gpt-5.6-sol") : (serving[0]?.key ?? SEAT_INFO[seat]?.model ?? "default binding"));
        const why = overridden ? "override" : prefersOpenai ? "OpenRouter key configured" : "default";
        return (
          <div key={seat} className={styles.seatCard}>
            <div className={styles.seatCardHead}>
              <span className={styles.seatName}>{seat}</span>
              <ZoneBadge zone={zone} size="xs" />
            </div>
            <p className={styles.seatRole}>{role}</p>
            <div className={styles.seatBind}>
              <span className={styles.seatBindLbl}>binding</span>
              <span className={styles.seatBindModel}>{binding}</span>
              <DataClassChip cls={zone === "LOCAL" ? "RAW" : "SANITIZED"} size="xs" />
            </div>
            <div className={styles.seatWhy}>
              <span className={`${styles.whyDot} ${overridden ? styles.whyOverride : prefersOpenai ? styles.whyPref : ""}`} />
              {why}
            </div>
            {seat === "planner" && !openaiConfigured && (
              <div className={styles.seatNote}>Prefers <code>openai/gpt-5.6-sol</code> via OpenRouter when a key is configured.</div>
            )}
            <div className={styles.seatCardFoot}>
              <select
                className={styles.seatSelect}
                value=""
                disabled={!unlocked}
                onChange={(e) => e.target.value && rebind(seat, e.target.value)}
                title={unlocked ? "Override this seat's binding" : "Presenter mode required"}
              >
                <option value="">override…</option>
                {modelKeys.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              {flash[seat] && <span className={`${styles.seatFlash} ${flash[seat]!.kind === "ok" ? styles.ok : styles.err}`}>{flash[seat]!.msg}</span>}
            </div>
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
        <h1 className={styles.title}>Settings</h1>
        <p className={styles.sub}>
          The routing substrate. Application code addresses seats, never models — bring your own keys, bind seats to endpoints, and every
          route is checked against the seat's zone and data-class ceiling before a single token moves.
        </p>
      </div>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <Plug weight="regular" style={{ width: 16, color: "var(--text-muted)" }} />
          <span className={styles.sectionTitle}>Model connections</span>
          <span className={styles.sectionNote}>BYOK endpoints — keys stored write-only, returned masked</span>
        </div>
        <Connections connections={connections} />
        <div className={styles.subHead}>
          <Cpu weight="regular" style={{ width: 14, color: "var(--text-faint)" }} />
          <span className={styles.subTitle}>Model registry</span>
          <span className={styles.sectionNote}>{models.length} models · builtin + BYOK, with capability flags</span>
        </div>
        <div className={styles.body}>
          {models.length ? <ModelRegistry models={models} /> : <div className={styles.empty}>{modelsQ.isLoading ? "Loading registry…" : "No models registered."}</div>}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <ShieldCheck weight="regular" style={{ width: 16, color: "var(--text-muted)" }} />
          <span className={styles.sectionTitle}>Seat bindings</span>
          <span className={styles.sectionNote}>who does what, and which model holds the seat · overriding to an ineligible model is rejected (409)</span>
        </div>
        <div className={styles.body}>
          <SeatCards models={models} connections={connections} />
        </div>
      </section>

      <EgressLedger />
    </div>
  );
}
