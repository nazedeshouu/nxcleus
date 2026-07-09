"""Boundary enforcement — the data boundary is code, not convention (01 §3, 02 §4)."""
from __future__ import annotations

import pytest

from app.boundary.errors import BoundaryViolation, SovereignViolation
from app.config import settings
from app.db import dao
from app.models.registry import Resolved
from app.models.router import _check_boundary, router
from app.seats.base import Message


def _resolved(zone: str, data_class_max: str = "RAW") -> Resolved:
    return Resolved(seat="x", backend=zone.lower(), zone=zone, model="m", node=None,
                    data_class_max=data_class_max, temperature=0.2, timeout_s=60, use_mock=True)


def test_matrix_raw_external_blocked():
    badge, violation = _check_boundary(_resolved("EXTERNAL"), "RAW", False, None)
    assert violation == "boundary"


def test_matrix_sovereign_external_blocked():
    badge, violation = _check_boundary(_resolved("EXTERNAL"), "SANITIZED", True, None)
    assert violation == "sovereign"


def test_matrix_raw_amd_hosted_demo_exception():
    object.__setattr__(settings, "allow_raw_on_amd_hosted", True)
    badge, violation = _check_boundary(_resolved("AMD_HOSTED"), "RAW", False, None)
    assert violation is None and badge == "demo-exception"


def test_matrix_raw_amd_hosted_enforced_when_flag_off():
    object.__setattr__(settings, "allow_raw_on_amd_hosted", False)
    badge, violation = _check_boundary(_resolved("AMD_HOSTED"), "RAW", False, None)
    assert violation == "boundary"
    object.__setattr__(settings, "allow_raw_on_amd_hosted", True)


def test_matrix_raw_local_ok():
    badge, violation = _check_boundary(_resolved("LOCAL"), "RAW", False, None)
    assert violation is None


def test_matrix_custom_raw_requires_attestation():
    r = _resolved("CUSTOM")
    assert _check_boundary(r, "RAW", False, {"ceiling": "SANITIZED"})[1] == "boundary"
    assert _check_boundary(r, "RAW", False, {"ceiling": "RAW"})[1] is None


async def test_planner_raw_raises_boundary_violation():
    with pytest.raises(BoundaryViolation):
        await router.complete("planner", [Message(role="user", content="x")],
                              scope="job:test", data_class="RAW")
    # the blocked attempt is logged for the network monitor
    rows = await dao.list_egress(scope="job:test")
    assert len(rows) >= 1


async def test_sovereign_custom_dispatch_raises():
    from app.boundary.secrets import store_secret
    ref = await store_secret("sk-x")
    conn = await dao.create_connection(name="c", base_url="https://api.x/v1", api_key_ref=ref,
                                       data_class_ceiling="SANITIZED", counts_as_local=False)
    model_id = await dao.add_custom_model(connection_id=conn, provider_model_id="m", display_name="M",
                                          flags=[])
    await dao.set_seat_override(seat="oracle", model_key=model_id, scope="job:sv")
    with pytest.raises(SovereignViolation):
        await router.complete("oracle", [Message(role="user", content="x")], scope="job:sv",
                              data_class="SANITIZED", sovereign=True)
    rows = await dao.list_egress(scope="job:sv", zone="CUSTOM")
    assert any(r["sovereign_violation"] == 1 for r in rows)
