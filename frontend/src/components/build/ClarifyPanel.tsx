import { useState, type CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChatsCircle, PaperPlaneRight, CheckCircle } from "@phosphor-icons/react";
import { Panel } from "./Panel";
import { api } from "../../api/client";
import { MOCK_FORCED } from "../../api/config";
import type { JobView } from "../../store/jobStore";
import type { ClarifyQuestion } from "../../lib/events";

const KINDS = ["delivery", "threshold", "population", "scope"];

/** The job payload may carry the pending questions under a few names. */
function extractQuestions(raw: Record<string, unknown> | undefined): ClarifyQuestion[] {
  if (!raw) return [];
  const spec = (raw.spec ?? {}) as Record<string, unknown>;
  const src = raw.clarifications ?? raw.questions ?? spec.clarifications ?? spec.questions;
  if (!Array.isArray(src)) return [];
  return (src as Array<Record<string, unknown>>).map((q, i) => ({
    id: typeof q.id === "string" ? q.id : `q${i}`,
    question: typeof q.question === "string" ? q.question : typeof q.text === "string" ? q.text : "",
    kind: (KINDS.includes(q.kind as string) ? q.kind : "scope") as ClarifyQuestion["kind"],
    options: Array.isArray(q.options) ? (q.options as string[]) : undefined,
    required: q.required !== false,
  }));
}

/** Intake Q&A: renders when the job parks in awaiting_input. Answer all,
 *  submit once, optimistically resume. */
export function ClarifyPanel({ view, jobId }: { view: JobView; jobId?: string }) {
  const fromEvents = view.clarifications?.questions ?? [];
  const awaiting = view.status === "awaiting_input" || (fromEvents.length > 0 && !view.clarifications?.answered);

  // fallback: parked job whose questions ride on the job payload, not the stream
  const jobQ = useQuery({
    queryKey: ["job-full", jobId],
    queryFn: () => api.getJobFull(jobId!),
    enabled: awaiting && fromEvents.length === 0 && !!jobId && !MOCK_FORCED,
    retry: 0,
  });
  const questions = fromEvents.length ? fromEvents : extractQuestions(jobQ.data);

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!awaiting && !sent) return null;
  if (!sent && questions.length === 0) return null;

  const missing = questions.filter((q) => q.required !== false && !(answers[q.id] ?? "").trim());

  const submit = async () => {
    if (!jobId || missing.length) return;
    setBusy(true);
    setErr(null);
    try {
      await api.answerJob(jobId, questions.map((q) => ({ id: q.id, answer: (answers[q.id] ?? "").trim() })));
      setSent(true); // optimistic: the stream carries the job back into intake
    } catch (e) {
      if ((e as { status?: number }).status === 409) {
        setSent(true); // 409 = no longer awaiting_input — the job already resumed
      } else {
        setErr(`Could not send the answers: ${(e as Error).message}`);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="A few decisions before we build" icon={ChatsCircle} status={sent ? "ok" : "active"} tag="intake · parked">
      {sent ? (
        <div className="bv-clarify-sent">
          <CheckCircle weight="fill" />
          Answers sent. Intake is resuming with your decisions baked in.
        </div>
      ) : (
        <>
          <p className="bv-clarify-lead">
            The platform paused before spending anything: these choices shape the plan, the quote, and the deliverables.
          </p>
          <div className="bv-clarify-cards">
            {questions.map((q, i) => (
              <div className="bv-clarify-card" key={q.id} style={{ "--i": i } as CSSProperties}>
                <div className="bv-clarify-top">
                  <span className={`bv-clarify-kind ${q.kind}`}>{q.kind}</span>
                  {q.required !== false && <span className="bv-clarify-req">required</span>}
                </div>
                <p className="bv-clarify-q">{q.question}</p>
                {q.options?.length ? (
                  <div className="bv-clarify-opts">
                    {q.options.map((o) => (
                      <button
                        key={o}
                        className={`bv-clarify-opt ${answers[q.id] === o ? "on" : ""}`}
                        onClick={() => setAnswers((a) => ({ ...a, [q.id]: o }))}
                      >
                        {o}
                      </button>
                    ))}
                  </div>
                ) : (
                  <input
                    className="bv-clarify-input"
                    value={answers[q.id] ?? ""}
                    onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                    placeholder="Type your answer"
                  />
                )}
              </div>
            ))}
          </div>
          <div className="bv-clarify-foot">
            <button className="bv-clarify-submit" disabled={!jobId || busy || missing.length > 0} onClick={submit}>
              <PaperPlaneRight weight="fill" style={{ width: 14, height: 14 }} />
              {busy ? "Sending…" : "Send answers & resume"}
            </button>
            <span className="bv-clarify-note">
              {!jobId
                ? "replay — answers disabled"
                : missing.length
                  ? `${missing.length} required answer${missing.length === 1 ? "" : "s"} left`
                  : "the run resumes the moment these land"}
            </span>
          </div>
          {err && <p className="bv-clarify-note" style={{ color: "var(--danger)", marginTop: 8 }}>{err}</p>}
        </>
      )}
    </Panel>
  );
}
