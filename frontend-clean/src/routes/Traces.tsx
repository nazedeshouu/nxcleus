import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Check, Copy, LockKey, Wrench, CaretDown, CaretRight, CaretUp,
  CheckCircle, XCircle, MagnifyingGlass, Brain, DownloadSimple,
  ArrowSquareOut, ShieldCheck, ArrowUpRight, ArrowDown,
} from "@phosphor-icons/react";
import { api, type ToolInfo, type TraceDetail, type TraceSummary } from "../api/client";
import { API_BASE, MOCK_FORCED } from "../api/config";
import { openEventStream } from "../api/sse";
import { ZoneBadge } from "../components/ui/ZoneBadge";
import { DataClassChip } from "../components/ui/DataClassChip";
import { SEAT_INFO, normalizeEvent } from "../api/adapt";
import { usePublicConfig } from "../components/shell/usePublicConfig";
import { usd } from "../lib/format";
import type { Zone, BoundarySanitizedPayload } from "../lib/events";
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

/** Pull readable text out of a message `content` (string, or multimodal text parts). */
function contentText(c: unknown): string {
  if (typeof c === "string") return c;
  if (Array.isArray(c))
    return c.map((p) => (p && typeof p === "object" && "text" in p ? String((p as { text: unknown }).text) : "")).filter(Boolean).join(" ");
  return c == null ? "" : JSON.stringify(c);
}
/** The list preview is a raw messages-JSON string; surface the content, not the envelope. */
function previewText(s?: string): string {
  const t = (s ?? "").trim().replace(/\\+$/, ""); // previews cut mid-escape leave a dangling backslash
  if (!(t.startsWith("[") || t.startsWith("{"))) return t;
  try {
    const v = JSON.parse(t);
    const parts = (Array.isArray(v) ? v : [v]).map((m) => (m && typeof m === "object" ? contentText(m.content) : String(m))).filter(Boolean);
    if (parts.length) return parts.join("  ·  ");
  } catch { /* previews are truncated → invalid JSON; pull the content strings out by hand */ }
  const clean = (x: string) => x.replace(/\\[nrt]/g, " ").replace(/\\"/g, '"').replace(/\\\\/g, "\\").trim();
  const complete = [...t.matchAll(/"(?:content|text)"\s*:\s*"((?:[^"\\]|\\.)*)"/g)].map((m) => clean(m[1])).filter(Boolean);
  if (complete.length) return complete.join("  ·  ");
  // a single content value truncated mid-string: take from the last opener to the end
  const open = t.match(/"(?:content|text)"\s*:\s*"((?:[^"\\]|\\.)*)$/);
  return open ? `${clean(open[1]).replace(/\.{2,}$/, "")}…` : t;
}

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
      type="button"
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
      <div className={styles.msgHead}>
        <button type="button" className={styles.msgToggle} onClick={() => setOpen((o) => !o)}>
          {isSystem && (open ? <CaretDown weight="bold" className={styles.msgCaret} /> : <CaretRight weight="bold" className={styles.msgCaret} />)}
          <span className={styles.msgRole}>{role}</span>
          {isSystem && !open && <span className={styles.msgHint}>{content.length.toLocaleString()} chars — click to expand</span>}
        </button>
        <CopyBtn text={content} />
      </div>
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

/** Boundary action verbs the backend actually emits (free-form) -> friendly label + tone class. */
const ACTION_META: Record<string, { label: string; cls: string }> = {
  never_leak: { label: "never leaves", cls: "aNever" },
  drop: { label: "dropped", cls: "aDrop" },
  dropped: { label: "dropped", cls: "aDrop" },
  mask: { label: "masked", cls: "aMask" },
  masked: { label: "masked", cls: "aMask" },
  generalize: { label: "generalized", cls: "aGen" },
  abstracted: { label: "generalized", cls: "aGen" },
};
const actionMeta = (a: string) => ACTION_META[a] ?? { label: a.replace(/_/g, " "), cls: "aMask" };

/**
 * What the boundary stripped from this brief before it crossed the wall. Sourced
 * from the job's `boundary.sanitized` event — the same findings the cockpit shows,
 * pinned here beside the exact outgoing prompt so the crossing reads as supervised.
 */
