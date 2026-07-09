"""Boundary vault — the raw->placeholder map that NEVER leaves the LOCAL zone (05, 03 §2.3).

Stage 0 masks raw values into typed placeholders (`«PERSON_1»`, `«ACCOUNT_A»`) and stores the map
here. Stage 2 rehydrates (placeholder->raw) once everything downstream is local (D9). The consult
gate (03 §4.2) reverse-substitutes (raw->placeholder) any payload going back to the planner.
"""
from __future__ import annotations

from app.db.engine import db


async def store(job_id: str, entries: list[tuple[str, str, str]]) -> None:
    """entries: list of (placeholder, raw_value, kind). Upsert so a re-run is idempotent."""
    for placeholder, raw_value, kind in entries:
        await db.execute(
            "INSERT INTO boundary_vault (job_id, placeholder, raw_value, kind) "
            "VALUES (:j, :p, :r, :k) "
            "ON CONFLICT(job_id, placeholder) DO UPDATE SET raw_value=:r, kind=:k",
            {"j": job_id, "p": placeholder, "r": raw_value, "k": kind},
        )


async def get_map(job_id: str) -> dict[str, str]:
    """placeholder -> raw_value."""
    rows = await db.fetchall(
        "SELECT placeholder, raw_value FROM boundary_vault WHERE job_id = :j", {"j": job_id}
    )
    return {r["placeholder"]: r["raw_value"] for r in rows}


def rehydrate_text(text: str, mapping: dict[str, str]) -> str:
    """placeholder -> raw. Used inside the LOCAL zone only (D9)."""
    for placeholder, raw in mapping.items():
        text = text.replace(placeholder, raw)
    return text


def reverse_substitute(text: str, mapping: dict[str, str]) -> str:
    """raw -> placeholder. Mechanical re-masking before a consult crosses the boundary (03 §4.2).

    Longest raw values first so a substring of one value can't shadow a longer match.
    """
    for placeholder, raw in sorted(mapping.items(), key=lambda kv: len(kv[1]), reverse=True):
        if raw:
            text = text.replace(raw, placeholder)
    return text


async def count(job_id: str) -> int:
    n = await db.scalar("SELECT COUNT(*) FROM boundary_vault WHERE job_id = :j", {"j": job_id})
    return int(n or 0)
