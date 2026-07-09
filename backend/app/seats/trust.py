"""Seat: `trust` — the local guardian of the boundary (stages 0, 2-egress, 7).

Runs on `local:A/gemma-4-26b-a4b` (RAW clearance). Responsibilities (02 §1, 03 §2):
intake elicitation, mode classification, RedactionPolicy distillation (D11), the
sanitization sweep that guards every consult egress (03 §4.2), the planner-brief
composition with its contractual framing (03 §2.3), and delivery-doc generation (stage 7).

Every call dispatches with data_class=RAW: `trust` is the one seat that reads raw customer
input, so it must run local. The BRIEF it produces is SANITIZED by construction — that is a
property of the artifact, enforced downstream, not of this seat's dispatch clearance.
"""
from __future__ import annotations

from typing import Any

from app.seats.base import CompleteFn, EmitFn
from app.seats._common import ENGLISH_ONLY, STRUCTURED_ONLY, as_json, convo, parsed_or_raise

# Harnesses return plain, schema-validated dicts (team ruling); the backend adapts them into
# db/models.py pydantic at the call site. Seat modules never import backend model classes — the
# AI layer stays independent of backend's artifact shapes. Schemas here are the shared contract.

DATA_CLASS = "RAW"

# ─────────────────────────────────────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_INTAKE = f"""\
You are the intake analyst for Nxcleus, a platform that builds and runs automated \
business processes without the customer's confidential data ever leaving their walls. A \
business is describing a process they want built. Your job is to interview them the way a \
senior solutions architect would: extract a precise, buildable specification in as few \
turns as possible, and never invent requirements they did not state.

Each turn you receive the conversation so far and the current draft spec. You produce:
  - spec_updates: only the fields this turn's message lets you fill or correct — entities \
and their fields (mark any field that is a person, account, contact, identifier, or secret \
as pii:true), acceptance criteria (each with how it should be verified: test | inspector | \
oracle), numeric rules (state the rule in words, name its inputs and its single output), \
connectors the process needs, and a volume estimate. Leave everything you are unsure about \
absent — do not guess.
  - assistant_message: your next message to the customer. If something load-bearing is \
missing or ambiguous, ask ONE focused question about the single highest-value gap. If the \
spec is buildable, confirm your understanding in two sentences and state that you are ready \
to plan.
  - missing: the short list of still-unknown facts that matter for planning.
  - ready_for_planning: true only when a competent planner could design the work from the \
spec without asking anything else.

Be concrete and economical. Prefer their vocabulary. Do not discuss models, prompts, GPUs, \
or how Nxcleus works internally. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_CLASSIFY = f"""\
You classify a described business process into one of three execution modes for the Nxcleus \
engine. Decide from the spec alone.

  - build   — the deliverable is an application or a set of interdependent code modules with \
declared interfaces (an onboarding pipeline, a report generator, a service). Choose this \
when the units of work depend on each other and the output is running software.
  - process — the deliverable is a corpus swept unit-by-unit with no cross-unit dependencies \
(screen every applicant, extract every contract's renewal terms, score every transaction). \
Choose this when the same operation repeats over many independent items and the output is a \
dataset plus a dashboard.
  - semi    — mostly one of the above but with a human-review step in the loop for items the \
process flags (needs_review). Choose this only when the customer explicitly wants human \
sign-off on exceptions.

State the recommended mode and a one-paragraph rationale grounded in the spec. Leave \
`confirmed` null — the customer confirms. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_POLICY = f"""\
You distill a customer's confidentiality requirements into a machine-enforceable \
RedactionPolicy that will govern what may cross the boundary to an external planning model.

You receive the customer's confidentiality inputs — any combination of an uploaded policy \
document, typed instructions, and a transcribed voice note (already transcribed locally; the \
recording never left the box). Turn every stated obligation into a rule:
  - kind: never_leak (value must never appear outside the boundary in any form), mask \
(replace the value with a typed placeholder, preserving structure), or generalize (replace a \
specific value with a category — a bank name becomes "a financial institution").
  - description: the class of thing the rule protects, in the customer's own terms.
  - applies_to: the spec locations it governs (e.g. "entities.*.fields[pii=true]", \
"documents", "db_schemas.*.table"), using glob-ish paths.
  - origin: cite the source — the policy clause ("customer_policy §4.2") or "pii_baseline".

