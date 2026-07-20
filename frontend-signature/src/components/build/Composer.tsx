import { useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Lightning, Lock, ShieldCheck, FileText, X, Database, Plus, CaretDown, CaretRight,
  UploadSimple, Table, FolderOpen, CheckCircle, Warning,
} from "@phosphor-icons/react";
import { api, type CompanySummary, type Dataset } from "../../api/client";
import { useDemoToken } from "../../api/useDemoToken";
import { usePublicConfig } from "../shell/usePublicConfig";
import { OriginBadge } from "../ui/OriginBadge";
import { compact } from "../../lib/format";
import styles from "./Composer.module.css";

export interface ComposerSubmit {
  request: string;
  title?: string;
  policy_text?: string;
  company?: string;
  sovereign: boolean;
}

interface Props {
  variant: "build" | "sandbox";
  /** sandbox: the fixed data source; its prompts + business values seed the chips */
  boundCompany?: CompanySummary;
  suggestions?: Array<{ prompt: string; value?: string; reasoning?: boolean }>;
  placeholder?: string;
  submitLabel: string;
  onSubmit: (p: ComposerSubmit) => Promise<void>;
}

type Policy = { name: string; text: string };

const POLICY_ACCEPT = ".txt,.md,.markdown,.pdf,.png,.jpg,.jpeg,.webp";
const isPolicyFile = (f: File) => /\.(txt|md|markdown|pdf|png|jpe?g|webp)$/i.test(f.name);
const isTextPolicy = (f: File) => /\.(txt|md|markdown)$/i.test(f.name);

function sourceCounts(c: CompanySummary): string {
  const tables = c.tables ?? [];
  const rows = tables.reduce((n, t) => n + (t.row_count ?? 0), 0);
  if (c.kind === "files") return `${tables.length || "—"} file${tables.length === 1 ? "" : "s"}`;
  if (!tables.length) return "dataset ready";
  return `${tables.length} table${tables.length === 1 ? "" : "s"} · ${compact(rows)} rows`;
}

