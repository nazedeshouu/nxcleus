"""Placeholder seat modules (backend-owned) — minimal message-builders that make MockClient produce
pipeline-coherent artifacts, so the walking skeleton runs stages 0->7 before the AI engineer's real
seat modules land (brief item 7).

Each namespace here (`trust`, `planner`, ...) mirrors the entrypoint surface of the real
`app/seats/<seat>.py` module. The engine resolves seats through `app.orchestrator.seatlib.seat(name)`,
which prefers the real module and falls back to these — so the swap is zero stage edits.

Contract for every seat fn: `async def fn(complete: CompleteFn, emit: EmitFn, *, <typed inputs>) -> dict`.
`complete` is router.complete curried with scope+sovereign (seat name + data_class passed at call
time, per base.py). `emit` is scope-bound. Real seats import ONLY from app.seats.base + app.db.models.
"""
from __future__ import annotations

from app.db import models
from app.seats.base import CompleteFn, EmitFn, Message


def _msgs(system: str, user: str) -> list[Message]:
    return [Message(role="system", content=system), Message(role="user", content=user)]


_EN = "Output English only (track rule)."


async def _ask(complete: CompleteFn, seat: str, data_class: str, schema: dict | None,
               system: str, user: str, fixture: str | None = None):
    hint = f" [[fixture:{fixture}]]" if fixture else ""
    comp = await complete(seat, _msgs(system + hint + " " + _EN, user), data_class=data_class, schema=schema)
    return comp.parsed if comp.parsed is not None else {}


# --------------------------------------------------------------------------- trust
class _Trust:
    async def build_spec(self, complete: CompleteFn, emit: EmitFn, *, request: str, files: list,
                         code_map: dict, db_schema: dict, policy: dict, messages: list) -> dict:
        parsed = await _ask(
            complete, "trust", "RAW", models.SanitizedSpec.model_json_schema(),
            "You are the trust seat. Compose a SANITIZED planner brief for a stronger frontier planner: "
            "strip values, keep structure; describe the codebase/schemas well enough to plan against.",
            f"Customer request: {request}", fixture="spec_kyc",
        )
        return parsed or models.SanitizedSpec(title=request[:60]).model_dump()

    async def distill_policy(self, complete: CompleteFn, emit: EmitFn, *, sources: list) -> dict:
        parsed = await _ask(
            complete, "trust", "RAW", models.RedactionPolicy.model_json_schema(),
            "You are the trust seat. Distill the customer's confidentiality sources into a RedactionPolicy. "
            "The PII baseline is always on; add company-specific rules on top.",
            f"Sources: {sources}", fixture="policy_kyc",
        )
        return parsed or models.RedactionPolicy().model_dump()

    async def write_docs(self, complete: CompleteFn, emit: EmitFn, *, plan: dict, goal: str) -> dict:
        await _ask(complete, "trust", "RAW", None,
                   "You are the trust seat. Write a README and runbook from the certified plan.",
                   f"Goal: {goal}")
        name = plan.get("modules", [{}])[0].get("name", "process")
        return {
            "readme": f"# {plan.get('mode','build').title()} process\n\nGoal: {goal}\n\n"
                      f"Modules: {', '.join(m.get('id','') for m in plan.get('modules', []))}\n",
            "runbook": "## Runbook\n1. Provide a batch of units.\n2. Run the process.\n"
                       "3. Review any needs_review units in the queue.\n",
            "qa_report": "## QA report\nSee tickets and oracle checks in the package.\n",
            "entry_module": name,
        }

    async def sanitize_consult(self, complete: CompleteFn, emit: EmitFn, *, payload: str,
                               vault_map: dict) -> tuple[str, dict]:
        from app.boundary.sanitize import consult_sanitize

        sanitized, receipt = consult_sanitize(payload, vault_map)
        await _ask(complete, "trust", "RAW", None,
                   "You are the trust seat performing the consult residual sweep before egress.",
                   sanitized[:400])
        return sanitized, receipt


