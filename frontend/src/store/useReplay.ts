/**
 * Replay player. Fetches the full ordered event dump for a scope (09 §6),
 * normalizes it through the same adapter as the live stream, and folds
 * events.slice(0, cursor) so scrubbing/seek is free — identical fold, identical
 * panels as the live cockpit.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { normalizeEvent } from "../api/adapt";
import { foldEvents, type JobView } from "./jobStore";
import type { NxEvent } from "../lib/events";

export type ReplaySpeed = 1 | 4 | 16;
const BASE_MS = 200; // per-event pacing at ×1

export interface UseReplay {
  view: JobView;
  events: NxEvent[];
  cursor: number;
  playing: boolean;
  speed: ReplaySpeed;
  loading: boolean;
  error: string | null;
  toggle: () => void;
  setSpeed: (s: ReplaySpeed) => void;
  seek: (n: number) => void;
  restart: () => void;
}

export function useReplay(scope: string): UseReplay {
  const [events, setEvents] = useState<NxEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState<ReplaySpeed>(4);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCursor(0);
    setPlaying(true);
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

  // advance the cursor while playing
  useEffect(() => {
    if (!playing || loading || events.length === 0) return;
    if (cursor >= events.length) {
      setPlaying(false);
      return;
    }
    timer.current = setTimeout(() => setCursor((c) => Math.min(events.length, c + 1)), BASE_MS / speed);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [playing, loading, cursor, events.length, speed]);

  const view = useMemo(() => foldEvents(events.slice(0, cursor), scope), [events, cursor, scope]);

  return {
    view,
    events,
    cursor,
    playing,
    speed,
    loading,
    error,
    toggle: () => setPlaying((p) => (cursor >= events.length ? (setCursor(0), true) : !p)),
    setSpeed,
    seek: (n) => {
      setPlaying(false);
      setCursor(Math.max(0, Math.min(events.length, n)));
    },
    restart: () => {
      setCursor(0);
      setPlaying(true);
    },
  };
}
