"""PII masking — the always-on baseline (03 §2.1), mechanical part only.

Wave 1 ships the deterministic regex baseline (emails, phones, government IDs, cards, IBANs, secret
tokens, long digit runs) plus the consult sanitization gate's mechanical reverse-substitution +
residual sweep (03 §4.2). The trust-model-driven, policy-aware extraction is the seat layer's job
(Wave 2) and plugs in through `app/seats/trust.py`; this module is what it falls back to and what
the gate always re-runs as a backstop.
"""
from __future__ import annotations

import re

from app.boundary.vault import reverse_substitute

# (regex, placeholder-kind) — order matters: more specific patterns first
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "EMAIL"),
    (re.compile(r"\b(?:sk|pk|api|key|token)[-_][A-Za-z0-9]{12,}\b", re.I), "SECRET"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"), "IBAN"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "CARD"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "GOV_ID"),
    (re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b"), "PHONE"),
]


def baseline_mask(text: str, start_index: int = 0) -> tuple[str, list[tuple[str, str, str]]]:
    """Replace baseline PII with typed placeholders.

    Returns (masked_text, entries) where entries = list of (placeholder, raw_value, kind), ready for
    `vault.store`. `start_index` lets a caller keep placeholder numbers unique across fields.
    """
    entries: list[tuple[str, str, str]] = []
    counters: dict[str, int] = {}
    masked = text
    for pattern, kind in _PATTERNS:
        def _sub(m: re.Match, kind: str = kind) -> str:
            raw = m.group(0)
            counters[kind] = counters.get(kind, start_index) + 1
            placeholder = f"«{kind}_{counters[kind]}»"
            entries.append((placeholder, raw, kind.lower()))
            return placeholder

        masked = pattern.sub(_sub, masked)
    return masked, entries


def consult_sanitize(payload: str, vault_map: dict[str, str]) -> tuple[str, dict]:
    """Consult sanitization gate (03 §4.2): reverse-substitute known raw values, then a residual
    baseline sweep. Returns (sanitized_payload, receipt) — the receipt renders in the egress ledger.
    """
    reverse = reverse_substitute(payload, vault_map)
    swept, residual = baseline_mask(reverse)
    receipt = {
        "known_values_remasked": sum(1 for raw in vault_map.values() if raw and raw not in swept),
        "residuals_caught": len(residual),
        "data_class": "SANITIZED",
    }
    return swept, receipt
