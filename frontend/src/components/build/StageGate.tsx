import { useState } from "react";
import { Receipt, CheckCircle, Prohibit, ArrowRight } from "@phosphor-icons/react";
import { Panel } from "./Panel";
import { api } from "../../api/client";
import { useDemoToken } from "../../api/useDemoToken";
import { usd } from "../../lib/format";
import type { JobView } from "../../store/jobStore";

/** The two human gates a live job can park at: spec confirmation (stage 0)
 *  and quote approval (stage 3). Renders nothing when the job is moving. */
export function StageGate({ view, jobId }: { view: JobView; jobId?: string }) {
  const unlocked = useDemoToken();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null); // optimistic label
  const [err, setErr] = useState<string | null>(null);

  const atQuote = view.status === "quoted";
  const atSpec = view.status === "intake" && view.stage === 0 && !!view.intake.specSummary;
  if (!jobId || (!atQuote && !atSpec) || view.status === "aborted") return null;

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      setDone(label); // the stream carries the real transition
    } catch (e) {
      const status = (e as { status?: number }).status;
      setErr(status === 401 ? "Presenter token required." : status === 409 ? "Not allowed in this state." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <Panel title={atQuote ? "Quote" : "Spec"} icon={Receipt} status="ok" tag="gate">
        <div className="bv-clarify-sent">
          <CheckCircle weight="fill" /> {done} — the run continues on the stream.
        </div>
      </Panel>
    );
  }

  if (atQuote) {
    return (
      <Panel title="Quote — your approval gate" icon={Receipt} status="active" tag="stage 3 · parked">
        {view.quote.lines.length > 0 && (
          <div className="bv-gate-lines">
            {view.quote.lines.map((l, i) => (
              <div className="bv-gate-line" key={i}>
                <span className="bv-gate-label">{l.label}</span>
                <span className="bv-gate-detail">{l.detail}</span>
                <span className="bv-gate-amt tnum">{usd(l.amount_usd)}</span>
              </div>
            ))}
          </div>
        )}
        <div className="bv-gate-total">
          Estimated {usd(view.quote.low ?? 0)}–{usd(view.quote.high ?? 0)} · nothing is spent until you approve.
        </div>
        <div className="bv-clarify-foot">
          <button className="bv-clarify-submit" disabled={!unlocked || busy} onClick={() => act("Quote approved", () => api.approveQuote(jobId))}>
            <CheckCircle weight="fill" style={{ width: 14, height: 14 }} /> Approve quote
          </button>
          <button className="bv-gate-abort" disabled={!unlocked || busy} onClick={() => act("Job aborted", () => api.abort(jobId))}>
            <Prohibit weight="bold" style={{ width: 12, height: 12 }} /> Abort
          </button>
          {!unlocked && <span className="bv-clarify-note">Presenter mode required.</span>}
        </div>
        {err && <p className="bv-clarify-note" style={{ color: "var(--danger)", marginTop: 8 }}>{err}</p>}
      </Panel>
    );
  }

  // parked at intake with a drafted spec: let the customer push it forward
  return (
    <Panel title="Spec drafted — ready when you are" icon={Receipt} status="active" tag="stage 0">
      <p className="bv-clarify-lead">{view.intake.specSummary}</p>
      <div className="bv-clarify-foot">
        <button
          className="bv-clarify-submit"
          disabled={!unlocked || busy}
          onClick={() => act("Spec confirmed", () => api.confirmSpec(jobId, view.mode ?? view.intake.classification?.mode ?? "build"))}
        >
          <ArrowRight weight="bold" style={{ width: 14, height: 14 }} /> Confirm spec & start planning
        </button>
        {!unlocked && <span className="bv-clarify-note">Presenter mode required.</span>}
      </div>
      {err && <p className="bv-clarify-note" style={{ color: "var(--danger)", marginTop: 8 }}>{err}</p>}
    </Panel>
  );
}