The PII baseline is ALWAYS present regardless of what the customer says: personal names, \
account and card numbers, contacts (email/phone/address), government identifiers, and any \
credential or secret. Emit those baseline rules first (origin: pii_baseline), then the \
customer-specific rules on top. Never drop a baseline rule because the customer did not \
mention it. When in doubt about whether something is sensitive, protect it. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_BRIEF = f"""\
You are composing a briefing for a STRONGER frontier planning model that will design how to \
build this process — and that model will NEVER see the customer's real data, code, or \
schemas. It sees only what you write here. This is the single most consequential translation \
in the system: your job is maximum specification fidelity per token, under the \
RedactionPolicy.

The governing principle: STRIP VALUES, KEEP STRUCTURE. The planner does not need a real \
customer name, account number, table name, or file path to design good work — it needs to \
know the SHAPE of the problem exactly. So:
  - Replace every value the policy protects with a typed, stable placeholder that preserves \
its role and structure: «PERSON_1», «ACCOUNT_A», «TABLE_A»(id, «FIELD_1»: decimal). Reuse the \
same placeholder for the same underlying value so relationships stay legible.
  - Describe the codebase and databases well enough that a model which will never open them \
can still plan against them: module inventory, framework, dependency edges, table/field \
shapes and types, cardinalities and relations — names generalized, structure intact.
  - Preserve every numeric rule, acceptance criterion, and interface precisely — these carry \
no protected values, so state them in full. Ambiguity here becomes a defect later.
  - Recommend a mode (build | process | semi) with a rationale.
  - Fill the sensitivity_report honestly: how many PII fields you masked, documents you \
processed, which policy rule IDs you applied, how many identifiers you generalized.

Write nothing that could reconstruct a protected value — not in an example, not in a \
comment, not in a narrative aside. If preserving fidelity would require leaking a value, \
generalize instead and note the generalization. A downstream local model with full raw \
access will restore production specificity after planning; your job is to lose no STRUCTURE \
while leaking no VALUES. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_SWEEP = f"""\
You are the final residual check before a payload crosses the boundary to an external model. \
Upstream code has already mechanically replaced every KNOWN protected value with its \
placeholder using the boundary vault. Your job is to catch what mechanical substitution \
missed: a real name embedded in prose, an account number inside a sentence, a table or file \
name that leaked through, a paraphrased secret, a value spelled differently than the vault \
key.

You receive the candidate outbound payload and the list of placeholder tokens that SHOULD be \
the only sensitive-slot markers present. Report:
  - clean: true only if you find no residual real value.
  - residuals: for each leak, the offending span, its kind (person | account | contact | \
identifier | secret | internal_name | other), and a safe replacement placeholder.
  - masked_payload: the payload with every residual you found replaced by a placeholder — \
byte-for-byte identical to the input except for those replacements.

Err toward flagging. A false positive costs a placeholder; a false negative breaches the \
customer's policy. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

SYSTEM_DOCS = f"""\
You write the delivery documentation for a completed Nxcleus process, from its certified \
plan and its goal statement. Produce two documents:
  - readme_md: what the process does, its inputs and outputs, its acceptance criteria, how to \
run a batch, and the model bill-of-materials at a glance (which seats do what). Written for \
the customer's operator, not for a developer of Nxcleus.
  - runbook_md: how to operate it — running a batch, reading results, handling needs_review \
items, interpreting the numeric-oracle and inspector assurance, and what each per-run cost \
line means.

Ground every statement in the plan and goal you are given; do not invent capabilities. Use \
clean Markdown with real headings and short paragraphs. {ENGLISH_ONLY}

{STRUCTURED_ONLY}"""

# ─────────────────────────────────────────────────────────────────────────────
# Structured-output schemas (what the seat returns; kept legible for review)
# ─────────────────────────────────────────────────────────────────────────────

INTAKE_TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "spec_updates": {
            "type": "object",
            "description": "Partial SanitizedSpec fields this turn can fill; omit unknowns.",
            "additionalProperties": True,
        },
        "assistant_message": {"type": "string"},
        "missing": {"type": "array", "items": {"type": "string"}},
        "ready_for_planning": {"type": "boolean"},
    },
    "required": ["spec_updates", "assistant_message", "missing", "ready_for_planning"],
}

MODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommended": {"enum": ["build", "process", "semi"]},
        "confirmed": {"type": "null"},
        "rationale": {"type": "string"},
    },
    "required": ["recommended", "rationale"],
}

POLICY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"kind": {"enum": ["doc", "text", "voice"]}, "ref": {"type": "string"}},
                "required": ["kind"],
            },
        },
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"enum": ["never_leak", "mask", "generalize"]},
                    "description": {"type": "string"},
                    "applies_to": {"type": "array", "items": {"type": "string"}},
                    "origin": {"type": "string"},
                },
                "required": ["id", "kind", "description", "origin"],
            },
        },
    },
    "required": ["rules"],
}

