"""Stage 5 - source-aware consolidation and a fail-closed validation wall."""
from __future__ import annotations

from app.events import E
from app.orchestrator import codeexec
from app.orchestrator.seatlib import seat
from app.runtime import workspace

_FIX_CAP = 3
_ASSEMBLED_CHECKPOINT = "consolidation_assembled"
_FIX_STATE_CHECKPOINT = "consolidation_fix_state"


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def _current_source_files(job_id: str) -> list[dict[str, str]]:
    """Read the current generated package as UTF-8 for consolidation and repair prompts."""
    files = workspace.read_src(job_id)
    entrypoint = workspace.job_dir(job_id) / "process.py"
    if entrypoint.is_file():
        files.append({"path": "process.py", "content": entrypoint.read_text(encoding="utf-8")})
    return [
        {"path": _normalized_path(source["path"]), "content": source["content"]}
        for source in files
    ]


def _source_mapping(job_id: str) -> dict[str, str]:
    return {
        source["path"]: source["content"]
        for source in _current_source_files(job_id)
    }


def _content_changing_fix(fix: dict, current: dict[str, str]) -> list[dict]:
    files = fix.get("files") if isinstance(fix, dict) else None
    if not isinstance(files, list) or not files:
        raise ValueError("coder fix returned no files")

    canonical_paths = {_normalized_path(path).casefold(): path for path in current}
    current_by_fold = {
        _normalized_path(path).casefold(): content for path, content in current.items()
    }
    normalized_files: list[dict] = []
    seen: set[str] = set()
    changed = False
    for source in files:
        if not isinstance(source, dict):
            raise ValueError("coder fix contains an invalid file record")
        path = source.get("path")
        content = source.get("content")
        if not isinstance(path, str) or not path.strip() or not isinstance(content, str):
            raise ValueError("coder fix files require a path and text content")
        key = _normalized_path(path).casefold()
        if key in seen:
            raise ValueError("coder fix contains duplicate file paths")
        seen.add(key)
        canonical_path = canonical_paths.get(key, _normalized_path(path))
        normalized_files.append({**source, "path": canonical_path})
        changed = changed or current_by_fold.get(key) != content
    if not changed:
        raise ValueError("coder fix did not change any source content")
    return normalized_files


async def _human_review(ctx, ticket_ids: list[str], reason: str) -> None:
    for ticket_id in ticket_ids:
        await ctx.dao.update_ticket(ticket_id, status="human_review")
        await ctx.emit(E.TICKET_HUMAN_REVIEW, {"ticket_id": ticket_id, "reason": reason})


async def run(ctx) -> None:
    await ctx.refresh()
    plan_id = await ctx.get_checkpoint("certified_plan_id")
    plan_row = await ctx.dao.get_plan(plan_id) if plan_id else await ctx.dao.current_plan(ctx.job_id)
    plan = plan_row["body"]
    modules = plan.get("modules", [])
    interfaces = plan.get("interfaces", [])
    tests = await ctx.get_checkpoint("tests") or []

    await ctx.emit(E.CONSOLIDATE_STARTED, {"modules": len(modules)})

    # Reassembly is checkpointed so a stage-level retry cannot overwrite an already-applied fix.
    if not await ctx.get_checkpoint(_ASSEMBLED_CHECKPOINT):
        merged = workspace.merge_agent_src(ctx.job_id)
        if merged:
            await ctx.emit(E.SYSTEM_NOTICE, {
                "text": f"merged {len(merged)} files from agent folders",
                "level": "info",
                "scope": "consolidate",
            })

        source_files = _current_source_files(ctx.job_id)
        consolidator = seat("consolidator")
        package = await consolidator.consolidate(
            ctx.complete,
            ctx.emit,
            modules=modules,
            interfaces=interfaces,
            source_files=source_files,
            plan=plan,
        )
        workspace.write_files(ctx.job_id, package.get("files", []))
        await ctx.checkpoint(_ASSEMBLED_CHECKPOINT, True)

    fix_state = await ctx.get_checkpoint(_FIX_STATE_CHECKPOINT) or {}
    fix_attempts = int(fix_state.get("attempts", 0))
    tracked_tickets = list(fix_state.get("tickets", []))

    while True:
        result = await codeexec.run_tests(
            workspace=str(workspace.job_dir(ctx.job_id)), tests=tests)
        await ctx.checkpoint("integration_result", result)
        await ctx.emit(E.CONSOLIDATE_TEST_RUN, {
            "passed": result["passed"],
            "total": result["total"],
            "failed": result["failed"],
            "attempt": fix_attempts + 1,
            "verification": result["verification"],
            "sandboxed": result["sandboxed"],
            "reason": result.get("reason", ""),
        })

        verification = result["verification"]
        if verification == "passed":
            for ticket_id in tracked_tickets:
                await ctx.dao.update_ticket(ticket_id, status="verified")
                await ctx.emit(E.TICKET_VERIFIED, {"ticket_id": ticket_id, "retested": True})
            await ctx.emit(E.CONSOLIDATE_COMPLETED, {
                "passed": result["passed"], "total": result["total"],
                "verification": verification, "sandboxed": result["sandboxed"],
            })
            await ctx.advance("qa")
            return

        if verification == "unverified":
            if tracked_tickets:
                await _human_review(
                    ctx, tracked_tickets,
                    "fixed source did not receive a passing test-suite verification",
                )
            if not codeexec.unverified_demo_delivery_allowed():
                raise RuntimeError(
                    "integration suite is unverified and demo delivery override is disabled")
            await ctx.emit(E.CONSOLIDATE_COMPLETED, {
                "passed": 0, "total": result["total"], "verification": "unverified",
                "sandboxed": result["sandboxed"],
            })
            await ctx.advance("qa")
            return

        if verification != "failed":
            raise RuntimeError(f"unknown integration verification state: {verification}")

        if fix_attempts >= _FIX_CAP:
            await _human_review(ctx, tracked_tickets, "suite still failing after fix cap")
            raise RuntimeError("integration suite still failing after fix cap")

        ticket_id = await ctx.dao.create_ticket(
            scope=ctx.scope,
            source="consolidation",
            severity="major",
            title="integration suite failure",
            body={"instrument": "consolidation", "suspected_modules": [], "result": result},
        )
        fix_attempts += 1
        tracked_tickets.append(ticket_id)
        await ctx.checkpoint(_FIX_STATE_CHECKPOINT, {
            "attempts": fix_attempts,
            "tickets": tracked_tickets,
        })
        await ctx.emit(E.TICKET_OPENED, {"ticket_id": ticket_id, "source": "consolidation"})
        await ctx.dao.update_ticket(ticket_id, status="in_fix")
        await ctx.emit(E.TICKET_IN_FIX, {"ticket_id": ticket_id, "attempt": fix_attempts})

        coder = seat("coder")
        current = _source_mapping(ctx.job_id)
        try:
            fix = await coder.fix(
                ctx.complete,
                ctx.emit,
                ticket={"title": "integration suite failure", "result": result},
                module_src=current,
                tests=tests,
            )
            fix_files = _content_changing_fix(fix, current)
            workspace.write_files(ctx.job_id, fix_files)
        except Exception:
            await _human_review(
                ctx, tracked_tickets,
                "coder returned an empty, invalid, or unapplied fix",
            )
            raise

        await ctx.dao.update_ticket(ticket_id, status="fix_applied")
        await ctx.emit(E.TICKET_FIX_APPLIED, {"ticket_id": ticket_id, "retested": False})
