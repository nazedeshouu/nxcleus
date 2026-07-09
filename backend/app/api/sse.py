"""SSE responder (06 §3) — replay-then-tail with `from_seq`, `Last-Event-ID` resume, and a
`: heartbeat` comment every heartbeat_s. `id:` = seq so browser EventSource reconnects resume
automatically.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.events import bus, replay, replay_prefix


def _format_event(event: dict) -> str:
    data = json.dumps({"seq": event["seq"], "ts": event["ts"], "scope": event["scope"],
                       "type": event["type"], "payload": event["payload"]})
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n"


async def sse_response(request: Request, *, scope: str | None = None, type_prefix: str | None = None,
                       from_seq: int = 0) -> StreamingResponse:
    # Last-Event-ID resume takes precedence over ?from_seq
    last_id = request.headers.get("last-event-id")
    if last_id and last_id.lstrip("-").isdigit():
        from_seq = int(last_id) + 1

    async def gen():
        # subscribe BEFORE replay so no event slips through the gap
        sub = bus.subscribe(scope=scope, type_prefix=type_prefix)
        sent_max = from_seq - 1
        try:
            backlog = (await replay(scope, from_seq)) if scope else await replay_prefix(type_prefix or "", from_seq)
            for ev in backlog:
                sent_max = max(sent_max, ev["seq"])
                yield _format_event(ev)
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(sub.queue.get(), timeout=settings.sse_heartbeat_s)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if ev["seq"] <= sent_max and ev["seq"] != -1:
                    continue
                sent_max = max(sent_max, ev["seq"])
                yield _format_event(ev)
        finally:
            bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
