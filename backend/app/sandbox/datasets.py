"""Bring-your-own-data intake (hardening 2026-07-10). Four paths land a customer corpus as a local
read-only SQLite the existing sandbox/seeds engine already knows how to browse and fan out over:

  a) SQLite upload   — validate the magic header, store, introspect, register.
  b) CSV upload      — stdlib csv + sqlite3, one table per file, types inferred by sampling.
  c) DB connector    — postgres/mysql, SNAPSHOT capped rows into a local sqlite (honest: snapshot at
                       connect; re-connect to refresh).
  d) Codebase corpus — walk a directory (or shallow git clone) into a files(path,ext,size,lines,
                       content) table (kind='files') + a compact code_map in meta.

Builtins stay in api/sandbox COMPANIES; only custom datasets land in the `datasets` table.
seeds.seed_db_path resolves db_path from here, so every browse endpoint works over custom corpora.
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.config import settings
from app.db import dao
from app.events import now_iso
from app.ids import new_id
from app.sandbox import seeds

# ── deliberate ceilings (ponytail: sized for the demo; each is the one knob to raise) ─────────────
SQLITE_MAGIC = b"SQLite format 3\x00"          # 16 bytes at offset 0 (sqlite file format)
MAX_DB_BYTES = 500 * 1024 * 1024               # ponytail: 500MB upload cap
SNAPSHOT_CAP = 50_000                          # ponytail: rows/table copied from a remote DB
MAX_FILES = 5000                               # ponytail: files walked into a codebase corpus
MAX_FILE_BYTES = 200 * 1024                    # ponytail: skip files larger than 200KB
_CSV_SAMPLE = 200                              # rows sampled to infer a column's type

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
              ".next", "target", ".idea", ".mypy_cache", ".pytest_cache", ".gradle", "vendor",
              "coverage", ".turbo", "out"}
_BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar",
                ".db", ".sqlite", ".pyc", ".so", ".dylib", ".dll", ".exe", ".bin", ".woff",
                ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".mov", ".wav", ".jar", ".class",
                ".lock", ".map", ".min.js", ".svg"}
_ENTRY_FILES = {"main.py", "app.py", "__main__.py", "cli.py", "manage.py", "server.py", "wsgi.py",
                "asgi.py", "index.js", "index.ts", "package.json", "pyproject.toml", "Dockerfile",
                "docker-compose.yml", "Makefile", "go.mod", "Cargo.toml"}


def _uploads_dir() -> Path:
    d = settings.data_path / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _corpora_dir() -> Path:
    d = settings.data_path / "corpora"
    d.mkdir(parents=True, exist_ok=True)
    return d


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s or "dataset"


async def unique_slug(name: str) -> str:
    """A slug that collides with neither a builtin seed file nor an existing custom dataset."""
    base = slugify(name)
    taken = bool(await dao.get_dataset(base)) or (seeds._SEEDS_DIR / f"{base}.db").exists()
    return base if not taken else f"{base}_{new_id('x')[-6:].lower()}"


# ── validation / introspection ───────────────────────────────────────────────────────────────────
def validate_sqlite_bytes(data: bytes) -> None:
    if len(data) > MAX_DB_BYTES:
        raise ValueError(f"file exceeds {MAX_DB_BYTES // (1024 * 1024)}MB cap")
    if data[:16] != SQLITE_MAGIC:
        raise ValueError("not a SQLite database (bad magic header)")


def _introspect(path: Path) -> list[dict]:
    """[{name, rows, columns}] over a read-only connection."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = []
        for t in tables:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            out.append({"name": t, "rows": n, "columns": cols})
        return out
    finally:
        con.close()


def suggested_prompts(schema: list[dict], kind: str) -> list[str]:
    """3-4 generic-but-schema-aware prompts (name real tables/columns)."""
    if kind == "files":
        return ["Summarize what this codebase does — its top-level structure, languages, and entry points.",
                "Find files whose content references secrets, credentials, API keys, or passwords.",
                "List the largest source files and flag any over 400 lines that likely need refactoring.",
                "Search the code for TODO or FIXME markers and group them by directory."]
    tabs = sorted([s for s in schema if s.get("rows")], key=lambda s: -s["rows"]) or schema
    if not tabs:
        return ["Summarize this dataset and flag any obvious data-quality issues."]
    t0 = tabs[0]
    prompts = [f"Summarize the {t0['name']} table — row count, key columns, and any data-quality issues.",
               f"Find duplicate or near-duplicate records in {t0['name']} and rank them by how many fields match."]
    if t0.get("columns"):
        prompts.append(f"Flag rows in {t0['name']} whose {t0['columns'][-1]} is an outlier versus the rest.")
    if len(tabs) > 1:
        prompts.append(f"Reconcile {t0['name']} against {tabs[1]['name']} and flag records that don't match across the two.")
    return prompts[:4]


