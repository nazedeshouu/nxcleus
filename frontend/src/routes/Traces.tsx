import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, LockKey, Terminal, Wrench, CaretDown, CaretRight, CheckCircle, XCircle } from "@phosphor-icons/react";
import { api, type ToolInfo, type TraceDetail, type TraceSummary } from "../api/client";
import { API_BASE, MOCK_FORCED } from "../api/config";
import { openEventStream } from "../api/sse";
import { ZoneBadge } from "../components/ui/ZoneBadge";
import { DataClassChip } from "../components/ui/DataClassChip";
import { usePublicConfig } from "../components/shell/usePublicConfig";
import { usd } from "../lib/format";
import type { Zone } from "../lib/events";
import styles from "./Traces.module.css";

function scopeEventsPath(scope: string): string | null {
  if (scope.startsWith("job:")) return `/jobs/${scope.slice(4)}/events`;
  if (scope.startsWith("run:")) return `/runs/${scope.slice(4)}/events`;
  return null;
}

function parseMessages(detail: TraceDetail): Array<{ role: string; content: string }> {
  // authoritative field is the already-parsed `messages`; messages_json is the raw fallback
  let m: unknown = Array.isArray(detail.messages) ? detail.messages : detail.messages_json;
  if (typeof m === "string") {
    try {
      m = JSON.parse(m);
    } catch {
      return [{ role: "raw", content: m as string }];
    }
  }
  if (!Array.isArray(m)) return [];
  return (m as Array<Record<string, unknown>>).map((x) =>
    x && typeof x === "object"
      ? {
          role: String(x.role ?? "user"),
          content: typeof x.content === "string" ? x.content : JSON.stringify(x.content, null, 2),
        }
      : { role: "user", content: String(x) },
  );
}

