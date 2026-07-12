import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Check, Copy, LockKey, Terminal, Wrench, CaretDown, CaretRight, CaretUp,
  CheckCircle, XCircle, MagnifyingGlass, Brain, DownloadSimple,
} from "@phosphor-icons/react";
import { api, type ToolInfo, type TraceDetail, type TraceSummary } from "../api/client";
import { API_BASE, MOCK_FORCED } from "../api/config";
import { openEventStream } from "../api/sse";
import { ZoneBadge } from "../components/ui/ZoneBadge";
import { DataClassChip } from "../components/ui/DataClassChip";
import { SEAT_INFO } from "../api/adapt";
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

const hhmmss = (ts?: string) => ts?.slice(11, 19) ?? "";
const secs = (ms?: number | null) => (ms != null ? `${(ms / 1000).toFixed(1)}s` : "");
const modelOf = (t: TraceSummary) => t.model ?? SEAT_INFO[t.seat]?.model ?? t.backend;

/** Pull <think>/<reasoning> spans out of an assistant reply so they render as a distinct block. */
function splitReasoning(text: string): { reasoning: string[]; body: string } {
  const reasoning: string[] = [];
  const body = text
    .replace(/<(think|reasoning|thinking)>([\s\S]*?)<\/\1>/gi, (_all, _tag, inner: string) => {
      const t = inner.trim();
      if (t) reasoning.push(t);
      return "";
    })
    .trim();
  return { reasoning, body };
}

/* ---------- lightweight, dependency-free markdown (code fences + json + inline) ---------- */
function inlineMd(text: string, k: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("`")) out.push(<code key={`${k}i${i}`} className={styles.inlineCode}>{tok.slice(1, -1)}</code>);
    else out.push(<strong key={`${k}i${i}`}>{tok.slice(2, -2)}</strong>);
    last = m.index + tok.length;
    i++;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function Prose({ text }: { text: string }) {
  const lines = text.replace(/\n{3,}/g, "\n\n").split("\n");
  return (
    <>
      {lines.map((ln, i) => {
        const h = /^(#{1,3})\s+(.*)/.exec(ln);
        if (h) return <div key={i} className={styles.mdH}>{inlineMd(h[2], `h${i}`)}</div>;
        const b = /^\s*[-*]\s+(.*)/.exec(ln);
        if (b) return <div key={i} className={styles.mdLi}>{inlineMd(b[1], `b${i}`)}</div>;
        if (!ln.trim()) return <div key={i} className={styles.mdBr} />;
        return <div key={i} className={styles.mdP}>{inlineMd(ln, `p${i}`)}</div>;
      })}
    </>
  );
}

function Markdown({ text }: { text: string }) {
  const trimmed = text.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return <pre className={styles.code}>{JSON.stringify(JSON.parse(trimmed), null, 2)}</pre>;
    } catch {
      /* not JSON — fall through to prose/code-fence rendering */
    }
  }
  const parts = trimmed.split(/```(\w*)\n?([\s\S]*?)```/g);
  const out: ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 3) {
    const prose = parts[i];
    if (prose && prose.trim()) out.push(<Prose key={`p${i}`} text={prose} />);
    const code = parts[i + 2];
    if (code != null) {
      const lang = parts[i + 1];
      out.push(
        <pre key={`c${i}`} className={styles.code}>
          {lang ? <span className={styles.codeLang}>{lang}</span> : null}
          {code.replace(/\n$/, "")}
        </pre>,
      );
    }
  }
  return <div className={styles.md}>{out}</div>;
}

function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className={styles.copy}
      title={label ? `Copy ${label}` : "Copy"}
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text).catch(() => undefined);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
    >
      {done ? <Check weight="bold" /> : <Copy weight="regular" />}
      {label && <span>{done ? "copied" : label}</span>}
    </button>
  );
}

function MessageBlock({ role, content }: { role: string; content: string }) {
  const isSystem = role === "system" || role === "developer";
  const isAssistant = role === "assistant" || role === "response";
  const [open, setOpen] = useState(!isSystem); // system prompts collapsed by default (long, stable)
  const { reasoning, body } = isAssistant ? splitReasoning(content) : { reasoning: [], body: content };

  return (
    <div className={`${styles.msg} ${styles[`m_${role}`] ?? ""}`}>
      <button className={styles.msgHead} onClick={() => setOpen((o) => !o)}>
        {isSystem && (open ? <CaretDown weight="bold" className={styles.msgCaret} /> : <CaretRight weight="bold" className={styles.msgCaret} />)}
        <span className={styles.msgRole}>{role}</span>
        {isSystem && !open && <span className={styles.msgHint}>{content.length.toLocaleString()} chars — click to expand</span>}
        <CopyBtn text={content} />
      </button>
      {open && (
        <div className={styles.msgBody}>
          {reasoning.map((r, i) => (
            <div key={i} className={styles.reasoning}>
              <span className={styles.reasoningTag}><Brain weight="fill" /> reasoning</span>
              <Prose text={r} />
            </div>
          ))}
          <Markdown text={body} />
        </div>
      )}
    </div>
  );
}

