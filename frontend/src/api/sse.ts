/**
 * SSE wrapper for 06 §2/§3. Native EventSource gives us `Last-Event-ID` reconnect
 * resume for free (envelope `id:` == seq). `from_seq` opens replay-then-tail.
 * A watchdog tracks liveness (heartbeats arrive as `: heartbeat` comments the
 * browser hides, so we treat any message OR reconnect as proof of life).
 */
import type { NxEvent } from "../lib/events";

export type ConnState = "connecting" | "open" | "reconnecting" | "closed";

export interface StreamHandlers {
  onEvent: (ev: NxEvent) => void;
  onState?: (s: ConnState) => void;
}

export interface StreamHandle {
  close: () => void;
}

const HEARTBEAT_TIMEOUT = 25_000; // spec sends `: heartbeat` every 10s

export function openEventStream(path: string, handlers: StreamHandlers, fromSeq = 0): StreamHandle {
  let es: EventSource | null = null;
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  let closed = false;
  let lastSeq = fromSeq;

  const setState = (s: ConnState) => handlers.onState?.(s);

  const armWatchdog = () => {
    if (watchdog) clearTimeout(watchdog);
    watchdog = setTimeout(() => {
      // No traffic for too long: the browser will retry on its own, but signal it.
      setState("reconnecting");
    }, HEARTBEAT_TIMEOUT);
  };

  const connect = () => {
    if (closed) return;
    const sep = path.includes("?") ? "&" : "?";
    // On first connect use from_seq; native reconnect uses Last-Event-ID header,
    // but we also pin from_seq to lastSeq so a manual reconnect is deterministic.
    const url = `${path}${sep}from_seq=${lastSeq}`;
    es = new EventSource(url);
    setState("connecting");

    es.onopen = () => {
      setState("open");
      armWatchdog();
    };

    es.onmessage = (e) => {
      armWatchdog();
      if (!e.data) return;
      try {
        const ev = JSON.parse(e.data) as NxEvent;
        if (typeof ev.seq === "number") lastSeq = Math.max(lastSeq, ev.seq);
        handlers.onEvent(ev);
      } catch {
        /* ignore malformed frame */
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects (with Last-Event-ID). Surface the state.
      if (closed) return;
      setState("reconnecting");
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      if (watchdog) clearTimeout(watchdog);
      es?.close();
      setState("closed");
    },
  };
}
