/** One hook, two sources: live SSE or fixture replay, folded through the same store. */
import { useEffect, useRef, useState } from "react";
import { foldEvent, initialJobView, type JobView } from "./jobStore";
import { openEventStream, type ConnState } from "../api/sse";
import { API_BASE, MOCK_FORCED } from "../api/config";
import { playEvents } from "../fixtures/player";
import { KYC_EVENTS, KYC_JOB_ID } from "../fixtures/kycJob";
import type { NxEvent } from "../lib/events";

export interface UseJobStream {
  view: JobView;
  conn: ConnState;
  mock: boolean;
  /** inject an event (presenter controls: e.g. simulate a sovereign breach) */
  inject: (ev: NxEvent) => void;
}

export function useJobStream(jobId: string, opts: { speed?: number; forceMock?: boolean } = {}): UseJobStream {
  const [view, setView] = useState<JobView>(() => initialJobView(`job:${jobId}`));
  const [conn, setConn] = useState<ConnState>("connecting");
  const viewRef = useRef(view);
  viewRef.current = view;

  // decide source: forced mock, global mock flag, or the well-known fixture job id
  const isMock = opts.forceMock || MOCK_FORCED || jobId === KYC_JOB_ID;

  const apply = (ev: NxEvent) => {
    setView((prev) => foldEvent(prev, ev));
  };

  useEffect(() => {
    setView(initialJobView(`job:${jobId}`));

    if (isMock) {
      setConn("open");
      const handle = playEvents(KYC_EVENTS, apply, { speed: opts.speed ?? 16, onDone: () => setConn("closed") });
      return () => handle.stop();
    }

    const stream = openEventStream(`${API_BASE}/jobs/${jobId}/events`, {
      onEvent: apply,
      onState: setConn,
    });
    // GPU telemetry lives on the fleet scope, not the job stream — merge it in
    // so the cockpit's MI300X panel shows real utilization for any live job.
    const fleet = openEventStream(`${API_BASE}/fleet/telemetry`, { onEvent: apply });
    return () => {
      stream.close();
      fleet.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, isMock, opts.speed]);

  return { view, conn, mock: isMock, inject: apply };
}
