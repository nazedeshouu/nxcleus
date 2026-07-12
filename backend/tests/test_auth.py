"""Login/session auth (auth.py + deps.py gate integration). Runs in mock mode (conftest)."""
from __future__ import annotations

import contextlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import create_app


@contextlib.contextmanager
def _auth(admin="", judge=""):
    """Toggle login on/off around a test without leaking into the suite."""
    old = (settings.auth_admin_password, settings.auth_judge_password, settings.auth_secret)
    object.__setattr__(settings, "auth_admin_password", admin)
    object.__setattr__(settings, "auth_judge_password", judge)
    object.__setattr__(settings, "auth_secret", "test-key")  # stable key => cookies survive within test
    try:
        yield
    finally:
        object.__setattr__(settings, "auth_admin_password", old[0])
        object.__setattr__(settings, "auth_judge_password", old[1])
        object.__setattr__(settings, "auth_secret", old[2])


def _client():
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


async def test_login_sets_cookie_and_me_roundtrips():
    with _auth(judge="jpw"):
        async with _client() as c:
            r = await c.post("/api/auth/login", json={"username": "judge", "password": "jpw"})
            assert r.status_code == 200, r.text
            assert r.json()["role"] == "judge"
            assert "nx_session" in r.cookies
            me = await c.get("/api/auth/me")  # cookie carried by the client jar
            assert me.status_code == 200 and me.json()["username"] == "judge"


async def test_bad_password_401_no_cookie():
    with _auth(admin="apw"):
        async with _client() as c:
            r = await c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            assert r.status_code == 401
            assert "nx_session" not in r.cookies


async def test_tampered_cookie_rejected():
    with _auth(admin="apw"):
        async with _client() as c:
            c.cookies.set("nx_session", "admin|admin|9999999999.deadbeef")
            assert (await c.get("/api/auth/me")).status_code == 401


async def test_write_requires_session_when_auth_on():
    with _auth(judge="jpw"):
        async with _client() as c:
            # no session -> gate closes (401), even though ADMIN_TOKEN is empty (dev-open no longer applies)
            assert (await c.post("/api/jobs/nope/abort")).status_code == 401
            await c.post("/api/auth/login", json={"username": "judge", "password": "jpw"})
            # session opens the gate; handler then 404s on the missing job -> gate passed
            assert (await c.post("/api/jobs/nope/abort")).status_code == 404


async def test_admin_only_forbids_judge_allows_admin():
    with _auth(admin="apw", judge="jpw"):
        async with _client() as c:
            await c.post("/api/auth/login", json={"username": "judge", "password": "jpw"})
            assert (await c.post("/api/admin/sovereign", json={"enabled": False})).status_code == 403
        async with _client() as c:
            await c.post("/api/auth/login", json={"username": "admin", "password": "apw"})
            assert (await c.post("/api/admin/sovereign", json={"enabled": False})).status_code == 200


async def test_auth_off_is_open_and_me_is_dev():
    # conftest leaves passwords empty + ADMIN_TOKEN empty => legacy dev-open behavior
    async with _client() as c:
        assert (await c.get("/api/auth/me")).json() == {"username": "dev", "role": "admin", "auth_enabled": False}
        assert (await c.post("/api/jobs/nope/abort")).status_code == 404  # open, handler 404s
