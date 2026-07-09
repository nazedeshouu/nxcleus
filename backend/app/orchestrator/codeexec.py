"""Code-exec sandbox interface (01 §5, 03 §6). Wave 1 is a deterministic stub — the real
`python:3.12-slim` + pytest container with `--network none` and per-task workspace mounts is Wave 2.
The seam is final: stages call `run_tests(...)` and get pass/fail counts; only the body deepens.
"""
from __future__ import annotations

import asyncio


async def run_tests(*, workspace: str, tests: list, module_id: str | None = None) -> dict:
    """Run integration/unit tests against the workspace. Stub: reports all specs pass.

    TODO(wave2): docker run python:3.12-slim, mount workspace read-only, pytest, --network none.
    """
    await asyncio.sleep(0)   # yield; real impl awaits the container
    total = len(tests)
    return {"total": total, "passed": total, "failed": 0, "module_id": module_id, "stub": True}
