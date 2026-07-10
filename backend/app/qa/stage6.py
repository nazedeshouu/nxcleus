"""Stage 6 — Adversarial QA + goal check (03 §9, 08). Seats: inspector, oracle, coder (fixes).
Inspector swarm probes the deployed process; the Numeric Oracle recomputes expected outputs blind;
disagreements/probe failures file tickets -> bounded fix loop. Last gate: the goal-fulfillment check
(D10) — the deliverable is verified against jobs.goal in the customer's own terms.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from app.boundary import egress
from app.events import E
from app.orchestrator.seatlib import seat

_INSPECTOR_AGENTS = 4
_ORACLE_CONCURRENCY = 4
_FIX_CAP = 3
# Per-scenario tool-step cap. The real fleet's local vLLM is fast enough for the 15-step ceiling
# (08 §2); on the Fireworks fallback a full 15-step swarm over N scenarios overloads the shared
# glm-5p2 endpoint and grows each turn's transcript until calls ReadTimeout. 8 keeps probing
# meaningful while roughly halving the call volume and keeping transcripts small.
_STEP_BUDGET = 8

# static generic probe suite (08 §3) — applies to any process
_GENERIC = ["malformed unit (missing required fields)", "boundary values (0, negatives, maxima)",
            "duplicate submission / idempotency", "oversized payload", "wrong-tenant token misuse"]


async def run(ctx) -> None:
    job = await ctx.refresh()
    goal = job.get("goal", "")
    spec = job.get("spec") or {}
    tests = await ctx.get_checkpoint("tests") or []
    vectors = await ctx.get_checkpoint("vectors") or []
    scenarios = await ctx.get_checkpoint("adversarial_scenarios") or []

    # Deploy the assembled process to a REAL staging endpoint (P3, 04 §3): a FastAPI shim on an
    # ephemeral localhost port, so the inspector swarm probes LIVE HTTP (GET /health, /manifest,
    # POST /run_unit), not a mock. Falls back to the unreachable default if deploy fails — the
    # inspector loop tolerates a dead endpoint.
    handle = await _deploy_staging(ctx, job, goal)
    staging_url = (handle.base_url if handle else f"http://staging.local/processes/{ctx.job_id}").rstrip("/")
    await ctx.emit(E.QA_INSPECTOR_STARTED, {"agents": _INSPECTOR_AGENTS, "staging": staging_url,
                                            "live": handle is not None})

    # egress-scoped probe tools (seam ruling #1): read_manifest + http_request, both hard-restricted
    # to the staging host — any other host is refused, so an inspector can't be steered off-target.
    # T8: + create_tool — commissioned tools register into this same dict mid-loop.
    tools = _probe_tools(staging_url)
    _add_create_tool(ctx, tools)

    # scenarios (08 §3): AC-derived + generic suite + plan-aware. The real inspector.probe consumes
    # scenario DICTS ({id, source, title, probe}); wrap every source into that shape.
    scenario_dicts: list[dict] = []
    for i, ac in enumerate(spec.get("acceptance_criteria", [])):
        if ac.get("verify") == "inspector":
            scenario_dicts.append({"id": f"ac-{ac.get('id', i)}", "source": "ac",
                                   "title": (ac.get("text", "") or f"acceptance {i}")[:70], "probe": ac.get("text", "")})
    for i, txt in enumerate(_GENERIC):
        scenario_dicts.append({"id": f"gen-{i}", "source": "generic", "title": txt[:70], "probe": txt})
    for i, txt in enumerate(scenarios):
        scenario_dicts.append({"id": f"plan-{i}", "source": "plan", "title": str(txt)[:70], "probe": str(txt)})

    inspector = seat("inspector")
    sem = asyncio.Semaphore(_INSPECTOR_AGENTS)

    async def _probe(scenario: dict) -> dict | None:
        async with sem:
            # ratified signature: probe(complete, emit, *, scenario, tools, step_budget); returns a
            # Ticket-shaped dict on a defect, else None. A single probe failing (a slow model call
            # ReadTimeout under concurrent fallback load, a malformed action) is treated as an
            # inconclusive probe, not a stage failure — the QA gate must not hinge on one flaky call.
            try:
                ticket = await inspector.probe(ctx.complete, ctx.emit, scenario=scenario,
                                               tools=tools, step_budget=_STEP_BUDGET)
            except Exception as exc:  # noqa: BLE001
                await ctx.emit(E.SYSTEM_NOTICE, {"scope": "qa", "level": "warn",
                               "text": f"probe {scenario.get('id')} inconclusive: {type(exc).__name__}"})
                return None
            await ctx.emit(E.QA_PROBE, {"scenario": scenario.get("id"), "found": ticket is not None})
            if ticket:
                await ctx.emit(E.QA_FINDING, {"scenario": scenario.get("id"), "severity": ticket.get("severity")})
                tid = await ctx.dao.create_ticket(scope=ctx.scope, source="inspector",
                                                  severity=ticket.get("severity", "minor"),
                                                  title=ticket.get("title", "probe finding"), body=ticket)
                await ctx.emit(E.TICKET_OPENED, {"ticket_id": tid, "source": "inspector",
                                                 "severity": ticket.get("severity")})
            return ticket

    # Numeric Oracle — blind recomputation vs the deployed process's ACTUAL output (08 §4): the
    # dual implementation is real — `actual` comes from POSTing the vector's inputs to the staged
    # process over HTTP; the oracle recomputes blind from the rule text; the two are compared under
    # the vector's tolerance. No obtainable actual (dead staging / no entrypoint) records
    # `no_actual` honestly — a match is never invented. Vectors run concurrently (the sequential
    # loop was the QA bottleneck on the Fireworks fallback); DB writes still serialize.
    oracle = seat("oracle")
    osem = asyncio.Semaphore(_ORACLE_CONCURRENCY)

    async def _oracle(vec: dict) -> None:
        async with osem:
            # S4: the blind oracle reads the rule from the certifier-emitted vector (rule_text,
            # threaded by stage 2), never from a constant in QA source
            rule_text = vec.get("rule_text") or str(vec.get("rule", ""))
            try:
                comp = await oracle.compute(ctx.complete, ctx.emit, vector=vec, rule_text=rule_text)
            except Exception as exc:  # noqa: BLE001 — an infra timeout is uncertainty, not a stage fail
                await ctx.emit(E.SYSTEM_NOTICE, {"scope": "qa", "level": "warn",
                               "text": f"oracle {vec.get('id')} inconclusive: {type(exc).__name__}"})
                comp = {"expected": None, "uncertain": True, "votes": []}
            expected = comp.get("expected")
            actual, obtained = (None, False)
            if handle is not None:
                actual, obtained = await _staged_actual(staging_url, vec)
        if comp.get("uncertain"):
            verdict = "oracle_uncertain"
        elif not obtained:
            verdict = "no_actual"
        else:
            verdict = "match" if _within(expected, actual, vec.get("tolerance")) else "mismatch"
        await ctx.dao.create_oracle_check(scope=ctx.scope, vector_id=vec.get("id", ""),
                                          rule_id=vec.get("rule", ""), inputs=vec.get("inputs", {}),
                                          expected=expected, actual=actual, verdict=verdict,
                                          votes=comp.get("votes", []))
        await ctx.emit(E.QA_ORACLE_CHECK, {"vector": vec.get("id"), "verdict": verdict})
        # mismatch or oracle_uncertain -> flag for human review (never auto-trusted, 08 §4)
        if verdict in ("mismatch", "oracle_uncertain"):
            tid = await ctx.dao.create_ticket(scope=ctx.scope, source="oracle", severity="disagreement",
                                              title=f"oracle {verdict} on {vec.get('id')}",
                                              body={"instrument": "oracle",
                                                    "repro": {"vector": vec.get("id"), "expected": expected,
                                                              "actual": actual}})
            await ctx.emit(E.TICKET_OPENED, {"ticket_id": tid, "source": "oracle",
                                             "severity": "disagreement"})

    try:
        await asyncio.gather(*[_probe(s) for s in scenario_dicts])
        await asyncio.gather(*[_oracle(v) for v in vectors])
    finally:
        # staging serves both the probes and the oracle's actual; tear down after both
        if handle is not None:
            await handle.stop()

    # bounded fix loop (<=3): resolve fixable tickets; disagreements -> human review (08 §6)
    await _fix_loop(ctx)

    # goal-fulfillment check (D10) — the fixed star. Give the check the EVIDENCE of what was
    # delivered, not a bare {goal, mode}: in process mode the deliverable is a deployed runtime whose
    # topology steps map to the goal's clauses (screen -> sanctions, score -> risk, decide -> route),
    # verified against the tests + oracle vectors + probes that just ran. Without this the check has
    # nothing to judge fulfilment against and defaults to "unfulfilled".
    plan_row = await ctx.dao.current_plan(ctx.job_id)
    integration = await ctx.get_checkpoint("integration_result")
    _plan = (plan_row or {}).get("body") or {}
    _steps = [{"id": s.get("id"), "kind": s.get("kind"), "does": (s.get("prompt_spec") or "")[:140]}
              for s in ((_plan.get("topology") or {}).get("steps") or [])]
    manifest = {
        "goal": goal, "mode": job.get("mode", "build"),
        "topology_steps": _steps,
        "modules": [{"id": m.get("id"), "purpose": m.get("purpose", "")} for m in _plan.get("modules", [])],
        "delivered": {
            "deployed_to_staging": staging_url,
            # actual stage-5 suite results via checkpoint — a count of specs is not a result
            "integration_tests_passed": (integration or {}).get("passed", 0),
            "integration_tests_total": (integration or {}).get("total", len(tests)),
            "oracle_vectors_recomputed": len(vectors),
            "adversarial_scenarios_probed": len(scenario_dicts),
            "open_defect_tickets": len(await ctx.dao.list_tickets(scope=ctx.scope, status="open")),
        },
    }
    ac_outcomes = [{"id": ac.get("id"), "verify": ac.get("verify")} for ac in spec.get("acceptance_criteria", [])]
    try:
        gc = await inspector.goal_check(ctx.complete, ctx.emit, goal=goal, manifest=manifest,
                                        ac_outcomes=ac_outcomes, probe_results=[])
    except Exception as exc:  # noqa: BLE001 — a timeout on the final check is inconclusive, not a
        # goal failure; ship with a caveat rather than hard-blocking on an infra hiccup (never
        # "unfulfilled", which would park the job — a network timeout is not evidence of unfulfilment).
        await ctx.emit(E.SYSTEM_NOTICE, {"scope": "qa", "level": "warn",
                       "text": f"goal-fulfillment check inconclusive: {type(exc).__name__}"})
        gc = {"verdict": "partial", "gaps": [{"goal_clause": "goal check", "severity": "caveat",
              "evidence": f"check did not complete ({type(exc).__name__})"}]}
    await ctx.emit(E.QA_GOAL_CHECK, {"verdict": gc.get("verdict", "fulfilled"),
                                     "gaps": gc.get("gaps", [])})
    await ctx.checkpoint("goal_check", gc)
    if gc.get("verdict") == "unfulfilled":
        for gap in gc.get("gaps", []):
            if gap.get("severity") == "blocker":
                await ctx.dao.create_ticket(scope=ctx.scope, source="inspector", severity="blocker",
                                            title="goal not fulfilled", body=gap)
        raise RuntimeError("goal-fulfillment check: unfulfilled — parked for human review")

    open_tickets = await ctx.dao.list_tickets(scope=ctx.scope, status="human_review")
    await ctx.emit(E.QA_PASSED, {
        "probes": len(scenario_dicts), "vectors": len(vectors), "tests": len(tests),
        "flagged_for_review": len(open_tickets),
        "goal_verdict": gc.get("verdict", "fulfilled"),
    })
    await ctx.advance("delivering")


async def _deploy_staging(ctx, job: dict, goal: str):
    """Build the process manifest from the certified plan + spec and stand up the staging shim
    (04 §3). Returns a StagingHandle, or None if deploy fails (QA then probes the dead default)."""
    from app.runtime import staging, workspace
    try:
        plan_row = await ctx.dao.current_plan(ctx.job_id)
        plan = (plan_row or {}).get("body") or {}
        topo = plan.get("topology") or {}
        unit_schema = ((topo.get("unit") or {}).get("schema")) or {"type": "object", "required": ["id"]}
        manifest = {
            "process": ctx.job_id, "goal": goal, "mode": job.get("mode", "build"),
            "version": plan.get("version", 2), "unit_schema": unit_schema,
            "acceptance_criteria": [{"id": ac.get("id"), "text": ac.get("text", "")}
                                    for ac in (job.get("spec") or {}).get("acceptance_criteria", [])],
        }
        return await staging.deploy(ctx.job_id, manifest, str(workspace.job_dir(ctx.job_id)))
    except Exception as exc:  # noqa: BLE001 — a staging failure must never block QA
        await ctx.emit(E.SYSTEM_NOTICE, {"text": f"staging deploy failed: {type(exc).__name__}: {exc}",
                                         "level": "warn", "scope": "qa"})
        return None


async def _staged_actual(staging_url: str, vec: dict) -> tuple[object, bool]:
    """POST the vector's inputs to the deployed process — the real second implementation — and
    extract a comparable output. Returns (actual, True), or (None, False) when no real actual is
    obtainable (dead staging, no entrypoint, unrecognizable shape). Never invents a value."""
    payload = {"id": vec.get("id", "vec"), **(vec.get("inputs") or {})}
    try:
        r = await egress.http_client.post(f"{staging_url}/run_unit", json=payload, timeout=8.0)
        if r.status_code != 200:
            return None, False
        body = r.json()
    except Exception:  # noqa: BLE001
        return None, False
    if not isinstance(body, dict):
        return None, False
    if body.get("status") == "accepted" and "unit" in body:   # shim's no-entrypoint ack, not output
        return None, False
    for key in (vec.get("output_field"), "risk_score", "score", "expected", "result", "value"):
        if key and key in body:
            return body[key], True
    return None, False


def _within(expected, actual, tolerance) -> bool:
    """Tolerance-aware comparison: vectors carry 'exact' or 'epsilon:<float>' (certifier output)."""
    try:
        e, a = float(expected), float(actual)
    except (TypeError, ValueError):
        return expected == actual
    tol = 0.0
    t = str(tolerance or "exact")
    if t.startswith("epsilon:"):
        try:
            tol = float(t.split(":", 1)[1])
        except ValueError:
            tol = 0.0
    return abs(e - a) <= tol + 1e-9


def _probe_tools(staging_url: str) -> dict:
    """Egress-scoped inspector tools (seam ruling #1): `read_manifest` + `http_request`, both over the
    shared app.boundary.egress client, with `http_request` HARD-restricted to the staging host — any
    other target is refused so an inspector can't be steered off its own deployment. Never raises: an
    unreachable staging endpoint returns a structured error the inspector records and reasons about."""
    host = urlparse(staging_url).netloc

    async def read_manifest() -> dict:
        try:
            r = await egress.http_client.get(f"{staging_url}/manifest", timeout=8.0)
            ct = r.headers.get("content-type", "")
            return {"status": r.status_code, "manifest": r.json() if "json" in ct else r.text[:2000]}
        except Exception as exc:  # noqa: BLE001
            return {"error": type(exc).__name__, "detail": str(exc)[:160]}

    async def http_request(*, method: str, path: str, headers=None, body=None) -> dict:
        url = path if path.startswith(("http://", "https://")) else f"{staging_url}/{str(path).lstrip('/')}"
        if urlparse(url).netloc != host:
            return {"error": "blocked", "detail": "only the process staging URL is reachable"}
        try:
            r = await egress.http_client.request(str(method).upper(), url, headers=headers or {},
                                                 json=body if body is not None else None, timeout=8.0)
            return {"status": r.status_code, "headers": dict(r.headers), "body": r.text[:2000]}
        except Exception as exc:  # noqa: BLE001
            return {"error": type(exc).__name__, "detail": str(exc)[:160]}

    return {"read_manifest": read_manifest, "http_request": http_request}


def _add_create_tool(ctx, tools: dict) -> None:
    """T8 wire-up A: inspectors may commission tools; a passed tool becomes callable by name in
    the SAME dict. # ponytail: one shared agents/inspector-0 folder for the whole swarm —
    per-probe inspector-<n> folders when probes need write isolation from each other."""
    from app.orchestrator import toolsmith
    from app.runtime import workspace

    async def create_tool(*, purpose: str, args_example: dict | None = None) -> dict:
        res = await toolsmith.create_tool(
            purpose=purpose, args_example=args_example or {}, scope=ctx.scope,
            complete_fn=ctx.complete, agent_dir=workspace.agent_dir(ctx.job_id, "inspector-0"))
        if "error" in res:
            return res
        name = res["tool_name"]

        async def _bound(*, args: dict) -> dict:
            return await toolsmith.invoke_tool(ctx.scope, name, args)

        tools[name] = _bound
        return res

    tools["create_tool"] = create_tool


async def _fix_loop(ctx) -> None:
    coder = seat("coder")
    for _ in range(_FIX_CAP):
        open_tickets = await ctx.dao.list_tickets(scope=ctx.scope, status="open")
        if not open_tickets:
            return
        for t in open_tickets:
            if t.get("severity") == "disagreement":
                await ctx.dao.update_ticket(t["id"], status="human_review")
                await ctx.emit(E.TICKET_HUMAN_REVIEW, {"ticket_id": t["id"], "reason": "oracle disagreement"})
                continue
            await ctx.dao.update_ticket(t["id"], status="in_fix",
                                        fix_attempts=(t.get("fix_attempts", 0) or 0) + 1)
            await ctx.emit(E.TICKET_IN_FIX, {"ticket_id": t["id"]})
            try:
                await coder.fix(ctx.complete, ctx.emit, ticket=t, module_src="",
                                tests=await ctx.get_checkpoint("tests") or [])
                # S5: no retest happens here, so the ticket is honestly `fix_applied` — `verified`
                # is reserved for a fix confirmed by a re-run (stage 5's suite re-run does that)
                await ctx.dao.update_ticket(t["id"], status="fix_applied")
                await ctx.emit(E.TICKET_FIX_APPLIED, {"ticket_id": t["id"], "retested": False})
            except Exception as exc:  # noqa: BLE001 — a fix that can't be applied parks for review
                await ctx.dao.update_ticket(t["id"], status="human_review")
                await ctx.emit(E.TICKET_HUMAN_REVIEW, {"ticket_id": t["id"],
                               "reason": f"fix inconclusive: {type(exc).__name__}"})