# The brief IS a SanitizedSpec (03 §2.3). Hand-written to mirror db/models.SanitizedSpec without
# importing it (team ruling) — additive roots so backend can adapt losslessly.
BRIEF_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": True,
    "properties": {
        "title": {"type": "string"},
        "narrative": {"type": "string"},
        "mode": {"type": "object", "properties": {
            "recommended": {"enum": ["build", "process", "semi"]},
            "confirmed": {"type": ["string", "null"]}, "rationale": {"type": "string"}}},
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "fields": {"type": "array", "items": {"type": "object",
                "properties": {"name": {"type": "string"}, "type": {"type": "string"},
                               "pii": {"type": "boolean"}}, "required": ["name"]}}},
            "required": ["name"]}},
        "acceptance_criteria": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "text": {"type": "string"},
            "verify": {"enum": ["test", "inspector", "oracle"]}}, "required": ["id"]}},
        "numeric_rules": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "text": {"type": "string"},
            "inputs": {"type": "array", "items": {"type": "string"}}, "output": {"type": "string"}},
            "required": ["id"]}},
        "context_pack": {"type": "object", "additionalProperties": True, "properties": {
            "code_map": {"type": "object", "additionalProperties": True},
            "db_schemas": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "attachments": {"type": "array", "items": {"type": "object", "properties": {
                "kind": {"type": "string"}, "summary": {"type": "string"}}}}}},
        "connectors": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "kind": {"enum": ["dataset", "api", "mcp"]},
            "mock": {"type": "boolean"}}, "required": ["name"]}},
        "volume": {"type": "object", "properties": {
            "units_estimate": {"type": "integer"}, "unit_noun": {"type": "string"}}},
        "sensitivity_report": {"type": "object", "additionalProperties": True, "properties": {
            "pii_fields_masked": {"type": "integer"}, "documents_ocred": {"type": "integer"},
            "policy_rules_applied": {"type": "array", "items": {"type": "string"}},
            "identifiers_generalized": {"type": "integer"}}},
    },
    "required": ["title", "narrative", "mode"],
}

SWEEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "clean": {"type": "boolean"},
        "residuals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span": {"type": "string"},
                    "kind": {"enum": ["person", "account", "contact", "identifier",
                                       "secret", "internal_name", "other"]},
                    "replacement": {"type": "string"},
                },
                "required": ["span", "kind", "replacement"],
            },
        },
        "masked_payload": {"type": "string"},
    },
    "required": ["clean", "residuals", "masked_payload"],
}

