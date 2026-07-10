import { Scroll, ArrowsLeftRight, Check, Link as LinkIcon, Wrench, Prohibit } from "@phosphor-icons/react";
import { Panel } from "./Panel";
import type { JobView } from "../../store/jobStore";

export function AuditRail({ view }: { view: JobView }) {
  const { amendments, consults, scopeViolations, deferredConsults } = view.certify;
  const active = view.stage === 2 || view.stage === 4;

  return (
    <Panel
      title="Amendment log"
      icon={Scroll}
      status={active ? "active" : amendments.length ? "ok" : "pending"}
      tag={amendments.length ? `${amendments.length} · hash-chained` : "audit"}
    >
      {amendments.length === 0 && consults.length === 0 && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          Local patches and frontier consults appear here as a signed, hash-chained feed.
        </p>
      )}

      {amendments.map((a) => (
        <div className={`bv-amend ${a.origin}`} key={a.id}>
          <div className="bv-amend-top">
            <span className="bv-amend-origin">{a.origin}</span>
            {a.region && <span className="bv-amend-region">→ {a.region}</span>}
          </div>
          <p className="bv-amend-summary">{a.summary}</p>
          <div className="bv-amend-hash">
            <LinkIcon weight="bold" style={{ width: 11, height: 11 }} />
            <span>{a.prev_hash.slice(0, 6)}</span>→<b>{a.hash}</b>
          </div>
        </div>
      ))}

      {consults.map((c) => (
        <div className="bv-consult" key={c.id}>
          <div className="bv-consult-top">
            <ArrowsLeftRight weight="bold" /> Frontier consult · round {c.round}
            {c.repaired && (
              <span className="bv-consult-repaired" title="Scope-lock was auto-repaired to a valid region">
                <Wrench weight="bold" style={{ width: 9, verticalAlign: "-1px" }} /> scope repaired
              </span>
            )}
          </div>
          <p className="bv-consult-scope">{c.scope}</p>
          <div className="bv-consult-receipt">
            <span style={{ fontSize: "0.56rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              sanitized · {c.brief_tokens} tok
            </span>
            {c.rules_applied.map((r) => (
              <span className="bv-consult-rule" key={r}>{r}</span>
            ))}
          </div>
          {c.resolution && (
            <p className="bv-consult-res">
              <Check weight="bold" /> {c.resolution}
            </p>
          )}
        </div>
      ))}

      {scopeViolations.map((s) => (
        <div className="bv-scopeviol" key={s.seq}>
          <div className="bv-scopeviol-top">
            <Prohibit weight="bold" /> Out-of-scope edit rejected
          </div>
          <p>
            {s.region && <>Region <b>{s.region}</b>. </>}
            {s.detail ?? "A re-plan tried to touch a region outside the certified scope lock."}
          </p>
        </div>
      ))}

      {deferredConsults != null && deferredConsults > 0 && (
        <div className="bv-deferred" title="Consults dropped at the per-round soft cap">
          <ArrowsLeftRight weight="bold" style={{ width: 11 }} /> {deferredConsults} consult{deferredConsults === 1 ? "" : "s"} deferred (cap)
        </div>
      )}
    </Panel>
  );
}
