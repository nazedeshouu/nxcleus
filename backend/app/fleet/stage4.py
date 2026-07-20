"""Stage 4 — Parallel code generation in waves (03 §6, build mode). Seat: coder pool + conductor.
Zone: LOCAL. The engine partitions the DAG into topological waves; within a wave, tasks dispatch to
the coder pool with capability routing (02 §7); between waves the conductor reviews (D8).

Process-mode jobs (plan.topology present) run the corpus fan-out via the operate runner instead.
"""
from __future__ import annotations

import asyncio
import re

from app.conduct import conductor
from app.events import E
from app.fleet import pool
from app.ids import deterministic
from app.metering import meter
from app.models.registry import registry
from app.orchestrator import codeexec
from app.orchestrator.seatlib import seat
from app.runtime import workspace

_MODULE_ID_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_MODULE_ID_RE = re.compile(_MODULE_ID_PATTERN)


def _modules_by_id(modules: list) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for module in modules:
        module_id = module.get("id") if isinstance(module, dict) else None
        if not isinstance(module_id, str) or _MODULE_ID_RE.fullmatch(module_id) is None:
            raise ValueError("plan contains an invalid module id")
        if module_id in indexed:
            raise ValueError(f"plan contains duplicate module id: {module_id}")
        indexed[module_id] = module
    return indexed


def waves_from_dag(dag: list, modules: list) -> list[list[dict]]:
    """Return Kahn topological levels and reject malformed or cyclic dependency graphs."""
    module_ids = set(_modules_by_id(modules))
    if not dag:
        return [[{"task": f"t_{m['id']}", "module": m["id"]} for m in modules]] if modules else []
    for task in dag:
        module_id = task.get("module") if isinstance(task, dict) else None
        if not isinstance(module_id, str) or _MODULE_ID_RE.fullmatch(module_id) is None:
            raise ValueError("build DAG task contains an invalid module id")
        if module_id not in module_ids:
            raise ValueError(f"build DAG references unknown module: {module_id}")
    module_refs = [task["module"] for task in dag]
    duplicate_refs = sorted({module_id for module_id in module_refs
                             if module_refs.count(module_id) > 1})
    if duplicate_refs:
        raise ValueError(
            f"build DAG contains duplicate module references: {', '.join(duplicate_refs)}")
    missing_modules = sorted(module_ids - set(module_refs))
    if missing_modules:
        raise ValueError(
            f"build DAG does not cover plan modules: {', '.join(missing_modules)}")
    tasks = {t["task"]: t for t in dag}
    if len(tasks) != len(dag):
        raise ValueError("build DAG contains duplicate task ids")
    missing = sorted({dep for task in dag for dep in task.get("deps", []) if dep not in tasks})
    if missing:
        raise ValueError(f"build DAG references unknown dependencies: {', '.join(missing)}")
    remaining = set(tasks)
    waves: list[list[dict]] = []
    done: set[str] = set()
    while remaining:
        ready = sorted(t for t in remaining
                       if all(dep in done for dep in tasks[t].get("deps", [])))
        if not ready:                      # a remaining graph with no ready node is cyclic
            raise ValueError(f"build DAG contains a cycle involving: {', '.join(sorted(remaining))}")
        waves.append([tasks[t] for t in ready])
        for t in ready:
            done.add(t)
            remaining.remove(t)
    return waves


async def run(ctx) -> None:
    job = await ctx.refresh()
    plan_id = await ctx.get_checkpoint("certified_plan_id")
    plan_row = await ctx.dao.get_plan(plan_id) if plan_id else await ctx.dao.current_plan(ctx.job_id)
    plan = plan_row["body"]
    plan_id = plan_row["id"]
    goal = job.get("goal", "")

    if plan.get("topology"):               # process mode — corpus fan-out (03 §8)
        from app.runtime.operate import run_process_fanout

        result = await run_process_fanout(ctx, plan)
        verification = result.get("verification") if isinstance(result, dict) else None
        reasons = result.get("reasons") if isinstance(result, dict) else None
        reason_text = "; ".join(reasons) if isinstance(reasons, list) else "missing evidence"
        if verification == "failed":
            raise RuntimeError(f"process fan-out failed: {reason_text}")
        if verification == "unverified":
            override = (
                result.get("demo_override") is True
                and codeexec.unverified_demo_delivery_allowed()
            )
            if not override:
                raise RuntimeError(f"process fan-out unverified: {reason_text}")
        elif verification != "passed":
            raise RuntimeError("process fan-out returned malformed verification evidence")
        await ctx.advance("delivering")
        return

    modules = _modules_by_id(plan.get("modules", []))
    tests = await ctx.get_checkpoint("tests") or []
    waves = waves_from_dag(plan.get("dag", []), plan.get("modules", []))
    total = len(waves)

    bom_fleet = plan.get("model_bom", {}).get("fleet", {})
    await ctx.emit(E.FLEET_PROFILE_REQUESTED, {"profile": bom_fleet.get("profile", "P2"),
                                               "nodes": bom_fleet.get("nodes", 1),
                                               "parallel_width": bom_fleet.get("parallel_width", 1)})

    coder_pool = registry.seat("coder").pool
    slots = asyncio.Semaphore(max(1, len(coder_pool) * 2))
    load: dict[str, int] = {}

    built: set[str] = set()
    for idx, wave in enumerate(waves):
        for t in wave:
            t["_wave"] = idx                    # persist wave membership on build_tasks (07 §3.1)
        await ctx.emit(E.CONDUCTOR_WAVE_STARTED, {"wave": idx + 1, "of": total,
                                                  "tasks": [t["task"] for t in wave]})
        outputs = await asyncio.gather(*[
            _build_task(ctx, t, modules.get(t.get("module", ""), {}), plan, tests, coder_pool, load, slots)
            for t in wave
        ])
        for t in wave:
            built.add(t.get("module", ""))

        unbuilt = set(modules) - built
        if total > 1 or plan.get("model_bom", {}).get("conductor", {}).get("always"):
            remaining = [modules[m] for m in unbuilt]
            await conductor.review_wave(ctx, plan=plan, plan_id=plan_id, goal=goal, wave_idx=idx,
                                        total_waves=total, wave_outputs=[o for o in outputs if o],
                                        unbuilt_module_ids=unbuilt, remaining_modules=remaining)
        await meter.tick(ctx.scope)

    await ctx.advance("consolidating")


