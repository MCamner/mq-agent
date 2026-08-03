import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]


def schema(name: str) -> dict:
    data = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(data)
    return data


def decision(**overrides: object) -> dict:
    value = {
        "schema": "mq.model-route-decision.v1",
        "decision_id": "route-20260803-001",
        "task_class": "diff-summary",
        "risk": "low",
        "recommended_route": "local-shadow",
        "local_model": "qwen3:4b-instruct",
        "authoritative_agent": "codex",
        "reason_codes": ["read-only", "deterministic-verification-available"],
        "escalation_conditions": ["schema-invalid", "verification-failed"],
    }
    value.update(overrides)
    return value


def outcome(**overrides: object) -> dict:
    value = {
        "schema": "mq.model-route-outcome.v1",
        "decision_id": "route-20260803-001",
        "task_class": "diff-summary",
        "selected_route": "local-shadow",
        "local_model": "qwen3:4b-instruct",
        "authoritative_agent": "codex",
        "attempted": True,
        "model_output_received": True,
        "schema_valid": True,
        "verification": {"status": "PASS", "checks": ["output-schema"]},
        "accepted_by_agent": True,
        "accepted_by_operator": False,
        "escalated": False,
        "escalation_reason": None,
        "recorded_at": "2026-08-03T12:00:00Z",
    }
    value.update(overrides)
    return value


def test_decision_and_outcome_examples_are_valid() -> None:
    Draft202012Validator(schema("model_route_decision.schema.json")).validate(decision())
    Draft202012Validator(schema("model_route_outcome.schema.json")).validate(outcome())


@pytest.mark.parametrize(
    "field,value",
    [("task_class", "write-anything"), ("risk", "maybe"), ("recommended_route", "auto")],
)
def test_decision_rejects_unknown_closed_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(schema("model_route_decision.schema.json")).validate(
            decision(**{field: value})
        )


def test_decision_requires_reasons_and_escalation_conditions() -> None:
    for field in ("reason_codes", "escalation_conditions", "authoritative_agent"):
        value = decision()
        value.pop(field)
        with pytest.raises(ValidationError):
            Draft202012Validator(schema("model_route_decision.schema.json")).validate(value)


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(schema("model_route_decision.schema.json")).validate(
            decision(surprise=True)
        )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema("model_route_outcome.schema.json")).validate(
            outcome(raw_model_output="untrusted")
        )


def test_outcome_preserves_verification_and_acceptance_distinctions() -> None:
    validator = Draft202012Validator(schema("model_route_outcome.schema.json"))
    validator.validate(outcome(attempted=True, model_output_received=False, schema_valid=False,
                               verification={"status": "SKIPPED", "checks": []},
                               accepted_by_agent=False, accepted_by_operator=False,
                               escalated=True, escalation_reason="model-unavailable"))
    with pytest.raises(ValidationError):
        validator.validate(outcome(verification={"status": "MAYBE", "checks": []}))
