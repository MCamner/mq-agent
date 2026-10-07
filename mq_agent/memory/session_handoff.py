"""Typed session -> memory-observation.v1 candidate handoff.

Only explicit typed facts are accepted. There is intentionally no transcript,
prompt, stdout/stderr, or generic payload input. The result is an observation
candidate in mqobsidian's normal review/scoring path, never durable memory.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from mq_agent.memory.cochange_observation import emit_observation

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
)
_PRIVATE_PATHS = (
    re.compile(r"/(?:Users|home)/[^/\s]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
)
_MAX_FACT = 320
_MAX_FACTS = 32


def _safe_text(value: str, *, label: str) -> str:
    text = " ".join(value.split()).strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > _MAX_FACT:
        raise ValueError(f"{label} exceeds {_MAX_FACT} characters")
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise ValueError(f"{label} contains a credential-like value")
    if any(pattern.search(text) for pattern in _PRIVATE_PATHS):
        raise ValueError(f"{label} contains a private absolute path")
    return text


def _safe_list(values: list[str], *, label: str) -> list[str]:
    if len(values) > _MAX_FACTS:
        raise ValueError(f"{label} accepts at most {_MAX_FACTS} items")
    return [_safe_text(value, label=label) for value in values]


def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[1] / "schemas" / "memory_observation.schema.json"
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "schemas" / "memory_observation.schema.json"
    import json

    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def build_session_observation(
    *,
    session_id: str,
    task_class: str,
    repository: str,
    outcome: str,
    decisions: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    corrections: list[str] | None = None,
    confidence: float = 0.7,
) -> dict[str, Any]:
    """Build one bounded, public-safe memory candidate from typed session facts."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    safe_session = _safe_text(session_id, label="session-id")
    safe_task = _safe_text(task_class, label="task-class")
    safe_repo = Path(_safe_text(repository, label="repository")).name
    safe_outcome = _safe_text(outcome, label="outcome")
    safe_decisions = _safe_list(decisions or [], label="decision")
    safe_artifacts = _safe_list(artifact_refs or [], label="artifact")
    safe_corrections = _safe_list(corrections or [], label="correction")

    parts = [f"Outcome: {safe_outcome}."]
    if safe_decisions:
        parts.append("Decisions: " + "; ".join(safe_decisions) + ".")
    if safe_corrections:
        parts.append("Operator corrections: " + "; ".join(safe_corrections) + ".")
    observation = " ".join(parts)

    evidence = [
        {"source": "session-artifact", "reference": value}
        for value in safe_artifacts
    ]
    if not evidence:
        evidence = [{"source": "session-id", "reference": safe_session}]

    now = datetime.now(UTC)
    record = {
        "schema": "memory-observation.v1",
        "id": f"mo-session-{uuid.uuid4()}",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "producer": "mq-agent",
        "repository": safe_repo,
        "workflow": "session-handoff",
        "session_id": safe_session,
        "title": f"Verified {safe_task} session handoff",
        "summary": safe_outcome,
        "observation": observation,
        "category": "learning",
        "confidence": float(confidence),
        "evidence": evidence,
        "tags": ["session-handoff", safe_task],
        "proposed_memory_key": f"session-{safe_task}-{safe_session}"[:160],
    }
    _schema_validator().validate(record)
    return record


def handoff_session(
    *,
    session_id: str,
    task_class: str,
    repository: str,
    outcome: str,
    decisions: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    corrections: list[str] | None = None,
    confidence: float = 0.7,
    vault: Path | None = None,
) -> dict[str, Any]:
    record = build_session_observation(
        session_id=session_id,
        task_class=task_class,
        repository=repository,
        outcome=outcome,
        decisions=decisions,
        artifact_refs=artifact_refs,
        corrections=corrections,
        confidence=confidence,
    )
    path = emit_observation(record, vault=vault)
    if path is None:
        raise RuntimeError("mqobsidian observation handoff failed")
    return {
        "kind": "mq-session-handoff-result",
        "status": "SUBMITTED_FOR_REVIEW",
        "observation_id": record["id"],
        "session_id": record["session_id"],
        "repository": record["repository"],
        "durable_memory_written": False,
    }
