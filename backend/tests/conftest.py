"""Test harness — mock mode, a fresh SQLite file per test, schema applied."""
from __future__ import annotations

import os

os.environ.setdefault("MODEL_MODE", "mock")
os.environ.setdefault("ADMIN_TOKEN", "")

import pytest_asyncio  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.engine import db  # noqa: E402
from app.orchestrator.engine import engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    object.__setattr__(settings, "sqlite_path", str(tmp_path / "test.db"))
    object.__setattr__(settings, "model_mode", "mock")
    object.__setattr__(settings, "unsafe_demo_runtime", True)
    object.__setattr__(settings, "allow_unverified_demo_delivery", True)
    await db.connect()
    await db.apply_schema()
    try:
        yield db
    finally:
        # cancel any in-flight engine tasks so they don't bleed into the next test's fresh db
        await engine.stop()
        await db.disconnect()
