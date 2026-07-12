"""Hardening-wave regressions (2026-07-10): B1 raw-request anchor, sql-step guard,
execute_topology with sql + judgment steps, clarifying intake park/resume."""
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3

import pytest

from app.db import dao
from app.db.engine import db
from app.models.router import router
from app.orchestrator.engine import engine
from app.sandbox import seeds


async def _wait_status(job_id: str, statuses: set[str], timeout: float = 60.0) -> dict:
    for _ in range(int(timeout * 20)):
        job = await dao.get_job(job_id)
        if job and job["status"] in statuses:
            return job
        await asyncio.sleep(0.05)
    return await dao.get_job(job_id)


async def test_b1_raw_request_survives_intake_spec_overwrite():
    """Intake overwrites job.spec with the sanitized brief; the certifier's RAW anchor must still
    see the original request (jobs.request column), not an empty string."""
    raw = "run kyc/aml onboarding checks for ACME with a 0.6 red threshold"
    job_id = await dao.create_job(title="B1", request=raw)
    engine.submit_job(job_id)
    job = await _wait_status(job_id, {"quoted", "done", "blocked", "aborted"})
    assert job["status"] in ("quoted", "done"), f"pipeline stalled at {job['status']}"
    # intake replaced the spec (sanitized brief has no raw request)...
    assert (job.get("spec") or {}).get("request") != raw
    # ...but the raw anchor survives where stage 2 / operate now read it
    assert job.get("request") == raw
    raw_context_request = job.get("request") or (job.get("spec") or {}).get("request", "")
    assert raw_context_request == raw


# ---------------------------------------------------------------- sql steps (T3)
def test_sql_guard_rejects_writes_and_multi_statements():
    assert seeds.safe_select("SELECT 1;") == "SELECT 1"
    assert seeds.safe_select("  WITH x AS (SELECT 1) SELECT * FROM x ").startswith("WITH")
    for bad in ("UPDATE claims SET amount=0", "delete from claims", "PRAGMA writable_schema=1",
                "ATTACH DATABASE 'x' AS y", "SELECT 1; DROP TABLE claims", ""):
        with pytest.raises(ValueError):
            seeds.safe_select(bad)


@pytest.fixture
def tiny_corpus(tmp_path, monkeypatch):
    """A throwaway corpus with two duplicate claim pairs, wired in as company 'tiny'."""
    db_file = tmp_path / "tiny.db"
    con = sqlite3.connect(db_file)
    con.executescript("""
        CREATE TABLE claims (claim_id TEXT PRIMARY KEY, policy_id TEXT, amount REAL, incident TEXT);
        INSERT INTO claims VALUES
          ('c1','p1',100.0,'2026-01-01'), ('c2','p1',101.0,'2026-01-01'),
          ('c3','p2',500.0,'2026-02-02'), ('c4','p3',500.0,'2026-03-03'),
          ('c5','p2',502.0,'2026-02-02');
    """)
    con.commit()
    con.close()
    monkeypatch.setattr(seeds, "seed_db_path", lambda c: db_file if c == "tiny" else None)
    return db_file


_PAIR_SQL = ("SELECT a.claim_id AS a_id, b.claim_id AS b_id, a.policy_id, a.amount, b.amount AS "
             "amount_b FROM claims a JOIN claims b ON a.policy_id=b.policy_id AND "
             "a.incident=b.incident AND a.claim_id<b.claim_id")


async def test_execute_topology_sql_candidates_then_judgment(tiny_corpus):
    from app.runtime.operate import execute_topology

    run_id = await dao.create_run(process_id="", version=1, kind="batch", input_ref="")
    events: list = []

    async def emit_fn(t, p=None):
        events.append((t, p))

    async def complete_fn(seat, messages, *, data_class, schema=None, **kw):
        return await router.complete(seat, messages, scope=f"run:{run_id}",
                                     data_class=data_class, schema=schema, **kw)

    topology = {"unit": {"noun": "claim"}, "steps": [
        {"id": "s_pairs", "kind": "sql", "per_unit": False, "sql": _PAIR_SQL, "label": "dup pairs"},
        {"id": "s_judge", "per_unit": True, "seat": "coder",
         "prompt_spec": "Judge whether this candidate pair is a duplicate claim.",
         "output_schema": {"type": "object", "properties": {
             "flagged": {"type": "boolean"}, "why": {"type": "string"}},
             "required": ["flagged", "why"]}},
    ]}
    summary = await execute_topology(
        scope=f"run:{run_id}", complete_fn=complete_fn, emit_fn=emit_fn, dao=dao,
        plan_topology=topology, request="find duplicate claims", corpus_units=[],
        width=2, run_id=run_id, corpus_company="tiny")

    # the SQL found exactly the two planted pairs; each became one judged unit
    assert summary["sql_rows"] == 2
    assert summary["done"] == 2
    units = await dao.list_run_units(run_id, limit=50)
    assert len(units) == 2
    assert all(u["trace"] and u["trace"][0]["step"] == "s_judge" for u in units)
    assert {("run.sql_step" == t) for t, _ in events} >= {True}


