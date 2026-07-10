"""Jobs router — the build pipeline surface (06 §2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_demo_token
from app.api.sse import sse_response
from app.boundary import whisper
from app.db import dao
from app.events import E, emit
from app.orchestrator.engine import engine
from app.orchestrator.seatlib import seat

router = APIRouter(tags=["jobs"])


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


@router.post("/jobs", status_code=202, dependencies=[Depends(require_demo_token)])
async def create_job(body: dict) -> dict:
    request = body.get("request", "")
    if not request:
        raise _err(400, "request is required")
    policy = {"sources": [{"kind": "text", "ref": body["policy_text"]}]} if body.get("policy_text") else None
    # optional corpus binding: any dataset id (builtin or BYOD) -> spec["company"], so a customer
    # job fans out over a real corpus exactly like a sandbox run (hardening 2026-07-10)
    job_id = await dao.create_job(title=body.get("title", "Untitled job"), request=request,
                                  sovereign=bool(body.get("sovereign")), policy=policy,
                                  company=body.get("company") or None)
    await emit(f"job:{job_id}", E.JOB_CREATED, {"title": body.get("title", ""),
                                                "sovereign": bool(body.get("sovereign"))})
    engine.submit_job(job_id)
    return {"job": await dao.get_job(job_id)}


@router.get("/jobs")
async def list_jobs(origin: str | None = None, status: str | None = None) -> dict:
    return {"jobs": await dao.list_jobs(origin=origin, status=status)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await dao.get_job(job_id)
    if not job:
        raise _err(404, "job not found")
    out = {"job": job, "policy_summary": job.get("policy"), "goal": job.get("goal")}
    if job.get("status") == "awaiting_input":
        out["clarifications"] = await dao.get_checkpoint(f"job:{job_id}", "clarifications") or []
    return out


@router.post("/jobs/{job_id}/answers", dependencies=[Depends(require_demo_token)])
async def post_answers(job_id: str, body: dict) -> dict:
    """Clarifying-intake resume (hardening 2026-07-10): fold the customer's answers into the
    spec and re-run intake — the trust seat re-composes the brief with the answers binding."""
    job = await dao.get_job(job_id)
    if not job:
        raise _err(404, "job not found")
    if job["status"] != "awaiting_input":
        raise _err(409, f"job is not awaiting input (status {job['status']})")
    answers = [a for a in (body.get("answers") or []) if isinstance(a, dict)]
    if not answers:
        raise _err(400, "answers[] is required")
    spec = job.get("spec") if isinstance(job.get("spec"), dict) else {}
    spec["clarification_answers"] = answers
    questions = await dao.get_checkpoint(f"job:{job_id}", "clarifications") or []
    kinds = {q.get("id"): q.get("kind") for q in questions}
    for a in answers:
        if kinds.get(a.get("id")) == "delivery" and a.get("answer"):
            spec["deliverable"] = _deliverable_from_answer(str(a["answer"]))
    await dao.update_job(job_id, spec=spec, status="intake", current_stage=0)
    await emit(f"job:{job_id}", E.INTAKE_CLARIFICATION_ANSWERED,
               {"auto": False, "answers": [{"id": a.get("id"), "answer": a.get("answer")}
                                           for a in answers]})
    engine.submit_job(job_id)
    return {"job": await dao.get_job(job_id)}


def _deliverable_from_answer(answer: str) -> dict:
    a = answer.lower()
    formats = [f for f in ("csv", "report") if f in a]
    if ("pdf" in a or "case file" in a) and "report" not in formats:
        formats.append("report")
    return {"formats": formats or ["csv", "report"],
            "granularity": "summary" if "summary" in a else "per_entity",
            "audience": ""}


@router.post("/jobs/{job_id}/messages", dependencies=[Depends(require_demo_token)])
async def post_message(job_id: str, body: dict) -> dict:
    if not await dao.get_job(job_id):
        raise _err(404, "job not found")
    mid = await dao.add_message(job_id, "customer", body.get("content", ""))
    await emit(f"job:{job_id}", E.INTAKE_MESSAGE, {"role": "customer", "content": body.get("content", "")})
    return {"message_id": mid}


@router.post("/jobs/{job_id}/policy", dependencies=[Depends(require_demo_token)])
async def add_policy(job_id: str, request: Request) -> dict:
    job = await dao.get_job(job_id)
    if not job:
        raise _err(404, "job not found")
    text = ""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        if form.get("kind") == "voice" and form.get("file") is not None:
            upload = form["file"]
            tmp = f"/tmp/{job_id}-policy-audio"
            with open(tmp, "wb") as f:
                f.write(await upload.read())
            try:
                text = await whisper.transcribe(tmp)
            except whisper.WhisperUnavailable as e:
                raise _err(400, str(e)) from e
        else:
            text = str(form.get("text", ""))
    else:
        body = await request.json()
        text = body.get("text", "")
    sources = [{"kind": "text", "ref": text}]
    distilled = await seat("trust").distill_policy(_noop_complete, _noop_emit(job_id), sources=sources)
    await dao.update_job(job_id, policy=distilled)
    await emit(f"job:{job_id}", E.INTAKE_POLICY_REGISTERED,
               {"sources": ["text"], "rule_count": len(distilled.get("rules", []))})
    return {"policy_summary": distilled}


@router.post("/jobs/{job_id}/confirm-spec", dependencies=[Depends(require_demo_token)])
async def confirm_spec(job_id: str, body: dict) -> dict:
    job = await dao.get_job(job_id)
    if not job:
        raise _err(404, "job not found")
    if job["status"] != "intake":
        raise _err(409, f"cannot confirm spec in status {job['status']}")
    await dao.update_job(job_id, mode=body.get("mode", job.get("mode", "build")))
    await engine.set_stage(job_id, "planning")
    engine.submit_job(job_id)
    return {"job": await dao.get_job(job_id)}


@router.get("/jobs/{job_id}/plan")
async def get_plan(job_id: str) -> dict:
    plan = await dao.current_plan(job_id)
    if not plan:
        raise _err(404, "no plan yet")
    return {"plan": plan.get("body"), "amendments": await dao.list_amendments(plan["id"]),
            "consults": await dao.list_consults(plan["id"])}


@router.get("/jobs/{job_id}/quote")
async def get_quote(job_id: str) -> dict:
    quote = await dao.get_quote(job_id)
    if not quote:
        raise _err(404, "no quote yet")
    return {"quote": quote}


@router.post("/jobs/{job_id}/approve-quote", dependencies=[Depends(require_demo_token)])
async def approve_quote(job_id: str) -> dict:
    job = await dao.get_job(job_id)
    if not job:
        raise _err(404, "job not found")
    if job["status"] != "quoted":
        raise _err(409, f"quote not awaiting approval (status {job['status']})")
    await dao.approve_quote(job_id)
    await emit(f"job:{job_id}", E.QUOTE_APPROVED, {})
    await engine.set_stage(job_id, "building")
    engine.submit_job(job_id)
    return {"job": await dao.get_job(job_id)}


@router.post("/jobs/{job_id}/abort", dependencies=[Depends(require_demo_token)])
async def abort_job(job_id: str) -> dict:
    if not await dao.get_job(job_id):
        raise _err(404, "job not found")
    await dao.update_job(job_id, status="aborted")
    await emit(f"job:{job_id}", E.JOB_ABORTED, {})
    return {"ok": True}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request, from_seq: int = 0):
    return await sse_response(request, scope=f"job:{job_id}", from_seq=from_seq)


# --- helpers for the policy endpoint (curried complete/emit outside a StageContext) ---------------
async def _noop_complete(seat_name, messages, **kw):
    from app.models.router import router as _r
    return await _r.complete(seat_name, messages, scope="system", data_class=kw.get("data_class", "RAW"),
                             schema=kw.get("schema"))


def _noop_emit(job_id):
    async def _emit(type_, payload):
        await emit(f"job:{job_id}", type_, payload)
    return _emit
