"""ULID identifiers with type prefixes (05 header).

`job_01J...`, `pln_...`, `prc_...`, `run_...`, `tkt_...` etc. ULIDs are monotonic + sortable, so
event order and creation order agree. `deterministic()` yields a stable id from a seed string so a
resumed stage upserts the same row instead of duplicating side effects (07 §4).
"""
from __future__ import annotations

import hashlib

from ulid import ULID

# type prefix per aggregate — keep in sync with the DAO modules
PREFIX = {
    "job": "job",
    "plan": "pln",
    "amendment": "amd",
    "consult": "cns",
    "quote": "qte",
    "build_task": "bt",
    "process": "prc",
    "process_version": "pv",
    "run": "run",
    "run_unit": "ru",
    "ticket": "tkt",
    "oracle_check": "ock",
    "node": "nod",
    "meter": "mtr",
    "egress": "egr",
    "sandbox_session": "sbx",
    "connection": "con",
    "custom_model": "cm",
    "seat_override": "so",
    "message": "msg",
    "user": "usr",
}


def new_id(kind: str) -> str:
    prefix = PREFIX.get(kind, kind)
    return f"{prefix}_{ULID()}"


def deterministic(kind: str, *seed_parts: str) -> str:
    """Stable id from a seed so re-running a stage upserts rather than duplicates (07 §4).

    ULID is 26 base32 chars; we derive a valid one from a sha256 of the seed.
    """
    prefix = PREFIX.get(kind, kind)
    digest = hashlib.sha256("::".join(seed_parts).encode()).digest()
    ulid = ULID.from_bytes(digest[:16])
    return f"{prefix}_{ulid}"
