import { describe, expect, it } from "vitest";
import { buildTimeline, indexAtTime, realElapsedAtClock, GAP_CLAMP_MS } from "../src/store/replayClock.ts";
import type { NxEvent } from "../src/lib/events.ts";

const ev = (seq: number, sec: number): NxEvent =>
  ({ seq, ts: new Date(sec * 1000).toISOString(), scope: "job:t", type: "meter.tick", payload: {} } as unknown as NxEvent);

describe("replay clock", () => {
  it("clamps long gaps while preserving the honest real-time axis", () => {
    const events = [ev(1, 0), ev(2, 1), ev(3, 60), ev(4, 61)];
    const timeline = buildTimeline(events, GAP_CLAMP_MS);

    expect(timeline.playbackEnd).toBe(5000);
    expect(timeline.realDuration).toBe(61000);
    expect(timeline.playAt).toEqual([0, 1000, 4000, 5000]);
    expect(indexAtTime(timeline, 0)).toBe(0);
    expect(indexAtTime(timeline, timeline.playbackEnd)).toBe(4);
    expect(indexAtTime(timeline, 1000)).toBe(1);
    expect(indexAtTime(timeline, 4000)).toBe(2);
    expect(realElapsedAtClock(timeline, 0)).toBe(0);
    expect(realElapsedAtClock(timeline, timeline.playbackEnd)).toBe(61000);
    expect(realElapsedAtClock(timeline, 2500)).toBe(1000 + 0.5 * (60000 - 1000));
  });

  it("handles flat and empty timelines", () => {
    const flat = buildTimeline([ev(1, 5), ev(2, 5), ev(3, 5)]);
    expect(flat.playbackEnd).toBe(0);
    expect(indexAtTime(flat, 0)).toBe(3);
    expect(buildTimeline([]).playbackEnd).toBe(0);
    expect(indexAtTime(buildTimeline([]), 0)).toBe(0);
  });
});
