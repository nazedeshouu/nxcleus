#!/usr/bin/env python
"""Live smoke test (addendum) — <=10-token verification calls to Anthropic (claude-fable-5) and
Fireworks (glm-5p2) through the real clients + egress ledger. Run MANUALLY (never in CI); needs live
keys in .env. Confirms the real dispatch path, structured output, metering, and the egress row.

Run:  uv run --project backend python scripts/live_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
os.environ["MODEL_MODE"] = "live"   # force real clients

from app.boundary import egress  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import dao  # noqa: E402
from app.db.engine import db  # noqa: E402
from app.models.router import router  # noqa: E402
from app.seats.base import Message  # noqa: E402


async def probe(seat: str, data_class: str, sovereign: bool = False) -> None:
    scope = "job:live-smoke"
    try:
        comp = await router.complete(seat, [Message(role="user", content="Reply with the single word OK.")],
                                     scope=scope, data_class=data_class, sovereign=sovereign, max_tokens=10)
        print(f"  {seat}: OK — {comp.usage} — {comp.text[:40]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  {seat}: FAILED — {type(e).__name__}: {e}")


async def main() -> None:
    await db.connect()
    await db.apply_schema()
    print("Nxcleus live smoke (MODEL_MODE=live)")
    print(f"  anthropic key present: {bool(settings.anthropic_api_key)}; "
          f"fireworks key present: {bool(settings.fireworks_api_key)}")
    # planner default -> Anthropic (EXTERNAL, SANITIZED); certifier fallback -> Fireworks glm-5p2
    await probe("planner", "SANITIZED")
    await probe("certifier", "RAW")     # local unavailable -> auto fallback to fireworks (badged)
    rows = await dao.list_egress(scope="job:live-smoke")
    print(f"  egress ledger rows: {len(rows)}")
    for r in rows:
        print(f"    {r['zone']:10} {r['host']:24} seat={r['seat']} bytes={r['bytes_out']}/{r['bytes_in']}")
    await egress.aclose()
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
