"""Every structured-output schema a seat exposes is a structurally valid JSON Schema."""
from _fake import is_valid_json_schema

from app.seats import certifier, coder, conductor, consolidator, inspector, oracle, planner, trust

SCHEMAS = [
    ("trust.INTAKE_TURN_SCHEMA", trust.INTAKE_TURN_SCHEMA),
    ("trust.MODE_SCHEMA", trust.MODE_SCHEMA),
    ("trust.POLICY_SCHEMA", trust.POLICY_SCHEMA),
    ("trust.BRIEF_SCHEMA", trust.BRIEF_SCHEMA),
    ("trust.SWEEP_SCHEMA", trust.SWEEP_SCHEMA),
    ("trust.DOCS_SCHEMA", trust.DOCS_SCHEMA),
    ("planner.PLAN_SCHEMA", planner.PLAN_SCHEMA),
    ("certifier.FINDINGS_SCHEMA", certifier.FINDINGS_SCHEMA),
    ("certifier.GOAL_SCHEMA", certifier.GOAL_SCHEMA),
    ("certifier.TESTS_SCHEMA", certifier.TESTS_SCHEMA),
    ("certifier.SCENARIOS_SCHEMA", certifier.SCENARIOS_SCHEMA),
    ("certifier.REFINE_TRIAGE_SCHEMA", certifier.REFINE_TRIAGE_SCHEMA),
    ("conductor.REVIEW_SCHEMA", conductor.REVIEW_SCHEMA),
    ("coder.CODER_OUTPUT_SCHEMA", coder.CODER_OUTPUT_SCHEMA),
    ("consolidator.CONSOLIDATE_SCHEMA", consolidator.CONSOLIDATE_SCHEMA),
    ("oracle.ORACLE_ANSWER_SCHEMA", oracle.ORACLE_ANSWER_SCHEMA),
    ("inspector.ACTION_SCHEMA", inspector.ACTION_SCHEMA),
    ("inspector.GOAL_CHECK_SCHEMA", inspector.GOAL_CHECK_SCHEMA),
]


def test_all_schemas_structurally_valid():
    for name, schema in SCHEMAS:
        problems = is_valid_json_schema(schema)
        assert not problems, f"{name} invalid: {problems}"


def test_schemas_are_objects_with_properties():
    for name, schema in SCHEMAS:
        assert isinstance(schema, dict), name
        assert schema.get("type") == "object" or "$ref" in schema or "properties" in schema, name


def test_plan_module_ids_share_the_ascii_build_contract():
    expected = r"^[A-Za-z_][A-Za-z0-9_]*$"
    module_id = planner.PLAN_SCHEMA["properties"]["modules"]["items"]["properties"]["id"]
    dag_module = planner.PLAN_SCHEMA["properties"]["dag"]["items"]["properties"]["module"]

    assert module_id == {"type": "string", "pattern": expected}
    assert dag_module == {"type": "string", "pattern": expected}
    assert planner.PLAN_SCHEMA["properties"]["dag"]["items"]["required"] == ["task", "module"]
