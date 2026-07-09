"""Shared fleet health state (07 §5.1). The fleet manager updates it on heartbeats; the router
reads it to decide local-vs-fallback. Kept in its own tiny module so router and manager both import
it without a cycle."""
from __future__ import annotations

_ready_nodes: dict[str, str] = {}   # node name ('A'/'B'/...) -> ip


def mark_ready(name: str, ip: str) -> None:
    _ready_nodes[name] = ip


def mark_down(name: str) -> None:
    _ready_nodes.pop(name, None)


def ready_node_names() -> set[str]:
    return set(_ready_nodes.keys())


def node_ip(name: str) -> str | None:
    return _ready_nodes.get(name)
