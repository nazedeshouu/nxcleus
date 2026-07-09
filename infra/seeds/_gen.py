"""Shared synthetic-data helpers for the seed generators (09 §2, §5).

Every generator seeds a *local* `random.Random(SEED + salt)` so a regenerate reproduces byte-for-byte
(rehearsal gate 09 §7: "seed regenerated from scratch ... proves no hand-tuned state"). No global
`random` state is touched, so generators are order-independent and composable.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

SEED = 20260709  # fixed RNG seed (09 §2) — bump only to intentionally reshuffle every dataset

_FIRST = ["James", "Mary", "Wei", "Fatima", "Ivan", "Sofia", "Omar", "Elena", "Chen", "Aisha",
          "Liam", "Noor", "Diego", "Yuki", "Hassan", "Anna", "Raj", "Lena", "Kofi", "Marta",
          "Sergei", "Priya", "Tomas", "Zara", "Andrei", "Nadia", "Pavel", "Leila", "Mateo", "Iryna"]
_LAST = ["Smith", "Johnson", "Nguyen", "Al-Rashid", "Petrov", "Garcia", "Haddad", "Ivanova",
         "Wang", "Okoro", "Kim", "Silva", "Novak", "Costa", "Volkov", "Mensah", "Dubois",
         "Rossi", "Hassan", "Larsson", "Sokolov", "Patel", "Muller", "Popova", "Fernandez",
         "Bauer", "Andersson", "Kowalski", "Reyes", "Marchenko"]
_COUNTRIES = ["US", "GB", "DE", "FR", "AE", "KZ", "RU", "NG", "CN", "BR", "IN", "UA", "TR", "MX"]

# Names deliberately shaped near real sanctions entries (transliteration variants) so a good
# "screen against the sanctions-adjacent list" prompt finds real hits. NOT real designated persons.
SANCTIONS_ADJACENT = ["Viktor Sokolov", "Ivan Petrov", "Sergei Volkov", "Nadia Popova",
                      "Andrei Marchenko", "Pavel Ivanov"]


def rng(salt: int = 0) -> random.Random:
    return random.Random(SEED + salt)


def full_name(r: random.Random) -> str:
    return f"{r.choice(_FIRST)} {r.choice(_LAST)}"


def country(r: random.Random) -> str:
    return r.choice(_COUNTRIES)


def dob(r: random.Random, min_age: int = 18, max_age: int = 85) -> str:
    days = r.randint(min_age * 365, max_age * 365)
    return (date(2026, 7, 9) - timedelta(days=days)).isoformat()


def day_between(r: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=r.randint(0, (end - start).days))
