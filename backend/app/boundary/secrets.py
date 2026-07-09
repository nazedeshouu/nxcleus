"""Encrypted-at-rest secret store for BYOK keys (D13, 05 `secrets` table + `api_key_ref`).

Keys are write-only: stored as Fernet ciphertext, surfaced masked, never serialized into events,
logs, or packages. The Fernet key comes from `FERNET_KEY`; in dev an ephemeral key is generated so
BYOK works with zero config (keys don't survive a restart — acceptable for the hackathon).
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings
from app.db.engine import db
from app.ids import new_id


@lru_cache
def _fernet() -> Fernet:
    key = settings.fernet_key.strip()
    if not key:
        key = Fernet.generate_key().decode()   # ephemeral dev key
    return Fernet(key.encode())


async def store_secret(plaintext: str) -> str:
    ref = new_id("secret")
    ciphertext = _fernet().encrypt(plaintext.encode()).decode()
    await db.execute(
        "INSERT INTO secrets (ref, ciphertext, created_at) VALUES (:ref, :ct, datetime('now'))",
        {"ref": ref, "ct": ciphertext},
    )
    return ref


async def decrypt_ref(ref: str) -> str | None:
    row = await db.fetchone("SELECT ciphertext FROM secrets WHERE ref = :ref", {"ref": ref})
    if not row:
        return None
    return _fernet().decrypt(row["ciphertext"].encode()).decode()


def mask(value: str) -> str:
    if len(value) <= 8:
        return "••••"
    return f"{value[:3]}••••{value[-4:]}"
