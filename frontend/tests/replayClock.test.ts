/**
 * Standalone self-check for the pure replay-clock math (no test framework — run
 * with `node tests/replayClock.test.ts` from frontend/; Node strips the types).
 * Lives outside src/ so tsc (vite/client types only) doesn't try to compile it.
 */
import assert from "node:assert/strict";
import { buildTimeline, indexAtTime, realElapsedAtClock, GAP_CLAMP_MS } from "../src/store/replayClock.ts";
import type { NxEvent } from "../src/lib/events.ts";

const ev = (seq: number, sec: number): NxEvent =>
  ({ seq, ts: new Date(sec * 1000).toISOString(), scope: "job:t", type: "meter.tick", payload: {} } as unknown as NxEvent);

// events at 0s, 1s, 60s, 61s with a 3s gap clamp
const events = [ev(1, 0), ev(2, 1), ev(3, 60), ev(4, 61)];
const tl = buildTimeline(events, GAP_CLAMP_MS);

// gaps 1s,59s,1s clamp to 1s,3s,1s -> playbackEnd 5s; real axis stays 61s
assert.equal(tl.playbackEnd, 5000, `playbackEnd ${tl.playbackEnd}`);
assert.equal(tl.realDuration, 61000, `realDuration ${tl.realDuration}`);
assert.deepEqual(tl.playAt, [0, 1000, 4000, 5000]);

// seek(0) applies none, seek(tEnd) applies all
assert.equal(indexAtTime(tl, 0), 0, "seek(0) -> 0");
assert.equal(indexAtTime(tl, tl.playbackEnd), 4, "seek(tEnd) -> all");
assert.equal(indexAtTime(tl, 1000), 1, "at 1s -> event 0 only");
assert.equal(indexAtTime(tl, 4000), 2, "at 4s -> two events");

// real-time readout is honest: mid-clamped-gap interpolates toward the real 60s mark
assert.equal(realElapsedAtClock(tl, 0), 0);
assert.equal(realElapsedAtClock(tl, tl.playbackEnd), 61000);
assert.equal(realElapsedAtClock(tl, 2500), 1000 + 0.5 * (60000 - 1000)); // halfway through the clamped big gap

// degenerate: all same/invalid ts -> instant timeline, everything folds at once
const flat = buildTimeline([ev(1, 5), ev(2, 5), ev(3, 5)]);
assert.equal(flat.playbackEnd, 0, "flat timeline instant");
assert.equal(indexAtTime(flat, 0), 3, "flat -> all events at t0");

// empty is safe
assert.equal(buildTimeline([]).playbackEnd, 0);
assert.equal(indexAtTime(buildTimeline([]), 0), 0);

console.log("replayClock: all assertions passed");
