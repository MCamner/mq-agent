"""Versioned feedback comparison and candidate contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

COMPARISON_SCHEMA_ID = "mq.feedback-comparison.v1"
CANDIDATE_SCHEMA_ID = "mq.feedback-candidate.v1"
ACTIVATION_READINESS_SCHEMA_ID = "mq.feedback-activation-readiness.v1"

_SCHEMA_FILES = {
    COMPARISON_SCHEMA_ID: "feedback_comparison.schema.json",
    CANDIDATE_SCHEMA_ID: "feedback_candidate.schema.json",
    ACTIVATION_READINESS_SCHEMA_ID: "feedback_activation_readiness.schema.json",
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
