"""Versioned feedback comparison and candidate contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

COMPARISON_SCHEMA_ID = "mq.feedback-comparison.v1"
CANDIDATE_SCHEMA_ID = "mq.feedback-candidate.v1"
ACTIVATION_READINESS_SCHEMA_ID = "mq.feedback-activation-readiness.v1"
APPROVAL_SCHEMA_ID = "mq.feedback-approval.v1"
POLICY_EVENT_SCHEMA_ID = "mq.feedback-policy-event.v1"
CANARY_SCHEMA_ID = "mq.feedback-canary.v1"
POLICY_SNAPSHOT_SCHEMA_ID = "mq.feedback-policy-snapshot.v1"

_SCHEMA_FILES = {
    COMPARISON_SCHEMA_ID: "feedback_comparison.schema.json",
    CANDIDATE_SCHEMA_ID: "feedback_candidate.schema.json",
    ACTIVATION_READINESS_SCHEMA_ID: "feedback_activation_readiness.schema.json",
    APPROVAL_SCHEMA_ID: "feedback_approval.schema.json",
    POLICY_EVENT_SCHEMA_ID: "feedback_policy_event.schema.json",
    CANARY_SCHEMA_ID: "feedback_canary.schema.json",
    POLICY_SNAPSHOT_SCHEMA_ID: "feedback_policy_snapshot.schema.json",
}


def _schema_path(filename: str) -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / filename
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / filename


def validator(schema_id: str) -> Draft202012Validator:
    filename = _SCHEMA_FILES[schema_id]
    schema = json.loads(_schema_path(filename).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_comparison(record: dict[str, Any]) -> None:
    validator(COMPARISON_SCHEMA_ID).validate(record)


def validate_candidate(record: dict[str, Any]) -> None:
    validator(CANDIDATE_SCHEMA_ID).validate(record)


def validate_activation_readiness(record: dict[str, Any]) -> None:
    validator(ACTIVATION_READINESS_SCHEMA_ID).validate(record)


def validate_approval(record: dict[str, Any]) -> None:
    validator(APPROVAL_SCHEMA_ID).validate(record)


def validate_policy_event(record: dict[str, Any]) -> None:
    validator(POLICY_EVENT_SCHEMA_ID).validate(record)


def validate_canary_record(record: dict[str, Any]) -> None:
    validator(CANARY_SCHEMA_ID).validate(record)


def validate_policy_snapshot(record: dict[str, Any]) -> None:
    validator(POLICY_SNAPSHOT_SCHEMA_ID).validate(record)
