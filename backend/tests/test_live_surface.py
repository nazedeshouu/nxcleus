"""Wave-2 backend surface: live model-id resolution, seat-config loading, rate card, seed
determinism, and the OCR seam. All run in mock mode (no live keys, no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ── registry: seats.yaml actually loads, and keys resolve to served provider ids ──────────────
def test_seats_yaml_loads_all_eight_seats():
    from app.models.registry import registry
    assert set(registry.seats) == {"trust", "planner", "certifier", "conductor", "coder",
                                    "consolidator", "oracle", "inspector"}
    # coder is a pool authored as bindings.default: [ ... ] — the parser must not fall back to builtin
    assert len(registry.seats["coder"].pool) >= 3


def test_provider_id_resolves_models_yaml_keys():
    from app.models.registry import registry
    # models.yaml keys -> the id sent on the wire (Fireworks/Anthropic 404 on the bare key otherwise)
    assert registry.provider_id("glm-52-hosted") == "accounts/fireworks/models/glm-5p2"
    assert registry.provider_id("deepseek-v4-pro") == "accounts/fireworks/models/deepseek-v4-pro"
    assert registry.provider_id("claude-fable-5") == "claude-fable-5"
    # pass-through for anything not in the registry (BYOK custom ids, built-in full paths)
    assert registry.provider_id("accounts/fireworks/models/glm-5p2") == "accounts/fireworks/models/glm-5p2"


def test_fireworks_fallbacks_resolve_to_served_models():
    from app.models.registry import registry
    served = {"accounts/fireworks/models/glm-5p2", "accounts/fireworks/models/deepseek-v4-pro"}
    for name in ("trust", "certifier", "consolidator", "oracle", "inspector", "coder"):
        fb = registry.seats[name].fallback
        assert fb is not None and registry.provider_id(fb.model) in served, name
    assert registry.seats["conductor"].fallback is None   # no fallback -> engine skips wave review


# ── rate card: real confirmed prices, keyed by models.yaml key ────────────────────────────────
def test_rate_card_confirmed_prices():
    from app.metering.rates import token_rate
    assert token_rate("anthropic", "claude-fable-5") == (10.0, 50.0)
    assert token_rate("fireworks", "glm-52-hosted") == (1.40, 4.40)
    assert token_rate("fireworks", "deepseek-v4-pro") == (1.74, 3.48)
    assert token_rate("local", "glm-46") == (0.0, 0.0)


# ── seed kits: deterministic, planted patterns present (companies only — no network) ──────────
def test_company_seeds_are_deterministic(tmp_path, monkeypatch):
    from infra.seeds import companies
    monkeypatch.setattr(companies, "OUT", tmp_path / "a")
    first = companies.generate_all()
    monkeypatch.setattr(companies, "OUT", tmp_path / "b")
    second = companies.generate_all()
    assert first == second                                  # fixed RNG -> byte-identical report
    # spec 09 §2 volumes + planted patterns fire
    assert first["bank"]["counts"]["customers"] == 800
    assert first["clinic"]["counts"]["lab_results"] == 4000
    assert first["lawfirm"]["counts"]["contracts"] == 200
    assert first["bank"]["planted"]["structuring_accounts"] > 0
    assert first["lawfirm"]["planted"]["auto_renew_short_notice"] > 0


# ── codeexec: real docker isolation, with a deterministic no-docker fallback ──────────────────
@pytest.mark.asyncio
async def test_codeexec_falls_back_without_docker(monkeypatch, tmp_path):
    from app.orchestrator import codeexec
    monkeypatch.setattr(codeexec, "docker_available", lambda: False)
    r = await codeexec.run_tests(workspace=str(tmp_path), tests=[{"id": "a"}, {"id": "b"}])
    assert r["sandboxed"] is False and r["passed"] == 2 and r["failed"] == 0


@pytest.mark.asyncio
async def test_codeexec_sandbox_isolation(tmp_path):
    from app.orchestrator import codeexec
    if not codeexec.docker_available():
        pytest.skip("docker not available")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("x = 1\n")
    # some Docker Desktop setups don't bind-mount tmp dirs (macOS /var/folders) — skip if so
    probe = await codeexec.run_in_sandbox(str(tmp_path), "test -f /work/src/m.py && echo OK || echo NO")
    if "OK" not in probe["stdout"]:
        pytest.skip("docker bind-mount of tmp not shared in this environment")
    # network is OFF inside the sandbox
    net = await codeexec.run_in_sandbox(
        str(tmp_path), "python -c \"import socket; socket.create_connection(('1.1.1.1',80),2)\" 2>&1; true")
    assert "Network is unreachable" in (net["stdout"] + net["stderr"])
    # valid code compiles; broken code fails — real execution, not a stub
    good = await codeexec.run_tests(workspace=str(tmp_path), tests=[{"id": "t"}])
    assert good["sandboxed"] and good["failed"] == 0
    (tmp_path / "src" / "bad.py").write_text("def f(x)\n    return x\n")
    bad = await codeexec.run_tests(workspace=str(tmp_path), tests=[{"id": "t"}])
    assert bad["failed"] >= 1


# ── OCR seam: sidecar text-layer path works with no tesseract binary ──────────────────────────
def test_ocr_reads_generated_id_document(tmp_path):
    pytest.importorskip("PIL")
    from infra.seeds.kyc import _id_image

    from app.boundary.ocr import extract_text
    doc = tmp_path / "APP-001.png"
    _id_image({"name": "Viktor Sokolov", "dob": "1979-02-14", "nationality": "GB",
               "issuer": "GB", "doc_type": "passport", "doc_number": "GB5514855",
               "issue": "2020-04-27", "expiry": "2030-04-25"}, doc)
    text, method = extract_text(doc)
    assert method in ("text-layer", "tesseract")
    assert "Viktor Sokolov" in text and "GB5514855" in text


# ── proxy token: per-process HMAC scoping (P3) ────────────────────────────────────────────────
def test_proxy_token_scoping():
    from app.boundary import proxy_token
    tok = proxy_token.sign_token("proc-A", ["coder", "consolidator"])
    claims = proxy_token.verify_token(tok)
    assert claims and claims["process"] == "proc-A"
    assert proxy_token.seat_allowed(claims, "proc-A", "coder")
    assert not proxy_token.seat_allowed(claims, "proc-B", "coder")     # wrong process
    assert not proxy_token.seat_allowed(claims, "proc-A", "planner")   # seat not in allowlist
    assert proxy_token.verify_token(tok[:-3] + "xyz") is None          # tampered signature
    assert proxy_token.verify_token("not-a-token") is None


# ── staging shim: the inspector's staging endpoint is real HTTP (P3, 04 §3) ───────────────────
@pytest.mark.asyncio
async def test_staging_shim_serves_real_http(tmp_path):
    import httpx

    from app.boundary import proxy_token
    from app.runtime import staging
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "process.py").write_text(
        "def run_unit(u):\n    return {'id': u.get('id'), 'decision': 'review'}\n")
    manifest = {"process": "p1", "goal": "g", "mode": "process",
                "unit_schema": {"type": "object", "required": ["id"]}}
    h = await staging.deploy("p1", manifest, str(tmp_path), expect_token=True)
    try:
        async with httpx.AsyncClient() as c:
            assert (await c.get(h.base_url + "/health")).json()["status"] == "ok"
            assert (await c.get(h.base_url + "/manifest")).json()["goal"] == "g"
            tok = proxy_token.sign_token("p1", ["coder"])
            r = await c.post(h.base_url + "/run_unit", json={"id": "u1"}, headers={"x-proxy-token": tok})
            assert r.status_code == 200 and r.json()["decision"] == "review"
            assert (await c.post(h.base_url + "/run_unit", json={"id": "u1"})).status_code == 401  # no token
            assert (await c.post(h.base_url + "/run_unit", json={}, headers={"x-proxy-token": tok})
                    ).status_code == 422  # missing required field
    finally:
        await h.stop()


# ── sandbox pagination: page is 1-indexed; page 1 must be the FIRST page (regression) ──────────
# Two user-reported bugs had one root cause: the frontend DataBrowser starts at page 1, the API
# computed OFFSET = page*page_size, so page 1 => OFFSET 50. Big tables "started at id 51"; small
# tables (ledger.entities has 20 rows) fell off the end and browsed EMPTY ("Aldgate has no entities").
@pytest.mark.asyncio
async def test_sandbox_browse_page1_is_first_page():
    from app.api.sandbox import browse_table
    from app.sandbox.seeds import builtin_corpus_present
    if not builtin_corpus_present():
        pytest.skip("seed corpus not generated (infra/seeds/out/*.db)")
    page1 = await browse_table("ledger", "entities", page=1)
    rows = page1["rows"]
    assert rows, "ledger.entities page 1 came back empty — off-by-a-page offset regressed"
    assert rows[0]["id"] == 1, f"page 1 should start at id 1, got {rows[0]['id']}"
    assert len(rows) == 20, f"ledger.entities has 20 rows, page 1 returned {len(rows)}"
    # page 0 clamps to the first page too (defensive), not a negative offset
    assert (await browse_table("ledger", "entities", page=0))["rows"][0]["id"] == 1
