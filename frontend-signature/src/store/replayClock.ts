/**
 * Pure timeline math for the replay player — no React, no DOM, so it's testable
 * on its own (see replayClock.test.ts).
 *
 * A recorded job replays on its real wall-clock timeline. From each event's `ts`
 * we build two parallel, monotonic arrays:
 *   realAt[i] — real ms since the first event (the TRUE time axis; never clamped)
 *   playAt[i] — playback ms at ×1, with dead air between events capped so a long
 *               idle stretch doesn't stall the demo
 * The virtual clock runs over playAt (0 … playbackEnd); realAt drives the labels.
 */
import type { NxEvent } from "../lib/events";

// ponytail: gap clamp — cap any inter-event gap to this many ms of ×1 playback.
// Real time is preserved in realAt (the axis stays honest); only the pace of
// playback through idle stretches is compressed.
export const GAP_CLAMP_MS = 3000;

export interface Timeline {
  playAt: number[]; // playback offset (ms, ×1) when event i appears; playAt[0] = 0
  realAt: number[]; // real offset (ms) since the first event when event i ran
  playbackEnd: number; // total ×1 playback ms (playAt of the last event)
  realDuration: number; // total real ms (realAt of the last event)
  startEpoch: number; // epoch ms of the first event (for wall-clock labels)
}

const EMPTY: Timeline = { playAt: [], realAt: [], playbackEnd: 0, realDuration: 0, startEpoch: 0 };

/**
 * Build the timeline from events in their authoritative (seq) order. `ts` is
 * used only for timing — order is never changed. Missing/unparseable/out-of-order
 * timestamps clamp to the previous event (gap 0) so realAt stays monotonic and
 * identical timestamps replay together.
 */
export function buildTimeline(events: NxEvent[], gapClampMs = GAP_CLAMP_MS): Timeline {
  const n = events.length;
  if (n === 0) return EMPTY;

  const startEpoch = parseTs(events[0].ts, Date.now());
  const realAt: number[] = new Array(n);
  const playAt: number[] = new Array(n);
  realAt[0] = 0;
  playAt[0] = 0;
  let prevEpoch = startEpoch;

  for (let i = 1; i < n; i++) {
    const epoch = Math.max(parseTs(events[i].ts, prevEpoch), prevEpoch);
    realAt[i] = epoch - startEpoch;
    const gap = realAt[i] - realAt[i - 1];
    playAt[i] = playAt[i - 1] + Math.min(gap, gapClampMs);
    prevEpoch = epoch;
  }

  return { playAt, realAt, playbackEnd: playAt[n - 1], realDuration: realAt[n - 1], startEpoch };
}

function parseTs(ts: string | undefined, fallback: number): number {
  const v = ts ? Date.parse(ts) : NaN;
  return Number.isNaN(v) ? fallback : v;
}

/**
 * Cursor for a virtual playback clock: how many events to fold (events.slice(0, n)).
 * Uses a strict "<" so seek(0) applies none, and snaps to all at/after the end so
 * seek(playbackEnd) applies every event. Ties (same playAt) resolve together.
 */
export function indexAtTime(tl: Timeline, clockMs: number): number {
  const { playAt, playbackEnd } = tl;
  if (playAt.length === 0) return 0;
  if (clockMs >= playbackEnd) return playAt.length;
  // lower_bound: first index with playAt[i] >= clockMs == count of playAt[i] < clockMs
  let lo = 0;
  let hi = playAt.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (playAt[mid] < clockMs) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * Real elapsed ms at a given playback clock, interpolated within the current gap
 * so the time readout tracks the scrubber smoothly (fast through clamped dead air).
 */
export function realElapsedAtClock(tl: Timeline, clockMs: number): number {
  const { playAt, realAt, playbackEnd, realDuration } = tl;
  if (playAt.length === 0 || clockMs <= 0) return 0;
  if (clockMs >= playbackEnd) return realDuration;
  // i = last event whose playAt <= clockMs
  let lo = 0;
  let hi = playAt.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (playAt[mid] <= clockMs) lo = mid + 1;
    else hi = mid;
  }
  const i = lo - 1;
  const span = playAt[i + 1] - playAt[i];
  const frac = span > 0 ? (clockMs - playAt[i]) / span : 0;
  return realAt[i] + frac * (realAt[i + 1] - realAt[i]);
}