# --------------------------------------------------------------------------- planner
class _Planner:
    async def plan(self, complete: CompleteFn, emit: EmitFn, *, brief: dict) -> dict:
        async def _stream(chunk: str) -> None:
            await emit("plan.delta", {"delta": chunk})

        system = ("You are the planner seat. Design an executable work order for a fleet of parallel "
                  "sub-agents, a conductor between waves, a consolidator, and adversarial QA. Choose "
                  "independent or interdependent parallelism; emit modules + interfaces + dag with "
                  "task_flags; the BoM is mandatory.")
        mode = (brief.get("mode") or {}).get("confirmed") or (brief.get("mode") or {}).get("recommended")
        fixture = "planner_process" if mode == "process" else "planner_kyc"
        comp = await complete("planner", _msgs(system + f" [[fixture:{fixture}]] " + _EN,
                                               f"Brief: {brief.get('title','')}"),
                              data_class="SANITIZED", schema=models.Plan.model_json_schema(), stream=_stream)
        plan = comp.parsed or models.Plan().model_dump()
        return plan

    async def replan(self, complete: CompleteFn, emit: EmitFn, *, plan: dict, findings: list,
                     scope_lock: dict) -> dict:
        await _ask(complete, "planner", "SANITIZED", None,
                   "You are the planner seat performing a constrained re-plan. Patch ONLY the locked regions.",
                   f"Scope lock: {scope_lock}; findings: {findings}")
        return {"patched_regions": scope_lock.get("only_regions", []), "patch": []}


# --------------------------------------------------------------------------- certifier
class _Certifier:
    async def certify(self, complete: CompleteFn, emit: EmitFn, *, plan: dict, raw_context: dict,
                      policy: dict) -> dict:
        parsed = await _ask(
            complete, "certifier", "RAW", models.CertifyResult.model_json_schema(),
            "You are the certifier seat. A stronger model authored this plan without the real context; "
            "find and fix everything that gap caused. Run the checklist, triage findings (amend|consult), "
            "rehydrate identifiers, emit the goal + integration tests + oracle vectors.",
            f"Plan modules: {[m.get('id') for m in plan.get('modules', [])]}", fixture="certify_kyc",
        )
        return parsed or models.CertifyResult().model_dump()

    async def triage_refine(self, complete: CompleteFn, emit: EmitFn, *, plan: dict, request: str) -> dict:
        parsed = await _ask(
            complete, "certifier", "RAW",
            {"type": "object", "properties": {"triage": {"type": "string", "enum": ["amend", "consult"]},
                                              "regions": {"type": "array", "items": {"type": "string"}},
                                              "rationale": {"type": "string"}},
             "required": ["triage"]},
            "You are the certifier seat triaging a refine request as amend (mechanical) or consult (structural).",
            f"Request: {request}",
        )
        return parsed or {"triage": "amend", "regions": [], "rationale": "mechanical change"}


# --------------------------------------------------------------------------- conductor
class _Conductor:
    async def review(self, complete: CompleteFn, emit: EmitFn, *, plan: dict, goal: str,
                     wave_outputs: list, remaining: list) -> dict:
        parsed = await _ask(
            complete, "conductor", "RAW", models.ConductorReview.model_json_schema(),
            "You are the conductor seat. Review the wave's outputs against the plan + goal. You may amend "
            "ONLY not-yet-built regions; problems in built modules become rework orders. Then green-flag.",
            f"Goal: {goal}; built this wave: {[o.get('module') for o in wave_outputs]}; remaining: {remaining}",
        )
        if parsed:
            return parsed
        # placeholder review: proceed, but on early waves refine an unbuilt region (exercises the
        # scope-locked conductor amendment beat, D8)
        amendments = []
        if len(remaining) >= 2:
            target = remaining[-1].get("id", "")
            amendments = [{"plan_ref": f"modules.{target}", "patch": {"op": "add",
                          "path": f"/modules/{target}/note", "value": "tighten error handling per wave-1 outputs"},
                          "rationale": "wave outputs suggest an unhandled edge in the not-yet-built region"}]
        return {"verdict": "amend" if amendments else "proceed",
                "wave_assessment": "outputs consistent with plan", "goal_drift": None,
                "amendments": amendments, "rework": []}


