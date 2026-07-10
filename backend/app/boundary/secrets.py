"""Encrypted-at-rest secret store for BYOK keys (D13, 05 `secrets` table + `api_key_ref`).

Keys are write-only: stored as Fernet ciphertext, surfaced masked, never serialized into events,
logs, or packages. The Fernet key comes from `FERNET_KEY`; with none set it is generated once and
persisted next to the SQLite file (0600) so BYOK keys survive a restart with zero config.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings
from app.db.engine import db
from app.ids import new_id


def _load_or_create_key() -> str:
    """Persist a generated key beside the DB (0600) so encrypted BYOK keys survive restart."""
    key_file = settings.sqlite_file.parent / ".fernet_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = Fernet.generate_key().decode()
    key_file.write_text(key)
    key_file.chmod(0o600)
    return key


@lru_cache
def _fernet() -> Fernet:
    key = settings.fernet_key.strip() or _load_or_create_key()
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
