/** Replays a fixture event stream honoring relative timestamps, at a speed multiplier. */
import type { NxEvent } from "../lib/events";

export interface PlayHandle {
  stop: () => void;
}

export function playEvents(
  events: NxEvent[],
  onEvent: (ev: NxEvent) => void,
  opts: { speed?: number; onDone?: () => void; minGap?: number; maxGap?: number } = {}
): PlayHandle {
  const speed = opts.speed ?? 16;
  const minGap = opts.minGap ?? 8;
  const maxGap = opts.maxGap ?? 220;
  let i = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const t0 = events.length ? Date.parse(events[0].ts) : 0;

  const step = () => {
    if (stopped || i >= events.length) {
      if (i >= events.length) opts.onDone?.();
      return;
    }
    const ev = events[i];
    onEvent(ev);
    i += 1;
    if (i >= events.length) {
      opts.onDone?.();
      return;
    }
    const gapReal = Date.parse(events[i].ts) - Date.parse(ev.ts);
    const gap = Math.min(maxGap, Math.max(minGap, gapReal / speed));
    timer = setTimeout(step, gap);
  };

  // small initial delay so the mount paints before events fire
  timer = setTimeout(step, 60);
  void t0;

  return {
    stop: () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    },
  };
}
