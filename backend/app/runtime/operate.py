"""Operate phase — real run execution (04 §4) + process-mode corpus fan-out (03 §8).

One topology executor serves BOTH the stage-4 build fan-out and registered-process runs
(`drive_run`): real corpus units, real per-unit metering, sql candidate steps (cross-row
detections), honest warranty spot-checks, and run artifacts (findings.csv + report.html).
No synthetic units or scripted verdicts anywhere (hardening 2026-07-10, S1).
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.db import dao
from app.events import E, emit, now_iso
from app.metering import meter
from app.models.registry import registry
from app.models.router import router
from app.orchestrator import codeexec
from app.seats.base import Message

_DEFAULT_STEP = {"id": "extract", "seat": "coder",
                 "prompt_spec": "Process this unit against the request and report findings.",
                 "output_schema": {"type": "object", "properties": {
                     "findings": {"type": "string"}, "flagged": {"type": "boolean"}},
                     "required": ["findings", "flagged"]}}

_FLAG_KEYS = ("flag", "flagged", "needs_review", "suspicious")


def _contains_review_signal(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("decision") == "review" or any(value.get(key) for key in _FLAG_KEYS):
            return True
        return any(_contains_review_signal(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_review_signal(child) for child in value)
    return False


def _runtime_unit_status(body: dict) -> str:
    """Honor explicit UnitResult status, then retain legacy review signals inside output."""
    status = body.get("status")
    if status in ("needs_review", "error"):
        return status
    if status != "ok":
        return "error"
    return "needs_review" if _contains_review_signal(body.get("output")) else "ok"


def _classify_process_fanout(summary: dict, artifact: dict) -> dict:
    """Classify build-time process fan-out from persisted execution evidence."""
    failed: list[str] = []
    partial: list[str] = []
    unverified: list[str] = []

    counts = summary.get("counts")
    if not isinstance(counts, dict):
        failed.append("execution counts are missing")
        counts = {}
    numeric_counts = {name: counts.get(name) for name in ("ok", "needs_review", "error")}
    if any(type(value) is not int or value < 0 for value in numeric_counts.values()):
        failed.append("execution counts are malformed")
    elif numeric_counts["error"]:
        failed.append(f"{numeric_counts['error']} unit(s) failed")

    execution_errors = summary.get("execution_errors")
    if isinstance(execution_errors, list) and execution_errors:
        failed.append(f"execution recorded {len(execution_errors)} error(s)")
    elif execution_errors not in (None, []):
        failed.append("execution error evidence is malformed")

    done = summary.get("done")
    total = summary.get("total")
    if type(done) is not int or type(total) is not int or done < 0 or total < 0:
        failed.append("execution coverage counts are malformed")
    elif done > total:
        failed.append("processed unit count exceeds selected unit count")
    else:
        if all(type(value) is int for value in numeric_counts.values()) \
                and sum(numeric_counts.values()) != done:
            failed.append("execution counts do not match processed units")
        if done < total:
            partial.append("not all selected units were processed")

    if summary.get("partial") is True:
        partial.append("execution coverage is partial")
    elif type(summary.get("partial")) is not bool:
        failed.append("partial coverage evidence is malformed")
    if summary.get("zero_candidate") is True:
        unverified.append("candidate execution surfaced zero rows")
    elif type(summary.get("zero_candidate")) is not bool:
        failed.append("zero-candidate evidence is malformed")
    if summary.get("actual_units") is not True:
        unverified.append("execution used no actual corpus units")

    mock_dispatches = summary.get("mock_dispatches")
    if type(mock_dispatches) is not int or mock_dispatches < 0:
        failed.append("model dispatch evidence is malformed")
    elif mock_dispatches:
        unverified.append("execution dispatched to the mock model backend")

    artifact_state = artifact.get("verification") if isinstance(artifact, dict) else None
    if artifact_state == "failed":
        failed.append("artifact generation failed")
    elif artifact_state != "passed" or artifact.get("degraded") is not False:
        reason = artifact.get("reason") if isinstance(artifact, dict) else None
        unverified.append(reason or "artifacts are degraded or unverified")
    else:
        raw_artifacts = artifact.get("artifacts")
        kinds = [item.get("kind") for item in raw_artifacts
                 if isinstance(item, dict)] if isinstance(raw_artifacts, list) else []
        if sorted(kinds) != ["csv", "report"]:
            unverified.append("passed artifact evidence lacks one CSV and one report")

    failed = list(dict.fromkeys(failed))
    partial = list(dict.fromkeys(partial))
    unverified = list(dict.fromkeys(unverified))
    if failed:
        return {"status": "failed", "verification": "failed",
                "reasons": [*failed, *partial, *unverified]}
    if partial:
        return {"status": "partial", "verification": "unverified",
                "reasons": [*partial, *unverified]}
    if unverified:
        return {"status": "unverified", "verification": "unverified",
                "reasons": unverified}
    return {"status": "done", "verification": "passed", "reasons": []}


# When a candidate (sql/analysis) step already established the STRUCTURAL match the request targets,
# the per-unit judge is a confirmation pass, not an independent re-derivation. Without this framing a
# judge handed both sides of a matched pair reads the incidental free-text (a re-filed claim gets
# fresh narrative + its own ids) and rejects a true finding as "different story" — the demo-critical
# duplicate-claims miss. Generic across every dataset: the SQL/tool IS the detection; the judge must
# apply the request's definition, no stricter, and treat expected within-pattern variation as noise.
_CANDIDATE_FRAME = (
    "DECISION RULE (authoritative — overrides any wording above that asks for more):\n"
    "This row was surfaced by an upstream detection step that ALREADY matched the structural "
    "pattern the request targets (matched keys, sums vs limits, shared identifiers, time-window "
    "bursts). Judge it against the request's OWN definition of a finding — applying exactly that "
    "definition, never a stricter one.\n"
    "1. The structural match is established. Differences in free-text wording, narrative, or "
    "incidental fields between the rows are EXPECTED (a duplicated or re-filed record carries fresh "
    "prose and its own ids) and are NOT, by themselves, grounds to reject. Do NOT require the rows "
    "to describe the same incident, story, or detail — the finding is defined structurally, not by "
    "matching prose.\n"
    "2. Confirm the PHENOMENON the request describes, not merely its numeric thresholds. The upstream "
    "step may cast a slightly loose or off-target net, so check this row against the request's own "
    "words: (a) its named entities and their state — if the request scopes to a described subset "
    "(a 'dormant' account, a 'closed' case, an 'external' party) and a field on this row contradicts "
    "that (status=active), set flagged=false; (b) the direction/type of event — if the request is "
    "about an inflow/reactivation/deposit and this row is an outbound debit/withdrawal/transfer, it "
    "is NOT the phenomenon, set flagged=false; (c) its quantitative qualifiers (a magnitude it calls "
    "large/material/unusual, a minimum count/run-length, a time gap, a threshold vs a limit) — the "
    "row must MEET them. Clearing the upstream filter's numbers is NOT enough; the row must be the "
    "thing the request is looking for. In your `findings` text, name which qualifier(s) it satisfies "
    "and cite the specific field and value; if a scoping field contradicts the request, say so and "
    "set flagged=false.\n"
    "3. When the request states no qualifier beyond the structural match, the structural match alone "
    "confirms the row (flagged=true). Rule out ONLY on affirmative evidence the row falls outside "
    "what the request targets — never on absent prose."
)


def _judge_schema(step: dict) -> dict:
    """A self-contained output schema for one judgment call. A planner-generated output_schema that
    is a bare named $ref (resolvable only against the plan's data_schemas, never at judge time) is
    useless to both the model and the validator — fall back to the default {findings, flagged} shape
    so the judge is actually guided and its verdict carries a flag the sweep can read."""
    schema = step.get("output_schema")
    if isinstance(schema, dict) and "$ref" not in schema and (schema.get("properties") or schema.get("type")):
        return schema
    return _DEFAULT_STEP["output_schema"]


def _judge_prompt(step: dict, content: dict, request: str, *, from_candidate: bool) -> str:
    """Assemble one judgment step's prompt for a unit (extracted so the assembly is unit-testable).
    A candidate-derived unit gets the confirmation frame LAST — as the authoritative closing rule —
    so a drifted prompt_spec that demands identical prose can't override the use case's structural
    definition of a finding; raw corpus units are judged on their own content as before."""
    if "path" in content and "content" in content:   # files corpus: path + text, not a row-JSON blob
        body = f"File: {content['path']}\n\n{str(content['content'])[:6000]}"
    else:
        body = f"candidate data:\n{json.dumps(content, default=str)[:4000]}"
    spec = step.get("prompt_spec") or "Process this unit and report findings."
    prompt = f"{spec}\n\nOriginal request: {request[:500]}\n\n{body}"
    if from_candidate:   # closing decision rule wins over an over-strict prompt_spec (last instruction)
        prompt = f"{prompt}\n\n{_CANDIDATE_FRAME}"
    return prompt


def _unit_flagged(result: dict) -> bool:
    for step_out in result.values():
        if isinstance(step_out, dict) and any(step_out.get(k) for k in _FLAG_KEYS):
            return True
    return False


def _row_ref(step_id: str, i: int, row: dict) -> str:
    """Readable unit_ref for a sql candidate row: join its *id columns, else index."""
    ids = [str(v) for k, v in row.items() if "id" in k.lower() and v is not None]
    return f"{step_id}:{'-'.join(ids)[:80]}" if ids else f"{step_id}:{i}"


def _scope_workspace_id(scope: str) -> str:
    """job:<id> -> that job's workspace; run:<id> -> a run-keyed workspace folder."""
    return scope.split(":", 1)[1] if ":" in scope else scope


async def _run_analysis_step(step: dict, units: list[tuple[str, dict]], *, scope: str,
                             complete_fn, emit_fn, run_id: str) -> list[tuple[str, dict]]:
    """One analysis candidate step: createTool (cached by scope+step id), invoke over the current
    rows, and replace the unit set with validated findings. Candidate failures are terminal."""
    from app.ids import deterministic
    from app.orchestrator import toolsmith
    from app.runtime import workspace

    step_id = step.get("id", "analysis")
    purpose = step.get("purpose") or step.get("prompt_spec") or ""
    tool_id = deterministic("tool", scope, step_id)
    cached = await toolsmith.get_tool(tool_id)
    rows_in = [content for _, content in units][:settings.sql_step_row_cap]
    if cached:
        name = cached["name"]
    else:
        res = await toolsmith.create_tool(
            purpose=purpose, args_example={"rows": rows_in[:2]}, scope=scope,
            complete_fn=complete_fn,
            agent_dir=workspace.agent_dir(_scope_workspace_id(scope), "toolsmith"),
            tool_id=tool_id)
        if "error" in res:
            reason = f"analysis step {step_id} tool not created: {str(res['error'])[:200]}"
            await emit_fn(E.SYSTEM_NOTICE, {"text": reason, "level": "error"})
            raise RuntimeError(reason)
        name = res["tool_name"]
    out = await toolsmith.invoke_tool(scope, name, {"rows": rows_in})
    findings = out.get("findings") if isinstance(out, dict) else None
    if not isinstance(findings, list) or any(not isinstance(row, dict) for row in findings):
        reason = f"analysis step {step_id} returned malformed findings: {str(out)[:200]}"
        await emit_fn(E.SYSTEM_NOTICE, {"text": reason, "level": "error"})
        raise RuntimeError(reason)
    await emit_fn(E.RUN_SQL_STEP, {"run_id": run_id, "step": step_id, "kind": "analysis",
                                   "label": step.get("label", purpose[:80]), "rows": len(findings)})
    return [(_row_ref(step_id, i, row), row) for i, row in enumerate(findings)]


async def execute_topology(*, scope: str, complete_fn, emit_fn, dao, plan_topology: dict,
                           request: str, corpus_units: list[tuple[str, dict]], width: int,
                           run_id: str, corpus_company: str | None = None,
                           process_id: str | None = None) -> dict:
    """Execute a process topology over a corpus. Called from BOTH the stage-4 fan-out and
    registered-process runs (drive_run).

    Semantics:
      - candidate steps (kind=="sql" or kind=="analysis", per_unit false) run first, in plan
        order; each result-row set REPLACES the unit set for subsequent per-unit judgment steps
        (candidates pattern). sql runs read-only against the bound corpus; analysis commissions
        a deterministic tool via createTool (cached per scope+step in the tools table) and runs
        it over the current rows ({"rows": [...]} -> {"findings": [...]}).
      - per-unit judgment steps keep the established behavior: seat-name defense, budget-stop,
        per-unit isolation, real metering through complete_fn.
      - candidate-only topologies: the final rows ARE the findings; rows carrying a truthy flag
        column — or rows with no flag column at all (the query/tool itself is the detection) —
        land as needs_review units so the review queue fills.
      - sandbox_max_units caps LLM-JUDGED units only; sql steps run the full table.

    Returns {"counts", "flagged", "done", "total", "partial", "sql_rows", "spot_checks",
    "discrepancies"}.
    """
    from app.boundary.errors import BudgetExceeded
    from app.sandbox import seeds

    steps = plan_topology.get("steps") or []
    candidate_steps = [s for s in steps
                       if (s.get("kind") == "sql" and s.get("sql"))
                       or (s.get("kind") == "analysis" and (s.get("purpose") or s.get("prompt_spec")))]
    judgment_steps = [s for s in steps
                      if s.get("per_unit", True) and s.get("kind") not in ("sql", "aggregate",
                                                                           "analysis")]
    if not candidate_steps and not judgment_steps:
        judgment_steps = [_DEFAULT_STEP]

    units = list(corpus_units)
    sql_rows = 0
    for step in candidate_steps:
        if step.get("kind") == "sql":
            try:
                rows = await asyncio.to_thread(
                    seeds.run_select, corpus_company, step["sql"],
                    cap=settings.sql_step_row_cap, timeout_s=settings.sql_step_timeout_s)
            except Exception as exc:  # noqa: BLE001 — a broken query is a run finding, not a crash
                await emit_fn(E.SYSTEM_NOTICE, {
                    "text": f"sql step {step.get('id')} failed: {type(exc).__name__}: {str(exc)[:200]}",
                    "level": "error"})
                rows = []
            sql_rows = len(rows)
            units = [(_row_ref(step.get("id", "sql"), i, r), r) for i, r in enumerate(rows)]
            await emit_fn(E.RUN_SQL_STEP, {"run_id": run_id, "step": step.get("id"),
                                           "label": step.get("label", ""), "rows": len(rows)})
        else:   # analysis (T8 wire-up B): commission once, run deterministically over the rows
            units = await _run_analysis_step(step, units, scope=scope,
                                             complete_fn=complete_fn, emit_fn=emit_fn,
                                             run_id=run_id)
            sql_rows = len(units)

    # visible-zero backstop: a candidate step that ran but surfaced nothing is a query/literal mismatch,
    # not a clean result — surfaced in the summary (like mock_dispatches) so no path ships a silent 0.
    zero_candidate = bool(candidate_steps) and not units

    counts = {"ok": 0, "needs_review": 0, "error": 0}
    flagged: list[str] = []
    budget_stop = asyncio.Event()
    done_n = 0
    completed: list[tuple[str, dict, bool]] = []   # (ref, content, flagged) for spot-checks

    if not judgment_steps:
        # sql-only: rows are the findings themselves
        for i, (ref, row) in enumerate(units):
            has_flag_col = any(k in row for k in _FLAG_KEYS)
            is_finding = (not has_flag_col) or any(row.get(k) for k in _FLAG_KEYS)
            status = "needs_review" if is_finding else "ok"
            counts[status] += 1
            if status == "needs_review":
                flagged.append(ref)
            await dao.add_run_unit(run_id=run_id, unit_ref=ref, status=status,
                                   result={"candidate": row}, trace=[{"step": "sql", "kind": "sql"}],
                                   unit_id=f"{run_id}-u{i}")
            done_n += 1
            if done_n % 25 == 0 or done_n == len(units):
                await emit_fn(E.RUN_PROGRESS, {"run_id": run_id, "done": done_n, "total": len(units)})
        return {"counts": counts, "flagged": flagged, "done": done_n, "total": len(units),
                "partial": False, "sql_rows": sql_rows, "spot_checks": 0, "discrepancies": 0,
                "zero_candidate": zero_candidate}

    # LLM-judged units respect the cap; sql steps above already ran the full table
    units = units[:settings.sandbox_max_units]
    from_candidate = bool(candidate_steps)   # a judged unit came from a detection step -> confirm, not re-derive

    async def _judge(content: dict) -> tuple[dict, list]:
        """One unit through the judgment steps. Raises on failure; caller isolates."""
        result: dict = {}
        trace: list = []
        for step in judgment_steps:
            seat_name = step.get("seat") or "coder"
            if seat_name not in registry.seats or seat_name == "planner":
                seat_name = "coder"   # live planners invent seat names; RAW never routes EXTERNAL
            prompt = _judge_prompt(step, content, request, from_candidate=from_candidate)
            comp = await complete_fn(seat_name, [Message(role="user", content=prompt)],
                                     data_class="RAW", schema=_judge_schema(step))
            result[step.get("id") or "step"] = comp.parsed or {}
            trace.append({"step": step.get("id") or "step", "seat": seat_name})
        return result, trace

    sem = asyncio.Semaphore(max(1, width))

    async def _unit(i: int, unit_ref: str, content: dict) -> None:
        nonlocal done_n
        async with sem:
            if budget_stop.is_set():
                return
            status = "ok"
            try:
                result, trace = await _judge(content)
                if _unit_flagged(result):
                    status = "needs_review"
            except BudgetExceeded:
                budget_stop.set()
                return
            except Exception as exc:  # per-unit isolation — one bad unit never kills the sweep
                status, result, trace = "error", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, []
            counts[status] += 1
            if status == "needs_review":
                flagged.append(unit_ref)
            if status != "error":
                completed.append((unit_ref, content, status == "needs_review"))
            await dao.add_run_unit(run_id=run_id, unit_ref=unit_ref, status=status,
                                   result=result, trace=trace, unit_id=f"{run_id}-u{i}")
            done_n += 1
            await emit_fn(E.RUN_UNIT_COMPLETED, {"run_id": run_id, "unit": unit_ref, "status": status})
            if done_n % 5 == 0 or done_n == len(units):
                await emit_fn(E.RUN_PROGRESS, {"run_id": run_id, "done": done_n, "total": len(units)})

    await asyncio.gather(*[_unit(i, ref, content) for i, (ref, content) in enumerate(units)])

    # honest warranty spot-checks (08 §6): re-run K random completed units a second time and
    # compare the flagged verdicts — a real discrepancy files a real ticket. No rehearsed beats.
    spot_checks = discrepancies = 0
    if process_id and completed and not budget_stop.is_set():
        for ref, content, was_flagged in random.sample(completed, min(3, len(completed))):
            spot_checks += 1
            try:
                re_result, _ = await _judge(content)
                match = _unit_flagged(re_result) == was_flagged
            except Exception:  # noqa: BLE001 — an inconclusive re-run is not a discrepancy
                continue
            await emit_fn(E.RUN_SPOTCHECK, {"run_id": run_id, "unit": ref,
                                            "verdict": "match" if match else "mismatch"})
            if not match:
                discrepancies += 1
                tid = await dao.create_ticket(
                    scope=f"process:{process_id}", source="warranty", severity="minor",
                    title="spot-check discrepancy",
                    body={"instrument": "warranty",
                          "repro": {"unit": ref, "first_flagged": was_flagged}})
                await emit_fn(E.WARRANTY_TICKET, {"ticket_id": tid, "unit": ref})

    return {"counts": counts, "flagged": flagged, "done": done_n, "total": len(units),
            "partial": budget_stop.is_set(), "sql_rows": sql_rows,
            "spot_checks": spot_checks, "discrepancies": discrepancies,
            "zero_candidate": zero_candidate}


async def run_process_fanout(ctx, plan: dict) -> dict:
    """Process-mode stage 4'/5' — corpus fan-out + aggregation (03 §8, 09 §3–4), through the
    shared topology executor. Budget exhaustion degrades to a partial dashboard (09 §4)."""
    from app.sandbox import seeds

    existing = await ctx.get_checkpoint("fanout_result")
    if isinstance(existing, dict) and existing.get("status") in {
        "done", "failed", "partial", "unverified",
    }:
        return existing

    job = await ctx.refresh()
    spec = job.get("spec") or {}
    request = job.get("request") or (spec.get("request", "") if isinstance(spec, dict) else "")
    topology = plan.get("topology") or {}
    unit_def = topology.get("unit") or {}
    noun = unit_def.get("noun") or "unit"

    company = spec.get("company") if isinstance(spec, dict) else None
    units = seeds.load_units(company, source=unit_def.get("source"), noun=noun,
                             cap=settings.sandbox_max_units)
    actual_units = bool(units)
    if not actual_units:
        # ponytail: no corpus attached (non-sandbox process job) -> nominal refs; real customer
        # corpus intake (uploads/connectors) is post-deadline scope
        units = [(f"{noun}-{i}", {"ref": f"{noun}-{i}"}) for i in range(6)]

    kind = "sandbox" if job.get("origin") == "sandbox" else "batch"
    run_id = await ctx.dao.create_run(process_id="", version=1, kind=kind, input_ref=str(len(units)))
    await ctx.checkpoint("fanout_run_id", run_id)
    await ctx.dao.update_run(run_id, status="running")
    await ctx.emit(E.RUN_STARTED, {"run_id": run_id, "kind": kind, "units": len(units)})

    baseline = (await meter.scope_totals(ctx.scope))["cost_usd"]   # job spend before the fan-out

    fleet = (plan.get("model_bom") or {}).get("fleet") or {}
    width = max(1, min(8, int(fleet.get("parallel_width") or 4)))

    try:
        summary = await execute_topology(
            scope=ctx.scope, complete_fn=ctx.complete, emit_fn=ctx.emit, dao=ctx.dao,
            plan_topology=topology, request=request, corpus_units=units, width=width,
            run_id=run_id, corpus_company=company)
    except Exception as exc:  # noqa: BLE001 - persist terminal evidence before Stage 4 blocks
        reason = f"{type(exc).__name__}: {str(exc)[:240]}"
        summary = {
            "counts": {"ok": 0, "needs_review": 0, "error": 1},
            "flagged": [], "done": 1, "total": len(units), "partial": True,
            "sql_rows": 0, "spot_checks": 0, "discrepancies": 0,
            "zero_candidate": False, "execution_errors": [reason],
        }
        await ctx.emit(E.SYSTEM_NOTICE, {
            "run_id": run_id, "text": f"process fan-out failed: {reason}", "level": "error"})

    summary.update({
        "actual_units": actual_units,
        "synthetic_units": not actual_units,
        "mock_dispatches": await meter.mock_dispatches(ctx.scope),
    })

    stats = {"units": summary["total"], "completed": summary["done"], **summary["counts"],
             "flagged_refs": summary["flagged"][:20], "partial": summary["partial"],
             "sql_rows": summary["sql_rows"],
             "zero_candidate": summary.get("zero_candidate", False),
             "actual_units": summary["actual_units"],
             "synthetic_units": summary["synthetic_units"],
             "mock_dispatches": summary["mock_dispatches"]}
    if summary.get("zero_candidate"):
        await ctx.emit(E.SYSTEM_NOTICE, {
            "text": "candidate step ran but surfaced zero rows — 0 findings is a query/literal "
                    "mismatch, not a clean result", "level": "error"})
    fanout_usd = round((await meter.scope_totals(ctx.scope))["cost_usd"] - baseline, 6)
    cost = {"total_usd": fanout_usd,
            "cost_per_unit": round(fanout_usd / max(1, summary["done"]), 6), "frontier_calls": 0}
    # artifacts BEFORE the status flip — clients poll status==done and expect artifacts to exist
    artifact = await _finalize_artifacts(
        run_id, scope=ctx.scope, process_name=job.get("title", ""), goal=job.get("goal", ""),
        corpus=company, stats=stats, cost=cost,
        deliverable=spec.get("deliverable") if isinstance(spec, dict) else None,
        mirror_emit=ctx.emit)
    summary["artifact"] = artifact
    outcome = _classify_process_fanout(summary, artifact)
    stats.update({
        "artifact": artifact,
        "verification": outcome["verification"],
        "verification_reasons": outcome["reasons"],
        "run_status": outcome["status"],
    })
    result = {
        "run_id": run_id, **outcome, "stats": stats, "cost": cost,
        "execution": summary, "artifact": artifact,
        "demo_override": (
            outcome["verification"] == "unverified"
            and codeexec.unverified_demo_delivery_allowed()
        ),
    }
    await ctx.dao.update_run(
        run_id, status=outcome["status"], finished_at=now_iso(), stats=stats, cost=cost)
    await ctx.checkpoint("fanout_result", result)
    if outcome["verification"] == "passed":
        await ctx.emit(E.RUN_COMPLETED, {"run_id": run_id, "stats": stats, "cost": cost})
    else:
        await ctx.emit(E.SYSTEM_NOTICE, {
            "run_id": run_id,
            "text": f"process fan-out {outcome['status']}: " + "; ".join(outcome["reasons"]),
            "level": "error" if outcome["verification"] == "failed" else "warn",
        })
    if summary["partial"]:
        await ctx.emit(E.SYSTEM_NOTICE, {
            "text": f"budget cap reached — partial dashboard ({summary['done']} of "
                    f"{summary['total']} units)", "level": "warn"})
    return result


async def drive_run(run_id: str) -> None:
    """Registered-process run: load the version package, bind the corpus, execute the REAL
    topology (or the real built artifact over the staging shim) with per-run metering."""
    run = await dao.get_run(run_id)
    if run is None:
        return
    scope = f"run:{run_id}"

    async def _emit(type_: str, payload: dict | None = None) -> None:
        await emit(scope, type_, payload or {})

    try:
        await _drive_run_inner(run, run_id, scope, _emit)
    except Exception as exc:  # noqa: BLE001 — a failed run is a failed run, said out loud
        await dao.update_run(run_id, status="failed", finished_at=now_iso())
        await _emit(E.SYSTEM_NOTICE, {"text": f"run failed: {type(exc).__name__}: {str(exc)[:300]}",
                                      "level": "error"})


async def _drive_run_inner(run: dict, run_id: str, scope: str, _emit) -> None:
    from app.sandbox import seeds

    process = await dao.get_process(run["process_id"]) if run.get("process_id") else None
    version = await dao.get_version(run["process_id"], run["version"]) if process else None
    if not process or not version or not version.get("package_path"):
        await dao.update_run(run_id, status="failed", finished_at=now_iso())
        await _emit(E.SYSTEM_NOTICE, {"text": "run has no registered process/version package",
                                      "level": "error"})
        return
    package = Path(version["package_path"])

    params = run.get("params") or {}
    company = ((params.get("corpus") or {}).get("company")
               or process.get("corpus_company")
               or (run.get("input_ref", "").removeprefix("company:")
                   if str(run.get("input_ref", "")).startswith("company:") else None))
    sample = params.get("sample") or {}

    await dao.update_run(run_id, status="running")
    await _emit(E.RUN_STARTED, {"process_id": run["process_id"], "version": run["version"],
                                "kind": run["kind"], "corpus": company})

    source_job = await dao.get_job(process.get("created_from_job") or "") or {}
    request = source_job.get("request") or process.get("goal") or ""
    spec = source_job.get("spec") if isinstance(source_job.get("spec"), dict) else {}
    deliverable = params.get("deliverable") or (spec or {}).get("deliverable")

    async def complete_fn(seat, messages, *, data_class, schema=None, **kw):
        return await router.complete(seat, messages, scope=scope, data_class=data_class,
                                     schema=schema, **kw)

    topo_file = package / "topology.json"
    if topo_file.exists():
        topology = json.loads(topo_file.read_text())
        unit_def = topology.get("unit") or {}
        noun = unit_def.get("noun") or "unit"
        cap = int(sample.get("n") or settings.sandbox_max_units)
        units = seeds.load_units(company, source=unit_def.get("source"), noun=noun,
                                 cap=cap, sample=sample.get("mode", "first"))
        actual_units = bool(units)
        summary = await execute_topology(
            scope=scope, complete_fn=complete_fn, emit_fn=_emit, dao=dao,
            plan_topology=topology, request=request, corpus_units=units, width=4,
            run_id=run_id, corpus_company=company, process_id=run["process_id"])
    else:
        summary = await _drive_build_units(run, run_id, package, company, _emit)
        actual_units = summary.get("actual_units") is True

    totals = await meter.scope_totals(scope)
    mock_dispatches = await meter.mock_dispatches(scope)
    summary.update({
        "actual_units": actual_units,
        "synthetic_units": not actual_units,
        "mock_dispatches": mock_dispatches,
    })
    stats = {"units": summary["total"], "completed": summary["done"], **summary["counts"],
             "flagged_refs": summary["flagged"][:20], "partial": summary["partial"],
             "sql_rows": summary["sql_rows"], "spot_checks": summary["spot_checks"],
             "discrepancies": summary["discrepancies"], "corpus": company,
             "zero_candidate": summary.get("zero_candidate", False),
             "actual_units": actual_units, "synthetic_units": not actual_units,
             "mock_dispatches": mock_dispatches}
    if summary.get("zero_candidate"):
        await _emit(E.SYSTEM_NOTICE, {
            "text": "candidate step ran but surfaced zero rows — 0 findings is a query/literal "
                    "mismatch, not a clean result", "level": "error"})
    cost = {"total_usd": totals["cost_usd"],
            "cost_per_unit": round(totals["cost_usd"] / max(1, summary["done"]), 6),
            "frontier_calls": 0}
    # artifacts BEFORE the status flip — clients poll status==done and expect artifacts to exist
    artifact = await _finalize_artifacts(
        run_id, scope=scope, process_name=process.get("name", ""),
        goal=process.get("goal", ""), corpus=company, stats=stats, cost=cost,
        deliverable=deliverable)
    stats["artifact"] = artifact
    summary["artifact"] = artifact
    await _persist_run_outcome(run_id, summary, stats, cost, _emit)


async def _persist_run_outcome(run_id: str, summary: dict, stats: dict, cost: dict, _emit) -> str:
    """Persist and emit the same explicit terminal evidence used by build-time fan-out."""
    outcome = _classify_process_fanout(summary, stats.get("artifact"))
    status = outcome["status"]
    stats.update({
        "verification": outcome["verification"],
        "verification_reasons": outcome["reasons"],
        "run_status": status,
        "demo": summary.get("synthetic_units") is True or summary.get("mock_dispatches", 0) > 0,
    })
    await dao.update_run(run_id, status=status, finished_at=now_iso(), stats=stats, cost=cost)
    payload = {
        "run_id": run_id, "status": status, "verification": outcome["verification"],
        "reasons": outcome["reasons"], "stats": stats, "cost": cost,
        "demo": stats["demo"],
    }
    if outcome["verification"] == "passed":
        await _emit(E.RUN_COMPLETED, payload)
    else:
        await _emit(E.SYSTEM_NOTICE, {
            "run_id": run_id,
            "text": f"run {status}: " + "; ".join(outcome["reasons"]),
            "level": "error" if outcome["verification"] == "failed" else "warn",
        })
        await _emit(E.RUN_FINISHED, payload)
    return status


async def _drive_build_units(run: dict, run_id: str, package: Path, company: str | None,
                             _emit) -> dict:
    """Build-mode process (entrypoint process.py): drive units through the staging shim over real
    HTTP — the actual delivered artifact executes every unit.
    # ponytail: in-proc uvicorn shim, not the per-process container — same contract (04 §3),
    # upgrade path is the docker process-runtime image."""
    from app.boundary.egress import http_client
    from app.runtime import staging
    from app.sandbox import seeds

    manifest = {}
    mf = package / "manifest.json"
    if mf.exists():
        manifest = json.loads(mf.read_text(encoding="utf-8"))

    units = seeds.load_units(company, source=None, noun="unit", cap=settings.sandbox_max_units) \
        if company else []
    actual_units = bool(units)
    if not units:
        n = int(run["input_ref"]) if str(run.get("input_ref", "")).isdigit() else 8
        units = [(f"unit-{i}", {"id": f"unit-{i}"}) for i in range(n)]

    handle = await staging.deploy(run["process_id"], manifest, str(package))
    counts = {"ok": 0, "needs_review": 0, "error": 0}
    flagged: list[str] = []
    done = 0
    responses: list[tuple[str, dict, dict]] = []
    try:
        for i, (ref, content) in enumerate(units):
            try:
                r = await http_client.post(f"{handle.base_url}/run_unit",
                                           json={"id": ref, **content}, timeout=15.0)
                body = r.json() if "json" in r.headers.get("content-type", "") else {}
                if r.status_code != 200 or not isinstance(body, dict) or body.get("error"):
                    status = "error"
                else:
                    status = _runtime_unit_status(body)
            except Exception as exc:  # noqa: BLE001
                status, body = "error", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            counts[status] += 1
            if status == "needs_review":
                flagged.append(ref)
            if status != "error":
                responses.append((ref, content, body))
            await dao.add_run_unit(run_id=run_id, unit_ref=ref, status=status,
                                   result={"output": body}, trace=[{"step": "run_unit", "via": "staging"}],
                                   unit_id=f"{run_id}-u{i}")
            done += 1
            if done % 5 == 0 or done == len(units):
                await _emit(E.RUN_PROGRESS, {"run_id": run_id, "done": done, "total": len(units)})

        # deterministic warranty spot-checks: the same input twice must answer the same
        spot_checks = discrepancies = 0
        for ref, content, first in random.sample(responses, min(3, len(responses))):
            spot_checks += 1
            try:
                r2 = await http_client.post(f"{handle.base_url}/run_unit",
                                            json={"id": ref, **content}, timeout=15.0)
                second = r2.json() if "json" in r2.headers.get("content-type", "") else {}
            except Exception:  # noqa: BLE001
                continue
            match = second == first
            await _emit(E.RUN_SPOTCHECK, {"run_id": run_id, "unit": ref,
                                          "verdict": "match" if match else "mismatch"})
            if not match:
                discrepancies += 1
                tid = await dao.create_ticket(
                    scope=f"process:{run['process_id']}", source="warranty", severity="minor",
                    title="spot-check discrepancy",
                    body={"instrument": "warranty", "repro": {"unit": ref}})
                await _emit(E.WARRANTY_TICKET, {"ticket_id": tid, "unit": ref})
    finally:
        await handle.stop()

    return {"counts": counts, "flagged": flagged, "done": done, "total": len(units),
            "partial": counts["error"] > 0, "sql_rows": 0, "spot_checks": spot_checks,
            "discrepancies": discrepancies, "zero_candidate": False,
            "actual_units": actual_units}


async def _finalize_artifacts(run_id: str, *, scope: str, process_name: str, goal: str,
                              corpus: str | None, stats: dict, cost: dict,
                              deliverable: dict | None, mirror_emit=None) -> dict:
    """Generate findings.csv + report.html for a completed run and announce them. Never fails
    the run — a deliverable bug must not eat the sweep that produced the data."""
    from app.runtime import deliverables

    # headline facts for the report; both degrade gracefully to absent (never fail the run)
    egress = duration_s = None
    try:
        egress = await dao.trace_zone_counts(scope)
        run = await dao.get_run(run_id)
        if run and run.get("started_at"):
            duration_s = (datetime.now(UTC)
                          - datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
                          ).total_seconds()
    except Exception:  # noqa: BLE001 — a report garnish must never break delivery
        pass
    try:
        units = await dao.list_run_units(run_id, limit=settings.sql_step_row_cap)
        artifacts = deliverables.generate(run_id, process_name=process_name, goal=goal,
                                          corpus=corpus, stats=stats, cost=cost, units=units,
                                          deliverable=deliverable, egress=egress,
                                          duration_s=duration_s)
        evidence = {"verification": "passed", "degraded": False,
                    "reason": None, "artifacts": artifacts}
    except Exception as exc:  # noqa: BLE001 — a deliverable bug must never 404 a completed run
        # write a minimal stub so /report + /export.csv still resolve; a live demo can't end in 404
        reason = (f"artifact generation degraded to stub: {type(exc).__name__}: "
                  f"{str(exc)[:200]}")
        try:
            stub_stats = {
                **stats, "verification": "unverified", "run_status": "unverified",
                "verification_reasons": [reason],
            }
            artifacts = deliverables.write_stub(
                run_id, process_name=process_name, goal=goal, corpus=corpus,
                stats=stub_stats, cost=cost)
        except Exception as stub_exc:  # noqa: BLE001 - preserve missing-artifact evidence
            artifacts = []
            reason += f"; stub failed: {type(stub_exc).__name__}: {str(stub_exc)[:160]}"
        evidence = {"verification": "unverified", "degraded": True,
                    "reason": reason, "artifacts": artifacts}
        await emit(f"run:{run_id}", E.SYSTEM_NOTICE,
                   {"text": reason, "level": "warn"})
    payload = {"run_id": run_id, **evidence}
    await emit(f"run:{run_id}", E.RUN_ARTIFACTS_READY, payload)
    if mirror_emit is not None:   # fan-out watchers live on the job scope
        await mirror_emit(E.RUN_ARTIFACTS_READY, payload)
    return evidence