async def test_execute_topology_sql_only_rows_fill_review_queue(tiny_corpus):
    from app.runtime.operate import execute_topology

    run_id = await dao.create_run(process_id="", version=1, kind="batch", input_ref="")

    async def emit_fn(t, p=None):
        pass

    topology = {"steps": [{"id": "s_pairs", "kind": "sql", "per_unit": False, "sql": _PAIR_SQL}]}
    summary = await execute_topology(
        scope=f"run:{run_id}", complete_fn=None, emit_fn=emit_fn, dao=dao,
        plan_topology=topology, request="", corpus_units=[], width=1, run_id=run_id,
        corpus_company="tiny")
    # no flag column in the query -> the rows themselves are the findings
    assert summary["counts"]["needs_review"] == 2
    units = await dao.list_run_units(run_id, status="needs_review", limit=50)
    assert len(units) == 2
    assert units[0]["result"]["candidate"]["policy_id"]


# ---------------------------------------------------------------- clarifying intake (T5)
async def test_clarifying_intake_parks_then_resumes_via_answers():
    from app.api.jobs import post_answers

    job_id = await dao.create_job(
        title="Dup claims", request="flag duplicate claims — please clarify the delivery format")
    engine.submit_job(job_id)
    job = await _wait_status(job_id, {"awaiting_input", "quoted", "done", "blocked", "aborted"})
    assert job["status"] == "awaiting_input", f"expected park, got {job['status']}"

    questions = await dao.get_checkpoint(f"job:{job_id}", "clarifications")
    assert questions and questions[0].get("question")

    await post_answers(job_id, {"answers": [
        {"id": questions[0]["id"], "answer": "csv and a per-entity report"}]})
    job = await _wait_status(job_id, {"quoted", "done", "blocked", "aborted"})
    assert job["status"] in ("quoted", "done"), f"resume stalled at {job['status']}"
    spec = job.get("spec") or {}
    assert spec.get("clarification_answers")
    assert spec.get("deliverable", {}).get("formats") == ["csv", "report"]


# ---------------------------------------------------------------- createTool (T8)
async def _tool_complete(seat, messages, *, data_class, schema=None, **kw):
    return await router.complete(seat, messages, scope="job:tooltest",
                                 data_class=data_class, schema=schema, **kw)


def _docker_daemon_up() -> bool:
    import subprocess
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _docker_daemon_up(), reason="docker daemon unavailable")
async def test_create_tool_self_tests_registers_and_invokes():
    from app.config import settings
    from app.orchestrator import toolsmith

    # docker desktop (mac) can't mount pytest's /private/var tmp dirs — use the shared data tree
    tmp_path = settings.workspaces_dir / "tooltest-agent"
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir(parents=True)

    res = await toolsmith.create_tool(
        purpose="flag candidate rows whose two amounts are within 5% of each other",
        args_example={"rows": [{"amount": 100.0, "amount_b": 103.0}]},
        scope="job:tooltest", complete_fn=_tool_complete, agent_dir=tmp_path)
    assert res.get("tool_name") == "amount_pair_matcher", res
    assert (tmp_path / "tools" / "amount_pair_matcher.py").exists()

    rows = await db.fetchall("SELECT * FROM tools WHERE scope = 'job:tooltest'")
    assert rows and rows[0]["self_test_passed"] == 1

    out = await toolsmith.invoke_tool("job:tooltest", "amount_pair_matcher",
                                      {"rows": [{"amount": 50.0, "amount_b": 51.0},
                                                {"amount": 50.0, "amount_b": 90.0}]})
    assert out.get("findings") == [{"amount": 50.0, "amount_b": 51.0}], out


async def test_create_tool_double_self_test_failure_returns_error(tmp_path, monkeypatch):
    from app.orchestrator import codeexec, toolsmith

    calls = {"n": 0}

    async def failing_sandbox(workspace, script, *, timeout=120.0):
        calls["n"] += 1
        return {"returncode": 1, "stdout": "", "stderr": "AssertionError: missing expect_keys",
                "sandboxed": True, "timed_out": False}

    monkeypatch.setattr(codeexec, "docker_available", lambda: True)
    monkeypatch.setattr(codeexec, "run_in_sandbox", failing_sandbox)
    res = await toolsmith.create_tool(
        purpose="anything", args_example={}, scope="job:tooltest2",
        complete_fn=_tool_complete, agent_dir=tmp_path)
    assert "error" in res and "self-test failed" in res["error"]
    assert calls["n"] == 2   # build + one repair round, then structured error
    rows = await db.fetchall("SELECT * FROM tools WHERE scope = 'job:tooltest2'")
    assert rows == []   # a failed tool never registers


