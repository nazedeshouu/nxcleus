"""Bring-your-own-data endpoints (hardening 2026-07-10). Custom corpora register into the `datasets`
table; seeds.seed_db_path then resolves them so every sandbox browse/fan-out path works unchanged.
Frozen contract (additive): responses carry {id,name,blurb,origin,kind,tables:[{name,rows}]} (+meta
for connector/codebase). DELETE refuses builtins (they have no datasets row)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from app.api.deps import require_demo_token
from app.db import dao
from app.sandbox import datasets

router = APIRouter(tags=["datasets"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.post("/datasets", dependencies=[Depends(require_demo_token)])
async def upload_dataset(files: list[UploadFile] = File(...), name: str = Form(""),
                         blurb: str = Form("")) -> dict:
    if not files:
        raise _err(400, "at least one file is required")
    name = name or Path(files[0].filename or "dataset").stem
    payloads = [(f.filename or "file", await f.read()) for f in files]
    is_sqlite = any((fn or "").lower().endswith((".db", ".sqlite", ".sqlite3")) for fn, _ in payloads)
    try:
        if is_sqlite:
            _, data = next(p for p in payloads
                           if (p[0] or "").lower().endswith((".db", ".sqlite", ".sqlite3")))
            return await datasets.ingest_sqlite(data, name=name, blurb=blurb)
        csvs = [(fn, d) for fn, d in payloads if (fn or "").lower().endswith(".csv")] or payloads
        return await datasets.ingest_csv(csvs, name=name, blurb=blurb)
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.post("/datasets/connect", dependencies=[Depends(require_demo_token)])
async def connect_dataset(body: dict) -> dict:
    url = body.get("url", "")
    if not url:
        raise _err(400, "url is required")
    try:
        return await datasets.ingest_connector(url, name=body.get("name", ""))
    except ModuleNotFoundError as exc:
        raise _err(400, f"connector driver missing: {exc.name} (install psycopg / pymysql)") from exc
    except (ValueError, Exception) as exc:  # noqa: BLE001 — remote failures are a 400 to the caller
        raise _err(400, f"connect failed: {type(exc).__name__}: {str(exc)[:200]}") from exc


@router.post("/datasets/codebase", dependencies=[Depends(require_demo_token)])
async def codebase_dataset(body: dict) -> dict:
    name = body.get("name") or (body.get("git_url", "").rstrip("/").split("/")[-1]
                                or Path(body.get("path", "corpus")).name)
    try:
        return await datasets.ingest_codebase(path=body.get("path"), git_url=body.get("git_url"),
                                              name=name)
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.delete("/datasets/{dataset_id}", status_code=204,
               dependencies=[Depends(require_demo_token)])
async def delete_dataset(dataset_id: str) -> Response:
    row = await dao.get_dataset(dataset_id)
    if not row:
        raise _err(400, "unknown or builtin dataset (only custom datasets can be deleted)")
    await dao.delete_dataset(dataset_id)
    if row.get("db_path"):
        Path(row["db_path"]).unlink(missing_ok=True)
    return Response(status_code=204)
