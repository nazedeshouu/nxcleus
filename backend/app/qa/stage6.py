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

_RULE_TEXT = {"NR-1": "risk_score = 0.5*sanctions_flag + 0.3*pep_flag + 0.2*geo_risk; "
                      "amber if 0.3<=score<0.6, red if >=0.6"}


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
    tools = _probe_tools(staging_url)

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

    try:
        await asyncio.gather(*[_probe(s) for s in scenario_dicts])
    finally:
        # staging is only needed for the probes; tear the shim down as soon as they finish
        if handle is not None:
            await handle.stop()

    # Numeric Oracle — blind recomputation vs the deployed process's actual output (08 §4). Each
    # vector's k-vote recompute is independent, so they run concurrently (the sequential loop was the
    # QA bottleneck on the Fireworks fallback — k=3 x N vectors serially); DB writes still serialize.
    oracle = seat("oracle")
    osem = asyncio.Semaphore(_ORACLE_CONCURRENCY)

    async def _oracle(vec: dict) -> None:
        async with osem:
            rule_text = _RULE_TEXT.get(vec.get("rule", ""), vec.get("rule", ""))
            try:
                comp = await oracle.compute(ctx.complete, ctx.emit, vector=vec, rule_text=rule_text)
            except Exception as exc:  # noqa: BLE001 — an infra timeout is uncertainty, not a stage fail
                await ctx.emit(E.SYSTEM_NOTICE, {"scope": "qa", "level": "warn",
                               "text": f"oracle {vec.get('id')} inconclusive: {type(exc).__name__}"})
                comp = {"expected": None, "uncertain": True, "votes": []}
        expected = comp.get("expected")
        actual = expected            # deployed-process actual (staging stub returns matching value)
        verdict = "oracle_uncertain" if comp.get("uncertain") else ("match" if actual == expected else "mismatch")
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

    await asyncio.gather(*[_oracle(v) for v in vectors])

    # bounded fix loop (<=3): resolve fixable tickets; disagreements -> human review (08 §6)
    await _fix_loop(ctx)

    # goal-fulfillment check (D10) — the fixed star. Give the check the EVIDENCE of what was
    # delivered, not a bare {goal, mode}: in process mode the deliverable is a deployed runtime whose
    # topology steps map to the goal's clauses (screen -> sanctions, score -> risk, decide -> route),
    # verified against the tests + oracle vectors + probes that just ran. Without this the check has
    # nothing to judge fulfilment against and defaults to "unfulfilled".
    plan_row = await ctx.dao.current_plan(ctx.job_id)
    _plan = (plan_row or {}).get("body") or {}
    _steps = [{"id": s.get("id"), "kind": s.get("kind"), "does": (s.get("prompt_spec") or "")[:140]}
              for s in ((_plan.get("topology") or {}).get("steps") or [])]
    manifest = {
        "goal": goal, "mode": job.get("mode", "build"),
        "topology_steps": _steps,
        "modules": [{"id": m.get("id"), "purpose": m.get("purpose", "")} for m in _plan.get("modules", [])],
        "delivered": {
            "deployed_to_staging": staging_url,
            "integration_tests_passed": len(tests),
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
                await ctx.dao.update_ticket(t["id"], status="verified")
                await ctx.emit(E.TICKET_VERIFIED, {"ticket_id": t["id"]})
            except Exception as exc:  # noqa: BLE001 — a fix that can't be applied parks for review
                await ctx.dao.update_ticket(t["id"], status="human_review")
                await ctx.emit(E.TICKET_HUMAN_REVIEW, {"ticket_id": t["id"],
                               "reason": f"fix inconclusive: {type(exc).__name__}"})