# ---------------------------------------------------------------- agent folders (T9)
async def test_build_agents_get_isolated_folders_and_consolidate():
    from pathlib import Path

    from app.runtime import workspace

    job_id = await dao.create_job(title="T9", request="run kyc/aml onboarding checks")
    engine.submit_job(job_id)
    job = await _wait_status(job_id, {"quoted", "blocked", "aborted"})
    assert job["status"] == "quoted"
    await dao.approve_quote(job_id)
    await engine.set_stage(job_id, "building")
    engine.submit_job(job_id)
    job = await _wait_status(job_id, {"done", "blocked", "aborted"})
    assert job["status"] == "done"

    base = workspace.job_dir(job_id)
    # each module's source landed in ITS OWN agents/<id>/src/, not a shared tree
    for mid in ("mod_ocr", "mod_risk"):
        assert (base / "agents" / mid / "src" / f"{mid}.py").exists(), mid
    # shared interface specs published read-only at stage 2
    assert (base / "shared" / "interfaces.json").exists()
    # consolidation merged the isolated folders into the single package src/ tree
    procs = [p for p in await dao.list_processes() if p["created_from_job"] == job_id]
    version = await dao.get_version(procs[0]["id"], 1)
    merged = {p.name for p in (Path(version["package_path"]) / "src").glob("*.py")}
    assert {"mod_ocr.py", "mod_risk.py"} <= merged, merged


# ---------------------------------------------------------------- abort must stick (backend-w3)
async def test_abort_survives_a_stage_finishing_late():
    """The evidence: abort landed mid-stage, then stage 2 called advance('quoted') and clobbered it.
    Reproduce the race directly — abort lands, THEN the stage tries to advance — and assert the
    terminal status is not overwritten."""
    from app.orchestrator.engine import StageContext, _persist_status
    job_id = await dao.create_job(title="abort", request="do a thing")
    await dao.update_job(job_id, status="certifying")          # engine is mid-stage
    ctx = StageContext(await dao.get_job(job_id))
    await dao.update_job(job_id, status="aborted")             # abort lands mid-stage
    await ctx.advance("quoted")                                # stage finishes, tries to advance
    assert (await dao.get_job(job_id))["status"] == "aborted"  # not clobbered

    assert await _persist_status(job_id, "aborted") is True    # terminal->terminal write still allowed
    assert await _persist_status(job_id, "building") is False  # forward transition suppressed
    assert (await dao.get_job(job_id))["status"] == "aborted"


async def test_abort_stops_the_engine_drive_loop():
    """A job already aborted must make the driver return without advancing, and the task must end."""
    job_id = await dao.create_job(title="abort2", request="do a thing")
    await dao.update_job(job_id, status="aborted")
    engine.submit_job(job_id)
    for _ in range(200):
        t = engine._tasks.get(job_id)
        if t is not None and t.done():
            break
        await asyncio.sleep(0.02)
    t = engine._tasks.get(job_id)
    assert t is not None and t.done()
    assert (await dao.get_job(job_id))["status"] == "aborted"


# ---------------------------------------------------------------- trace JSONL export
async def test_traces_export_streams_full_rows_as_jsonl():
    """GET /traces/export round-trips a seeded trace: one JSONL line per row, messages parsed,
    response + ts + model + seat + tokens/cost/latency + badge all present."""
    from app.api.traces import export_traces

    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    await db.execute(
        "INSERT INTO model_traces (id, ts, scope, seat, backend, model, zone, messages_json, "
        "response_text, parsed_ok, tokens_in, tokens_out, cost_usd, latency_ms, badge) VALUES "
        "(:id, datetime('now'), :scope, 'planner', 'openrouter', 'openai/gpt-5.6-sol', 'EXTERNAL', "
        ":msgs, 'hello', 1, 10, 5, 0.02, 1234, 'fallback-serving')",
        {"id": "trace_exp1", "scope": "job:JX", "msgs": json.dumps(msgs)},
    )
    # a row on a different scope must NOT leak into a scoped export
    await db.execute(
        "INSERT INTO model_traces (id, ts, scope, seat, backend, model, zone, messages_json, "
        "response_text, parsed_ok, tokens_in, tokens_out, cost_usd, latency_ms, badge) VALUES "
        "(:id, datetime('now'), 'job:OTHER', 'coder', 'local', 'glm-46', 'LOCAL', '[]', '', 1, "
        "1, 1, 0.0, 1, 'mock')",
        {"id": "trace_other"},
    )

    resp = await export_traces(scope="job:JX")
    body = "".join([chunk async for chunk in resp.body_iterator])
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert len(lines) == 1, "scope filter should exclude other scopes"
    row = json.loads(lines[0])
    assert row["id"] == "trace_exp1" and row["seat"] == "planner"
    assert row["model"] == "openai/gpt-5.6-sol" and row["zone"] == "EXTERNAL"
    assert row["response_text"] == "hello" and row["badge"] == "fallback-serving"
    assert row["tokens_in"] == 10 and row["cost_usd"] == 0.02 and row["latency_ms"] == 1234
    assert "ts" in row and row["messages"][0]["role"] == "system"
    assert "messages_json" not in row  # parsed into `messages`, not double-encoded
