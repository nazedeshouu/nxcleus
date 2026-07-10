"""Bring-your-own-data + BYOK/provider regressions (hardening 2026-07-10): sqlite-upload magic
validation + registration, CSV->sqlite type inference, codebase walk, datasets listing merge,
api_style routing resolution (no network), planner flagship (openai) + anthropic fallback, and
POST /jobs corpus binding reaching the spec."""
from __future__ import annotations

import sqlite3

import pytest

from app.config import BACKEND_ROOT, settings
from app.db import dao
from app.sandbox import datasets, seeds


# ---------------------------------------------------------------- (a) sqlite upload
async def test_sqlite_upload_validates_and_registers(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))   # uploads land in tmp, auto-reverted
    src = tmp_path / "src.db"
    con = sqlite3.connect(src)
    con.executescript("CREATE TABLE claims (id INTEGER, v TEXT);"
                       "INSERT INTO claims VALUES (1,'a'); INSERT INTO claims VALUES (2,'b');")
    con.commit()
    con.close()
    data = src.read_bytes()

    with pytest.raises(ValueError):
        datasets.validate_sqlite_bytes(b"definitely not a sqlite database header, nope")
    datasets.validate_sqlite_bytes(data)   # good magic -> no raise

    res = await datasets.ingest_sqlite(data, name="My Claims", blurb="test corpus")
    assert res["origin"] == "upload" and res["kind"] == "rows"
    assert {"claims"} <= {t["name"] for t in res["tables"]}
    assert next(t["rows"] for t in res["tables"] if t["name"] == "claims") == 2
    # registered + resolvable via the shared seeds path (so browse endpoints work over it)
    assert await dao.get_dataset(res["id"])
    assert seeds.seed_db_path(res["id"]) is not None
    assert seeds.company_schema(res["id"])   # introspection works through the registry


# ---------------------------------------------------------------- (b) csv inference
def test_csv_to_sqlite_infers_types(tmp_path):
    db_path = tmp_path / "csv.db"
    datasets.csvs_to_sqlite(db_path, [("nums.csv", b"a,b,c\n1,2.5,x\n3,4.5,y\n10,6.0,z\n")])
    con = sqlite3.connect(db_path)
    try:
        cols = {r[1]: r[2] for r in con.execute("PRAGMA table_info(nums)")}
        n = con.execute("SELECT count(*) FROM nums").fetchone()[0]
    finally:
        con.close()
    assert cols == {"a": "INTEGER", "b": "REAL", "c": "TEXT"}
    assert n == 3


# ---------------------------------------------------------------- (d) codebase walk
def test_codebase_walk_over_app(tmp_path):
    db_path = tmp_path / "code.db"
    out = datasets.walk_codebase(BACKEND_ROOT / "app", db_path)
    assert out["files"] > 0
    con = sqlite3.connect(db_path)
    try:
        paths = {r[0] for r in con.execute("SELECT path FROM files")}
        has_content = con.execute("SELECT content FROM files WHERE path LIKE '%main.py%'").fetchone()
    finally:
        con.close()
    assert any(p.endswith("main.py") for p in paths)
    assert has_content and "FastAPI" in has_content[0]
    assert ".py" in out["code_map"]["languages"]


# ---------------------------------------------------------------- listing merge
async def test_datasets_listing_merges_builtin_and_custom():
    from app.api.sandbox import companies

    await dao.register_dataset(dataset_id="acme_corp", name="Acme Corp", blurb="uploaded",
                               origin="upload", kind="rows", db_path="/tmp/acme.db",
                               meta={"tables": [{"name": "widgets", "rows": 12}],
                                     "suggested_prompts": ["Summarize widgets"]})
    out = (await companies())["companies"]
    by_id = {c["id"]: c for c in out}
    assert by_id["acme_corp"]["origin"] == "upload" and by_id["acme_corp"]["kind"] == "rows"
    assert by_id["acme_corp"]["suggested_prompts"] == ["Summarize widgets"]
    # builtins gained origin/kind, additively
    assert by_id["bank"]["origin"] == "builtin" and by_id["bank"]["kind"] == "rows"


# ---------------------------------------------------------------- api_style routing (no network)
async def test_api_style_resolves_on_seat_override():
    from app.boundary import secrets
    from app.models.router import _resolve_override

    key_ref = await secrets.store_secret("sk-byok")
    cid = await dao.create_connection(name="euro", base_url="https://eu.example/v1",
                                      api_key_ref=key_ref, data_class_ceiling="RAW",
                                      api_style="anthropic")
    mid = await dao.add_custom_model(connection_id=cid, provider_model_id="claude-local-1",
                                     display_name="EU Claude", flags=["merge-review"])
    await dao.set_seat_override(seat="certifier", model_key=mid, scope="global")

    binding, attrs = await _resolve_override("certifier", "job:x")
    assert binding.backend == "custom" and binding.model == "claude-local-1"
    assert attrs["api_style"] == "anthropic" and attrs["base_url"] == "https://eu.example/v1"