function TracePane({
  id, pos, onPrev, onNext, hasPrev, hasNext,
}: {
  id: string;
  pos: string;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  const q = useQuery({ queryKey: ["trace", id], queryFn: () => api.trace(id), retry: 0 });
  const t = q.data;
  if (q.isLoading) return <div className={styles.paneEmpty}>Loading trace…</div>;
  if (!t) return <div className={styles.paneEmpty}>Trace unavailable.</div>;
  const messages = parseMessages(t);
  const parsedOk = t.badge === "parsed_ok" || t.badge?.includes("ok");
  const rawAll = [
    ...messages.map((m) => `### ${m.role}\n${m.content}`),
    t.response_text ? `### response\n${t.response_text}` : "",
  ].filter(Boolean).join("\n\n");

  return (
    <div className={styles.pane}>
      <div className={styles.paneHead}>
        <div className={styles.paneMeta}>
          <span className={styles.seatArrow}>{t.seat} → {modelOf(t)}</span>
          <ZoneBadge zone={t.zone as Zone} size="xs" />
          {t.badge && <span className={`${styles.badge} ${parsedOk ? styles.badgeOk : ""}`}>{t.badge}</span>}
        </div>
        <div className={styles.paneRight}>
          <div className={styles.paneNums}>
            <span>{t.tokens_in.toLocaleString()} in</span>
            <span>{t.tokens_out.toLocaleString()} out</span>
            <span>{usd(t.cost_usd)}</span>
            {t.latency_ms != null && <span>{secs(t.latency_ms)}</span>}
          </div>
          <CopyBtn text={rawAll} label="all" />
          <div className={styles.nav}>
            <button className={styles.navBtn} onClick={onPrev} disabled={!hasPrev} title="Previous (↑)"><CaretUp weight="bold" /></button>
            <span className={styles.navPos}>{pos}</span>
            <button className={styles.navBtn} onClick={onNext} disabled={!hasNext} title="Next (↓)"><CaretDown weight="bold" /></button>
          </div>
        </div>
      </div>

      <div className={styles.msgs}>
        {messages.length === 0 && !t.response_text && (
          <div className={styles.paneEmpty}>No message payload on this trace.</div>
        )}
        {messages.map((m, i) => <MessageBlock key={i} role={m.role} content={m.content} />)}
        {t.response_text && <MessageBlock role="response" content={t.response_text} />}
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
              <pre className={styles.code}>{JSON.stringify(tool.args_schema, null, 2)}</pre>
            </div>
          )}
          {tool.code && (
            <div className={styles.msg}>
              <div className={styles.msgHead}>
                <span className={styles.msgRole}>code</span>
                <CopyBtn text={tool.code} />
              </div>
              <pre className={styles.code}>{tool.code}</pre>
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
  const seatParam = params.get("seat");
  const { config } = usePublicConfig();
  const qc = useQueryClient();
  const [seat, setSeat] = useState<string | null>(seatParam);
  const [search, setSearch] = useState("");
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
  // chronological (oldest first) reads like a transcript and defines prev/next order
  const chrono = useMemo(() => [...all].sort((a, b) => (a.ts ?? "").localeCompare(b.ts ?? "")), [all]);
  const seats = useMemo(() => [...new Set(chrono.map((t) => t.seat))], [chrono]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return chrono.filter((t) => {
      if (seat && t.seat !== seat) return false;
      if (!needle) return true;
      return (
        t.seat.toLowerCase().includes(needle) ||
        modelOf(t).toLowerCase().includes(needle) ||
        (t.messages_preview ?? "").toLowerCase().includes(needle) ||
        (t.response_preview ?? "").toLowerCase().includes(needle)
      );
    });
  }, [chrono, seat, search]);

  // group the filtered list by seat, preserving chronological order of first appearance
  const groups = useMemo(() => {
    const map = new Map<string, TraceSummary[]>();
    for (const t of filtered) (map.get(t.seat) ?? map.set(t.seat, []).get(t.seat)!).push(t);
    return [...map.entries()].map(([s, rows]) => ({ seat: s, model: modelOf(rows[0]), rows }));
  }, [filtered]);

  const selIdx = filtered.findIndex((t) => t.id === sel);
  const go = (delta: number) => {
    if (!filtered.length) return;
    const next = selIdx < 0 ? 0 : Math.min(Math.max(selIdx + delta, 0), filtered.length - 1);
    setSel(filtered[next].id);
  };

  // keyboard prev/next over the filtered list (ignore when typing in the search box)
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (tab !== "dispatches") return;
    const onKey = (e: KeyboardEvent) => {
      if (document.activeElement === searchRef.current) return;
      if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); go(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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
  const exportHref = `${API_BASE}/traces/export?${new URLSearchParams({
    ...(scope ? { scope } : {}),
    ...(seat ? { seat } : {}),
  }).toString()}`;

  return (
    <div className={styles.wrap}>
      <Link to={backTo} className={styles.back}><ArrowLeft weight="bold" /> Back</Link>

      <div className={styles.head}>
        <div>
          <h1 className={styles.title}><Terminal weight="bold" /> Trace inspector</h1>
          <p className={styles.sub}>
            Every model dispatch: exact prompts, responses, reasoning, tokens, cost, latency.
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
            <div className={styles.searchWrap}>
              <MagnifyingGlass weight="bold" />
              <input
                ref={searchRef}
                className={styles.search}
                placeholder="Search prompts, responses, models…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button className={`${styles.seatChip} ${seat == null ? styles.on : ""}`} onClick={() => setSeat(null)}>all seats</button>
            {seats.map((s) => (
              <button key={s} className={`${styles.seatChip} ${seat === s ? styles.on : ""}`} onClick={() => setSeat((cur) => (cur === s ? null : s))}>{s}</button>
            ))}
            {!MOCK_FORCED && filtered.length > 0 && (
              <a className={styles.seatChip} href={exportHref} style={{ marginLeft: "auto" }}
                 title="Download every dispatch on this scope as JSONL (full prompts + responses)">
                <DownloadSimple weight="bold" style={{ width: 11, verticalAlign: "-1px", marginRight: 4 }} /> Export JSONL
              </a>
            )}
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
            {!listQ.isLoading && filtered.length === 0 && (
              <div className={styles.paneEmpty}>
                {MOCK_FORCED
                  ? "Trace capture needs the live backend — fixtures don't carry prompts."
                  : search || seat
                    ? "No dispatches match this filter."
                    : "No traces recorded for this scope yet. They appear per model dispatch, live."}
              </div>
            )}
            {groups.map((g) => (
              <div key={g.seat} className={styles.group}>
                <div className={styles.groupHead}>
                  <span className={styles.groupSeat}>{g.seat}</span>
                  <span className={styles.groupModel}>{g.model}</span>
                  <span className={styles.groupCount}>{g.rows.length}×</span>
                </div>
                {SEAT_INFO[g.seat]?.purpose && (
                  <div className={styles.groupWhy}>{SEAT_INFO[g.seat]!.purpose}</div>
                )}
                {g.rows.map((t) => (
                  <button key={t.id} className={`${styles.row} ${sel === t.id ? styles.sel : ""}`} onClick={() => setSel(t.id)}>
                    <div className={styles.rowTop}>
                      <span className={styles.rowTs} title={t.ts}>{hhmmss(t.ts)}</span>
                      <ZoneBadge zone={t.zone as Zone} size="xs" />
                      <span className={styles.rowNums}>
                        <span>{(t.tokens_in + t.tokens_out).toLocaleString()} tok</span>
                        <span>{usd(t.cost_usd)}</span>
                        {t.latency_ms != null && <span>{secs(t.latency_ms)}</span>}
                      </span>
                    </div>
                    {(t.messages_preview || t.response_preview) && (
                      <div className={styles.rowPrev}>{t.messages_preview ?? t.response_preview}</div>
                    )}
                  </button>
                ))}
              </div>
            ))}
          </div>

          <div className={styles.detail}>
            {sel ? (
              <TracePane
                id={sel}
                pos={selIdx >= 0 ? `${selIdx + 1} / ${filtered.length}` : ""}
                onPrev={() => go(-1)}
                onNext={() => go(1)}
                hasPrev={selIdx > 0}
                hasNext={selIdx >= 0 && selIdx < filtered.length - 1}
              />
            ) : (
              <div className={`${styles.paneEmpty} ${styles.detailEmpty}`}>Select a dispatch to read its full prompt, reasoning, and response. Use ↑/↓ to move between dispatches.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
