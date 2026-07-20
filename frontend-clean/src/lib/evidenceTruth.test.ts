// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  countEvidenceState,
  deliveryNodeStatus,
  runNodeStatus,
  taskNodeStatus,
} from "./evidenceTruth";
import type { JobView, RunViewState, TaskState } from "../store/jobStore";

describe("evidence-driven UI states", () => {
  it("never treats a zero-test or unverified consolidation as passed", () => {
    expect(countEvidenceState({ passed: 0, failed: 0, total: 0, verification: "passed" }))
      .toBe("unverified");
    expect(countEvidenceState({ passed: 0, failed: 0, total: 0, verification: "unverified" }))
      .toBe("unverified");
  });

  it("keeps completed workers amber without passing test evidence", () => {
    const task = {
      module: "extractor", backend: "local:test", seat: "coder", zone: "LOCAL", wave: 1,
      why: "test", output: "", status: "completed",
      tests: { passed: 0, failed: 0, total: 0, verification: "unverified", sandboxed: false, reason: "Docker unavailable" },
    } satisfies TaskState;
    expect(taskNodeStatus(task)).toBe("unverified");
  });

  it("maps failed and unverified terminal runs without a green fallback", () => {
    const base = {
      units: 4, done: 4, flagged: 0, cost_usd: null, gpu_seconds: null,
      reasons: [], demo: false, spotchecks: [],
    } satisfies Omit<RunViewState, "status" | "verification">;
    expect(runNodeStatus({ ...base, status: "failed", verification: "failed" })).toBe("failed");
    expect(runNodeStatus({ ...base, status: "unverified", verification: "unverified" }))
      .toBe("unverified");
  });

  it("keeps unverified delivery amber in the run map", () => {
    const delivery = {
      process_id: "proc_1", version: 1,
      package: { plan: true, docs: true, qa_report: true, tests: 0 },
      verification: "unverified", verification_reasons: ["tests unavailable"],
      demo_override: true, delivery_label: "UNVERIFIED DEMO",
    } satisfies NonNullable<JobView["delivery"]>;
    expect(deliveryNodeStatus(delivery)).toBe("unverified");
  });
});
