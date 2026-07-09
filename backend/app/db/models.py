"""Pydantic artifact shapes — the source of truth for every `*_json` payload (spec 05 header).

Shapes are lifted verbatim from the canonical JSONC examples in specs 03 (build pipeline) and
04 (registry). Seat modules build these; the router validates structured output against
`Model.model_json_schema()`; DAO modules serialize them into the `*_json` columns.

Design rules:
- Additive-only after the UI session starts (06 rule). New optional fields are safe.
- Roots allow extra keys (`extra="allow"`) so a downstream consumer can annotate without a
  schema break; nested leaf shapes stay typed so the contract is real.
- Every field a stage *reads* has a default, so MockClient can synthesize a minimal valid
  instance from the schema and the walking skeleton never blocks on a missing key.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- shared

DataClass = Literal["RAW", "SANITIZED"]
Mode = Literal["build", "process", "semi"]
Severity = Literal["blocker", "major", "minor", "disagreement"]


class Artifact(BaseModel):
    """Base for top-level persisted artifacts: forbid nothing, keep validation cheap."""
    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------- stage 0: policy + spec


class PolicySource(BaseModel):
    kind: Literal["doc", "text", "voice"]
    ref: str = ""


class RedactionRule(BaseModel):
    id: str
    kind: Literal["never_leak", "mask", "generalize"]
    description: str = ""
    applies_to: list[str] = Field(default_factory=list)
    origin: str = "pii_baseline"          # "customer_policy §4.2" | "pii_baseline"


class RedactionPolicy(Artifact):
    """jobs.policy_json — the customer's distilled 'never leak' rules (03 §2.1, D11)."""
    sources: list[PolicySource] = Field(default_factory=list)
    rules: list[RedactionRule] = Field(default_factory=list)


class SpecField(BaseModel):
    name: str
    type: str = "string"
    pii: bool = False


class Entity(BaseModel):
    name: str
    fields: list[SpecField] = Field(default_factory=list)


class AcceptanceCriterion(BaseModel):
    id: str
    text: str = ""
    verify: Literal["test", "inspector", "oracle"] = "test"


class NumericRule(BaseModel):
    id: str
    text: str = ""
    inputs: list[str] = Field(default_factory=list)
    output: str = ""


class CodeMap(BaseModel):
    model_config = ConfigDict(extra="allow")
    files: int = 0
    modules: list[Any] = Field(default_factory=list)
    framework: str = ""
    tree_ref: str = ""


class DbSchemaRef(BaseModel):
    model_config = ConfigDict(extra="allow")
    table: str
    fields: list[Any] = Field(default_factory=list)


class Attachment(BaseModel):
    kind: str = "spec_doc"                 # policy_doc | spec_doc
    summary: str = ""


class ContextPack(BaseModel):
    model_config = ConfigDict(extra="allow")
    code_map: CodeMap | None = None
    db_schemas: list[DbSchemaRef] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)


class Connector(BaseModel):
    name: str
    kind: Literal["dataset", "api", "mcp"] = "dataset"
    mock: bool = True


class Volume(BaseModel):
    units_estimate: int = 0
    unit_noun: str = "unit"


class SensitivityReport(BaseModel):
    model_config = ConfigDict(extra="allow")
    pii_fields_masked: int = 0
    documents_ocred: int = 0
    policy_rules_applied: list[str] = Field(default_factory=list)
    identifiers_generalized: int = 0


class ModeChoice(BaseModel):
    recommended: Mode = "build"
    confirmed: Mode | None = None
    rationale: str = ""


class SanitizedSpec(Artifact):
    """jobs.spec_json — the planner brief (03 §2.3). SANITIZED by construction."""
    title: str = ""
    narrative: str = ""
    mode: ModeChoice = Field(default_factory=ModeChoice)
    entities: list[Entity] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    numeric_rules: list[NumericRule] = Field(default_factory=list)
    context_pack: ContextPack = Field(default_factory=ContextPack)
    connectors: list[Connector] = Field(default_factory=list)
    volume: Volume = Field(default_factory=Volume)
    sensitivity_report: SensitivityReport = Field(default_factory=SensitivityReport)


# --------------------------------------------------------------------------- stage 1: the Plan

# canonical capability flag vocabulary (02 §7.2) — kept as a Literal so nonsense flags are visible
TaskFlag = Literal[
    "greenfield-codegen", "refactor-edit", "sql-data", "test-writing", "docs-writing",
    "extraction", "math", "agentic-tool-use", "long-context", "merge-review",
]


