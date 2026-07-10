"""Model-proxy authz (06 §4, P3): only a signed, unexpired HMAC token scoped to the right process
and seat may drive the proxy — the bare-process-id form is dead, and cross-tenant tokens bounce."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.proxy import proxy_complete
from app.boundary import proxy_token
from app.db import dao


async def _make_process() -> str:
    return await dao.create_process(slug="proxy-test", name="Proxy Test", mode="process",
                                    goal="", created_from_job="job_x", created_from="build")


@pytest.mark.asyncio
async def test_bare_process_id_is_rejected():
    pid = await _make_process()
    with pytest.raises(HTTPException) as e:
        await proxy_complete({"seat": "coder", "messages": []}, x_process_token=pid)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_process_token_is_rejected():
    await _make_process()
    tok = proxy_token.sign_token("prc_someone_else", ["coder"])
    with pytest.raises(HTTPException) as e:
        await proxy_complete({"seat": "coder", "messages": []}, x_process_token=tok)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_seat_outside_token_allowlist_is_rejected():
    pid = await _make_process()
    tok = proxy_token.sign_token(pid, ["consolidator"])
    with pytest.raises(HTTPException) as e:
        await proxy_complete({"seat": "coder", "messages": []}, x_process_token=tok)
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_valid_token_completes():
    pid = await _make_process()
    tok = proxy_token.sign_token(pid, ["coder"])
    out = await proxy_complete({"seat": "coder",
                                "messages": [{"role": "user", "content": "ping"}]},
                               x_process_token=tok)
    assert "text" in out and "usage" in out