# --------------------------------------------------------------------------- coder
class _Coder:
    async def build_module(self, complete: CompleteFn, emit: EmitFn, *, module: dict,
                           interfaces: list, tests: list) -> dict:
        mid = module.get("id", "module")
        async def _stream(chunk: str) -> None:
            await emit("task.output_delta", {"module": mid, "delta": chunk})

        system = ("You are a coder seat. Implement the module against the runtime contract: pure-Python, "
                  "judgment steps via ctx.model(seat=...), never raw HTTP or hardcoded model names.")
        comp = await complete("coder", _msgs(system + " " + _EN,
                                             f"Module {mid}: {module.get('purpose','')}. "
                                             f"Provides {module.get('provides')}, consumes {module.get('consumes')}."),
                              data_class="RAW", schema=models.CoderOutput.model_json_schema(), stream=_stream)
        files = (comp.parsed or {}).get("files") or []
        if not files:
            files = [{"path": f"src/{mid}.py",
                      "content": _module_stub(mid, module)}]
        else:
            for f in files:
                f["path"] = f"src/{mid}.py"
                if not f.get("content"):
                    f["content"] = _module_stub(mid, module)
        return {"files": files, "notes": f"implemented {mid}"}

    async def fix(self, complete: CompleteFn, emit: EmitFn, *, ticket: dict, module_src: str,
                  tests: list) -> dict:
        await _ask(complete, "coder", "RAW", None,
                   "You are a coder seat fixing a defect ticket. Return the corrected module.",
                   f"Ticket: {ticket.get('title','')}")
        return {"files": [], "notes": f"fixed {ticket.get('title','')}"}


def _module_stub(mid: str, module: dict) -> str:
    provides = module.get("provides") or ["result"]
    return (
        f'"""Generated module {mid} — {module.get("purpose", "")}\n'
        f'Implements the runtime contract (04 §3). Judgment steps go through ctx.model(seat=...).\n"""\n\n'
        f"async def run_step(unit: dict, ctx) -> dict:\n"
        f"    # deterministic logic in plain Python; {module.get('algorithm', '')[:80]}\n"
        f"    ctx.log({mid!r}, module={mid!r})\n"
        f"    return {{{provides[0]!r}: unit}}\n"
    )


# --------------------------------------------------------------------------- consolidator
class _Consolidator:
    async def consolidate(self, complete: CompleteFn, emit: EmitFn, *, modules: list,
                          interfaces: list, plan: dict) -> dict:
        await _ask(complete, "consolidator", "RAW", None,
                   "You are the consolidator seat. Merge the module files into a coherent package with a "
                   "process.py entrypoint implementing the runtime contract; resolve imports; thread config.",
                   f"Modules: {[m.get('id') for m in modules]}")
        entry = _process_entrypoint(modules)
        return {"files": [{"path": "process.py", "content": entry}], "notes": "assembled process.py"}


def _process_entrypoint(modules: list) -> str:
    imports = "\n".join(f"from src.{m.get('id')} import run_step as {m.get('id')}_step"
                        for m in modules if m.get("id"))
    calls = "\n".join(f"    trace.append(await {m.get('id')}_step(unit, ctx))" for m in modules if m.get("id"))
    return (
        '"""Generated process entrypoint (runtime contract, 04 §3)."""\n'
        f"{imports}\n\n"
        "class Process:\n"
        "    input_schema = {'type': 'object'}\n"
        "    output_schema = {'type': 'object'}\n"
        "    steps = []\n\n"
        "    async def run_unit(self, unit, ctx):\n"
        "        trace = []\n"
        f"{calls or '        pass'}\n"
        "        return {'status': 'ok', 'output': trace[-1] if trace else {}, 'trace': trace}\n"
    )


