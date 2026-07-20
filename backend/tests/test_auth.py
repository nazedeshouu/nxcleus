"""Login/session auth (auth.py + deps.py gate integration). Runs in mock mode (conftest)."""
from __future__ import annotations

import contextlib

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import create_app


@contextlib.contextmanager
def _auth(admin="", judge="", signup_code=""):
    """Toggle login on/off around a test without leaking into the suite."""
    from app.api import auth as auth_mod
    auth_mod._signup_hits.clear()  # module-level limiter is process-global; reset per test
    old = (settings.auth_admin_password, settings.auth_judge_password, settings.auth_secret,
           settings.auth_signup_code)
    object.__setattr__(settings, "auth_admin_password", admin)
    object.__setattr__(settings, "auth_judge_password", judge)
    object.__setattr__(settings, "auth_signup_code", signup_code)
    object.__setattr__(settings, "auth_secret", "test-key")  # stable key => cookies survive within test
    try:
        yield
    finally:
        object.__setattr__(settings, "auth_admin_password", old[0])
        object.__setattr__(settings, "auth_judge_password", old[1])
        object.__setattr__(settings, "auth_secret", old[2])
        object.__setattr__(settings, "auth_signup_code", old[3])


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


# ---- self-serve signup ---------------------------------------------------------------------------
async def test_signup_happy_path_cookie_works_on_me_and_write_gate():
    with _auth(judge="jpw"):
        async with _client() as c:
            r = await c.post("/api/auth/signup", json={"username": "Alice_01", "password": "s3cretpw!"})
            assert r.status_code == 200, r.text
            assert r.json() == {"username": "alice_01", "role": "judge", "auth_enabled": True}
            assert "nx_session" in r.cookies
            me = await c.get("/api/auth/me")
            assert me.status_code == 200 and me.json()["username"] == "alice_01"
            # session opens the demo-write gate; handler then 404s on the missing job
            assert (await c.post("/api/jobs/nope/abort")).status_code == 404


async def test_signup_duplicate_username_409():
    with _auth(judge="jpw"):
        async with _client() as c:
            assert (await c.post("/api/auth/signup",
                                 json={"username": "dupe", "password": "s3cretpw!"})).status_code == 200
        async with _client() as c:  # fresh client, same db -> case-insensitive collision
            r = await c.post("/api/auth/signup", json={"username": "DUPE", "password": "another8!"})
            assert r.status_code == 409


async def test_signup_weak_password_400():
    with _auth(judge="jpw"):
        async with _client() as c:
            r = await c.post("/api/auth/signup", json={"username": "shorty", "password": "sh0rt"})
            assert r.status_code == 400


async def test_signup_invalid_username_400():
    with _auth(judge="jpw"):
        async with _client() as c:
            r = await c.post("/api/auth/signup", json={"username": "no", "password": "s3cretpw!"})
            assert r.status_code == 400
            r = await c.post("/api/auth/signup", json={"username": "bad name!", "password": "s3cretpw!"})
            assert r.status_code == 400


async def test_signup_reserved_username_collides_409():
    with _auth(admin="apw", judge="jpw"):
        async with _client() as c:
            r = await c.post("/api/auth/signup", json={"username": "Admin", "password": "s3cretpw!"})
            assert r.status_code == 409


async def test_signup_invite_code_required_wrong_right():
    with _auth(judge="jpw", signup_code="letmein"):
        async with _client() as c:  # missing code
            assert (await c.post("/api/auth/signup",
                                 json={"username": "gatedone", "password": "s3cretpw!"})).status_code == 403
        async with _client() as c:  # wrong code
            assert (await c.post("/api/auth/signup",
                                 json={"username": "gatedtwo", "password": "s3cretpw!",
                                       "invite_code": "nope"})).status_code == 403
        async with _client() as c:  # right code
            r = await c.post("/api/auth/signup", json={"username": "gatedthree", "password": "s3cretpw!",
                                                       "invite_code": "letmein"})
            assert r.status_code == 200, r.text


async def test_signup_rate_limit_trips():
    with _auth(judge="jpw"):
        async with _client() as c:
            hdr = {"X-Forwarded-For": "198.51.100.5"}  # pin the IP the limiter keys on
            for i in range(5):
                r = await c.post("/api/auth/signup", json={"username": f"user{i}", "password": "s3cretpw!"},
                                 headers=hdr)
                assert r.status_code == 200, (i, r.text)
            r = await c.post("/api/auth/signup", json={"username": "user5", "password": "s3cretpw!"},
                             headers=hdr)
            assert r.status_code == 429


async def test_db_user_login_roundtrip_and_env_users_coexist():
    with _auth(admin="apw", judge="jpw"):
        async with _client() as c:  # create the db account
            assert (await c.post("/api/auth/signup",
                                 json={"username": "dbuser", "password": "s3cretpw!"})).status_code == 200
        async with _client() as c:  # fresh jar: db-user login works
            r = await c.post("/api/auth/login", json={"username": "DBUser", "password": "s3cretpw!"})
            assert r.status_code == 200 and r.json()["role"] == "judge"
            assert (await c.get("/api/auth/me")).json()["username"] == "dbuser"
        async with _client() as c:  # env admin still logs in alongside the table
            r = await c.post("/api/auth/login", json={"username": "admin", "password": "apw"})
            assert r.status_code == 200 and r.json()["role"] == "admin"
        async with _client() as c:  # wrong db-user password rejected
            assert (await c.post("/api/auth/login",
                                 json={"username": "dbuser", "password": "bad"})).status_code == 401


async def test_db_user_rejected_by_admin_gate():
    with _auth(judge="jpw"):
        async with _client() as c:
            await c.post("/api/auth/signup", json={"username": "plebe", "password": "s3cretpw!"})
            # judge-role db session passes demo writes but is forbidden from admin ops
            assert (await c.post("/api/admin/sovereign", json={"enabled": False})).status_code == 403


async def test_signup_disabled_when_auth_off():
    # conftest leaves auth off (no env passwords) => signup returns a structured 409
    async with _client() as c:
        r = await c.post("/api/auth/signup", json={"username": "nobody", "password": "s3cretpw!"})
        assert r.status_code == 409
        assert r.json()["error"]["message"]
