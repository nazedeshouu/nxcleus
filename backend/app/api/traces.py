"""Prompt-trace inspector (hardening 2026-07-10). LOCAL-only debugging surface over model_traces:
every router dispatch, full messages as sent (incl. system) + response. List view truncates to
~200-char previews; the detail view returns the full row. Traces never leave the box by design.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.db.engine import db

router = APIRouter(tags=["traces"])


@router.get("/traces")
async def list_traces(scope: str | None = None, seat: str | None = None,
                      limit: int = 50, offset: int = 0) -> dict:
    where, params = [], {"lim": max(1, min(limit, 200)), "off": max(0, offset)}
    if scope:
        where.append("scope = :scope")
        params["scope"] = scope
    if seat:
        where.append("seat = :seat")
        params["seat"] = seat
    sql = ("SELECT * FROM model_traces" + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY ts DESC, id DESC LIMIT :lim OFFSET :off")
    out = []
    for r in await db.fetchall(sql, params):
        row = dict(r)
        row["messages_preview"] = (row.pop("messages_json") or "")[:200]
        row["response_preview"] = (row.pop("response_text") or "")[:200]
        out.append(row)
    return {"traces": out}


@router.get("/tools")
async def list_tools(scope: str | None = None) -> dict:
    """createTool registry (T8) — code included; only self-tested tools have rows here."""
    where = " WHERE scope = :sc" if scope else ""
    rows = await db.fetchall(f"SELECT * FROM tools{where} ORDER BY ts DESC",
                             {"sc": scope} if scope else {})
    out = []
    for r in rows:
        row = dict(r)
        try:
            row["args_schema"] = json.loads(row.get("args_schema_json") or "{}")
        except json.JSONDecodeError:
            row["args_schema"] = {}
        out.append(row)
    return {"tools": out}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict:
    row = await db.fetchone("SELECT * FROM model_traces WHERE id = :id", {"id": trace_id})
    if not row:
        raise HTTPException(status_code=404, detail={"error": {"code": 404, "message": "trace not found"}})
    row = dict(row)
    try:
        row["messages"] = json.loads(row.get("messages_json") or "[]")
    except json.JSONDecodeError:
        row["messages"] = []
    return {"trace": row}