export function Composer({ variant, boundCompany, suggestions, placeholder, submitLabel, onSubmit }: Props) {
  const unlocked = useDemoToken();
  const { config } = usePublicConfig();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [request, setRequest] = useState("");
  const [title, setTitle] = useState("");
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [sovereign, setSovereign] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // build variant lets you attach any registered source; sandbox is pre-bound
  const companiesQ = useQuery({
    queryKey: ["sb-companies"],
    queryFn: api.sandboxCompanies,
    enabled: variant === "build",
    retry: 0,
    staleTime: 60_000,
  });
  const companies = companiesQ.data?.companies ?? [];
  const selected = variant === "sandbox" ? boundCompany : companies.find((c) => c.id === sourceId);

  const attachPolicy = async (file: File | undefined) => {
    if (!file) return;
    if (isTextPolicy(file)) {
      setPolicy({ name: file.name, text: await file.text() });
      setPolicyOpen(true);
      return;
    }
    // PDF / image → server-side extraction into the same editable policy_text path
    setExtracting(true);
    setErr(null);
    try {
      const res = await api.extractPolicy(file);
      setPolicy({ name: file.name, text: res.text });
      setPolicyOpen(true);
    } catch (e) {
      const status = (e as { status?: number }).status;
      setErr(
        status === 401 ? "Sign in required to extract PDFs/images — or attach a .txt/.md."
          : status === 413 ? "That file is too large — the cap is 8 MB."
            : `Could not read that policy file: ${(e as Error).message}. A .txt/.md still works.`,
      );
    } finally {
      setExtracting(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void attachPolicy([...e.dataTransfer.files].find(isPolicyFile));
  };

  const submit = async () => {
    const text = request.trim();
    if (!text) return;
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({
        request: text,
        title: title.trim() || undefined,
        policy_text: policy?.text.trim() || undefined,
        company: selected?.id,
        sovereign,
      });
      // success navigates away; leave busy=true so the button stays disabled
    } catch (e) {
      const status = (e as { status?: number }).status;
      setErr(
        status === 401
          ? "Sign in required."
          : status === 429
            ? "At the sandbox budget or concurrency cap. Replay a completed run instead."
            : `Could not start: ${(e as Error).message}`,
      );
      setBusy(false);
    }
  };

  return (
    <div
      className={`${styles.composer} ${dragging ? styles.dragging : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
      onDrop={onDrop}
    >
      {dragging && (
        <div className={styles.dropVeil}>
          <FileText weight="regular" />
          Drop a policy to attach — .txt, .md, PDF, or an image
        </div>
      )}

      {config.fallback_serving && (
        <Link to="/config" className={styles.degraded}>
          <Warning weight="fill" />
          <span>Model serving is degraded — running on fallback. <strong>Bring your own key</strong> to keep every seat live.</span>
        </Link>
      )}

      {variant === "build" && (
        <input
          className={styles.titleField}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Untitled process"
          aria-label="Process title"
        />
      )}

      {suggestions && suggestions.length > 0 && (
        <div className={styles.chips}>
          {suggestions.map((s) => (
            <button
              key={s.prompt}
              type="button"
              className={styles.chip}
              onClick={() => setRequest(s.prompt)}
              title={s.value}
            >
              <span className={styles.chipText}>
                {s.reasoning && <span className={styles.reason}>reasoning</span>}
                {s.prompt}
              </span>
              {s.value && <span className={styles.chipValue}>{s.value}</span>}
            </button>
          ))}
        </div>
      )}

      <textarea
        className={styles.textarea}
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        placeholder={placeholder ?? "Describe the process you need. Every month, flag duplicate claims and coverage breaches; the committee gets a case file per flagged entity and a CSV for recovery."}
        rows={variant === "sandbox" ? 3 : 4}
      />

      {/* inline attachment sections — bordered sub-cards, not pills */}
      {(policy || selected) && (
        <div className={styles.sections}>
          {policy && (
            <section className={styles.section}>
              <header className={styles.sectionHead}>
                <button className={styles.sectionToggle} type="button" onClick={() => setPolicyOpen((o) => !o)}>
                  {policyOpen ? <CaretDown weight="bold" /> : <CaretRight weight="bold" />}
                  <FileText weight="regular" className={styles.sectionIcon} />
                  <span className={styles.sectionName}>Policy · {policy.name}</span>
                </button>
                <span className={styles.sectionMeta}>{policy.text.length.toLocaleString()} chars</span>
                <button className={styles.sectionRemove} type="button" onClick={() => setPolicy(null)} aria-label="Remove policy">
                  <X weight="bold" />
                </button>
              </header>
              {policyOpen ? (
                <textarea
                  className={styles.policyText}
                  value={policy.text}
                  onChange={(e) => setPolicy({ ...policy, text: e.target.value })}
                  rows={5}
                />
              ) : (
                <p className={styles.sectionPreview}>{policy.text.slice(0, 160)}{policy.text.length > 160 ? "…" : ""}</p>
              )}
            </section>
          )}

          {selected && (
            <section className={styles.section}>
              <header className={styles.sectionHead}>
                <Database weight="regular" className={styles.sectionIcon} />
                <span className={styles.sectionName}>{selected.name}</span>
                <OriginBadge origin={selected.origin ?? "builtin"} size="xs" />
                <span className={styles.sectionMeta}>{sourceCounts(selected)}</span>
                {variant === "build" && (
                  <button className={styles.sectionRemove} type="button" onClick={() => setSourceId(null)} aria-label="Remove data source">
                    <X weight="bold" />
                  </button>
                )}
              </header>
            </section>
          )}
        </div>
      )}

      {/* footer toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.tools}>
          {!policy && (
            <button className={styles.tool} type="button" onClick={() => fileRef.current?.click()} disabled={extracting}>
              <FileText weight="regular" /> {extracting ? "Extracting…" : "Attach policy"}
            </button>
          )}
          {variant === "build" && (
            <div className={styles.picker}>
              <button className={styles.tool} type="button" onClick={() => setMenuOpen((o) => !o)}>
                <Database weight="regular" /> {selected ? "Change data" : "Data source"}
              </button>
              {menuOpen && (
                <>
                  <div className={styles.menuScrim} onClick={() => setMenuOpen(false)} />
                  <div className={styles.menu} role="menu">
                    <div className={styles.menuLabel}>Attach a data source</div>
                    {companies.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={styles.menuItem}
                        onClick={() => { setSourceId(c.id); setMenuOpen(false); }}
                      >
                        <span className={styles.menuName}>{c.name}</span>
                        <OriginBadge origin={c.origin ?? "builtin"} size="xs" />
                      </button>
                    ))}
                    <button
                      type="button"
                      className={`${styles.menuItem} ${styles.menuAdd}`}
                      onClick={() => { setMenuOpen(false); setAddOpen(true); }}
                    >
                      <Plus weight="bold" /> Add a new data source
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
          {variant === "build" && (
            <label className={`${styles.tool} ${sovereign ? styles.on : ""}`} title="Zero external calls — even the sanitized planner brief stays inside">
              <input type="checkbox" checked={sovereign} onChange={(e) => setSovereign(e.target.checked)} hidden />
              <ShieldCheck weight={sovereign ? "fill" : "regular"} /> Sovereign
            </label>
          )}
        </div>

        <button className={styles.go} disabled={busy || !request.trim()} onClick={submit} title={unlocked ? "" : "Sign in required"}>
          {unlocked ? <Lightning weight="fill" /> : <Lock weight="regular" />} {busy ? "Starting…" : submitLabel}
        </button>
      </div>

      <input ref={fileRef} type="file" accept={POLICY_ACCEPT} hidden onChange={(e) => { void attachPolicy(e.target.files?.[0]); e.target.value = ""; }} />

      {err && <div className={styles.err}>{err}</div>}

      <div className={styles.boundary}>
        <ShieldCheck weight="fill" />
        <span>
          {variant === "sandbox" && boundCompany
            ? `Your data stays in ${boundCompany.name}'s zone. Only a sanitized brief — no names, no account numbers — ever crosses to the frontier planner.`
            : "Raw data stays inside the walls. Only a sanitized brief — no names, no identifiers — ever crosses to the frontier planner."}
        </span>
      </div>

      {addOpen && (
        <AddDataSource
          onClose={() => setAddOpen(false)}
          onAdded={(d) => { void qc.invalidateQueries({ queryKey: ["sb-companies"] }); setSourceId(d.id); setAddOpen(false); }}
        />
      )}
    </div>
  );
}

/* ---------- Add data source modal — upload / connect / codebase ---------- */

type Tab = "upload" | "connect" | "codebase";

function AddDataSource({ onClose, onAdded }: { onClose: () => void; onAdded: (d: Dataset) => void }) {
  const unlocked = useDemoToken();
  const [tab, setTab] = useState<Tab>("upload");
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [path, setPath] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<Dataset | null>(null);

  const run = async (fn: () => Promise<Dataset>) => {
    setBusy(true);
    setErr(null);
    try {
      const d = await fn();
      setDone(d);
      setTimeout(() => onAdded(d), 900); // let the confirmation land before selecting
    } catch (e) {
      const status = (e as { status?: number }).status;
      setErr(status === 401 ? "Sign in required." : `Could not register: ${(e as Error).message}`);
      setBusy(false);
    }
  };

  const canSubmit =
    tab === "upload" ? files.length > 0 : tab === "connect" ? !!url.trim() : !!(path.trim() || gitUrl.trim());

  return (
    <>
      <div className={styles.modalScrim} onClick={onClose} />
      <div className={styles.modal} role="dialog" aria-label="Add data source">
        <header className={styles.modalHead}>
          <h3 className={styles.modalTitle}>Add a data source</h3>
          <button className={styles.sectionRemove} onClick={onClose} aria-label="Close"><X weight="bold" /></button>
        </header>

        {done ? (
          <div className={styles.modalDone}>
            <CheckCircle weight="fill" />
            <div className={styles.modalDoneTitle}>{done.name} registered</div>
            <div className={styles.modalDoneMeta}>
              {done.kind === "files"
                ? `${(done.meta?.files as number) ?? done.tables.length} files indexed`
                : done.tables.length
                  ? `${done.tables.length} tables · ${compact(done.tables.reduce((n, t) => n + (t.rows ?? 0), 0))} rows`
                  : "ready"}
            </div>
            <div className={styles.modalDoneTables}>
              {done.tables.slice(0, 8).map((t) => (
                <span key={t.name} className={styles.modalTable}>{t.name}{t.rows ? ` · ${compact(t.rows)}` : ""}</span>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className={styles.tabs}>
              {(["upload", "connect", "codebase"] as Tab[]).map((t) => (
                <button key={t} className={`${styles.tab} ${tab === t ? styles.tabOn : ""}`} onClick={() => setTab(t)}>
                  {t === "upload" ? <UploadSimple weight="bold" /> : t === "connect" ? <Table weight="bold" /> : <FolderOpen weight="bold" />}
                  {t === "upload" ? "Upload files" : t === "connect" ? "Connect a DB" : "Codebase"}
                </button>
              ))}
            </div>

            <div className={styles.modalBody}>
              {tab === "upload" && (
                <>
                  <label className={styles.dropZone}>
                    <input type="file" accept=".db,.sqlite,.sqlite3,.csv" multiple hidden onChange={(e) => setFiles([...(e.target.files ?? [])])} />
                    <UploadSimple weight="regular" />
                    <span>{files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Choose .db / .sqlite / .csv files"}</span>
                    {files.length > 0 && <span className={styles.dropList}>{files.map((f) => f.name).join(", ")}</span>}
                  </label>
                  <input className={styles.modalInput} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" />
                </>
              )}
              {tab === "connect" && (
                <>
                  <input className={styles.modalInput} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="postgres://user:pass@host:5432/db  or  mysql://…" />
                  <input className={styles.modalInput} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" />
                  <p className={styles.modalNote}>A read-only snapshot is copied inside the walls — the live database is never queried during a run.</p>
                </>
              )}
              {tab === "codebase" && (
                <>
                  <input className={styles.modalInput} value={path} onChange={(e) => setPath(e.target.value)} placeholder="Local path  /srv/app" />
                  <div className={styles.modalOr}>or</div>
                  <input className={styles.modalInput} value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} placeholder="Git URL  https://github.com/org/repo" />
                  <input className={styles.modalInput} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" />
                </>
              )}
              {err && <div className={styles.err}>{err}</div>}
            </div>

            <footer className={styles.modalFoot}>
              {unlocked ? (
                <button
                  className={styles.go}
                  disabled={busy || !canSubmit}
                  onClick={() =>
                    run(() =>
                      tab === "upload"
                        ? api.addDataset(files, { name: name.trim() || undefined })
                        : tab === "connect"
                          ? api.connectDataset({ url: url.trim(), name: name.trim() || undefined })
                          : api.codebaseDataset({ path: path.trim() || undefined, git_url: gitUrl.trim() || undefined, name: name.trim() || undefined }),
                    )
                  }
                >
                  {busy ? "Registering…" : "Register source"}
                </button>
              ) : (
                <span className={styles.lockedNote}><Lock weight="regular" /> Sign in to register a data source.</span>
              )}
            </footer>
          </>
        )}
      </div>
    </>
  );
}
