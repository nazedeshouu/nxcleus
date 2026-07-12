"""Deep-iteration reliability guards: the topology guard's plan classification (a corpus-bound
detection plan must narrow the corpus with a candidate step) and the mock-dispatch rollup
(a run that fell through to simulated backends is counted, not hidden)."""
from __future__ import annotations

import sqlite3

import pytest

from app.events import E, emit
from app.metering import meter
from app.planning.stage1 import (
    _has_analysis_candidate,
    _has_candidate_step,
    _is_detection_plan,
    _is_refusal,
    _sql_candidate_steps,
)
from app.sandbox import seeds


def _plan(steps, *, mode="process", risks=None):
    return {"mode": mode, "topology": {"steps": steps}, "risks": risks or []}


def test_topology_classification():
    # sql candidate step present -> real narrowing
    assert _has_candidate_step(_plan([{"kind": "sql", "sql": "SELECT 1"}]))
    # analysis candidate step present
    assert _has_candidate_step(_plan([{"kind": "analysis", "purpose": "trace chains"}]))
    # judgment-only topology (the lawfirm/exchange 0-flag failure) -> NO candidate step
    assert not _has_candidate_step(_plan([{"id": "judge", "per_unit": True, "prompt_spec": "read it"}]))
    # a sql step with no actual query doesn't count
    assert not _has_candidate_step(_plan([{"kind": "sql", "sql": ""}]))

    # a deliberate out-of-scope refusal (empty topology + a risk) is NOT the silent-miss failure
    assert _is_refusal(_plan([], risks=["out of scope for this company"]))
    assert not _is_refusal(_plan([{"kind": "sql", "sql": "SELECT 1"}], risks=["x"]))
    assert not _is_refusal(_plan([]))  # empty + no risk is ambiguous, not a refusal

    assert _is_detection_plan(_plan([{"kind": "sql", "sql": "SELECT 1"}]))
    assert _is_detection_plan({"mode": "process"})
    assert not _is_detection_plan({"mode": "build", "modules": [{"id": "m"}]})


def test_zero_candidate_classification():
    # sql candidate with a query -> dry-runnable; no analysis step present
    sql_plan = _plan([{"kind": "sql", "sql": "SELECT 1", "id": "c"}])
    assert len(_sql_candidate_steps(sql_plan)) == 1
    assert not _has_analysis_candidate(sql_plan)
    # an empty sql query is not a runnable candidate step
    assert _sql_candidate_steps(_plan([{"kind": "sql", "sql": ""}])) == []
    # an analysis candidate can't be dry-run at plan time -> the guard must recognise and skip it
    an_plan = _plan([{"kind": "analysis", "purpose": "trace chains"}])
    assert _sql_candidate_steps(an_plan) == []
    assert _has_analysis_candidate(an_plan)


def test_enum_gating():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE txns (direction TEXT, kind TEXT, memo TEXT, counterparty TEXT, "
                "ref TEXT, amount REAL)")
    con.executemany("INSERT INTO txns VALUES (?,?,?,?,?,?)",
                    [("credit", "deposit", f"payment for invoice {i}", f"Person {i}", f"R{i:04d}", i)
                     for i in range(60)]
                    + [("debit", "withdrawal", "cash out", "Someone", "R9999", 2)])
    # credit/debit-style low-cardinality enum columns -> surfaced as schema vocabulary
    assert set(seeds._enum_values(con, "txns", "direction", "TEXT")) == {"credit", "debit"}
    assert set(seeds._enum_values(con, "txns", "kind", "TEXT")) == {"deposit", "withdrawal"}
    # free-text / identity columns -> denied by name, never cross the boundary
    assert seeds._enum_values(con, "txns", "memo", "TEXT") is None
    assert seeds._enum_values(con, "txns", "counterparty", "TEXT") is None
    # high-cardinality text column -> excluded by the distinct-count cap
    assert seeds._enum_values(con, "txns", "ref", "TEXT") is None
    # numeric column -> not TEXT affinity
    assert seeds._enum_values(con, "txns", "amount", "REAL") is None


def test_enum_char_cap(tmp_path, monkeypatch):
    dbp = tmp_path / "capco.db"
    con = sqlite3.connect(dbp)
    con.execute("CREATE TABLE t (a TEXT, b TEXT, c TEXT, note TEXT)")
    con.executemany("INSERT INTO t VALUES (?,?,?,?)", [("x", "y", "z", f"free {i}") for i in range(5)])
    con.commit()
    con.close()
    monkeypatch.setattr(seeds, "_SEEDS_DIR", tmp_path)
    monkeypatch.setattr(seeds, "_ENUM_CHAR_BUDGET", 20)   # room for ~1 enum column's values, not all 3

    cols = seeds.company_schema("capco", values=True)[0]["columns"]
    assert [c.split(" (")[0] for c in cols] == ["a", "b", "c", "note"]   # column list never truncated
    assert 1 <= len([c for c in cols if "(values:" in c]) < 3            # char cap drops later values
    # default (values=False) is unchanged for every non-brief caller
    assert all("(values:" not in c for c in seeds.company_schema("capco")[0]["columns"])


@pytest.mark.asyncio
async def test_mock_dispatch_rollup():
    scope = "run:test-rollup"
    # two live dispatches + one that fell through to a simulated (mock) backend
    await emit(scope, E.MODEL_CALL, {"seat": "coder", "backend": "fireworks", "badge": None})
    await emit(scope, E.MODEL_CALL, {"seat": "coder", "backend": "fireworks", "badge": "fallback-serving"})
    await emit(scope, E.MODEL_CALL, {"seat": "coder", "backend": "local", "badge": "mock"})
    # a different scope's mock must not leak into this one
    await emit("run:other", E.MODEL_CALL, {"seat": "coder", "badge": "mock"})

    assert await meter.mock_dispatches(scope) == 1
    assert await meter.mock_dispatches("run:none") == 0
