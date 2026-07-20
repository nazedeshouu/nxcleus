import type { JobView, RunViewState, TaskState } from "../store/jobStore";
import type { RunVerification } from "./events";

export type EvidenceState = "passed" | "failed" | "unverified";
export type EvidenceNodeStatus = "running" | "done" | "failed" | "unverified";

export interface CountEvidence {
  passed: number;
  failed: number;
  total: number;
  verification: RunVerification;
}

export function countEvidenceState(evidence: CountEvidence): EvidenceState {
  if (evidence.verification === "failed" || evidence.failed > 0) return "failed";
  if (
    evidence.verification === "passed"
    && evidence.total > 0
    && evidence.passed === evidence.total
  ) return "passed";
  return "unverified";
}

export function taskNodeStatus(task: TaskState): EvidenceNodeStatus {
  if (task.status === "failed") return "failed";
  if (task.tests && countEvidenceState(task.tests) === "failed") return "failed";
  if (task.status !== "completed") return "running";
  return task.tests && countEvidenceState(task.tests) === "passed" ? "done" : "unverified";
}

export function runNodeStatus(run: RunViewState): EvidenceNodeStatus {
  if (run.status === "running") return "running";
  if (run.status === "failed" || run.verification === "failed") return "failed";
  return run.status === "done" && run.verification === "passed" ? "done" : "unverified";
}

export function deliveryNodeStatus(
  delivery: NonNullable<JobView["delivery"]>,
): Extract<EvidenceNodeStatus, "done" | "unverified"> {
  return delivery.verification === "passed" ? "done" : "unverified";
}