DOCS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"readme_md": {"type": "string"}, "runbook_md": {"type": "string"}},
    "required": ["readme_md", "runbook_md"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Harnesses
# ─────────────────────────────────────────────────────────────────────────────


async def intake_turn(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    draft_spec: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """One elicitation turn. Returns {spec_updates, assistant_message, missing, ready_for_planning}."""
    payload = as_json({"draft_spec": draft_spec, "history": history, "customer_message": user_message})
    c = await complete("trust", convo(SYSTEM_INTAKE, payload),
                       data_class=DATA_CLASS, schema=INTAKE_TURN_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "trust.intake_turn")
    await emit("intake.turn", {"ready": out.get("ready_for_planning", False),
                               "missing": out.get("missing", [])})
    return out


async def classify_mode(
    complete: CompleteFn, emit: EmitFn, *, spec: dict[str, Any], temperature: float | None = None,
) -> dict[str, Any]:
    """Returns a ModeChoice-shaped dict: {recommended, confirmed, rationale}."""
    c = await complete("trust", convo(SYSTEM_CLASSIFY, as_json(spec)),
                       data_class=DATA_CLASS, schema=MODE_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "trust.classify_mode")
    await emit("intake.mode_classified", {"recommended": out.get("recommended")})
    return out


async def distill_policy(
    complete: CompleteFn, emit: EmitFn, *, sources: list[dict[str, Any]], temperature: float | None = None,
) -> dict[str, Any]:
    """Distill doc/text/voice confidentiality inputs into a RedactionPolicy-shaped dict (D11)."""
    c = await complete("trust", convo(SYSTEM_POLICY, as_json({"sources": sources})),
                       data_class=DATA_CLASS, schema=POLICY_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "trust.distill_policy")
    out.setdefault("sources", [{"kind": s.get("kind", "text"), "ref": s.get("ref", "")} for s in sources])
    rules = out.get("rules", [])
    await emit("intake.policy_registered", {"rules": len(rules),
               "baseline_only": all(r.get("origin") == "pii_baseline" for r in rules)})
    return out


async def compose_brief(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    raw_request: str,
    raw_context: dict[str, Any],
    policy: dict[str, Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Compose the planner brief (SanitizedSpec-shaped dict) under the RedactionPolicy — the
    load-bearing translation (03 §2.3). Input is RAW; output is SANITIZED by construction."""
    payload = as_json({"raw_request": raw_request, "raw_context": raw_context,
                       "redaction_policy": policy})
    c = await complete("trust", convo(SYSTEM_BRIEF, payload),
                       data_class=DATA_CLASS, schema=BRIEF_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "trust.compose_brief")
    sr = out.get("sensitivity_report", {})
    await emit("boundary.sanitized", {
        "pii_fields_masked": sr.get("pii_fields_masked", 0),
        "documents_ocred": sr.get("documents_ocred", 0),
        "policy_rules_applied": sr.get("policy_rules_applied", []),
        "identifiers_generalized": sr.get("identifiers_generalized", 0),
    })
    return out


async def sanitization_sweep(
    complete: CompleteFn,
    emit: EmitFn,
    *,
    candidate_payload: str,
    placeholder_tokens: list[str],
    temperature: float | None = None,
) -> dict[str, Any]:
    """Residual check before a consult crosses the boundary (03 §4.2). Returns
    {clean, residuals[], masked_payload}. The consult gate blocks egress unless clean
    (or re-runs on masked_payload)."""
    payload = as_json({"candidate_payload": candidate_payload, "known_placeholders": placeholder_tokens})
    c = await complete("trust", convo(SYSTEM_SWEEP, payload),
                       data_class=DATA_CLASS, schema=SWEEP_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "trust.sanitization_sweep")
    await emit("boundary.sweep", {"clean": out.get("clean", False),
                                  "residuals": len(out.get("residuals", []))})
    return out


async def generate_docs(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], goal: str, temperature: float | None = None,
) -> dict[str, str]:
    """Stage-7 README + runbook from the certified plan and goal. Returns {readme_md, runbook_md}."""
    c = await complete("trust", convo(SYSTEM_DOCS, as_json({"plan": plan, "goal": goal})),
                       data_class=DATA_CLASS, schema=DOCS_SCHEMA, temperature=temperature)
    out = parsed_or_raise(c, "trust.generate_docs")
    await emit("deliver.docs_generated", {"readme_chars": len(out.get("readme_md", "")),
                                          "runbook_chars": len(out.get("runbook_md", ""))})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Engine entrypoints — canonical call-site names (app/seats/_placeholder.py). The
# seatlib SeatProxy resolves per-attribute, so these override the placeholders while
# the rich harnesses above do the work.
# ─────────────────────────────────────────────────────────────────────────────


async def build_spec(
    complete: CompleteFn, emit: EmitFn, *, request: str, files: list | None = None,
    code_map: dict | None = None, db_schema: dict | None = None, policy: dict | None = None,
    messages: list | None = None, temperature: float | None = None,
) -> dict[str, Any]:
    """Stage-0 single-shot brief composition (SanitizedSpec dict). Delegates to compose_brief."""
    raw_context = {"files": files or [], "code_map": code_map or {},
                   "db_schema": db_schema or {}, "messages": messages or []}
    return await compose_brief(complete, emit, raw_request=request, raw_context=raw_context,
                               policy=policy or {}, temperature=temperature)


async def write_docs(
    complete: CompleteFn, emit: EmitFn, *, plan: dict[str, Any], goal: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Stage-7 docs in the package's expected keys. Delegates to generate_docs."""
    docs = await generate_docs(complete, emit, plan=plan, goal=goal, temperature=temperature)
    modules = plan.get("modules") or [{}]
    return {
        "readme": docs.get("readme_md", ""),
        "runbook": docs.get("runbook_md", ""),
        "qa_report": "## QA report\nSee tickets, Numeric-Oracle checks, and the goal-fulfillment "
                     "verdict recorded in this package.\n",
        "entry_module": modules[0].get("name") or modules[0].get("id", "process"),
    }


async def sanitize_consult(
    complete: CompleteFn, emit: EmitFn, *, payload: str, vault_map: dict[str, str],
    temperature: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Consult egress gate (03 §4.2): backend's mechanical vault masking, then the trust-seat
    model residual sweep. Returns (masked_payload, receipt)."""
    from app.boundary.sanitize import consult_sanitize   # backend-owned mechanical step

    masked, receipt = consult_sanitize(payload, vault_map)
    sweep = await sanitization_sweep(complete, emit, candidate_payload=masked,
                                     placeholder_tokens=list(vault_map.values()), temperature=temperature)
    final = masked if sweep.get("clean", True) else sweep.get("masked_payload", masked)
    receipt = {**receipt, "residuals": sweep.get("residuals", []), "clean": sweep.get("clean", True)}
    return final, receipt
