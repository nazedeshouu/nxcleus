/**
 * SSE wrapper for 06 §2/§3. Native EventSource gives us `Last-Event-ID` reconnect
 * resume for free (envelope `id:` == seq). `from_seq` opens replay-then-tail.
 *
 * The backend emits NAMED SSE events (`event: <type>`) and keeps the stream
 * alive with `: heartbeat` comments. Comments are invisible to EventSource, so
 * connection liveness is tracked purely via native onopen/onerror — a healthy
 * but idle stream (e.g. a completed job, fully replayed) stays "open".
 */
import type { NxEvent } from "../lib/events";
import { normalizeEvent, KNOWN_EVENT_TYPES } from "./adapt";

export type ConnState = "connecting" | "open" | "reconnecting" | "closed";

export interface StreamHandlers {
  onEvent: (ev: NxEvent) => void;
  onState?: (s: ConnState) => void;
}

export interface StreamHandle {
  close: () => void;
}

export function openEventStream(path: string, handlers: StreamHandlers, fromSeq = 0): StreamHandle {
  let es: EventSource | null = null;
  let closed = false;
  let lastSeq = fromSeq;

  const setState = (s: ConnState) => handlers.onState?.(s);

  const connect = () => {
    if (closed) return;
    const sep = path.includes("?") ? "&" : "?";
    // On first connect use from_seq; native reconnect also sends Last-Event-ID,
    // but pinning from_seq to lastSeq makes a manual reconnect deterministic too.
    const url = `${path}${sep}from_seq=${lastSeq}`;
    es = new EventSource(url);
    setState("connecting");

    es.onopen = () => setState("open");

    const handleFrame = (e: MessageEvent) => {
      if (!e.data) return;
      try {
        const raw = JSON.parse(e.data);
        if (typeof raw.seq === "number") lastSeq = Math.max(lastSeq, raw.seq);
        const ev = normalizeEvent(raw); // backend payload -> typed NxEvent
        if (ev) handlers.onEvent(ev);
      } catch {
        /* ignore malformed frame */
      }
    };

    // Named events don't fire onmessage; register the handler per type. onmessage
    // stays for any unnamed frames.
    es.onmessage = handleFrame;
    for (const type of KNOWN_EVENT_TYPES) es.addEventListener(type, handleFrame as EventListener);

    es.onerror = () => {
      // EventSource auto-reconnects (resuming from Last-Event-ID / from_seq).
      if (closed) return;
      setState("reconnecting");
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      es?.close();
      setState("closed");
    },
  };
}
