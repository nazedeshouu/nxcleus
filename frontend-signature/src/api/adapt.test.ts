// @vitest-environment node
import { describe, expect, it } from "vitest";
import { normalizeEvent } from "./adapt";

const baseEvent = {
  seq: 1,
  ts: "2026-07-19T00:00:00Z",
  scope: "run:run_test",
};

describe("normalizeEvent verification truth", () => {
  it("preserves a no_actual oracle verdict", () => {
    const event = normalizeEvent({
      ...baseEvent,
      type: "qa.oracle_check",
      payload: { vector: "V1", verdict: "no_actual", model: "oracle" },
    });

    expect(event).not.toBeNull();
    if (!event || event.type !== "qa.oracle_check") throw new Error("unexpected event type");
    expect(event.payload.verdict).toBe("no_actual");
  });

  it("does not report an unverified completed run as done", () => {
    const event = normalizeEvent({
      ...baseEvent,
      type: "run.completed",
      payload: { status: "done", verification: "unverified", reasons: ["tests unavailable"] },
    });

    expect(event).not.toBeNull();
    if (!event || event.type !== "run.completed") throw new Error("unexpected event type");
    expect(event.payload).toMatchObject({
      status: "unverified",
      verification: "unverified",
      reasons: ["tests unavailable"],
    });
  });

  it("makes a failed terminal status override a contradictory passed verification", () => {
    const event = normalizeEvent({
      ...baseEvent,
      type: "run.finished",
      payload: { status: "failed", verification: "passed", reasons: ["entrypoint failed"] },
    });

    expect(event).not.toBeNull();
    if (!event || event.type !== "run.finished") throw new Error("unexpected event type");
    expect(event.payload).toMatchObject({
      status: "failed",
      verification: "failed",
      reasons: ["entrypoint failed"],
    });
  });

  it("keeps an unverified QA completion out of the passed path", () => {
    const event = normalizeEvent({
      ...baseEvent,
      type: "qa.completed",
      payload: {
        verification: "unverified",
        reasons: ["staging deployment was unavailable"],
        demo_override: true,
      },
    });

    expect(event).not.toBeNull();
    if (!event || event.type !== "qa.completed") throw new Error("unexpected event type");
    expect(event.payload).toEqual({
      verification: "unverified",
      reasons: ["staging deployment was unavailable"],
      demo_override: true,
    });
  });

  it("preserves unverified worker test evidence", () => {
    const event = normalizeEvent({
      ...baseEvent,
      type: "task.tests",
      payload: {
        module: "extractor",
        passed: 0,
        failed: 0,
        total: 0,
        verification: "unverified",
        sandboxed: false,
        reason: "Docker unavailable",
      },
    });

    expect(event).not.toBeNull();
    if (!event || event.type !== "task.tests") throw new Error("unexpected event type");
    expect(event.payload).toMatchObject({
      verification: "unverified",
      sandboxed: false,
      reason: "Docker unavailable",
    });
  });

  it("does not turn an unverified zero-test consolidation green", () => {
    const event = normalizeEvent({
      ...baseEvent,
      type: "consolidate.completed",
      payload: { passed: 0, total: 0, verification: "unverified", sandboxed: false },
    });

    expect(event).not.toBeNull();
    if (!event || event.type !== "consolidate.completed") throw new Error("unexpected event type");
    expect(event.payload).toEqual({
      passed: 0,
      total: 0,
      verification: "unverified",
      sandboxed: false,
    });
  });
});
