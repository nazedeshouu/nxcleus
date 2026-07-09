"""Data access — thin typed helpers per aggregate (05). All writes go through the single-writer
engine; `*_json` columns are (de)serialized here so callers work in dicts. Rows come back as dicts
with `_json` columns already parsed into `*` keys.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.db.engine import db
from app.events import now_iso
from app.ids import new_id


def _j(v: Any) -> str | None:
    return None if v is None else json.dumps(v)


def _load(row: dict | None, *fields: str) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for f in fields:
        if f in out and isinstance(out[f], str):
            try:
                out[f.removesuffix("_json")] = json.loads(out[f])
            except (json.JSONDecodeError, TypeError):
                out[f.removesuffix("_json")] = None
    return out


# ============================================================ jobs
async def create_job(*, title: str, request: str, origin: str = "customer", mode: str | None = None,
                     sovereign: bool = False, policy: dict | None = None,
                     sandbox_session_id: str | None = None, parent_process_id: str | None = None) -> str:
    jid = new_id("job")
    await db.execute(
        "INSERT INTO jobs (id, created_at, title, origin, mode, sovereign, status, current_stage, "
        "spec_json, policy_json, goal, sandbox_session_id, parent_process_id) VALUES "
        "(:id, :ts, :title, :origin, :mode, :sov, 'intake', 0, :spec, :policy, NULL, :sbx, :ppid)",
        {"id": jid, "ts": now_iso(), "title": title, "origin": origin, "mode": mode,
         "sov": 1 if sovereign else 0, "spec": _j({"request": request}), "policy": _j(policy),
         "sbx": sandbox_session_id, "ppid": parent_process_id},
    )
    return jid


async def get_job(job_id: str) -> dict | None:
    return _load(await db.fetchone("SELECT * FROM jobs WHERE id = :id", {"id": job_id}),
                 "spec_json", "policy_json")


async def list_jobs(origin: str | None = None, status: str | None = None) -> list[dict]:
    where, params = [], {}
    if origin:
        where.append("origin = :origin")
        params["origin"] = origin
    if status:
        where.append("status = :status")
        params["status"] = status
    sql = "SELECT * FROM jobs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC"
    return [_load(r, "spec_json", "policy_json") for r in await db.fetchall(sql, params)]


async def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    for k in ("spec", "policy"):
        if k in fields:
            fields[f"{k}_json"] = _j(fields.pop(k))
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(f"UPDATE jobs SET {sets} WHERE id = :id", {**fields, "id": job_id})


async def add_message(job_id: str, role: str, content: str) -> str:
    mid = new_id("message")
    await db.execute(
        "INSERT INTO job_messages (id, job_id, role, content, ts) VALUES (:id, :j, :r, :c, :ts)",
        {"id": mid, "j": job_id, "r": role, "c": content, "ts": now_iso()},
    )
    return mid


async def list_messages(job_id: str) -> list[dict]:
    return await db.fetchall("SELECT * FROM job_messages WHERE job_id = :j ORDER BY ts", {"j": job_id})


# ============================================================ plans + amendments + consults
async def create_plan(*, job_id: str, version: int, status: str, body: dict, plan_id: str | None = None) -> str:
    pid = plan_id or new_id("plan")
    await db.execute(
        "INSERT INTO plans (id, job_id, version, status, body_json, certified_at) "
        "VALUES (:id, :j, :v, :s, :b, NULL) "
        "ON CONFLICT(id) DO UPDATE SET version=:v, status=:s, body_json=:b",
        {"id": pid, "j": job_id, "v": version, "s": status, "b": _j(body)},
    )
    return pid


async def update_plan(plan_id: str, **fields: Any) -> None:
    if "body" in fields:
        fields["body_json"] = _j(fields.pop("body"))
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(f"UPDATE plans SET {sets} WHERE id = :id", {**fields, "id": plan_id})


async def get_plan(plan_id: str) -> dict | None:
    return _load(await db.fetchone("SELECT * FROM plans WHERE id = :id", {"id": plan_id}), "body_json")


async def current_plan(job_id: str) -> dict | None:
    return _load(await db.fetchone(
        "SELECT * FROM plans WHERE job_id = :j ORDER BY version DESC LIMIT 1", {"j": job_id}), "body_json")


async def append_amendment(*, plan_id: str, origin: str, patch: Any, rationale: str,
                           finding_id: str = "", check_name: str = "", plan_ref: str = "",
                           spec_ref: str = "") -> dict:
    """Hash-chained amendment (03 §4): hash = sha256(prev_hash + patch + rationale)."""
    prev = await db.fetchone(
        "SELECT seq, hash FROM amendments WHERE plan_id = :p ORDER BY seq DESC LIMIT 1", {"p": plan_id})
    seq = (prev["seq"] + 1) if prev else 1
    prev_hash = prev["hash"] if prev else ""
    patch_json = _j(patch)
    h = hashlib.sha256((prev_hash + (patch_json or "") + rationale).encode()).hexdigest()
    aid = new_id("amendment")
    await db.execute(
        "INSERT INTO amendments (id, plan_id, seq, origin, finding_id, check_name, plan_ref, "
        "patch_json, rationale, spec_ref, prev_hash, hash, ts) VALUES "
        "(:id, :p, :seq, :o, :fid, :chk, :ref, :patch, :rat, :sref, :prev, :hash, :ts)",
        {"id": aid, "p": plan_id, "seq": seq, "o": origin, "fid": finding_id, "chk": check_name,
         "ref": plan_ref, "patch": patch_json, "rat": rationale, "sref": spec_ref,
         "prev": prev_hash, "hash": h, "ts": now_iso()},
    )
    return {"id": aid, "seq": seq, "origin": origin, "plan_ref": plan_ref, "patch": patch,
            "rationale": rationale, "hash": h, "prev_hash": prev_hash}


async def list_amendments(plan_id: str) -> list[dict]:
    return [_load(r, "patch_json")
            for r in await db.fetchall("SELECT * FROM amendments WHERE plan_id = :p ORDER BY seq", {"p": plan_id})]


async def create_consult(*, plan_id: str, round: int, scope: dict, request: dict) -> str:
    cid = new_id("consult")
    await db.execute(
        "INSERT INTO consults (id, plan_id, round, scope_json, request_json, response_summary, "
        "status, ts) VALUES (:id, :p, :r, :sc, :rq, NULL, 'open', :ts)",
        {"id": cid, "p": plan_id, "r": round, "sc": _j(scope), "rq": _j(request), "ts": now_iso()},
    )
    return cid


async def resolve_consult(consult_id: str, summary: str) -> None:
    await db.execute("UPDATE consults SET status='resolved', response_summary=:s WHERE id=:id",
                     {"s": summary, "id": consult_id})


async def list_consults(plan_id: str) -> list[dict]:
    return [_load(r, "scope_json", "request_json")
            for r in await db.fetchall("SELECT * FROM consults WHERE plan_id = :p ORDER BY ts", {"p": plan_id})]


# ============================================================ quotes
async def create_quote(*, job_id: str, plan_id: str, body: dict) -> str:
    qid = new_id("quote")
    await db.execute(
        "INSERT INTO quotes (id, job_id, plan_id, body_json, status, issued_at, approved_at) "
        "VALUES (:id, :j, :p, :b, 'issued', :ts, NULL)",
        {"id": qid, "j": job_id, "p": plan_id, "b": _j(body), "ts": now_iso()},
    )
    return qid


async def get_quote(job_id: str) -> dict | None:
    return _load(await db.fetchone(
        "SELECT * FROM quotes WHERE job_id = :j ORDER BY issued_at DESC LIMIT 1", {"j": job_id}), "body_json")


async def approve_quote(job_id: str) -> None:
    await db.execute("UPDATE quotes SET status='approved', approved_at=:ts WHERE job_id=:j AND status='issued'",
                     {"ts": now_iso(), "j": job_id})


# ============================================================ build_tasks
async def upsert_build_task(*, task_id: str, job_id: str, module_id: str, wave: int, status: str,
                            assigned_backend: str | None = None, attempts: int = 0,
                            workspace_path: str | None = None) -> None:
    await db.execute(
        "INSERT INTO build_tasks (id, job_id, module_id, wave, status, assigned_backend, attempts, "
        "workspace_path, ts) VALUES (:id, :j, :m, :w, :s, :ab, :at, :wp, :ts) "
        "ON CONFLICT(id) DO UPDATE SET status=:s, assigned_backend=:ab, attempts=:at, workspace_path=:wp, ts=:ts",
        {"id": task_id, "j": job_id, "m": module_id, "w": wave, "s": status, "ab": assigned_backend,
         "at": attempts, "wp": workspace_path, "ts": now_iso()},
    )


async def list_build_tasks(job_id: str) -> list[dict]:
    return await db.fetchall("SELECT * FROM build_tasks WHERE job_id = :j ORDER BY wave, id", {"j": job_id})


async def build_task_done(task_id: str) -> bool:
    row = await db.fetchone("SELECT status FROM build_tasks WHERE id = :id", {"id": task_id})
    return bool(row and row["status"] == "done")


# ============================================================ processes + versions
async def create_process(*, slug: str, name: str, mode: str, goal: str, created_from_job: str,
                         created_from: str = "build") -> str:
    pid = new_id("process")
    await db.execute(
        "INSERT INTO processes (id, slug, name, mode, goal, status, current_version, "
        "created_from_job, created_from, created_at) VALUES "
        "(:id, :slug, :name, :mode, :goal, 'active', 1, :job, :cf, :ts)",
        {"id": pid, "slug": slug, "name": name, "mode": mode, "goal": goal, "job": created_from_job,
         "cf": created_from, "ts": now_iso()},
    )
    return pid


async def get_process(process_id: str) -> dict | None:
    return await db.fetchone("SELECT * FROM processes WHERE id = :id", {"id": process_id})


async def get_process_by_slug(slug: str) -> dict | None:
    return await db.fetchone("SELECT * FROM processes WHERE slug = :s", {"s": slug})


async def list_processes() -> list[dict]:
    return await db.fetchall("SELECT * FROM processes ORDER BY created_at DESC")


async def update_process(process_id: str, **fields: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(f"UPDATE processes SET {sets} WHERE id = :id", {**fields, "id": process_id})


async def create_version(*, process_id: str, version: int, plan_id: str, package_path: str,
                         image_tag: str | None = None, diff: dict | None = None,
                         status: str = "certified") -> str:
    vid = new_id("process_version")
    await db.execute(
        "INSERT INTO process_versions (id, process_id, version, plan_id, package_path, image_tag, "
        "diff_json, certified_at, status) VALUES (:id, :p, :v, :pl, :pp, :it, :diff, :ts, :s)",
        {"id": vid, "p": process_id, "v": version, "pl": plan_id, "pp": package_path, "it": image_tag,
         "diff": _j(diff), "ts": now_iso(), "s": status},
    )
    return vid


async def get_version(process_id: str, version: int) -> dict | None:
    return _load(await db.fetchone(
        "SELECT * FROM process_versions WHERE process_id = :p AND version = :v", {"p": process_id, "v": version}),
        "diff_json")


async def list_versions(process_id: str) -> list[dict]:
    return [_load(r, "diff_json") for r in await db.fetchall(
        "SELECT * FROM process_versions WHERE process_id = :p ORDER BY version", {"p": process_id})]


# ============================================================ runs + units
async def create_run(*, process_id: str, version: int, kind: str, input_ref: str,
                     run_id: str | None = None) -> str:
    rid = run_id or new_id("run")
    await db.execute(
        "INSERT INTO runs (id, process_id, version, kind, status, input_ref, started_at, "
        "finished_at, stats_json, cost_json) VALUES (:id, :p, :v, :k, 'queued', :ir, :ts, NULL, NULL, NULL) "
        "ON CONFLICT(id) DO NOTHING",
        {"id": rid, "p": process_id, "v": version, "k": kind, "ir": input_ref, "ts": now_iso()},
    )
    return rid


async def get_run(run_id: str) -> dict | None:
    return _load(await db.fetchone("SELECT * FROM runs WHERE id = :id", {"id": run_id}),
                 "stats_json", "cost_json")


async def list_runs(process_id: str) -> list[dict]:
    return [_load(r, "stats_json", "cost_json") for r in await db.fetchall(
        "SELECT * FROM runs WHERE process_id = :p ORDER BY started_at DESC", {"p": process_id})]


async def update_run(run_id: str, **fields: Any) -> None:
    for k in ("stats", "cost"):
        if k in fields:
            fields[f"{k}_json"] = _j(fields.pop(k))
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(f"UPDATE runs SET {sets} WHERE id = :id", {**fields, "id": run_id})


async def add_run_unit(*, run_id: str, unit_ref: str, status: str, result: dict, trace: list,
                       unit_id: str | None = None) -> str:
    uid = unit_id or new_id("run_unit")
    await db.execute(
        "INSERT INTO run_units (id, run_id, unit_ref, status, result_json, trace_json, "
        "review_verdict, review_note, ts) VALUES (:id, :r, :ur, :s, :res, :tr, NULL, NULL, :ts) "
        "ON CONFLICT(id) DO UPDATE SET status=:s, result_json=:res, trace_json=:tr, ts=:ts",
        {"id": uid, "r": run_id, "ur": unit_ref, "s": status, "res": _j(result), "tr": _j(trace),
         "ts": now_iso()},
    )
    return uid


async def list_run_units(run_id: str, status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    params: dict = {"r": run_id, "lim": limit, "off": offset}
    where = "run_id = :r"
    if status:
        where += " AND status = :s"
        params["s"] = status
    return [_load(r, "result_json", "trace_json") for r in await db.fetchall(
        f"SELECT * FROM run_units WHERE {where} ORDER BY ts LIMIT :lim OFFSET :off", params)]


async def review_unit(unit_id: str, verdict: str, note: str) -> None:
    status = "ok" if verdict == "approve" else "error"
    await db.execute(
        "UPDATE run_units SET review_verdict=:v, review_note=:n, status=:s WHERE id=:id",
        {"v": verdict, "n": note, "s": status, "id": unit_id})


# ============================================================ tickets + oracle
async def create_ticket(*, scope: str, source: str, severity: str, title: str, body: dict,
                        status: str = "open") -> str:
    tid = new_id("ticket")
    await db.execute(
        "INSERT INTO tickets (id, scope, source, severity, status, title, body_json, fix_attempts, ts) "
        "VALUES (:id, :sc, :src, :sev, :st, :title, :b, 0, :ts)",
        {"id": tid, "sc": scope, "src": source, "sev": severity, "st": status, "title": title,
         "b": _j(body), "ts": now_iso()},
    )
    return tid


async def update_ticket(ticket_id: str, **fields: Any) -> None:
    if "body" in fields:
        fields["body_json"] = _j(fields.pop("body"))
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(f"UPDATE tickets SET {sets} WHERE id = :id", {**fields, "id": ticket_id})


async def list_tickets(scope: str | None = None, status: str | None = None,
                       source: str | None = None) -> list[dict]:
    where, params = [], {}
    for col, val in (("scope", scope), ("status", status), ("source", source)):
        if val:
            where.append(f"{col} = :{col}")
            params[col] = val
    sql = "SELECT * FROM tickets" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ts DESC"
    return [_load(r, "body_json") for r in await db.fetchall(sql, params)]


async def create_oracle_check(*, scope: str, vector_id: str, rule_id: str, inputs: dict,
                              expected: Any, actual: Any, verdict: str, votes: list) -> str:
    oid = new_id("oracle_check")
    await db.execute(
        "INSERT INTO oracle_checks (id, scope, vector_id, rule_id, inputs_json, expected_json, "
        "actual_json, verdict, votes_json, ts) VALUES (:id, :sc, :vec, :rule, :inp, :exp, :act, :v, :votes, :ts)",
        {"id": oid, "sc": scope, "vec": vector_id, "rule": rule_id, "inp": _j(inputs), "exp": _j(expected),
         "act": _j(actual), "v": verdict, "votes": _j(votes), "ts": now_iso()},
    )
    return oid


# ============================================================ nodes
async def register_node(*, name: str, ip: str, gpus: list, seats: list | None = None) -> str:
    existing = await db.fetchone("SELECT id FROM nodes WHERE name = :n", {"n": name})
    nid = existing["id"] if existing else new_id("node")
    await db.execute(
        "INSERT INTO nodes (id, name, ip, status, gpus_json, seats_json, last_heartbeat, registered_at) "
        "VALUES (:id, :n, :ip, 'ready', :g, :s, :ts, :ts) "
        "ON CONFLICT(id) DO UPDATE SET ip=:ip, status='ready', gpus_json=:g, seats_json=:s, last_heartbeat=:ts",
        {"id": nid, "n": name, "ip": ip, "g": _j(gpus), "s": _j(seats or []), "ts": now_iso()},
    )
    return nid


async def list_nodes() -> list[dict]:
    return [_load(r, "gpus_json", "seats_json") for r in await db.fetchall("SELECT * FROM nodes ORDER BY name")]


async def get_node(node_id: str) -> dict | None:
    return _load(await db.fetchone("SELECT * FROM nodes WHERE id = :id", {"id": node_id}),
                 "gpus_json", "seats_json")


async def set_node_status(node_id: str, status: str) -> None:
    await db.execute("UPDATE nodes SET status=:s WHERE id=:id", {"s": status, "id": node_id})


async def node_heartbeat(node_id: str) -> None:
    await db.execute("UPDATE nodes SET last_heartbeat=:ts, status='ready' WHERE id=:id",
                     {"ts": now_iso(), "id": node_id})


# ============================================================ sandbox sessions
async def create_sandbox_session(*, company: str, client_hash: str) -> str:
    sid = new_id("sandbox_session")
    await db.execute(
        "INSERT INTO sandbox_sessions (id, company, created_at, client_hash, runs_used, tokens_used) "
        "VALUES (:id, :c, :ts, :ch, 0, 0)",
        {"id": sid, "c": company, "ts": now_iso(), "ch": client_hash},
    )
    return sid


async def get_sandbox_session(session_id: str) -> dict | None:
    return await db.fetchone("SELECT * FROM sandbox_sessions WHERE id = :id", {"id": session_id})


async def incr_sandbox_runs(session_id: str) -> None:
    await db.execute("UPDATE sandbox_sessions SET runs_used = runs_used + 1 WHERE id = :id",
                     {"id": session_id})


# ============================================================ connections / custom models / overrides
async def create_connection(*, name: str, base_url: str, api_key_ref: str, zone: str = "CUSTOM",
                            data_class_ceiling: str = "SANITIZED", counts_as_local: bool = False) -> str:
    cid = new_id("connection")
    await db.execute(
        "INSERT INTO api_connections (id, name, base_url, api_key_ref, zone, data_class_ceiling, "
        "counts_as_local, created_at) VALUES (:id, :n, :u, :kr, :z, :dc, :col, :ts)",
        {"id": cid, "n": name, "u": base_url, "kr": api_key_ref, "z": zone, "dc": data_class_ceiling,
         "col": 1 if counts_as_local else 0, "ts": now_iso()},
    )
    return cid


async def list_connections() -> list[dict]:
    return await db.fetchall("SELECT * FROM api_connections ORDER BY created_at DESC")


async def get_connection(connection_id: str) -> dict | None:
    return await db.fetchone("SELECT * FROM api_connections WHERE id = :id", {"id": connection_id})


async def delete_connection(connection_id: str) -> None:
    await db.execute("DELETE FROM custom_models WHERE connection_id = :id", {"id": connection_id})
    await db.execute("DELETE FROM api_connections WHERE id = :id", {"id": connection_id})


async def add_custom_model(*, connection_id: str, provider_model_id: str, display_name: str,
                           flags: list, context_len: int = 0, notes: str = "") -> str:
    mid = new_id("custom_model")
    await db.execute(
        "INSERT INTO custom_models (id, connection_id, provider_model_id, display_name, flags_json, "
        "context_len, notes, created_at) VALUES (:id, :c, :pm, :dn, :f, :cl, :n, :ts)",
        {"id": mid, "c": connection_id, "pm": provider_model_id, "dn": display_name, "f": _j(flags),
         "cl": context_len, "n": notes, "ts": now_iso()},
    )
    return mid


async def list_custom_models() -> list[dict]:
    return [_load(r, "flags_json") for r in await db.fetchall("SELECT * FROM custom_models ORDER BY created_at")]


async def set_seat_override(*, seat: str, model_key: str, scope: str = "global") -> str:
    sid = new_id("seat_override")
    await db.execute(
        "INSERT INTO seat_overrides (id, seat, scope, model_key, set_at) VALUES (:id, :seat, :scope, :mk, :ts) "
        "ON CONFLICT(seat, scope) DO UPDATE SET model_key=:mk, set_at=:ts",
        {"id": sid, "seat": seat, "scope": scope, "mk": model_key, "ts": now_iso()},
    )
    return sid


async def list_seat_overrides() -> list[dict]:
    return await db.fetchall("SELECT * FROM seat_overrides ORDER BY seat")


# ============================================================ egress queries
async def list_egress(scope: str | None = None, zone: str | None = None, limit: int = 500) -> list[dict]:
    where, params = [], {"lim": limit}
    if scope:
        where.append("scope = :scope")
        params["scope"] = scope
    if zone:
        where.append("zone = :zone")
        params["zone"] = zone
    sql = "SELECT * FROM egress_log" + (" WHERE " + " AND ".join(where) if where else "") + \
          " ORDER BY id DESC LIMIT :lim"
    return await db.fetchall(sql, params)


# ============================================================ checkpoints (07 §1, §4)
async def set_checkpoint(scope: str, key: str, value: Any) -> None:
    await db.execute(
        "INSERT INTO checkpoints (scope, key, value_json, ts) VALUES (:sc, :k, :v, :ts) "
        "ON CONFLICT(scope, key) DO UPDATE SET value_json=:v, ts=:ts",
        {"sc": scope, "k": key, "v": _j(value), "ts": now_iso()},
    )


async def get_checkpoint(scope: str, key: str) -> Any:
    row = await db.fetchone("SELECT value_json FROM checkpoints WHERE scope=:sc AND key=:k",
                            {"sc": scope, "k": key})
    return json.loads(row["value_json"]) if row and row["value_json"] else None


async def resume_candidates() -> list[dict]:
    """Jobs to re-submit on startup (07 §4): not terminal and not parked."""
    return await db.fetchall(
        "SELECT * FROM jobs WHERE status NOT IN ('done','aborted','quoted','blocked') ORDER BY created_at")


async def resume_runs() -> list[dict]:
    return await db.fetchall("SELECT * FROM runs WHERE status IN ('queued','running') ORDER BY started_at")