function CopyBtn({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className={styles.copy}
      title="Copy"
      onClick={() => {
        navigator.clipboard?.writeText(text).catch(() => undefined);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
    >
      {done ? <Check weight="bold" /> : <Copy weight="regular" />}
    </button>
  );
}

function TracePane({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["trace", id], queryFn: () => api.trace(id), retry: 0 });
  const t = q.data;
  if (q.isLoading) return <div className={styles.paneEmpty}>Loading trace…</div>;
  if (!t) return <div className={styles.paneEmpty}>Trace unavailable.</div>;
  const messages = parseMessages(t);
  const parsedOk = t.badge === "parsed_ok" || t.badge?.includes("ok");

  return (
    <div className={styles.pane}>
      <div className={styles.paneHead}>
        <div className={styles.paneMeta}>
          <span className={styles.seatArrow}>{t.seat} → {t.model ?? t.backend}</span>
          <ZoneBadge zone={t.zone as Zone} size="xs" />
          {t.badge && <span className={`${styles.badge} ${parsedOk ? styles.badgeOk : ""}`}>{t.badge}</span>}
        </div>
        <div className={styles.paneNums}>
          <span>{t.tokens_in.toLocaleString()} in</span>
          <span>{t.tokens_out.toLocaleString()} out</span>
          <span>{usd(t.cost_usd)}</span>
          {t.latency_ms != null && <span>{(t.latency_ms / 1000).toFixed(1)}s</span>}
        </div>
      </div>

      <div className={styles.msgs}>
        {messages.length === 0 && <div className={styles.paneEmpty}>No message payload on this trace.</div>}
        {messages.map((m, i) => (
          <div className={`${styles.msg} ${styles[`m_${m.role}`] ?? ""}`} key={i}>
            <div className={styles.msgHead}>
              <span className={styles.msgRole}>{m.role}</span>
              <CopyBtn text={m.content} />
            </div>
            <pre className={styles.msgBody}>{m.content}</pre>
          </div>
        ))}
        {t.response_text && (
          <div className={`${styles.msg} ${styles.m_assistant}`}>
            <div className={styles.msgHead}>
              <span className={styles.msgRole}>response</span>
              <CopyBtn text={t.response_text} />
            </div>
            <pre className={styles.msgBody}>{t.response_text}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

/** F7: a runtime-commissioned python tool — card with expandable code + schema. */
function ToolCard({ tool }: { tool: ToolInfo }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.toolCard}>
      <button className={styles.toolHead} onClick={() => setOpen((o) => !o)}>
        {open ? <CaretDown weight="bold" /> : <CaretRight weight="bold" />}
        <Wrench weight="bold" className={styles.toolIcon} />
        <span className={styles.toolName}>{tool.name}</span>
        {tool.self_test_passed != null && (
          <span className={`${styles.badge} ${tool.self_test_passed ? styles.badgeOk : ""}`}>
            {tool.self_test_passed ? <CheckCircle weight="fill" /> : <XCircle weight="fill" />} self-test
          </span>
        )}
        <span className={styles.toolBy}>
          {[tool.created_by_seat, tool.model].filter(Boolean).join(" · ")}
        </span>
      </button>
      {tool.description && <p className={styles.toolDesc}>{tool.description}</p>}
      {open && (
        <div className={styles.toolBody}>
          {tool.args_schema != null && (
            <div className={styles.msg}>
              <div className={styles.msgHead}>
                <span className={styles.msgRole}>args schema</span>
                <CopyBtn text={JSON.stringify(tool.args_schema, null, 2)} />
              </div>
              <pre className={styles.msgBody}>{JSON.stringify(tool.args_schema, null, 2)}</pre>
            </div>
          )}
          {tool.code && (
            <div className={styles.msg}>
              <div className={styles.msgHead}>
                <span className={styles.msgRole}>code</span>
                <CopyBtn text={tool.code} />
              </div>
              <pre className={styles.msgBody}>{tool.code}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function Traces() {
  const [params] = useSearchParams();
  const scope = params.get("scope") ?? "";
  const { config } = usePublicConfig();
  const qc = useQueryClient();
  const [seat, setSeat] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [tab, setTab] = useState<"dispatches" | "tools">("dispatches");

  const listQ = useQuery({
    queryKey: ["traces", scope],
    queryFn: () => api.traces({ scope: scope || undefined, limit: 200 }),
    enabled: !MOCK_FORCED,
    retry: 0,
  });
  // ponytail: 404 from a backend without the tools endpoint = query error = tab hidden
  const toolsQ = useQuery({
    queryKey: ["tools", scope],
    queryFn: () => api.tools(scope || undefined),
    enabled: !MOCK_FORCED,
    retry: 0,
  });
  const tools = toolsQ.data?.tools ?? [];
  const all = useMemo(() => listQ.data?.traces ?? [], [listQ.data]);
  const seats = useMemo(() => [...new Set(all.map((t) => t.seat))], [all]);
  const traces = seat ? all.filter((t) => t.seat === seat) : all;

  // live-append: model.trace / tool.created on the active scope refresh the lists
  useEffect(() => {
    const path = scopeEventsPath(scope);
    if (!path || MOCK_FORCED) return;
    const stream = openEventStream(`${API_BASE}${path}`, {
      onEvent: (ev) => {
        if (ev.type === "model.trace") qc.invalidateQueries({ queryKey: ["traces", scope] });
        if (ev.type === "tool.created") qc.invalidateQueries({ queryKey: ["tools", scope] });
      },
    });
    return () => stream.close();
  }, [scope, qc]);

  const backTo = scope.startsWith("job:") ? `/build/${scope.slice(4)}` : "/operations";

  return (
    <div className={styles.wrap}>
      <Link to={backTo} className={styles.back}><ArrowLeft weight="bold" /> Back</Link>

      <div className={styles.head}>
        <div>
          <h1 className={styles.title}><Terminal weight="bold" /> Trace inspector</h1>
          <p className={styles.sub}>
            Every model dispatch: exact prompts, responses, tokens, cost, latency.
          </p>
        </div>
        <span className={styles.localNote}>
          <LockKey weight="fill" /> traces are LOCAL-only — they contain <DataClassChip cls="RAW" size="xs" /> data
        </span>
      </div>

      {config.trace_prompts === false && (
        <div className={styles.disabled}>
          Prompt tracing is switched off (<code>trace_prompts: false</code>). Metadata still lands here; message bodies are not stored.
        </div>
      )}

      <div className={styles.filters}>
        {scope && <span className={styles.scopeChip}>{scope}</span>}
        {tools.length > 0 && (
          <div className={styles.tabs}>
            <button className={`${styles.seatChip} ${tab === "dispatches" ? styles.on : ""}`} onClick={() => setTab("dispatches")}>
              dispatches · {all.length}
            </button>
            <button className={`${styles.seatChip} ${tab === "tools" ? styles.on : ""}`} onClick={() => setTab("tools")}>
              <Wrench weight="bold" style={{ width: 10, verticalAlign: "-1px", marginRight: 3 }} />
              tools · {tools.length}
            </button>
          </div>
        )}
        {tab === "dispatches" && (
          <>
            <button className={`${styles.seatChip} ${seat == null ? styles.on : ""}`} onClick={() => setSeat(null)}>all seats</button>
            {seats.map((s) => (
              <button key={s} className={`${styles.seatChip} ${seat === s ? styles.on : ""}`} onClick={() => setSeat(s)}>{s}</button>
            ))}
          </>
        )}
      </div>

      {tab === "tools" ? (
        <div className={styles.toolGrid}>
          {tools.map((t) => <ToolCard key={t.id} tool={t} />)}
        </div>
      ) : (
      <div className={styles.split}>
        <div className={styles.list}>
          {listQ.isLoading && <div className={styles.paneEmpty}>Loading traces…</div>}
          {!listQ.isLoading && traces.length === 0 && (
            <div className={styles.paneEmpty}>
              {MOCK_FORCED
                ? "Trace capture needs the live backend — fixtures don't carry prompts."
                : "No traces recorded for this scope yet. They appear per model dispatch, live."}
            </div>
          )}
          {traces.map((t: TraceSummary) => (
            <button key={t.id} className={`${styles.row} ${sel === t.id ? styles.sel : ""}`} onClick={() => setSel(t.id)}>
              <div className={styles.rowTop}>
                <span className={styles.seatArrow}>{t.seat} → {t.model ?? t.backend}</span>
                <span className={styles.rowTs}>{t.ts?.slice(11, 19)}</span>
              </div>
              <div className={styles.rowNums}>
                <ZoneBadge zone={t.zone as Zone} size="xs" />
                <span>{t.tokens_in.toLocaleString()}→{t.tokens_out.toLocaleString()} tok</span>
                <span>{usd(t.cost_usd)}</span>
                <span>{t.latency_ms != null ? `${(t.latency_ms / 1000).toFixed(1)}s` : ""}</span>
              </div>
              {(t.messages_preview || t.response_preview) && (
                <div className={styles.rowPrev}>{t.messages_preview ?? t.response_preview}</div>
              )}
            </button>
          ))}
        </div>

        <div className={styles.detail}>
          {sel ? <TracePane id={sel} /> : <div className={styles.paneEmpty}>Select a dispatch to read its full prompt and response.</div>}
        </div>
      </div>
      )}
    </div>
  );
}
