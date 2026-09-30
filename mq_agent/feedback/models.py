"""Versioned contracts for MQ feedback experiments."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_ID = "mq.feedback-experiment.v1"
SCHEMA_FILE = "feedback_experiment.schema.json"


def _schema_path() -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / SCHEMA_FILE
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / SCHEMA_FILE


def validator() -> Draft202012Validator:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_experiment(record: dict[str, Any]) -> None:
    validator().validate(record)


def build_feedback_experiment(
    *,
    task_class: str,
    repository: str,
    active_strategy: str,
    shadow_strategy: str,
    snapshot_ref: str,
    snapshot_commit: str,
    evidence_sources: list[str],
    state: str = "planned",
    execution_run_id: str | None = None,
    network_backends: list[str] | None = None,
    feedback_run_id: str | None = None,
) -> dict[str, Any]:
    """Build one bounded feedback experiment record without persisting it."""
    record: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "feedback_run_id": feedback_run_id or f"fb-{uuid.uuid4()}",
        "task_class": task_class,
        "repository": repository,
        "active_strategy": active_strategy,
        "shadow_strategy": shadow_strategy,
        "snapshot": {
            "kind": "git",
            "ref": snapshot_ref,
            "commit": snapshot_commit,
        },
        "evidence_sources": evidence_sources,
        "state": state,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    if execution_run_id is not None:
        record["execution_run_id"] = execution_run_id
    if network_backends is not None:
        record["network_backends"] = network_backends
    validate_experiment(record)
    return record
