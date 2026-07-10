"""Processes / runs / refine router — the operate-phase surface (06 §2)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import require_demo_token
from app.db import dao
from app.events import E, emit
from app.orchestrator.engine import engine

router = APIRouter(tags=["processes"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.get("/processes")
async def list_processes() -> dict:
    return {"processes": await dao.list_processes()}


@router.get("/processes/{process_id}")
async def get_process(process_id: str) -> dict:
    process = await dao.get_process(process_id)
    if not process:
        raise _err(404, "process not found")
    return {"process": process, "versions": await dao.list_versions(process_id),
            "runs": await dao.list_runs(process_id),
            "tickets": await dao.list_tickets(scope=f"process:{process_id}")}


@router.get("/processes/{process_id}/versions/{version}/diff")
async def version_diff(process_id: str, version: int) -> dict:
    v = await dao.get_version(process_id, version)
    if not v:
        raise _err(404, "version not found")
    return {"diff": v.get("diff")}


@router.get("/processes/{process_id}/package/{version}/{path:path}")
async def package_file(process_id: str, version: int, path: str):
    v = await dao.get_version(process_id, version)
    if not v or not v.get("package_path"):
        raise _err(404, "package not found")
    target = Path(v["package_path"]) / path
    if not target.exists() or not target.is_file():
        raise _err(404, "file not found")
    return FileResponse(str(target))


@router.post("/processes/{process_id}/runs", status_code=202, dependencies=[Depends(require_demo_token)])
async def start_run(process_id: str, body: dict) -> dict:
    process = await dao.get_process(process_id)
    if not process:
        raise _err(404, "process not found")
    version = body.get("version") or process["current_version"]
    # corpus binding (hardening): explicit body {"corpus": {"company": ...}} wins, else the
    # process's stored binding; optional {"sample": {"mode": "first"|"random", "n": N}} and
    # {"deliverable": {...}} ride along on params_json
    company = (body.get("corpus") or {}).get("company") or process.get("corpus_company")
    params = {k: v for k, v in (("corpus", {"company": company} if company else None),
                                ("sample", body.get("sample")),
                                ("deliverable", body.get("deliverable"))) if v}
    run_id = await dao.create_run(process_id=process_id, version=version, kind=body.get("kind", "batch"),
                                  input_ref=str(body.get("input_ref", "") or
                                                (f"company:{company}" if company else "")))
    if params:
        await dao.update_run(run_id, params=params)
    engine.submit_run(run_id)
    return {"run": await dao.get_run(run_id)}


@router.post("/processes/{process_id}/refine", status_code=202, dependencies=[Depends(require_demo_token)])
async def refine(process_id: str, body: dict) -> dict:
    if not await dao.get_process(process_id):
        raise _err(404, "process not found")
    from app.refine.refine import run_refine

    job_id = await run_refine(process_id, body.get("request", ""))
    return {"job_id": job_id}


@router.post("/processes/{process_id}/instantiate", status_code=202, dependencies=[Depends(require_demo_token)])
async def instantiate(process_id: str, body: dict) -> dict:
    process = await dao.get_process(process_id)
    if not process:
        raise _err(404, "process not found")
    version = await dao.get_version(process_id, process["current_version"])
    plan_row = await dao.get_plan(version["plan_id"]) if version and version.get("plan_id") else None
    if not plan_row:
        raise _err(409, "process has no certified plan to instantiate from")

    # re-enter at stage 4 with the certified plan as-is + new connector bindings —
    # NO stage-1 planner call (04 §5)
    job_id = await dao.create_job(title=f"Instantiate: {process['name']}",
                                  request=f"Re-instantiate {process['slug']}", origin="reinstantiate",
                                  mode=process["mode"], parent_process_id=process_id)
    source_job = await dao.get_job(process.get("created_from_job") or "")
    spec = {"request": f"Re-instantiate {process['slug']}",
            "connectors": body.get("connectors", [])}
    src_spec = (source_job or {}).get("spec") or {}
    if isinstance(src_spec, dict) and src_spec.get("company"):
        spec["company"] = src_spec["company"]   # process-mode corpus binding carries over
    plan_id = await dao.create_plan(job_id=job_id, version=1, status="certified",
                                    body=plan_row["body"])
    await dao.update_job(job_id, spec=spec, goal=process.get("goal") or "")
    await dao.set_checkpoint(f"job:{job_id}", "certified_plan_id", plan_id)
    # certified tests + oracle vectors travel with the package (04 §2) — QA reruns them as-is
    if version.get("package_path"):
        import json as _json
        for key, rel in (("tests", "tests/integration.json"), ("vectors", "tests/vectors.json")):
            f = Path(version["package_path"]) / rel
            if f.exists():
                try:
                    await dao.set_checkpoint(f"job:{job_id}", key, _json.loads(f.read_text()))
                except (ValueError, OSError):
                    pass  # package file unreadable -> QA falls back to plan-derived checks

    await emit(f"job:{job_id}", E.JOB_CREATED, {"origin": "reinstantiate", "parent_process": process_id})
    await engine.set_stage(job_id, "building")
    engine.submit_job(job_id)
    return {"job_id": job_id, "connectors": body.get("connectors", [])}
