/**
 * Time-based replay player. Fetches the full ordered event dump for a scope
 * (09 §6), builds a real wall-clock timeline from the events' `ts`, and drives a
 * virtual clock over it — every event whose playback time has passed is folded,
 * through the same fold as the live cockpit. Scrubbing/seek is a clock jump: the
 * cursor (how many events to fold) is derived from the clock, not an action index.
 *
 * Dead air between events is clamped for pacing (see replayClock.GAP_CLAMP_MS) but
 * the displayed time axis stays real.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { MOCK_FORCED } from "../api/config";
import { KYC_EVENTS } from "../fixtures/kycJob";
import { normalizeEvent } from "../api/adapt";
import { foldEvents, type JobView } from "./jobStore";
import { buildTimeline, indexAtTime, realElapsedAtClock } from "./replayClock";
import type { NxEvent } from "../lib/events";

export type ReplaySpeed = 1 | 4 | 16;
const TICK_MS = 80; // clock resolution (~12fps thumb); speed multiplies clock rate

export interface UseReplay {
  view: JobView;
  loading: boolean;
  error: string | null;
  playing: boolean;
  speed: ReplaySpeed;
  clockMs: number; // virtual playback position (×1 ms)
  playbackEnd: number; // total playback ms — the scrubber's range
  elapsedRealMs: number; // real ms at the current clock (labels)
  totalRealMs: number; // real recorded duration
  startEpoch: number; // first-event epoch ms (header + wall-clock)
  hasTimeline: boolean;
  toggle: () => void;
  setSpeed: (s: ReplaySpeed) => void;
  seek: (ms: number) => void;
  restart: () => void;
  wallClockAt: (ms: number) => number; // epoch ms at a given playback clock (hover)
}

export function useReplay(scope: string): UseReplay {
  const [events, setEvents] = useState<NxEvent[]>([]);
  const [clockMs, setClockMs] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState<ReplaySpeed>(4);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setClockMs(0);
    setPlaying(true);

    // Mock mode has no backend — replay the bundled fixture (already NxEvent[]).
    if (MOCK_FORCED) {
      setEvents(KYC_EVENTS);
      setLoading(false);
      return;
    }

    api
      .replay(scope)
      .then((r) => {
        if (cancelled) return;
        const evs = (r.events ?? [])
          .map((e) => normalizeEvent(e as never))
          .filter((e): e is NxEvent => e != null);
        setEvents(evs);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError((e as Error).message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scope]);

  const tl = useMemo(() => buildTimeline(events), [events]);

  // advance the virtual clock while playing; the end-of-timeline watcher stops it
  useEffect(() => {
    if (!playing || tl.playbackEnd === 0) return;
    const h = setInterval(() => {
      setClockMs((c) => Math.min(tl.playbackEnd, c + TICK_MS * speed));
    }, TICK_MS);
    return () => clearInterval(h);
  }, [playing, speed, tl.playbackEnd]);

  useEffect(() => {
    if (playing && tl.playbackEnd > 0 && clockMs >= tl.playbackEnd) setPlaying(false);
  }, [playing, clockMs, tl.playbackEnd]);

  const cursor = indexAtTime(tl, clockMs);
  const view = useMemo(() => foldEvents(events.slice(0, cursor), scope), [events, cursor, scope]);

  const atEnd = tl.playbackEnd > 0 && clockMs >= tl.playbackEnd;
  const toggle = useCallback(() => {
    if (atEnd) {
      setClockMs(0);
      setPlaying(true);
    } else {
      setPlaying((p) => !p);
    }
  }, [atEnd]);

  const seek = useCallback(
    (ms: number) => {
      setPlaying(false);
      setClockMs(Math.max(0, Math.min(tl.playbackEnd, ms)));
    },
    [tl.playbackEnd],
  );

  const restart = useCallback(() => {
    setClockMs(0);
    setPlaying(true);
  }, []);

  const wallClockAt = useCallback((ms: number) => tl.startEpoch + realElapsedAtClock(tl, ms), [tl]);

  return {
    view,
    loading,
    error,
    playing,
    speed,
    clockMs,
    playbackEnd: tl.playbackEnd,
    elapsedRealMs: realElapsedAtClock(tl, clockMs),
    totalRealMs: tl.realDuration,
    startEpoch: tl.startEpoch,
    hasTimeline: events.length > 0,
    toggle,
    setSpeed,
    seek,
    restart,
    wallClockAt,
  };
}