function SanitizationStrip({ p }: { p: BoundarySanitizedPayload }) {
  return (
    <div className={styles.sanit}>
      <div className={styles.sanitHead}>
        <ShieldCheck weight="fill" />
        <span className={styles.sanitTitle}>Sanitized at the boundary</span>
        <span className={styles.sanitSub}>
          {p.brief_tokens > 0 ? `${p.brief_tokens.toLocaleString()} tokens crossed` : "before this crossed"}
        </span>
      </div>
      {p.findings.length > 0 && (
        <div className={styles.findings}>
          {p.findings.map((f, i) => {
            const m = actionMeta(String(f.action));
            return (
              <div key={i} className={styles.finding}>
                <span className={`${styles.fAction} ${styles[m.cls] ?? ""}`}>{m.label}</span>
                <span className={styles.fLabel}>{f.label}</span>
                {f.count > 0 && <span className={styles.fCount}>{f.count.toLocaleString()}</span>}
                <span className={styles.fRule}>{f.rule_id}</span>
              </div>
            );
          })}
        </div>
      )}
      {p.never_leaves.length > 0 && (
        <div className={styles.neverRow}>
          <span className={styles.neverLabel}>frontier never sees</span>
          <span className={styles.neverChips}>
            {p.never_leaves.map((n, i) => <span key={i} className={styles.neverChip}>{n}</span>)}
          </span>
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
  // the planner's brief is what crosses the wall — pull the job's sanitization
  // receipt (boundary.sanitized) to pin beside the exact outgoing prompt.
  const isBoundarySeat = t?.seat === "planner" || t?.zone === "EXTERNAL";
  const boundaryScope = t?.scope ?? "";
  const boundaryQ = useQuery({
    queryKey: ["boundary", boundaryScope],
    queryFn: async (): Promise<BoundarySanitizedPayload | null> => {
      const r = await api.replay(boundaryScope);
      const last = (r.events ?? [])
        .map((e) => normalizeEvent(e as never))
        .reverse()
        .find((e) => e?.type === "boundary.sanitized");
      return last ? (last.payload as BoundarySanitizedPayload) : null;
    },
    enabled: isBoundarySeat && boundaryScope.startsWith("job:") && !MOCK_FORCED,
    retry: 0,
    staleTime: Infinity,
  });
  if (q.isLoading) return <div className={styles.paneEmpty}>Loading trace…</div>;
  if (!t) return <div className={styles.paneEmpty}>Trace unavailable.</div>;
  const isCrossing = t.zone === "EXTERNAL";
  const isMock = (t.badge ?? "").toLowerCase().includes("mock");
  const messages = parseMessages(t);
  const parsedOk = t.badge === "parsed_ok" || t.badge?.includes("ok");
  const purpose = SEAT_INFO[t.seat]?.purpose ?? `Handled the ${t.seat} step in this workflow.`;
  const dataHandling = isCrossing
    ? isMock
      ? "A simulated sanitized request represented the external boundary crossing."
      : "Only a sanitized request crossed the boundary; raw records stayed local."
    : "This call ran inside the local environment; no request left the boundary.";
  const outcome = isMock
    ? "Completed with a simulated model response."
    : parsedOk
      ? "Completed and returned a response the workflow accepted."
      : t.badge
        ? `Completed with status: ${t.badge.replaceAll("_", " ")}.`
        : "Completed and recorded a response.";
  const rawAll = [
    ...messages.map((m) => `### ${m.role}\n${m.content}`),
    t.response_text ? `### response\n${t.response_text}` : "",
  ].filter(Boolean).join("\n\n");

  return (
    <div className={`${styles.pane} ${isCrossing ? styles.paneExternal : ""}`}>
      {isBoundarySeat && (
        <div className={`${styles.crossing} ${isCrossing ? styles.crossingLive : styles.crossingSov}`}>
          {isCrossing ? (
            isMock ? (
              <><ArrowSquareOut weight="bold" /> The one boundary crossing — simulated in this run; live, only this call leaves the box</>
            ) : (
              <><ArrowSquareOut weight="bold" /> The one call that leaves the box — everything else stays on-box</>
            )
          ) : (
            <><LockKey weight="fill" /> Sovereign — the planner ran on-box; nothing left</>
          )}
        </div>
      )}
      <div className={`${styles.paneHead} ${isCrossing ? styles.paneHeadExternal : ""}`}>
        <div className={styles.paneMeta}>
          <span className={styles.seatArrow}>{t.seat} → {modelOf(t)}</span>
          <ZoneBadge zone={t.zone as Zone} size="xs" />
          {t.badge && <span className={`${styles.badge} ${parsedOk ? styles.badgeOk : ""}`}>{t.badge}</span>}
        </div>
        <div className={styles.paneRight}>
          <div className={styles.nav}>
            <button className={styles.navBtn} onClick={onPrev} disabled={!hasPrev} title="Previous (↑)"><CaretUp weight="bold" /></button>
            <span className={styles.navPos}>{pos}</span>
            <button className={styles.navBtn} onClick={onNext} disabled={!hasNext} title="Next (↓)"><CaretDown weight="bold" /></button>
          </div>
        </div>
      </div>

      <div className={styles.callSummary}>
        <div className={styles.summaryPurpose}>
          <span>Why this call ran</span>
          <strong>{purpose}</strong>
        </div>
        <dl className={styles.summaryGrid}>
          <div>
            <dt>Data handling</dt>
            <dd>{dataHandling}</dd>
          </div>
          <div>
            <dt>Outcome</dt>
            <dd>{outcome}</dd>
          </div>
          <div>
            <dt>Cost</dt>
            <dd className="tnum">{usd(t.cost_usd)}</dd>
          </div>
          <div>
            <dt>Time</dt>
            <dd className="tnum">{t.latency_ms != null ? secs(t.latency_ms) : "Not recorded"}</dd>
          </div>
        </dl>
      </div>

      <details className={styles.advanced}>
        <summary>
          <div>
            <strong>Advanced audit details</strong>
            <span>Exact prompts, reasoning, raw response and token usage</span>
          </div>
          <span className={styles.advancedUsage}>{t.tokens_in.toLocaleString()} in · {t.tokens_out.toLocaleString()} out</span>
          <CaretDown weight="bold" />
        </summary>
        <div className={styles.advancedCopy}><CopyBtn text={rawAll} label="Copy all" /></div>
        <div className={styles.msgs}>
          {isBoundarySeat && boundaryQ.data && <SanitizationStrip p={boundaryQ.data} />}
          {messages.length === 0 && !t.response_text && (
            <div className={styles.paneEmpty}>No message payload on this call.</div>
          )}
          {isBoundarySeat && messages.length > 0 && (
            <div className={styles.flow}>
              <ArrowUpRight weight="bold" /> Outgoing — the sanitized brief that crossed the wall
            </div>
          )}
          {messages.map((m, i) => <MessageBlock key={i} role={m.role} content={m.content} />)}
          {isBoundarySeat && t.response_text && (
            <div className={styles.flow}>
              <ArrowDown weight="bold" /> Inbound — returned from the frontier
            </div>
          )}
          {t.response_text && <MessageBlock role="response" content={t.response_text} />}
        </div>
      </details>
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
    queryKey: ["traces", scope, seat],
    queryFn: () => api.traces({ scope: scope || undefined, seat: seat || undefined, limit: 200 }),
    enabled: !MOCK_FORCED,
    retry: 0,
  });
  // The backend caps /traces at 200 rows oldest-first; intake's trust dispatches flood
  // that window and bury the planner — the one external call this inspector exists to show.
  // Pin the planner rows explicitly so they surface in the all-seats view regardless.
  const plannerQ = useQuery({
    queryKey: ["traces", scope, "planner-pin"],
    queryFn: () => api.traces({ scope: scope || undefined, seat: "planner", limit: 50 }),
    enabled: !MOCK_FORCED && !seat,
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
  const all = useMemo(() => {
    const base = listQ.data?.traces ?? [];
    if (seat) return base; // server already filtered to this seat
    const pin = plannerQ.data?.traces ?? [];
    const seen = new Set(base.map((t) => t.id));
    return [...base, ...pin.filter((t) => !seen.has(t.id))];
  }, [listQ.data, plannerQ.data, seat]);
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

  const visualRows = useMemo(() => groups.flatMap((group) => group.rows), [groups]);
  const activeSel = sel && visualRows.some((trace) => trace.id === sel) ? sel : (visualRows[0]?.id ?? null);
  const selIdx = visualRows.findIndex((t) => t.id === activeSel);
  const go = (delta: number) => {
    if (!visualRows.length) return;
    const next = selIdx < 0 ? 0 : Math.min(Math.max(selIdx + delta, 0), visualRows.length - 1);
    setSel(visualRows[next].id);
  };

  // keyboard prev/next follows the same grouped order the user sees on screen
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
          <h1 className={styles.title}><Brain weight="fill" /> Model activity</h1>
          <p className={styles.sub}>
            Follow each model call in this job: what it received, what it returned, and what it cost.
          </p>
        </div>
        <span className={styles.localNote}>
          <LockKey weight="fill" /> Private audit record · stored locally · may contain <DataClassChip cls="RAW" size="xs" /> data
        </span>
      </div>

      <div className={styles.guide} aria-label="How to use model activity">
        <div><span>1</span><b>Choose a call</b><small>Planner, coder, certifier or another role</small></div>
        <div><span>2</span><b>Check the boundary</b><small>See what stayed local and what crossed</small></div>
        <div><span>3</span><b>Review the result</b><small>See the outcome, cost and time</small></div>
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
              Calls · {all.length}
            </button>
            <button className={`${styles.seatChip} ${tab === "tools" ? styles.on : ""}`} onClick={() => setTab("tools")}>
              <Wrench weight="bold" style={{ width: 10, verticalAlign: "-1px", marginRight: 3 }} />
              Generated tools · {tools.length}
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
                placeholder="Search requests, responses or models…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button className={`${styles.seatChip} ${seat == null ? styles.on : ""}`} onClick={() => setSeat(null)}>All roles</button>
            {seats.map((s) => (
              <button key={s} className={`${styles.seatChip} ${seat === s ? styles.on : ""}`} onClick={() => setSeat((cur) => (cur === s ? null : s))}>{s}</button>
            ))}
            {!MOCK_FORCED && filtered.length > 0 && (
              <a className={styles.seatChip} href={exportHref} style={{ marginLeft: "auto" }}
                 title="Download the complete audit record as JSONL, including prompts and responses">
                <DownloadSimple weight="bold" style={{ width: 11, verticalAlign: "-1px", marginRight: 4 }} /> Export audit
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
          <section className={styles.column} aria-label="Model calls">
            <div className={styles.columnHead}>
              <span>Model calls</span>
              <small>{filtered.length} recorded</small>
            </div>
            <div className={styles.list}>
            {listQ.isError && (
              <div className={styles.paneEmpty} role="alert">
                Model activity could not be loaded. Check the backend connection and try again.
              </div>
            )}
            {!listQ.isError && listQ.isLoading && <div className={styles.paneEmpty}>Loading model activity…</div>}
            {!listQ.isError && !listQ.isLoading && filtered.length === 0 && (
              <div className={styles.paneEmpty}>
                {MOCK_FORCED
                  ? "Model activity appears when a live build calls a model. This demo stream has no prompt payloads."
                  : search || seat
                    ? "No model calls match this filter."
                    : "No model calls yet. Start or open a build and they will appear here as they happen."}
              </div>
            )}
            {groups.map((g) => {
              const groupExt = g.rows.some((r) => r.zone === "EXTERNAL");
              return (
              <div key={g.seat} className={`${styles.group} ${groupExt ? styles.groupExt : ""}`}>
                <div className={styles.groupHead}>
                  <span className={styles.groupSeat}>{g.seat}</span>
                  {groupExt && <ZoneBadge zone="EXTERNAL" size="xs" />}
                  <span className={styles.groupModel}>{g.model}</span>
                  <span className={styles.groupCount}>{g.rows.length}×</span>
                </div>
                {SEAT_INFO[g.seat]?.purpose && (
                  <div className={styles.groupWhy}>{SEAT_INFO[g.seat]!.purpose}</div>
                )}
                {g.rows.map((t) => (
                  <button key={t.id} className={`${styles.row} ${activeSel === t.id ? styles.sel : ""}`} onClick={() => setSel(t.id)}>
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
                      <div className={styles.rowPrev}>{previewText(t.messages_preview ?? t.response_preview)}</div>
                    )}
                  </button>
                ))}
              </div>
              );
            })}
            </div>
          </section>

          <section className={styles.column} aria-label="Call details">
            <div className={styles.columnHead}>
              <span>Call details</span>
              <small>Input · boundary · output · cost</small>
            </div>
            <div className={styles.detail}>
            {activeSel ? (
              <TracePane
                id={activeSel}
                pos={selIdx >= 0 ? `${selIdx + 1} / ${visualRows.length}` : ""}
                onPrev={() => go(-1)}
                onNext={() => go(1)}
                hasPrev={selIdx > 0}
                hasNext={selIdx >= 0 && selIdx < visualRows.length - 1}
              />
            ) : (
              <div className={styles.detailEmpty}>
                <span className={styles.detailEmptyIcon}><Brain weight="fill" /></span>
                <span className={styles.detailEmptyTitle}>No model call selected</span>
                <p className={styles.detailEmptyHint}>
                  Choose a call to see its input, boundary handling, response, cost and latency.
                </p>
              </div>
            )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
