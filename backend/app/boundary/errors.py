"""Boundary enforcement exceptions (02 §4). Raised by the router before any dispatch — the
data boundary is code, not convention (01 §3)."""
from __future__ import annotations


class BoundaryViolation(Exception):
    """RAW data class routed outside the LOCAL zone without the demo exception (01 §3)."""


class SovereignViolation(Exception):
    """A sovereign job attempted an EXTERNAL-zone dispatch — fail closed, paint the run red (D7)."""


class BudgetExceeded(Exception):
    """A budget guard refused a dispatch (07 §5.4, 10 §7)."""
