"""Stage 6: adversarial QA and the final goal check.

This stage is a truth gate. A missing instrument or an inconclusive instrument is never folded into
success, and QA findings are parked for human review instead of claiming that an unwritten fix was
applied.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from app.boundary import egress, proxy_token
from app.config import settings
from app.events import E
from app.orchestrator import codeexec
from app.orchestrator.seatlib import seat
from app.seats.inspector import ProbeInconclusive

_INSPECTOR_AGENTS = 4
_ORACLE_CONCURRENCY = 4
_MAX_PROBES = 40
_STEP_BUDGET = 8

_GENERIC = [
    "malformed unit (missing required fields)",
    "boundary values (0, negatives, maxima)",
    "duplicate submission / idempotency",
    "oversized payload",
    "wrong-tenant token misuse",
]


def _sample_probes(scenarios: list[dict], cap: int) -> list[dict]:
    """Take a deterministic, source-diverse sample without dropping a whole probe class."""
    if len(scenarios) <= cap:
        return scenarios
    buckets: dict[str, list[dict]] = {}
    for scenario in scenarios:
        buckets.setdefault(scenario.get("source", "?"), []).append(scenario)
    active = list(buckets.values())
    selected: list[dict] = []
    while len(selected) < cap and active:
        for bucket in active:
            if bucket:
                selected.append(bucket.pop(0))
                if len(selected) >= cap:
                    break
        active = [bucket for bucket in active if bucket]
    return selected


def _integration_state(integration: object) -> str:
    if not isinstance(integration, dict):
        return "missing"
    state = integration.get("verification")
    return state if state in {"passed", "failed", "unverified"} else "invalid"


def _integration_counts(integration: object) -> tuple[dict[str, int], str | None]:
    counts = {"total": 0, "passed": 0, "failed": 0}
    if not isinstance(integration, dict):
        return counts, None
    raw = {name: integration.get(name) for name in counts}
    if any(type(value) is not int or value < 0 for value in raw.values()):
        return counts, "integration_result has invalid counts"
    counts = raw
    if counts["passed"] + counts["failed"] != counts["total"]:
        return counts, "integration_result has inconsistent counts"
    if counts["failed"] > 0:
        return counts, "integration_result contains failed tests"
    if integration.get("verification") == "passed" and (
        counts["total"] == 0 or counts["passed"] != counts["total"]
    ):
        return counts, "passed integration_result lacks a fully passing executed suite"
    return counts, None


def _normalise_goal_check(value: object) -> dict:
    if not isinstance(value, dict):
        return {"verdict": "unknown", "gaps": []}
    verdict = value.get("verdict")
    if verdict not in {"fulfilled", "partial", "unfulfilled"}:
        verdict = "unknown"
    raw_gaps = value.get("gaps")
    if not isinstance(raw_gaps, list) or any(not isinstance(gap, dict) for gap in raw_gaps):
        valid_gaps = [gap for gap in raw_gaps if isinstance(gap, dict)] \
            if isinstance(raw_gaps, list) else []
        # A known negative verdict is sufficient failure evidence even when its explanation is
        # malformed. Positive/partial claims need well-formed evidence and become inconclusive.
        normalized_verdict = "unfulfilled" if verdict == "unfulfilled" else "unknown"
        return {"verdict": normalized_verdict, "gaps": valid_gaps}
    return {"verdict": verdict, "gaps": raw_gaps}


def _counts(outcomes: list[dict], field: str, values: tuple[str, ...]) -> dict[str, int]:
    return {value: sum(1 for outcome in outcomes if outcome.get(field) == value) for value in values}


def _classify(
    *,
    integration: object,
    staging_live: bool,
    probes: list[dict],
    oracles: list[dict],
    goal_check: dict,
) -> tuple[str, list[str]]:
    """Return the strictest tri-state result plus stable, human-readable reasons."""
    failed: list[str] = []
    unverified: list[str] = []

    integration_state = _integration_state(integration)
    _counts_summary, counts_issue = _integration_counts(integration)
    if integration_state in {"missing", "invalid"}:
        failed.append(f"integration_result is {integration_state}")
    elif integration_state == "failed":
        failed.append("integration verification failed")
    elif integration_state == "unverified":
        unverified.append("integration verification is unverified")
    if counts_issue:
        failed.append(counts_issue)

    if not staging_live:
        unverified.append("staging deployment was unavailable")

    for outcome in probes:
        scenario = outcome.get("scenario") or "unknown"
        if outcome.get("outcome") == "finding":
            failed.append(f"inspector found a defect in {scenario}")
        elif outcome.get("outcome") == "inconclusive":
            unverified.append(f"inspector probe {scenario} was inconclusive")

    for outcome in oracles:
        vector = outcome.get("vector") or "unknown"
        verdict = outcome.get("verdict")
        if verdict == "mismatch":
            failed.append(f"oracle mismatch on {vector}")
        elif verdict in {"no_actual", "oracle_uncertain"}:
            unverified.append(f"oracle {verdict} on {vector}")

    goal_verdict = goal_check.get("verdict")
    blockers = [gap for gap in goal_check.get("gaps", []) if gap.get("severity") == "blocker"]
    if goal_verdict == "unfulfilled" or blockers:
        failed.append("goal-fulfillment check found an unfulfilled blocker")
    elif goal_verdict == "partial":
        unverified.append("goal-fulfillment check is partial")
    elif goal_verdict != "fulfilled":
        unverified.append("goal-fulfillment check produced no conclusive verdict")

    if settings.model_mode == "mock":
        unverified.append("mock seats cannot provide independent QA evidence")

    reasons = list(dict.fromkeys(failed + unverified))
    if failed:
        return "failed", reasons
    if unverified:
        return "unverified", reasons
    return "passed", []


async def _resume_completed_qa(ctx, job: dict, result: object) -> None:
    """Replay only the terminal gate, never QA side effects, after an engine retry."""
    if not isinstance(result, dict):
        raise RuntimeError("qa_result checkpoint is malformed")
    verification = result.get("verification")
    reasons = result.get("reasons")
    if verification not in {"passed", "failed", "unverified"} or not isinstance(reasons, list):
        raise RuntimeError("qa_result checkpoint is malformed")
    detail = "; ".join(str(reason) for reason in reasons)
    if verification == "failed":
        raise RuntimeError("QA verification failed: " + detail)
    if verification == "unverified":
        override = (
            result.get("demo_override") is True
            and codeexec.unverified_demo_delivery_allowed()
        )
        if not override:
            raise RuntimeError("QA verification unverified: " + detail)
    # If a worker died after the final checkpoint but before the state transition, finish only that
    # transition. QA events, tickets, and oracle rows were already materialized before qa_result.
    if job.get("status", "qa") == "qa":
        await ctx.advance("delivering")


async def run(ctx) -> None:
    job = await ctx.refresh()
    existing_result = await ctx.get_checkpoint("qa_result")
    if existing_result is not None:
        await _resume_completed_qa(ctx, job, existing_result)
        return

    goal = job.get("goal", "")
    spec = job.get("spec") or {}
    tests = await ctx.get_checkpoint("tests") or []
    vectors = await ctx.get_checkpoint("vectors") or []
    planned_scenarios = await ctx.get_checkpoint("adversarial_scenarios") or []
    integration = await ctx.get_checkpoint("integration_result")

    auth_token = proxy_token.sign_token(ctx.job_id, ["inspector", "oracle"])
    handle = await _deploy_staging(ctx, job, goal)
    staging_url = (handle.base_url if handle else "http://127.0.0.1:1").rstrip("/")
    await ctx.emit(E.QA_INSPECTOR_STARTED, {
        "agents": _INSPECTOR_AGENTS,
        "staging": staging_url,
        "live": handle is not None,
        "auth": "process-scoped",
    })

    tools = _probe_tools(staging_url, auth_token)
    _add_create_tool(ctx, tools)
    scenario_dicts: list[dict] = []
    for index, criterion in enumerate(spec.get("acceptance_criteria", [])):
        if criterion.get("verify") == "inspector":
            scenario_dicts.append({
                "id": f"ac-{criterion.get('id', index)}",
                "source": "ac",
                "title": (criterion.get("text", "") or f"acceptance {index}")[:70],
                "probe": criterion.get("text", ""),
            })
    for index, text in enumerate(_GENERIC):
        scenario_dicts.append({
            "id": f"gen-{index}", "source": "generic", "title": text[:70], "probe": text,
        })
    for index, text in enumerate(planned_scenarios):
        scenario_dicts.append({
            "id": f"plan-{index}", "source": "plan", "title": str(text)[:70],
            "probe": str(text),
        })

    total_scenarios = len(scenario_dicts)
    scenario_dicts = _sample_probes(scenario_dicts, _MAX_PROBES)
    if len(scenario_dicts) < total_scenarios:
        await ctx.emit(E.SYSTEM_NOTICE, {
            "scope": "qa", "level": "info",
            "text": f"probe swarm sampled to {len(scenario_dicts)} of {total_scenarios} scenarios",
        })

    inspector = seat("inspector")
    oracle = seat("oracle")
    probe_sem = asyncio.Semaphore(_INSPECTOR_AGENTS)
    oracle_sem = asyncio.Semaphore(_ORACLE_CONCURRENCY)
    ticket_outcomes: list[dict] = []

    async def open_ticket(*, source: str, severity: str, title: str, body: dict,
                          reason: str) -> str:
        ticket_id = await ctx.dao.create_ticket(
            scope=ctx.scope, source=source, severity=severity, title=title, body=body)
        ticket_outcomes.append({
            "ticket_id": ticket_id,
            "source": source,
            "severity": severity,
            "reason": reason,
            "status": "open",
        })
        await ctx.emit(E.TICKET_OPENED, {
            "ticket_id": ticket_id, "source": source, "severity": severity,
        })
        return ticket_id

    async def run_probe(scenario: dict) -> dict:
        async with probe_sem:
            try:
                finding = await inspector.probe(
                    ctx.complete, ctx.emit, scenario=scenario, tools=tools,
                    step_budget=_STEP_BUDGET)
            except ProbeInconclusive as exc:
                outcome = {
                    "scenario": scenario.get("id"), "source": scenario.get("source"),
                    "outcome": "inconclusive", "reason": str(exc),
                    "instrument_outcome": exc.outcome,
                }
            except Exception as exc:  # noqa: BLE001 - instrument failure is evidence of uncertainty
                outcome = {
                    "scenario": scenario.get("id"), "source": scenario.get("source"),
                    "outcome": "inconclusive", "reason": type(exc).__name__,
                    "instrument_outcome": "exception",
                }
            else:
                if finding:
                    severity = finding.get("severity", "major")
                    ticket_id = await open_ticket(
                        source="inspector", severity=severity,
                        title=finding.get("title", "probe finding"), body=finding,
                        reason="inspector finding requires a real fix and retest",
                    )
                    await ctx.emit(E.QA_FINDING, {
                        "scenario": scenario.get("id"), "severity": severity,
                    })
                    outcome = {
                        "scenario": scenario.get("id"), "source": scenario.get("source"),
                        "outcome": "finding", "severity": severity, "ticket_id": ticket_id,
                    }
                else:
                    outcome = {
                        "scenario": scenario.get("id"), "source": scenario.get("source"),
                        "outcome": "clear",
                    }
            await ctx.emit(E.QA_PROBE, {
                "scenario": scenario.get("id"),
                "found": outcome["outcome"] == "finding",
                "outcome": outcome["outcome"],
            })
            if outcome["outcome"] == "inconclusive":
                await ctx.emit(E.SYSTEM_NOTICE, {
                    "scope": "qa", "level": "warn",
                    "text": f"probe {scenario.get('id')} inconclusive: {outcome.get('reason')}",
                })
            return outcome

    async def run_oracle(vector: dict) -> dict:
        async with oracle_sem:
            rule_text = vector.get("rule_text") or str(vector.get("rule", ""))
            try:
                computation = await oracle.compute(
                    ctx.complete, ctx.emit, vector=vector, rule_text=rule_text)
            except Exception as exc:  # noqa: BLE001 - oracle failure is an inconclusive check
                computation = {
                    "expected": None, "uncertain": True, "votes": [],
                    "reason": type(exc).__name__,
                }
            expected = computation.get("expected")
            actual, obtained = (None, False)
            if handle is not None:
                actual, obtained = await _staged_actual(staging_url, vector, auth_token)

        if computation.get("uncertain"):
            verdict = "oracle_uncertain"
        elif not obtained:
            verdict = "no_actual"
        else:
            verdict = "match" if _within(expected, actual, vector.get("tolerance")) else "mismatch"
        await ctx.dao.create_oracle_check(
            scope=ctx.scope,
            vector_id=vector.get("id", ""),
            rule_id=vector.get("rule", ""),
            inputs=vector.get("inputs", {}),
            expected=expected,
            actual=actual,
            verdict=verdict,
            votes=computation.get("votes", []),
        )
        await ctx.emit(E.QA_ORACLE_CHECK, {"vector": vector.get("id"), "verdict": verdict})
        outcome = {
            "vector": vector.get("id"), "verdict": verdict,
            "expected": expected, "actual": actual,
        }
        if computation.get("reason"):
            outcome["reason"] = computation["reason"]
        if verdict != "match":
            ticket_id = await open_ticket(
                source="oracle", severity="disagreement",
                title=f"oracle {verdict} on {vector.get('id')}",
                body={
                    "instrument": "oracle", "verdict": verdict,
                    "repro": {"vector": vector.get("id"), "expected": expected, "actual": actual},
                },
                reason=f"oracle outcome {verdict} is unresolved",
            )
            outcome["ticket_id"] = ticket_id
        return outcome

    try:
        probe_outcomes = await asyncio.gather(*(run_probe(item) for item in scenario_dicts))
        oracle_outcomes = await asyncio.gather(*(run_oracle(item) for item in vectors))
    finally:
        if handle is not None:
            await handle.stop()

    plan_row = await ctx.dao.current_plan(ctx.job_id)
    plan = (plan_row or {}).get("body") or {}
    steps = [
        {"id": step.get("id"), "kind": step.get("kind"),
         "does": (step.get("prompt_spec") or "")[:140]}
        for step in ((plan.get("topology") or {}).get("steps") or [])
    ]
    manifest = {
        "goal": goal,
        "mode": job.get("mode", "build"),
        "topology_steps": steps,
        "modules": [
            {"id": module.get("id"), "purpose": module.get("purpose", "")}
            for module in plan.get("modules", [])
        ],
        "delivered": {
            "deployed_to_staging": staging_url if handle is not None else None,
            "integration_verification": _integration_state(integration),
            "integration_tests_passed": (integration or {}).get("passed", 0)
            if isinstance(integration, dict) else 0,
            "integration_tests_total": (integration or {}).get("total", len(tests))
            if isinstance(integration, dict) else len(tests),
            "oracle_vectors_recomputed": len(oracle_outcomes),
            "adversarial_scenarios_probed": len(probe_outcomes),
        },
    }
    ac_outcomes = [
        {"id": criterion.get("id"), "verify": criterion.get("verify")}
        for criterion in spec.get("acceptance_criteria", [])
    ]
    probe_evidence = [
        {key: outcome[key] for key in (
            "scenario", "source", "outcome", "severity", "reason", "instrument_outcome")
         if key in outcome}
        for outcome in probe_outcomes
    ]
    try:
        raw_goal_check = await inspector.goal_check(
            ctx.complete,
            ctx.emit,
            goal=goal,
            manifest=manifest,
            ac_outcomes=ac_outcomes,
            probe_results=probe_evidence,
        )
    except Exception as exc:  # noqa: BLE001 - missing goal evidence remains unverified
        await ctx.emit(E.SYSTEM_NOTICE, {
            "scope": "qa", "level": "warn",
            "text": f"goal-fulfillment check inconclusive: {type(exc).__name__}",
        })
        raw_goal_check = {
            "verdict": "partial",
            "gaps": [{
                "goal_clause": "goal check",
                "severity": "caveat",
                "evidence": f"check did not complete ({type(exc).__name__})",
            }],
        }
    goal_check = _normalise_goal_check(raw_goal_check)
    await ctx.checkpoint("goal_check", goal_check)
    await ctx.emit(E.QA_GOAL_CHECK, goal_check)

    if goal_check["verdict"] == "unfulfilled":
        gaps = goal_check["gaps"] or [{
            "goal_clause": "goal", "severity": "blocker",
            "evidence": "goal checker returned unfulfilled",
        }]
        for gap in gaps:
            await open_ticket(
                source="inspector", severity="blocker", title="goal not fulfilled", body=gap,
                reason="goal-fulfillment blocker requires human review",
            )

    await _park_qa_tickets(ctx, ticket_outcomes)

    verification, reasons = _classify(
        integration=integration,
        staging_live=handle is not None,
        probes=probe_outcomes,
        oracles=oracle_outcomes,
        goal_check=goal_check,
    )
    demo_override = verification == "unverified" and codeexec.unverified_demo_delivery_allowed()
    probe_counts = _counts(probe_outcomes, "outcome", ("clear", "finding", "inconclusive"))
    oracle_counts = _counts(
        oracle_outcomes, "verdict", ("match", "mismatch", "no_actual", "oracle_uncertain"))
    integration_counts, _counts_issue = _integration_counts(integration)
    qa_result = {
        "verification": verification,
        "integration": {
            "verification": _integration_state(integration),
            **integration_counts,
        },
        "probes": {"total": len(probe_outcomes), **probe_counts, "outcomes": probe_outcomes},
        "oracles": {"total": len(oracle_outcomes), **oracle_counts, "outcomes": oracle_outcomes},
        "tickets": {
            "opened": len(ticket_outcomes),
            "human_review": sum(1 for ticket in ticket_outcomes
                                if ticket.get("status") == "human_review"),
            "outcomes": ticket_outcomes,
        },
        "goal_verdict": goal_check["verdict"],
        "reasons": reasons,
        "demo_override": demo_override,
    }
    await ctx.checkpoint("qa_result", qa_result)
    await ctx.emit(E.QA_COMPLETED, qa_result)

    if verification == "failed":
        raise RuntimeError("QA verification failed: " + "; ".join(reasons))
    if verification == "unverified" and not demo_override:
        raise RuntimeError("QA verification unverified: " + "; ".join(reasons))
    if verification == "passed":
        await ctx.emit(E.QA_PASSED, {
            "probes": len(probe_outcomes),
            "vectors": len(oracle_outcomes),
            "tests": len(tests),
            "flagged_for_review": len(ticket_outcomes),
            "goal_verdict": goal_check["verdict"],
            "verification": "passed",
        })
    else:
        await ctx.emit(E.SYSTEM_NOTICE, {
            "scope": "qa", "level": "warn",
            "text": "unverified mock demo override enabled; delivery remains labeled unverified",
        })
    await ctx.advance("delivering")


async def _park_qa_tickets(ctx, tickets: list[dict]) -> None:
    """Park unresolved QA findings. Stage 6 does not claim a fix without a write and retest."""
    for ticket in tickets:
        if ticket.get("status") != "open":
            continue
        await ctx.dao.update_ticket(ticket["ticket_id"], status="human_review")
        ticket["status"] = "human_review"
        await ctx.emit(E.TICKET_HUMAN_REVIEW, {
            "ticket_id": ticket["ticket_id"], "reason": ticket["reason"],
        })


async def _deploy_staging(ctx, job: dict, goal: str):
    """Deploy the generated process with process-scoped token enforcement enabled."""
    from app.runtime import staging, workspace

    try:
        plan_row = await ctx.dao.current_plan(ctx.job_id)
        plan = (plan_row or {}).get("body") or {}
        topology = plan.get("topology") or {}
        unit_schema = ((topology.get("unit") or {}).get("schema")) or {
            "type": "object", "required": ["id"],
        }
        manifest = {
            "process": ctx.job_id,
            "goal": goal,
            "mode": job.get("mode", "build"),
            "version": plan.get("version", 2),
            "unit_schema": unit_schema,
            "acceptance_criteria": [
                {"id": criterion.get("id"), "text": criterion.get("text", "")}
                for criterion in (job.get("spec") or {}).get("acceptance_criteria", [])
            ],
        }
        return await staging.deploy(
            ctx.job_id, manifest, str(workspace.job_dir(ctx.job_id)), expect_token=True)
    except Exception as exc:  # noqa: BLE001 - caller records staging as unverified evidence
        await ctx.emit(E.SYSTEM_NOTICE, {
            "text": f"staging deploy failed: {type(exc).__name__}: {exc}",
            "level": "warn",
            "scope": "qa",
        })
        return None


async def _staged_actual(staging_url: str, vector: dict, auth_token: str) -> tuple[object, bool]:
    """Obtain the actual output through the authenticated staging boundary."""
    payload = {"id": vector.get("id", "vec"), **(vector.get("inputs") or {})}
    try:
        response = await egress.http_client.post(
            f"{staging_url}/run_unit",
            json=payload,
            headers={"x-proxy-token": auth_token},
            timeout=8.0,
        )
        if response.status_code != 200:
            return None, False
        body = response.json()
    except Exception:  # noqa: BLE001 - no output is an explicit no_actual outcome
        return None, False
    if not isinstance(body, dict) or body.get("status") not in {"ok", "needs_review"}:
        return None, False
    output = body.get("output")
    containers = [value for value in (output, body) if isinstance(value, dict)]
    for container in containers:
        for key in (
            vector.get("output_field"), "risk_score", "score", "expected", "result", "value",
        ):
            if key and key in container:
                return container[key], True
    if output is not None and not isinstance(output, dict):
        return output, True
    return None, False


def _within(expected: object, actual: object, tolerance: object) -> bool:
    try:
        expected_number, actual_number = float(expected), float(actual)
    except (TypeError, ValueError):
        return expected == actual
    allowed = 0.0
    tolerance_text = str(tolerance or "exact")
    if tolerance_text.startswith("epsilon:"):
        try:
            allowed = float(tolerance_text.split(":", 1)[1])
        except ValueError:
            allowed = 0.0
    return abs(expected_number - actual_number) <= allowed + 1e-9


def _headers_with_token(headers: object, auth_token: str) -> dict[str, str]:
    supplied = dict(headers) if isinstance(headers, dict) else {}
    if not any(str(name).lower() == "x-proxy-token" for name in supplied):
        supplied["x-proxy-token"] = auth_token
    return supplied


def _probe_tools(staging_url: str, auth_token: str) -> dict:
    """Create staging-only HTTP tools; explicit token headers are preserved for auth probes."""
    host = urlparse(staging_url).netloc

    async def read_manifest() -> dict:
        try:
            response = await egress.http_client.get(
                f"{staging_url}/manifest",
                headers={"x-proxy-token": auth_token},
                timeout=8.0,
            )
            content_type = response.headers.get("content-type", "")
            return {
                "status": response.status_code,
                "manifest": response.json() if "json" in content_type else response.text[:2000],
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": type(exc).__name__, "detail": str(exc)[:160]}

    async def http_request(*, method: str, path: str, headers=None, body=None) -> dict:
        url = path if path.startswith(("http://", "https://")) \
            else f"{staging_url}/{str(path).lstrip('/')}"
        if urlparse(url).netloc != host:
            return {"error": "blocked", "detail": "only the process staging URL is reachable"}
        try:
            response = await egress.http_client.request(
                str(method).upper(),
                url,
                headers=_headers_with_token(headers, auth_token),
                json=body if body is not None else None,
                timeout=8.0,
            )
            return {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": response.text[:2000],
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": type(exc).__name__, "detail": str(exc)[:160]}

    return {"read_manifest": read_manifest, "http_request": http_request}


def _add_create_tool(ctx, tools: dict) -> None:
    from app.orchestrator import toolsmith
    from app.runtime import workspace

    async def create_tool(*, purpose: str, args_example: dict | None = None) -> dict:
        result = await toolsmith.create_tool(
            purpose=purpose,
            args_example=args_example or {},
            scope=ctx.scope,
            complete_fn=ctx.complete,
            agent_dir=workspace.agent_dir(ctx.job_id, "inspector-0"),
        )
        if "error" in result:
            return result
        name = result["tool_name"]

        async def bound(*, args: dict) -> dict:
            return await toolsmith.invoke_tool(ctx.scope, name, args)

        tools[name] = bound
        return result

    tools["create_tool"] = create_tool
