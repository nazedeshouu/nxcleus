"""Judge sandbox router (06 §2, 09). Three synthetic companies with suggested prompts; a run enters
the FIFO queue and streams the standard Build view. Company datasets are read-only SQLite files under
infra/seeds/out/ (generated in the seeds zone); until seeded, table browsing returns empty.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import client_hash, sandbox_session
from app.config import REPO_ROOT
from app.db import dao
from app.sandbox.queue import sandbox_queue

router = APIRouter(tags=["sandbox"])

_SEEDS_DIR = REPO_ROOT / "infra" / "seeds" / "out"

COMPANIES = [
    {"id": "bank", "name": "Meridian Bank",
     "prompts": ["Flag dormant accounts with unusual reactivation patterns and rank by risk",
                 "Detect structuring-shaped deposit runs across transactions",
                 "Screen customers against the sanctions-adjacent name list"]},
    {"id": "clinic", "name": "Aurora Clinic",
     "prompts": ["Find duplicate-billing shapes across encounters",
                 "Flag impossible vitals as data-quality issues",
                 "List overdue-screening cohorts by patient"]},
    {"id": "lawfirm", "name": "Hale & Ostrom",
     "prompts": ["Extract renewal dates and auto-renew clauses across all contracts; flag notice windows under 60 days",
                 "Find contracts missing signature blocks",
                 "Detect fee-cap breaches in billing entries"]},
]
_COMPANY_IDS = {c["id"] for c in COMPANIES}


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.get("/sandbox/companies")
async def companies() -> dict:
    return {"companies": COMPANIES}


@router.get("/sandbox/companies/{company_id}/tables")
async def company_tables(company_id: str) -> dict:
    db_path = _SEEDS_DIR / f"{company_id}.db"
    if not db_path.exists():
        return {"tables": [], "seeded": False}
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        con.close()
    return {"tables": [r[0] for r in rows], "seeded": True}


@router.get("/sandbox/companies/{company_id}/tables/{table}")
async def browse_table(company_id: str, table: str, page: int = 0, page_size: int = 50) -> dict:
    db_path = _SEEDS_DIR / f"{company_id}.db"
    if not db_path.exists():
        return {"rows": [], "seeded": False}
    if not table.isidentifier():
        raise _err(400, "invalid table name")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(f"SELECT * FROM {table} LIMIT ? OFFSET ?", (page_size, page * page_size))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        con.close()
    return {"rows": rows}


@router.post("/sandbox/runs", status_code=202)
async def sandbox_run(body: dict, request: Request, response: Response,
                      session_id: str = Depends(sandbox_session)) -> dict:
    company = body.get("company")
    prompt = body.get("prompt", "")
    if company not in _COMPANY_IDS:
        raise _err(400, "unknown company")
    if not prompt:
        raise _err(400, "prompt is required")
    # per-session rate limit: 3 runs/hour (09 §4)
    session = await dao.get_sandbox_session(session_id)
    if session is None:
        await dao.create_sandbox_session(company=company, client_hash=client_hash(request))
    job_id, position = await sandbox_queue.enqueue(company=company, prompt=prompt, session_id=session_id)
    await dao.incr_sandbox_runs(session_id)
    return {"job_id": job_id, "queue_position": position}


@router.get("/sandbox/queue")
async def sandbox_queue_state() -> dict:
    return sandbox_queue.queue_state()
