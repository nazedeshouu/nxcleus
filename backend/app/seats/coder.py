"""Seat: `coder` (pool) — module implementation + defect fixes (stage 4, QA loop).

Capability-routed pool (`qwen3-coder-next` / `qwen36-27b` / `devstral-small-2`, plus a Gemma
guest for docs/extraction), RAW clearance (the plan is production-specific by D9). The
scheduler picks the member from `task_flags` (02 §7.4); this module owns the prompt.

The output MUST target the runtime contract (04 §3): deterministic plain Python, all model
judgment via `await ctx.model(seat=...)`, no raw HTTP, no hardcoded model names.
"""
from __future__ import annotations

from typing import Any

from app.seats.base import CompleteFn, EmitFn
from app.seats._common import ENGLISH_ONLY, STRUCTURED_ONLY, as_json, convo, parsed_or_raise

# Returns a schema-validated dict; backend adapts into db/models.CoderOutput (team ruling).

DATA_CLASS = "RAW"

_RUNTIME_CONTRACT = """\
Your code runs inside the Nxcleus process-runtime container and MUST obey its contract:
  - Implement plain, DETERMINISTIC Python. Business logic is ordinary code — no hidden state, \
no wall-clock or random dependence unless the spec says so.
  - Any step that needs MODEL JUDGMENT (classification, extraction, a written rationale) calls \
`await ctx.model(seat="<seat>", messages=..., schema=...)`. You never open an HTTP client, you \
never name a model or provider, you never call an LLM API directly — the seat is the only way \
to reach intelligence, and the platform scopes and meters it.
  - The unit entrypoint returns a UnitResult with status "ok" | "needs_review" | "error", an \
`output` validated against the module's output schema, and a `trace` of per-step records via \
`ctx.log(step, **fields)`. Use "needs_review" for items a human must sign off (semi mode) — it \
is a first-class outcome, not an error.
  - Network is closed except `ctx.model`. External data comes through `ctx.connector(name)` \
(mock connectors), never a raw fetch. Read config from the unit/ctx, never hardcode secrets."""

SYSTEM_IMPLEMENT = f"""\
You implement ONE module of a certified plan. You receive the module spec (rehydrated — real \
names, real schemas), its TOUCH POINTS (exactly the interfaces it consumes and provides, so \
you cannot diverge from parallel agents you never see), the relevant test specs, and the \
coding standards. Build exactly this module against those interfaces — do not redesign, do not \
reach outside your declared touch points.

{_RUNTIME_CONTRACT}

Write real, complete code — no placeholders, no TODOs, no stubs that "would" work. Handle the \
failure branches the spec calls for. Emit every file the module needs (implementation and its \
own tests if the test specs imply them) as a files array with full contents. Put any decisions \
or assumptions in `notes`. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_FIX = f"""\
You fix a defect in a module that already exists. You receive the defect ticket (with a \
reproducible request/response or vector/expected/actual), the module's current source, and \
the relevant tests. Make the SMALLEST change that makes the failing case pass without breaking \
the others — a surgical edit, not a rewrite. Keep the module's interfaces and the runtime \
contract intact.

{_RUNTIME_CONTRACT}

Return the full updated contents of every file you changed, and explain the fix in `notes`. \
{ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

CODER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "files": {"type": "array", "items": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}},
        "notes": {"type": "string"},
    },
    "required": ["files"],
}


async def implement(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    module_spec: dict[str, Any],
    interfaces: list[dict[str, Any]],
    test_specs: list[dict[str, Any]],
    coding_standards: str = "",
    temperature: float | None = None,
) -> dict[str, Any]:
    """Implement one module against its touch points and test specs (03 §6 worker contract).
    Returns a CoderOutput-shaped dict: {files: [{path, content}], notes}."""
    payload = as_json({"module": module_spec, "interfaces": interfaces,
                       "test_specs": test_specs, "coding_standards": coding_standards})
    c = await complete("coder", convo(SYSTEM_IMPLEMENT, payload),
                       data_class=DATA_CLASS, schema=CODER_OUTPUT_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "coder.implement")
    await emit("task.files_written", {"module": module_spec.get("id"),
               "files": [f["path"] for f in out.get("files", [])]})
    return out


async def fix(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    ticket: dict[str, Any],
    module_source: dict[str, str],
    tests: list[dict[str, Any]],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Defect-fix micro-loop (08 §6): ticket + module source + tests -> surgical patch (dict)."""
    payload = as_json({"ticket": ticket, "module_source": module_source, "tests": tests})
    c = await complete("coder", convo(SYSTEM_FIX, payload),
                       data_class=DATA_CLASS, schema=CODER_OUTPUT_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "coder.fix")
    await emit("task.fix_applied", {"ticket": ticket.get("title"),
               "files": [f["path"] for f in out.get("files", [])]})
    return out