class Module(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str = ""
    purpose: str = ""
    consumes: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    algorithm: str = ""
    complexity: Literal["S", "M", "L"] = "M"
    task_flags: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    model: str | None = None               # explicit pin (02 §7.4) — overrides capability routing


class Interface(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    producer: str = ""
    consumers: list[str] = Field(default_factory=list)
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class DagTask(BaseModel):
    task: str
    module: str = ""
    deps: list[str] = Field(default_factory=list)


class TopologyUnit(BaseModel):
    model_config = ConfigDict(extra="allow")
    noun: str = "unit"
    source: str = "corpus"
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class TopologyStep(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    seat: str | None = None
    per_unit: bool = True
    kind: str | None = None                # e.g. "aggregate"
    prompt_spec: str = ""
    output_schema: dict[str, Any] = Field(default_factory=dict)
    task_flags: list[str] = Field(default_factory=list)


class Topology(BaseModel):
    model_config = ConfigDict(extra="allow")
    unit: TopologyUnit = Field(default_factory=TopologyUnit)
    steps: list[TopologyStep] = Field(default_factory=list)


class BomSeat(BaseModel):
    model_config = ConfigDict(extra="allow")
    seat: str
    count: int = 1
    why: str = ""
    sampling: float | None = None


class BomFleet(BaseModel):
    model_config = ConfigDict(extra="allow")
    profile: str = "P2"
    nodes: int = 1
    parallel_width: int = 1


class ModelBom(BaseModel):
    model_config = ConfigDict(extra="allow")
    seats: list[BomSeat] = Field(default_factory=list)
    fleet: BomFleet = Field(default_factory=BomFleet)
    conductor: dict[str, Any] | None = None    # {"always": true} forces review on single-wave DAGs


class PlanEstimates(BaseModel):
    model_config = ConfigDict(extra="allow")
    frontier_tokens: int = 0
    local_tokens: float = 0
    gpu_hours: float = 0


class Plan(Artifact):
    """plans.body_json — the frontier-authored, certifier-rehydrated-and-amended artifact (03 §3)."""
    plan_id: str = ""
    job_id: str = ""
    version: int = 1
    mode: Mode = "build"
    modules: list[Module] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    dag: list[DagTask] = Field(default_factory=list)
    topology: Topology | None = None
    data_schemas: dict[str, Any] = Field(default_factory=dict)
    model_bom: ModelBom = Field(default_factory=ModelBom)
    estimates: PlanEstimates = Field(default_factory=PlanEstimates)
    risks: list[str] = Field(default_factory=list)


class ScopeLock(BaseModel):
    """Constrained re-plan / conductor amendment scope (03 §3, §6)."""
    only_regions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- stage 2: certification


class Patch(BaseModel):
    """An RFC-6902-shaped patch applied to a plan region."""
    model_config = ConfigDict(extra="allow")
    op: str = "replace"
    path: str = ""
    value: Any = None


class Amendment(BaseModel):
    """amendments.patch_json + rationale (03 §4). Hash-chained by the DAO, not here."""
    model_config = ConfigDict(extra="allow")
    plan_ref: str = ""
    patch: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    rationale: str = ""
    spec_ref: str = ""


class ConsultRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    scope: ScopeLock = Field(default_factory=ScopeLock)
    question: str = ""
    findings: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """certify.finding payload + triage (03 §4)."""
    model_config = ConfigDict(extra="allow")
    finding_id: str
    check: str = ""
    plan_ref: str = ""
    severity: Literal["gap", "inconsistency", "structural"] = "gap"
    triage: Literal["amend", "consult"] = "amend"
    amendment: Amendment | None = None
    consult_request: ConsultRequest | None = None


class TestExpectation(BaseModel):
    path: str
    op: str = "eq"
    value: Any = None


class IntegrationTestSpec(BaseModel):
    """tests/integration.json entry (03 §4.3)."""
    model_config = ConfigDict(extra="allow")
    id: str
    module: str = ""
    kind: Literal["integration", "unit"] = "integration"
    given: dict[str, Any] = Field(default_factory=dict)
    expect: list[TestExpectation] = Field(default_factory=list)


class OracleVector(BaseModel):
    """tests/vectors.json entry — inputs only; expected computed blind at stage 6 (03 §4.3, 08 §4)."""
    model_config = ConfigDict(extra="allow")
    id: str
    rule: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    tolerance: str | None = None           # "exact" | "epsilon:0.01"


class Goal(Artifact):
    """jobs.goal is stored as plain text; this carries the goal + its stage-6 verdict in the package."""
    text: str = ""
    verdict: Literal["fulfilled", "partial", "unfulfilled", "unchecked"] = "unchecked"
    gaps: list[dict[str, Any]] = Field(default_factory=list)


class CertifyResult(BaseModel):
    """What the certifier seat returns to stage 2 (assembled by the certify stage)."""
    model_config = ConfigDict(extra="allow")
    findings: list[Finding] = Field(default_factory=list)
    goal: str = ""
    tests: list[IntegrationTestSpec] = Field(default_factory=list)
    vectors: list[OracleVector] = Field(default_factory=list)
    adversarial_scenarios: list[str] = Field(default_factory=list)
    identifiers_rehydrated: int = 0


# --------------------------------------------------------------------------- stage 4: conductor + coder


class ConductorReview(BaseModel):
    """conductor.review payload (03 §6)."""
    model_config = ConfigDict(extra="allow")
    verdict: Literal["proceed", "amend"] = "proceed"
    wave_assessment: str = ""
    goal_drift: str | None = None
    amendments: list[Amendment] = Field(default_factory=list)
    rework: list[dict[str, Any]] = Field(default_factory=list)   # [{module_id, instruction}]


class SourceFile(BaseModel):
    path: str
    content: str = ""


class CoderOutput(BaseModel):
    """Worker out (03 §6)."""
    files: list[SourceFile] = Field(default_factory=list)
    notes: str = ""


# --------------------------------------------------------------------------- stage 6: QA


class Repro(BaseModel):
    model_config = ConfigDict(extra="allow")
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    vector: str | None = None
    expected: Any = None
    actual: Any = None


class Ticket(BaseModel):
    """tickets.body_json (08 §6)."""
    model_config = ConfigDict(extra="allow")
    title: str = ""
    instrument: Literal["inspector", "oracle", "consolidation", "warranty"] = "inspector"
    repro: Repro = Field(default_factory=Repro)
    suspected_modules: list[str] = Field(default_factory=list)
    severity: Severity = "major"


class GoalGap(BaseModel):
    goal_clause: str = ""
    evidence: str = ""
    severity: Literal["blocker", "caveat"] = "caveat"


class GoalCheck(BaseModel):
    """qa.goal_check payload (08 §1.5)."""
    verdict: Literal["fulfilled", "partial", "unfulfilled"] = "fulfilled"
    gaps: list[GoalGap] = Field(default_factory=list)


class OracleComputation(BaseModel):
    """What the oracle seat returns for a vector (08 §4) — expected value + self-consistency votes."""
    model_config = ConfigDict(extra="allow")
    expected: Any = None
    votes: list[Any] = Field(default_factory=list)
    uncertain: bool = False


# --------------------------------------------------------------------------- stage 3 / 7: money


class QuoteLine(BaseModel):
    item: str
    qty: str = ""
    est_usd: list[float] = Field(default_factory=lambda: [0.0, 0.0])   # [low, high]


class QuoteBody(Artifact):
    """quotes.body_json (10 §4)."""
    lines: list[QuoteLine] = Field(default_factory=list)
    total_est_usd: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    basis: str = ""


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="allow")
    item: str
    qty: str = ""
    actual_usd: float = 0.0
    quote_usd: list[float] | None = None
    tokens_in: int = 0
    tokens_out: int = 0


class Invoice(Artifact):
    """package invoice.json (10 §5) — exact actuals aggregated from meter_events."""
    lines: list[InvoiceLine] = Field(default_factory=list)
    total_usd: float = 0.0
    quote_total_est_usd: list[float] | None = None
    footnote: str = "GPU-seconds are an estimate (10 §2); token counts are exact."
    frontier_calls: int = 0


# --------------------------------------------------------------------------- stage 7: package manifest + runtime


class StepMeta(BaseModel):
    name: str
    kind: str = ""


class Manifest(Artifact):
    """package manifest.json (04 §2)."""
    name: str = ""
    slug: str = ""
    version: int = 1
    mode: Mode = "build"
    goal: str = ""
    model_bom: ModelBom = Field(default_factory=ModelBom)
    connectors: list[Connector] = Field(default_factory=list)
    entrypoint: str = "process.py"
    image_tag: str | None = None
    sampling: float = 0.05
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepMeta] = Field(default_factory=list)
    seats: list[str] = Field(default_factory=list)         # model-proxy allowlist (06 §4)


class UnitResult(BaseModel):
    """runtime contract (04 §3) — one unit of work's result."""
    model_config = ConfigDict(extra="allow")
    status: Literal["ok", "needs_review", "error"] = "ok"
    output: dict[str, Any] = Field(default_factory=dict)
    trace: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [name for name in dir() if name[0].isupper()]
