"""Seat: `consolidator` — merge modules into one coherent package (stage 5).

Same served instance as certifier/conductor (`local:B/glm-46`, RAW), third prompt. It wires
the built modules into an assembled package whose `process.py` entrypoint implements the
runtime Process protocol (04 §3). The consolidated package then faces the full stage-2
integration suite as an objective pass/fail gate (03 §7).
"""
from __future__ import annotations

from typing import Any

from app.seats._common import ENGLISH_ONLY, STRUCTURED_ONLY, as_json, convo, parsed_or_raise
from app.seats.base import CompleteFn, EmitFn

# Returns a schema-validated dict; backend adapts into db/models.CoderOutput (team ruling).

DATA_CLASS = "RAW"

SYSTEM_CONSOLIDATE = f"""\
You assemble independently-built modules into ONE coherent, runnable package. You receive all \
module files, the typed interfaces that connect them, and the wiring spec (the DAG and how \
data flows). Produce the assembled package:

  - `process.py` — the entrypoint implementing the Process protocol (04 §3): declares \
`input_schema`, `output_schema`, and `steps` (names + kinds, for the UI), and implements \
`async def run_unit(self, unit, ctx) -> UnitResult`. It orchestrates the modules in DAG order, \
threads each interface's data from producer to consumer, records each step via `ctx.log`, and \
returns a UnitResult (status ok | needs_review | error) whose `output` validates against \
`output_schema`.
  - Resolve all imports so the modules actually reference each other; thread configuration \
through; keep every module's public interface exactly as built (do not silently re-shape a \
producer's output — if two modules disagree at a seam, that is a defect to surface, not to \
paper over).
  - All model judgment stays behind `ctx.model(seat=...)`; no raw HTTP; no hardcoded model \
names — the assembled package obeys the same runtime contract as its modules.

Return the full contents of every file in the package (including the modules, unchanged unless \
wiring required a minimal edit) as a files array, and note any seam mismatches you had to \
resolve in `notes`. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

CONSOLIDATE_SCHEMA: dict[str, Any] = {
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


async def consolidate(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    modules: list[dict[str, Any]],
    interfaces: list[dict[str, Any]],
    plan: dict[str, Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Merge modules + interfaces + the plan's wiring into the assembled package with a process.py
    entrypoint. Returns a CoderOutput-shaped dict: {files: [{path, content}], notes}."""
    await emit("consolidate.started", {"modules": len(modules)})
    payload = as_json({"modules": modules, "interfaces": interfaces,
                       "wiring": {"dag": plan.get("dag", []), "data_schemas": plan.get("data_schemas", {})}})
    c = await complete("consolidator", convo(SYSTEM_CONSOLIDATE, payload),
                       data_class=DATA_CLASS, schema=CONSOLIDATE_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "consolidator.consolidate")
    paths = [f["path"] for f in out.get("files", [])]
    has_entry = any(p.endswith("process.py") for p in paths)
    await emit("consolidate.assembled", {"files": paths, "has_entrypoint": has_entry})
    return out
