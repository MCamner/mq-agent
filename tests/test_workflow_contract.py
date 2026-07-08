"""Contract tests for the v1 workflow plan (Phase 1).

These lock the SHAPE of a workflow plan before any runner or execution exists.
They cover both the pydantic enforcement (mq_agent.workflows) and the declarative
JSON Schema artifact (schemas/workflow-plan.v1.json).

No OpenAI calls, no external services, no tool execution.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mq_agent.workflows import (
    DEFAULT_MAX_STEPS,
    MAX_STEPS_HARD_CAP,
    SCHEMA_ID,
    StepStatus,
    WorkflowPlan,
    WorkflowStatus,
    validate_plan,
)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "workflow-plan.v1.json"


def _step(step_id: str, *, tool: str = "run_mqlaunch_doctor", depends_on=None, **over):
    step: dict[str, object] = {
        "id": step_id,
        "name": f"Step {step_id}",
        "tool": tool,
        "args": {},
        "depends_on": depends_on or [],
        "condition": "always",
        "approval": "none",
        "status": "pending",
        "attempt": 0,
        "result": None,
        "error": None,
    }
    step.update(over)
    return step


def _plan(*, steps=None, **over):
    plan = {
        "schema": SCHEMA_ID,
        "run_id": "run_20260626_001",
        "template": "repo-preflight",
        "task": "Verify repository readiness",
        "repo": "/Users/mansys/macos-scripts",
        "status": "planned",
        "current_step": None,
        "max_steps": DEFAULT_MAX_STEPS,
        "max_replans": 0,
        "steps": steps if steps is not None else [_step("s1")],
    }
    plan.update(over)
    return plan


# --- valid plans -----------------------------------------------------------


def test_valid_plan_accepted():
    plan = validate_plan(_plan())
    assert isinstance(plan, WorkflowPlan)
    assert plan.schema_ == SCHEMA_ID
    assert plan.status is WorkflowStatus.PLANNED
    assert plan.steps[0].status is StepStatus.PENDING


def test_valid_multi_step_dependency_chain_accepted():
    steps = [
        _step("s1"),
        _step("s2", depends_on=["s1"]),
        _step("s3", depends_on=["s2"]),
    ]
    plan = validate_plan(_plan(steps=steps, current_step="s1"))
    assert [s.id for s in plan.steps] == ["s1", "s2", "s3"]


def test_defaults_applied_for_optional_step_fields():
    minimal_step = {"id": "s1", "name": "Doctor", "tool": "run_mqlaunch_doctor"}
    plan = validate_plan(_plan(steps=[minimal_step]))
    step = plan.steps[0]
    assert step.condition.value == "always"
    assert step.approval.value == "none"
    assert step.status is StepStatus.PENDING
    assert step.attempt == 0


# --- rejections ------------------------------------------------------------


def test_wrong_schema_id_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(schema="mq-workflow-plan.v2"))


def test_unknown_top_level_field_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(surprise="boom"))


def test_unknown_step_field_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1", surprise="boom")]))


def test_unknown_workflow_status_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(status="exploding"))


def test_unknown_step_status_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1", status="exploding")]))


def test_duplicate_step_ids_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1"), _step("s1")]))


def test_missing_dependency_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1", depends_on=["ghost"])]))


def test_self_dependency_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1", depends_on=["s1"])]))


def test_dependency_cycle_rejected():
    steps = [
        _step("s1", depends_on=["s3"]),
        _step("s2", depends_on=["s1"]),
        _step("s3", depends_on=["s2"]),
    ]
    with pytest.raises(ValidationError) as exc:
        validate_plan(_plan(steps=steps, max_steps=6))
    assert "cycle" in str(exc.value).lower()


def test_more_than_ten_steps_rejected():
    steps = [_step(f"s{i}") for i in range(MAX_STEPS_HARD_CAP + 1)]
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=steps, max_steps=MAX_STEPS_HARD_CAP))


def test_max_steps_above_cap_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(max_steps=MAX_STEPS_HARD_CAP + 1))


def test_step_count_exceeding_max_steps_rejected():
    steps = [_step("s1"), _step("s2"), _step("s3")]
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=steps, max_steps=2))


def test_max_replans_one_allowed_but_two_rejected():
    # Phase 10: a single adaptive replan is allowed; the cap stays 1.
    validate_plan(_plan(max_replans=1))
    with pytest.raises(ValidationError):
        validate_plan(_plan(max_replans=2))


def test_empty_tool_name_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1", tool="")]))


def test_shell_exec_tool_rejected():
    with pytest.raises(ValidationError):
        validate_plan(_plan(steps=[_step("s1", tool="shell_exec")]))


def test_current_step_must_reference_existing_step():
    with pytest.raises(ValidationError):
        validate_plan(_plan(current_step="ghost"))


# --- JSON Schema artifact --------------------------------------------------


def test_schema_file_is_present_and_well_formed():
    data = json.loads(SCHEMA_PATH.read_text())
    assert data["$id"].endswith("workflow-plan.v1.json")
    assert data["properties"]["schema"]["const"] == SCHEMA_ID
    assert data["additionalProperties"] is False


def test_json_schema_accepts_valid_plan():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    # Should not raise.
    jsonschema.validate(instance=_plan(), schema=schema)


def test_json_schema_rejects_shell_exec():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=_plan(steps=[_step("s1", tool="shell_exec")]), schema=schema
        )


def test_json_schema_rejects_unknown_top_level_field():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=_plan(surprise="boom"), schema=schema)
