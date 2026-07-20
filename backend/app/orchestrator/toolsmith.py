"""createTool() primitive (hardening 2026-07-10, §4 of PRODUCT-HARDENING).

One coder-seat completion produces a self-contained Python tool file:
    TOOL = {"name", "description", "args_schema"}
    SELF_TEST = {"args": {...}, "expect_keys": [...]}
    def run(args: dict) -> dict
The platform SELF-TESTS it in the code-exec sandbox (agent folder mount only, network off)
before registration; one repair round on failure; only a passed tool registers. Invocation is
the same sandbox — args in via a file in the agent folder, result JSON on stdout.

# ponytail: routing is the plain "coder" seat (task_flags note rides in the prompt) — pool
# pick_member routing lives in stage 4's task scheduler; per-dispatch member override isn't a
# router capability yet. Upgrade path: router accepts a binding hint.
"""
from __future__ import annotations

import ast
import json
import keyword
import re
import time
from pathlib import Path

from app.config import settings
from app.db.engine import db
from app.events import E, emit, now_iso
from app.ids import new_id
from app.orchestrator import codeexec
from app.safe_paths import UnsafePathError, resolve_within
from app.seats.base import Message

_SYSTEM = """\
You are a toolsmith coder (task_flags: greenfield-codegen). Write ONE self-contained Python \
file implementing a small deterministic tool. EXACT module contract:
  TOOL = {"name": "<snake_case>", "description": "<one line>", "args_schema": {<JSON schema>}}
  SELF_TEST = {"args": {<realistic example args>}, "expect_keys": ["<key>", ...]}
  def run(args: dict) -> dict: ...
Constraints: Python stdlib + sqlite3 ONLY; no network; no filesystem writes outside the \
current directory; deterministic (no randomness, no clock-dependent output); run() must \
return a dict containing every SELF_TEST expect_key; tools that analyze rows take \
{"rows": [...]} and return {"findings": [...]}. Return the complete file text.\
"""

_FILE_SCHEMA = {"type": "object", "additionalProperties": False,
                "properties": {"file": {"type": "string"}}, "required": ["file"]}

_TOOL_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")

_RUNNER = """\
python - <<'PY'
import json, importlib.util
spec = importlib.util.spec_from_file_location("tool_under_test", "tools/{fname}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
out = m.run(m.SELF_TEST["args"])
assert isinstance(out, dict), f"run() returned {{type(out).__name__}}, not dict"
missing = [k for k in m.SELF_TEST.get("expect_keys", []) if k not in out]
assert not missing, f"missing expect_keys: {{missing}}"
print(json.dumps({{"ok": True, "keys": sorted(out)}}))
PY"""

_INVOKE = """\
python - <<'PY'
import json, importlib.util
spec = importlib.util.spec_from_file_location("tool_invoked", "tools/{fname}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
args = json.load(open("tools/{argsname}"))
print(json.dumps(m.run(args), default=str))
PY"""


def _validated_tool_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("TOOL.name must be a lowercase snake_case identifier")
    if len(value) > 64:
        raise ValueError("TOOL.name must be at most 64 characters")
    if (not _TOOL_NAME.fullmatch(value) or not value.isidentifier()
            or keyword.iskeyword(value)):
        raise ValueError("TOOL.name must be a lowercase snake_case identifier")
    try:
        resolve_within(Path.cwd(), f"{value}.py")
    except UnsafePathError as exc:
        raise ValueError(f"TOOL.name is not a portable filename: {exc}") from None
    return value


def _parse_tool_file(source: str) -> dict:
    """Extract TOOL and SELF_TEST via the AST (never executes untrusted code in-process)."""
    tree = ast.parse(source)
    found: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ("TOOL", "SELF_TEST"):
                    found[t.id] = ast.literal_eval(node.value)
    tool, self_test = found.get("TOOL"), found.get("SELF_TEST")
    if not (isinstance(tool, dict) and tool.get("name") and isinstance(self_test, dict)):
        raise ValueError("file lacks a valid TOOL/SELF_TEST contract")
    _validated_tool_name(tool["name"])
    if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
        raise ValueError("file lacks def run(args)")
    return {"tool": tool, "self_test": self_test}


async def _ask_coder(complete_fn, purpose: str, args_example: dict, feedback: str | None) -> str:
    body = {"purpose": purpose, "args_example": args_example}
    if feedback:
        body["previous_attempt_failed"] = feedback
    hint = " [[fixture:toolsmith_tool]]" if settings.model_mode == "mock" else ""
    comp = await complete_fn("coder", [Message(role="system", content=_SYSTEM + hint),
                                       Message(role="user", content=json.dumps(body, default=str))],
                             data_class="RAW", schema=_FILE_SCHEMA)
    return (comp.parsed or {}).get("file", "")