async def _build_task(ctx, task, module, plan, tests, coder_pool, load, slots) -> dict | None:
    module_id = task.get("module", "")
    task_id = deterministic("build_task", ctx.job_id, module_id)

    # resume: skip already-built tasks (07 §4)
    if await ctx.dao.build_task_done(task_id):
        return None

    task_flags = module.get("task_flags", [])
    chosen, routing = pool.pick_member(coder_pool, task_flags, load)
    load[chosen.model] = load.get(chosen.model, 0) + 1

    async with slots:
        await ctx.dao.upsert_build_task(task_id=task_id, job_id=ctx.job_id, module_id=module_id,
                                        wave=task.get("_wave", 0), status="running",
                                        assigned_backend=chosen.model, attempts=1)
        await ctx.emit(E.TASK_STARTED, {"task": task.get("task"), "module": module_id,
                                        "backend": chosen.model, "routing": routing})

        coder = seat("coder")
        interfaces = [i for i in plan.get("interfaces", []) if module_id in i.get("consumers", [])
                      or i.get("producer") == module_id]
        module_tests = [t for t in tests if t.get("module") == module_id]
        try:
            result = await coder.build_module(ctx.complete, ctx.emit, module=module,
                                              interfaces=interfaces, tests=module_tests)
        except Exception as exc:
            # per-task failure surfaces as task.failed before the stage-level retry policy
            # (07 §3) takes over; resume skips already-done siblings on the retry
            await ctx.dao.upsert_build_task(task_id=task_id, job_id=ctx.job_id, module_id=module_id,
                                            wave=task.get("_wave", 0), status="failed",
                                            assigned_backend=chosen.model, attempts=1)
            await ctx.emit(E.TASK_FAILED, {"task": task.get("task"), "module": module_id,
                                           "backend": chosen.model,
                                           "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            raise
        # T9: each coder writes ONLY its own agents/<module_id>/ folder; its test run mounts
        # that folder alone (isolation = mount scope). Consolidation merges agents/*/ later.
        written = workspace.write_files(ctx.job_id, result.get("files", []), agent=module_id)

        test_result = await codeexec.run_tests(
            workspace=str(workspace.agent_dir(ctx.job_id, module_id)),
            tests=module_tests, module_id=module_id)
        await ctx.emit(E.TASK_TESTS, {
            "module": module_id,
            "passed": test_result["passed"],
            "failed": test_result["failed"],
            "total": test_result["total"],
            "verification": test_result["verification"],
            "sandboxed": test_result["sandboxed"],
            "reason": test_result.get("reason", ""),
        })

        verification = test_result["verification"]
        blocked_unverified = (
            verification == "unverified" and not codeexec.unverified_demo_delivery_allowed()
        )
        if verification == "failed" or blocked_unverified or verification not in {
            "passed", "unverified"
        }:
            reason = test_result.get("reason") or f"verification {verification}"
            await ctx.dao.upsert_build_task(
                task_id=task_id, job_id=ctx.job_id, module_id=module_id,
                wave=task.get("_wave", 0), status="failed",
                assigned_backend=chosen.model, attempts=1,
                workspace_path=str(workspace.job_dir(ctx.job_id)),
            )
            await ctx.emit(E.TASK_FAILED, {
                "task": task.get("task"), "module": module_id, "backend": chosen.model,
                "verification": verification, "sandboxed": test_result["sandboxed"],
                "error": reason,
            })
            raise RuntimeError(f"module {module_id} verification blocked delivery: {reason}")

        await ctx.dao.upsert_build_task(task_id=task_id, job_id=ctx.job_id, module_id=module_id,
                                        wave=task.get("_wave", 0), status="done",
                                        assigned_backend=chosen.model, attempts=1,
                                        workspace_path=str(workspace.job_dir(ctx.job_id)))
        await ctx.emit(E.TASK_COMPLETED, {"task": task.get("task"), "module": module_id,
                                          "files": written, "notes": result.get("notes", "")})
    return {"module": module_id, "files": result.get("files", []), "notes": result.get("notes", "")}
