"""Sandbox seed-corpus access (09 §2). Read-only introspection + unit loading over the per-company
SQLite files in infra/seeds/out/. Used by intake (inject the company schema into the planner brief)
and by the process-mode fan-out (real corpus units instead of synthetic refs).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import REPO_ROOT

_SEEDS_DIR = REPO_ROOT / "infra" / "seeds" / "out"


def seed_db_path(company: str | None) -> Path | None:
    if not company or not company.replace("_", "").isalnum():
        return None
    p = _SEEDS_DIR / f"{company}.db"
    return p if p.exists() else None


def company_terms(company: str | None) -> str | None:
    """Terms of Sensitive Data Use for a company (infra/seeds/out/terms/<id>_terms.md), or None if
    the id is invalid or the file hasn't been generated. Powers the stage-0 policy default (D11)."""
    if not company or not company.replace("_", "").isalnum():
        return None
    p = _SEEDS_DIR / "terms" / f"{company}_terms.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def company_schema(company: str | None) -> list[dict]:
    """[{table, columns, row_count}] for the planner brief. Synthetic demo data — SANITIZED by
    construction, safe in the brief."""
    path = seed_db_path(company)
    if path is None:
        return []
    con = _connect(path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = []
        for t in tables:
            cols = [r["name"] for r in con.execute(f"PRAGMA table_info({t})")]
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            out.append({"table": t, "columns": cols, "row_count": n})
        return out
    finally:
        con.close()


def load_units(company: str | None, *, source: str | None, noun: str, cap: int,
               sample: str = "first") -> list[tuple[str, dict]]:
    """Corpus units for the fan-out: rows of the plan's source table (fuzzy-matched to real tables,
    falling back to the largest). Returns [(unit_ref, row_dict)], at most `cap`.
    sample="random" draws a uniform sample instead of the first N.
    # ponytail: ORDER BY RANDOM() — fine at seed-DB sizes; reservoir/rowid sampling if corpora grow
    """
    path = seed_db_path(company)
    if path is None:
        return []
    schema = company_schema(company)
    if not schema:
        return []
    tables = {s["table"]: s["row_count"] for s in schema}
    table = _match_table(tables, source, noun)
    order = " ORDER BY RANDOM()" if sample == "random" else ""
    con = _connect(path)
    try:
        rows = con.execute(f"SELECT * FROM {table}{order} LIMIT ?", (cap,)).fetchall()
    finally:
        con.close()
    units = []
    for i, row in enumerate(rows):
        d = dict(row)
        ref = str(d.get("id") or d.get(f"{table.rstrip('s')}_id") or i)
        units.append((f"{table}-{ref}", d))
    return units


# --------------------------------------------------------------------- sql topology steps (M3 fix)
_WRITE_KEYWORDS = {"insert", "update", "delete", "drop", "create", "alter", "pragma", "attach",
                   "detach", "vacuum", "replace", "reindex", "begin", "commit", "rollback"}


def safe_select(sql: str) -> str:
    """Validate a topology sql step: exactly one read-only SELECT (CTEs allowed). Returns the
    normalized statement or raises ValueError.
    # ponytail: first-keyword + single-statement check over a read-only (mode=ro) connection —
    # not a SQL parser; the ro connection is the real enforcement, this is the fast fail
    """
    stmt = (sql or "").strip().rstrip(";").strip()
    if not stmt:
        raise ValueError("empty sql step")
    if ";" in stmt:
        raise ValueError("sql step must be a single statement")
    first = stmt.split(None, 1)[0].lower()
    if first in _WRITE_KEYWORDS:
        raise ValueError(f"sql step must be a SELECT (got {first.upper()})")
    if first not in ("select", "with"):
        raise ValueError(f"sql step must start with SELECT or WITH (got {first.upper()})")
    return stmt


def run_select(company: str | None, sql: str, *, cap: int, timeout_s: float = 10.0) -> list[dict]:
    """Execute one guarded SELECT against the company corpus (read-only URI connection), rows
    capped at `cap`, interrupted after `timeout_s`. Sync — call via asyncio.to_thread."""
    import threading

    stmt = safe_select(sql)
    path = seed_db_path(company)
    if path is None:
        raise ValueError(f"no corpus bound (company={company!r})")
    con = _connect(path)
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        rows = con.execute(stmt).fetchmany(cap)
        return [dict(r) for r in rows]
    finally:
        timer.cancel()
        con.close()


def _match_table(tables: dict[str, int], source: str | None, noun: str) -> str:
    for cand in (source, noun, f"{noun}s", f"{noun}es"):
        if cand and cand in tables:
            return cand
    low_noun = (noun or "").lower()
    for t in tables:
        if low_noun and (low_noun in t.lower() or t.lower().rstrip("s") == low_noun):
            return t
    return max(tables, key=lambda t: tables[t])  # ponytail: largest table = the corpus, per seed design