# ---------------------------------------------------------------- planner flagship chain (readiness)
def test_planner_flagship_openrouter_readiness_chain(monkeypatch):
    from app.models.registry import registry

    monkeypatch.setattr(settings, "model_mode", "auto")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or")
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-anthropic")
    # flagship: OpenRouter, slashed model key survives verbatim
    r = registry.resolve("planner", sovereign=False, healthy_local_nodes=set())
    assert r.backend == "openrouter" and r.model == "openai/gpt-5.6-sol"
    assert not r.use_mock and r.badge is None

    # gpt-5.5 rides the SAME openrouter key as the flagship — it's a call-time hop, so it must
    # appear in the candidate chain while openrouter is up...
    chain = [(b.backend, b.model) for b in registry.seat("planner").candidates(sovereign=False)]
    assert ("openrouter", "openai/gpt-5.5") in chain

    monkeypatch.setattr(settings, "openrouter_api_key", "")   # openrouter down kills BOTH hops -> anthropic
    r3 = registry.resolve("planner", sovereign=False, healthy_local_nodes=set())
    assert r3.backend == "anthropic" and r3.badge == "fallback-serving" and not r3.use_mock

    monkeypatch.setattr(settings, "anthropic_api_key", "")    # all keys down -> mock
    r4 = registry.resolve("planner", sovereign=False, healthy_local_nodes=set())
    assert r4.use_mock


def test_slashed_model_id_survives_everywhere():
    """The flagship key `openai/gpt-5.6-sol` carries a slash; it must survive as a registry key,
    a wire id (provider_id), and a rates key (token_rate) — it is never a URL path segment."""
    from app.metering.rates import token_rate
    from app.models.registry import registry
    assert "openai/gpt-5.6-sol" in registry.merged_models()
    assert registry.provider_id("openai/gpt-5.6-sol") == "openai/gpt-5.6-sol"
    assert token_rate("openrouter", "openai/gpt-5.6-sol") == (5.0, 30.0)


def test_planner_call_time_last_resort_is_hosted_amd(monkeypatch):
    """resolve_chain (Fix 2): with the external chain keyed AND fireworks keyed, the ordered
    dispatch candidates end with a hosted-AMD last resort before the mock terminal."""
    from app.models.registry import registry

    monkeypatch.setattr(settings, "model_mode", "auto")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "fireworks_api_key", "fw-key")
    chain = registry.resolve_chain("planner", sovereign=False, healthy_local_nodes=set())
    backends = [c.backend for c in chain]
    assert backends[0] == "openrouter"                 # ready flagship first
    assert "fireworks" in backends                     # hosted-AMD last resort appended
    assert chain[-1].use_mock                           # mock terminal
    assert backends.index("fireworks") < len(backends) - 1
    # sovereign gets NO non-local fallback (zero non-local calls, D7)
    sov = registry.resolve_chain("planner", sovereign=True, healthy_local_nodes=set())
    assert all(c.backend in ("local", "mock") for c in sov)


async def test_planner_call_time_falls_through_to_fireworks(monkeypatch):
    """Fix 2: a dispatch that RAISES (404/credit/timeout) advances to the next ready backend at CALL
    time — external chain exhausted -> hosted-AMD last resort — instead of blocking the stage."""
    from app.models import router as rmod
    from app.models.clients import ClientResult
    from app.seats.base import Message

    monkeypatch.setattr(settings, "model_mode", "auto")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or")
    monkeypatch.setattr(settings, "openai_api_key", "sk-oa")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-an")
    monkeypatch.setattr(settings, "fireworks_api_key", "fw")
    seen: list[str] = []

    async def fake_call(self, r, seat, messages, schema, conn_attrs, temperature, max_tokens, stream):
        seen.append(r.backend)
        if r.backend != "fireworks":
            raise RuntimeError(f"{r.backend} 404 model not found")   # external hop fails at call time
        return ClientResult("served by hosted-AMD", None, {"tokens_in": 5, "tokens_out": 3})

    monkeypatch.setattr(rmod.Router, "_call", fake_call)
    c = await rmod.router.complete("planner", [Message(role="user", content="plan")],
                                   scope="job:calltime", data_class="SANITIZED")
    assert c.text == "served by hosted-AMD"
    assert seen[0] == "openrouter" and "fireworks" in seen   # walked the whole chain to the last resort


# ---------------------------------------------------------------- POST /jobs corpus binding
async def test_jobs_company_binding_reaches_spec():
    from app.api.jobs import create_job

    res = await create_job({"request": "flag duplicate claims", "company": "insurer"})
    assert (res["job"].get("spec") or {}).get("company") == "insurer"