# --------------------------------------------------------------------------- oracle
class _Oracle:
    async def compute(self, complete: CompleteFn, emit: EmitFn, *, vector: dict, rule_text: str) -> dict:
        # blind recomputation from the sanitized rule text only (never the plan's code) — 08 §4
        inputs = vector.get("inputs", {})
        expected = _nr1(inputs) if "sanctions_flag" in inputs else None
        await _ask(complete, "oracle", "SANITIZED", models.OracleComputation.model_json_schema(),
                   "You are the oracle seat. Compute the expected output for these inputs from the rule "
                   "text alone. Self-consistency k=3; majority verdict.",
                   f"Rule: {rule_text}; inputs: {inputs}")
        # placeholder: the k=3 votes disagree on one vector -> oracle_uncertain (a flag, not a failure)
        uncertain = str(vector.get("id", "")).endswith("2")
        votes = [expected, expected, expected] if not uncertain else [expected, expected, None]
        return {"expected": expected, "votes": votes, "uncertain": uncertain or expected is None}


def _nr1(inputs: dict) -> float:
    return round(0.5 * inputs.get("sanctions_flag", 0) + 0.3 * inputs.get("pep_flag", 0)
                 + 0.2 * inputs.get("geo_risk", 0), 6)


# --------------------------------------------------------------------------- inspector
class _Inspector:
    async def probe(self, complete: CompleteFn, emit: EmitFn, *, scenario: dict, tools=None,
                    step_budget: int = 15) -> dict | None:
        # Conformed to the ratified inspector.probe signature (scenario DICT + injected egress tools
        # + step_budget; returns a Ticket-shaped dict or None). Placeholder stays deterministic and
        # does not need to drive the real tool loop.
        title = scenario.get("title", "") if isinstance(scenario, dict) else str(scenario)
        probe_txt = scenario.get("probe", "") if isinstance(scenario, dict) else ""
        sid = scenario.get("id") if isinstance(scenario, dict) else None
        await _ask(complete, "inspector", "SANITIZED", None,
                   "You are the inspector seat probing a deployed business process. You cannot see its "
                   "code; try to break the claim; every finding needs a reproducible request/response.",
                   f"Scenario: {title} — {probe_txt}")
        await emit("qa.probe_started", {"scenario": sid, "source": scenario.get("source")
                                        if isinstance(scenario, dict) else None})
        # placeholder swarm reports the main path healthy; malformed/missing scenarios yield a finding
        if "missing" in (title + probe_txt).lower() or "malformed" in (title + probe_txt).lower():
            return {"title": f"probe: {title}", "instrument": "inspector", "severity": "minor",
                    "suspected_modules": ["mod_ocr"],
                    "repro": {"request": {"method": "POST", "path": "/run_unit"},
                              "response": {"status": 500}}}
        return None

    async def goal_check(self, complete: CompleteFn, emit: EmitFn, *, goal: str, manifest: dict,
                         ac_outcomes: list, probe_results: list) -> dict:
        parsed = await _ask(
            complete, "inspector", "SANITIZED", models.GoalCheck.model_json_schema(),
            "You are the inspector seat, elevated. Judge the deliverable against the goal statement in the "
            "customer's own terms — not against the plan (the plan may have drifted).",
            f"Goal: {goal}",
        )
        return parsed or {"verdict": "fulfilled", "gaps": []}


# module-level namespaces resolved by seatlib
trust = _Trust()
planner = _Planner()
certifier = _Certifier()
conductor = _Conductor()
coder = _Coder()
consolidator = _Consolidator()
oracle = _Oracle()
inspector = _Inspector()
