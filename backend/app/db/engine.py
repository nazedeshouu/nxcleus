"""Database engine — SQLAlchemy Core over aiosqlite (05 / D5). WAL mode, single writer.

The API process is the only writer (07 §1); an asyncio lock serializes writes so a burst of
concurrent stages can't interleave a transaction. Reads run without the lock (WAL lets them
proceed against the last committed snapshot).
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _split_statements(sql: str) -> list[str]:
    # strip line comments, then split on ';' (schema has no ';' inside string literals)
    no_comments = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


class Database:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._write_lock = asyncio.Lock()

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Database not connected; call connect() in the lifespan hook")
        return self._engine

    async def connect(self) -> None:
        # (re)create the write lock bound to the current running loop — matters for tests that run
        # each case in its own event loop and reconnect a fresh db.
        self._write_lock = asyncio.Lock()
        url = f"sqlite+aiosqlite:///{settings.sqlite_file}"
        self._engine = create_async_engine(url, future=True, echo=False)

        # SQLite pragmas are PER-CONNECTION; setting them once on startup only configures one
        # pooled connection, leaving FK enforcement a per-request lottery (the sandbox FK bug).
        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_pragmas(dbapi_conn, _record) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

        async with self._engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")  # materialize one connection -> pragmas apply

    # additive columns for pre-existing DBs (CREATE TABLE IF NOT EXISTS won't alter them);
    # each ALTER is a no-op error ("duplicate column") on a fresh schema — swallowed below.
    _MIGRATIONS = (
        "ALTER TABLE jobs ADD COLUMN request TEXT",
        "ALTER TABLE processes ADD COLUMN corpus_company TEXT",
        "ALTER TABLE runs ADD COLUMN params_json TEXT",
        "ALTER TABLE runs ADD COLUMN next_steps_json TEXT",
        "ALTER TABLE api_connections ADD COLUMN api_style TEXT DEFAULT 'openai'",
    )

    async def apply_schema(self) -> None:
        statements = _split_statements(SCHEMA_PATH.read_text())
        async with self._write_lock, self.engine.begin() as conn:
            for stmt in statements:
                await conn.exec_driver_sql(stmt)
        for stmt in self._MIGRATIONS:  # own txn each: a duplicate-column error must not poison the batch
            try:
                async with self._write_lock, self.engine.begin() as conn:
                    await conn.exec_driver_sql(stmt)
            except Exception:  # noqa: BLE001 — column already exists (fresh schema)
                pass

    async def disconnect(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    # --- writes (serialized) --------------------------------------------------------------------
    async def execute(self, sql: str, params: dict | None = None) -> None:
        async with self._write_lock, self.engine.begin() as conn:
            await conn.execute(text(sql), params or {})

    async def execute_returning(self, sql: str, params: dict | None = None) -> Any:
        async with self._write_lock, self.engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            row = result.first()
            return row[0] if row else None

    # --- reads ----------------------------------------------------------------------------------
    async def fetchone(self, sql: str, params: dict | None = None) -> dict | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            row = result.mappings().first()
            return dict(row) if row else None

    async def fetchall(self, sql: str, params: dict | None = None) -> list[dict]:
        async with self.engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return [dict(r) for r in result.mappings().all()]

    async def scalar(self, sql: str, params: dict | None = None) -> Any:
        async with self.engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return result.scalar()


# process-wide singleton (single writer, 07 §1)
db = Database()