# ── (b) CSV -> sqlite ─────────────────────────────────────────────────────────────────────────────
def _infer_type(samples: list[str]) -> str:
    seen = [s for s in samples if s not in ("", None)]
    if not seen:
        return "TEXT"
    is_int = is_float = True
    for v in seen:
        try:
            int(v)
        except (ValueError, TypeError):
            is_int = False
        try:
            float(v)
        except (ValueError, TypeError):
            is_float = False
        if not is_float:
            break
    return "INTEGER" if is_int else "REAL" if is_float else "TEXT"


def _table_name(filename: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", Path(filename).stem.lower()).strip("_") or "table"
    if base[0].isdigit():
        base = f"t_{base}"
    name, i = base, 1
    while name in taken:
        name, i = f"{base}_{i}", i + 1
    taken.add(name)
    return name


def csvs_to_sqlite(db_path: Path, csvs: list[tuple[str, bytes]]) -> None:
    """One table per CSV (name from filename), INTEGER/REAL/TEXT inferred by sampling."""
    con = sqlite3.connect(db_path)
    taken: set[str] = set()
    try:
        wrote = False
        for filename, data in csvs:
            reader = csv.reader(io.StringIO(data.decode("utf-8", errors="replace")))
            rows = list(reader)
            if not rows:
                continue
            header = [re.sub(r"[^a-z0-9_]+", "_", (h or "col").strip().lower()).strip("_") or f"col{i}"
                      for i, h in enumerate(rows[0])]
            body = rows[1:]
            types = [_infer_type([r[c] if c < len(r) else "" for r in body[:_CSV_SAMPLE]])
                     for c in range(len(header))]
            table = _table_name(filename, taken)
            coldefs = ", ".join(f'"{h}" {t}' for h, t in zip(header, types, strict=True))
            con.execute(f'CREATE TABLE "{table}" ({coldefs})')
            ph = ", ".join(["?"] * len(header))
            con.executemany(
                f'INSERT INTO "{table}" VALUES ({ph})',
                [[_coerce(r[c] if c < len(r) else None, types[c]) for c in range(len(header))]
                 for r in body])
            wrote = True
        if not wrote:
            raise ValueError("no rows found in the uploaded CSV(s)")
        con.commit()
    finally:
        con.close()


def _coerce(v, t: str):
    if v in ("", None):
        return None
    try:
        return int(v) if t == "INTEGER" else float(v) if t == "REAL" else v
    except (ValueError, TypeError):
        return v


# ── (c) remote DB -> sqlite snapshot ────────────────────────────────────────────────────────────
def snapshot_remote(url: str, db_path: Path, *, cap: int = SNAPSHOT_CAP) -> dict:
    scheme = urlparse(url).scheme.lower()
    if scheme in ("postgres", "postgresql"):
        return _snapshot_postgres(url, db_path, cap)
    if scheme == "mysql":
        return _snapshot_mysql(url, db_path, cap)
    raise ValueError(f"unsupported scheme {scheme!r}; use postgres/postgresql/mysql")


def _copy_tables(src_cursor_factory, tables: list[str], db_path: Path, cap: int, quote) -> dict:
    rows_copied, capped = 0, False
    con = sqlite3.connect(db_path)
    try:
        for t in tables:
            cur = src_cursor_factory()
            cur.execute(f"SELECT * FROM {quote(t)} LIMIT {cap + 1}")
            fetched = cur.fetchall()
            cols = [d[0] for d in cur.description]
            cur.close()
            if len(fetched) > cap:
                fetched, capped = fetched[:cap], True
            coldefs = ", ".join(f'"{c}" TEXT' for c in cols)   # ponytail: TEXT snapshot, no type map
            con.execute(f'CREATE TABLE "{t}" ({coldefs})')
            ph = ", ".join(["?"] * len(cols))
            con.executemany(f'INSERT INTO "{t}" VALUES ({ph})',
                            [[None if v is None else str(v) for v in r] for r in fetched])
            rows_copied += len(fetched)
        con.commit()
    finally:
        con.close()
    return {"snapshot_at": now_iso(), "rows_copied": rows_copied, "capped": capped}


def _snapshot_postgres(url: str, db_path: Path, cap: int) -> dict:
    import psycopg

    src = psycopg.connect(url)
    try:
        cur = src.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
        tables = [r[0] for r in cur.fetchall()]
        cur.close()
        return _copy_tables(src.cursor, tables, db_path, cap, lambda t: '"' + t.replace('"', '') + '"')
    finally:
        src.close()


def _snapshot_mysql(url: str, db_path: Path, cap: int) -> dict:
    import pymysql

    p = urlparse(url)
    src = pymysql.connect(host=p.hostname or "localhost", port=p.port or 3306,
                          user=unquote(p.username or ""), password=unquote(p.password or ""),
                          database=(p.path or "/").lstrip("/"))
    try:
        cur = src.cursor()
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        cur.close()
        return _copy_tables(src.cursor, tables, db_path, cap, lambda t: "`" + t.replace("`", "") + "`")
    finally:
        src.close()


# ── (d) codebase -> sqlite files corpus ─────────────────────────────────────────────────────────
def walk_codebase(root: Path, db_path: Path, *, max_files: int = MAX_FILES,
                  max_bytes: int = MAX_FILE_BYTES) -> dict:
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE files (path TEXT, ext TEXT, size INTEGER, lines INTEGER, content TEXT)")
    n = 0
    langs: dict[str, int] = {}
    top_dirs: set[str] = set()
    entry_points: list[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                if n >= max_files:
                    break
                fp = Path(dirpath) / fn
                ext = fp.suffix.lower()
                if ext in _BINARY_EXTS:
                    continue
                try:
                    if fp.stat().st_size > max_bytes:
                        continue
                    text = fp.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue    # unreadable or binary-by-content -> skip
                rel = str(fp.relative_to(root))
                lines = text.count("\n") + 1
                con.execute("INSERT INTO files VALUES (?,?,?,?,?)", (rel, ext, len(text), lines, text))
                n += 1
                if ext:
                    langs[ext] = langs.get(ext, 0) + 1
                parts = Path(rel).parts
                if len(parts) > 1:
                    top_dirs.add(parts[0])
                if fn in _ENTRY_FILES:
                    entry_points.append(rel)
            if n >= max_files:
                break
        con.commit()
    finally:
        con.close()
    code_map = {"files": n, "top_dirs": sorted(top_dirs)[:20],
                "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])[:12]),
                "entry_points": entry_points[:20]}
    return {"files": n, "code_map": code_map}


def _git_clone(git_url: str, dest: Path) -> None:
    res = subprocess.run(["git", "clone", "--depth", "1", git_url, str(dest)],
                         capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        raise ValueError(f"git clone failed: {res.stderr.strip()[:300]}")


# ── async ingest wrappers (register + return the frozen contract shape) ──────────────────────────
async def _register(*, dataset_id: str, name: str, blurb: str, origin: str, kind: str,
                    db_path: Path, extra_meta: dict | None = None) -> dict:
    schema = _introspect(db_path)
    tables = [{"name": s["name"], "rows": s["rows"]} for s in schema]
    meta = {"tables": tables, "suggested_prompts": suggested_prompts(schema, kind), **(extra_meta or {})}
    await dao.register_dataset(dataset_id=dataset_id, name=name, blurb=blurb, origin=origin,
                              kind=kind, db_path=str(db_path), meta=meta)
    resp = {"id": dataset_id, "name": name, "blurb": blurb, "origin": origin, "kind": kind,
            "tables": tables}
    if extra_meta:
        resp["meta"] = extra_meta
    return resp


async def ingest_sqlite(data: bytes, *, name: str, blurb: str) -> dict:
    validate_sqlite_bytes(data)
    slug = await unique_slug(name)
    db_path = _uploads_dir() / f"{slug}.db"
    db_path.write_bytes(data)
    # a corrupt/renamed file passes the magic check but fails to open — surface it now, not at run time
    try:
        _introspect(db_path)
    except sqlite3.DatabaseError as exc:
        db_path.unlink(missing_ok=True)
        raise ValueError(f"unreadable SQLite file: {exc}") from exc
    return await _register(dataset_id=slug, name=name, blurb=blurb, origin="upload", kind="rows",
                           db_path=db_path)


async def ingest_csv(csvs: list[tuple[str, bytes]], *, name: str, blurb: str) -> dict:
    slug = await unique_slug(name)
    db_path = _uploads_dir() / f"{slug}.db"
    db_path.unlink(missing_ok=True)
    await asyncio.to_thread(csvs_to_sqlite, db_path, csvs)
    return await _register(dataset_id=slug, name=name, blurb=blurb, origin="upload", kind="rows",
                           db_path=db_path)


async def ingest_connector(url: str, *, name: str) -> dict:
    slug = await unique_slug(name or urlparse(url).path.lstrip("/") or "connector")
    db_path = _uploads_dir() / f"{slug}.db"
    db_path.unlink(missing_ok=True)
    meta = await asyncio.to_thread(snapshot_remote, url, db_path)
    return await _register(dataset_id=slug, name=name or slug, blurb=f"snapshot of {urlparse(url).scheme}",
                           origin="connector", kind="rows", db_path=db_path, extra_meta=meta)


async def ingest_codebase(*, path: str | None, git_url: str | None, name: str) -> dict:
    slug = await unique_slug(name)
    if git_url:
        src = _corpora_dir() / slug
        if src.exists():
            import shutil
            shutil.rmtree(src, ignore_errors=True)
        await asyncio.to_thread(_git_clone, git_url, src)
        root = src
    elif path:
        root = Path(path).expanduser()
        if not root.is_dir():
            raise ValueError(f"path is not a directory: {path}")
    else:
        raise ValueError("path or git_url required")
    db_path = _uploads_dir() / f"{slug}.db"
    db_path.unlink(missing_ok=True)
    walked = await asyncio.to_thread(walk_codebase, root, db_path)
    return await _register(dataset_id=slug, name=name, blurb=blurb_from_codemap(walked["code_map"]),
                           origin="codebase", kind="files", db_path=db_path,
                           extra_meta={"files": walked["files"], "code_map": walked["code_map"]})


def blurb_from_codemap(code_map: dict) -> str:
    langs = ", ".join(list(code_map.get("languages", {}))[:4]) or "mixed"
    return f"{code_map.get('files', 0)} files, {langs}"