async def create_tool(*, purpose: str, args_example: dict, scope: str, complete_fn,
                      agent_dir: str | Path, tool_id: str | None = None) -> dict:
    """Commission, self-test, and register one tool. Returns
    {tool_name, description, args_schema} or {error}."""
    agent_path = Path(agent_dir)
    if not codeexec.docker_available():
        return {"error": "sandbox unavailable (docker) — tools cannot be validated, not registered"}

    feedback: str | None = None
    for _attempt in (1, 2):   # one build + one repair round (router schema-repair pattern)
        source = await _ask_coder(complete_fn, purpose, args_example, feedback)
        try:
            meta = _parse_tool_file(source)
        except (SyntaxError, ValueError) as exc:
            feedback = f"contract parse failed: {exc}"
            continue
        tool = meta["tool"]
        fname = f"{tool['name']}.py"
        try:
            tool_file = resolve_within(agent_path, f"tools/{fname}")
        except UnsafePathError as exc:
            feedback = f"tool path rejected: {exc}"
            continue
        tool_file.parent.mkdir(parents=True, exist_ok=True)
        tool_file.write_text(source, encoding="utf-8")
        res = await codeexec.run_in_sandbox(str(agent_path), _RUNNER.format(fname=fname),
                                            timeout=20.0)
        if res["returncode"] == 0:
            await _register(scope=scope, agent_dir=str(agent_path), tool=tool, code=source,
                            tool_id=tool_id)
            await emit(scope, E.TOOL_CREATED, {"name": tool["name"],
                                               "description": tool.get("description", ""),
                                               "agent": agent_path.name})
            return {"tool_name": tool["name"], "description": tool.get("description", ""),
                    "args_schema": tool.get("args_schema", {})}
        feedback = (res["stderr"] or res["stdout"])[-800:] or f"exit {res['returncode']}"

    return {"error": f"self-test failed after repair round: {feedback[:400]}"}


async def _register(*, scope: str, agent_dir: str, tool: dict, code: str,
                    tool_id: str | None) -> None:
    await db.execute(
        "INSERT INTO tools (id, ts, scope, agent_dir, name, description, args_schema_json, code, "
        "self_test_passed, created_by_seat, model) VALUES (:id, :ts, :sc, :ad, :n, :d, :sch, "
        ":code, 1, 'coder', :model) ON CONFLICT(id) DO UPDATE SET code=:code, ts=:ts",
        {"id": tool_id or new_id("tool"), "ts": now_iso(), "sc": scope, "ad": agent_dir,
         "n": tool["name"], "d": tool.get("description", ""),
         "sch": json.dumps(tool.get("args_schema", {})), "code": code,
         "model": _coder_model()},
    )


def _coder_model() -> str:
    # ponytail: seat default model name, not the per-dispatch pool member — good enough for BoM
    from app.models.registry import registry
    sd = registry.seats.get("coder")
    return sd.default.model if sd and sd.default else ""


async def get_tool(tool_id: str) -> dict | None:
    return await db.fetchone("SELECT * FROM tools WHERE id = :id", {"id": tool_id})


async def get_tool_by_name(scope: str, name: str) -> dict | None:
    return await db.fetchone(
        "SELECT * FROM tools WHERE scope = :sc AND name = :n ORDER BY ts DESC LIMIT 1",
        {"sc": scope, "n": name})


async def invoke_tool(scope: str, name: str, args: dict) -> dict:
    """Run a registered tool in the sandbox: args via a file in the agent folder, stdout JSON
    back. Emits tool.invoked {name, ms, ok}."""
    try:
        safe_name = _validated_tool_name(name)
    except ValueError as exc:
        return {"error": str(exc)}
    row = await get_tool_by_name(scope, safe_name)
    if not row:
        return {"error": f"unknown tool {safe_name!r} in scope {scope}"}
    agent_path = Path(row["agent_dir"])
    try:
        row_name = _validated_tool_name(row["name"])
        fname = f"{row_name}.py"
        tool_file = resolve_within(agent_path, f"tools/{fname}")
    except (UnsafePathError, ValueError) as exc:
        return {"error": f"registered tool path rejected: {exc}"}
    if not tool_file.exists():   # re-materialize from the registry
        tool_file.parent.mkdir(parents=True, exist_ok=True)
        tool_file.write_text(row["code"], encoding="utf-8")
    argsname = f"args-{new_id('x')[-10:]}.json"
    try:
        args_file = resolve_within(agent_path, f"tools/{argsname}")
    except UnsafePathError as exc:  # generated id is trusted, but keep every write contained
        return {"error": f"tool args path rejected: {exc}"}
    args_file.write_text(json.dumps(args, default=str), encoding="utf-8")
    t0 = time.monotonic()
    try:
        res = await codeexec.run_in_sandbox(
            str(agent_path), _INVOKE.format(fname=fname, argsname=argsname), timeout=30.0)
    finally:
        args_file.unlink(missing_ok=True)
    ms = int((time.monotonic() - t0) * 1000)
    ok = res["returncode"] == 0
    await emit(scope, E.TOOL_INVOKED, {"name": name, "ms": ms, "ok": ok})
    if not ok:
        return {"error": (res["stderr"] or res["stdout"])[-400:] or f"exit {res['returncode']}"}
    try:
        return json.loads(res["stdout"].strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": f"tool printed non-JSON output: {res['stdout'][-200:]}"}
