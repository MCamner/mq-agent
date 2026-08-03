"""Deterministic model routing and advisory Ollama shadow evaluation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from mq_agent.tools.model_runtime import _ollama_generate, current_model


LOCAL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("diff-summary", ("diff", "change summary", "summarize changes")),
    ("docs-review", ("documentation", "docs", "readme")),
    ("repo-health", ("repo health", "repository health", "doctor", "status")),
    ("test-area-suggestions", ("test area", "tests", "testing")),
    ("review-finding-classification", ("review finding", "findings", "classify review")),
    ("context-pack-summary", ("context pack", "context-pack", "summarize context")),
)

CLOUD_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("security-review", "critical", ("security", "credential", "secret", "vulnerability")),
    ("destructive-operation", "critical", ("destructive", "delete", "remove data", "force push")),
    ("release-decision", "high", ("release decision", "approve release", "publish release")),
    ("schema-migration", "high", ("schema migration", "contract migration", "migrate schema")),
    ("architecture", "high", ("architecture", "cross-repo", "cross repository")),
)

_CANDIDATE_KEYS = {"task_class", "summary", "evidence", "suggestions"}


def _schema_path(name: str) -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / name


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads(_schema_path(name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _decision_id(task: str, authoritative_agent: str) -> str:
    digest = hashlib.sha256(f"{authoritative_agent}\0{task.strip()}".encode()).hexdigest()[:16]
    return f"route-{digest}"


def _matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def inspect_route(
    task: str,
    *,
    authoritative_agent: str = "codex",
    local_model: str | None = None,
) -> dict[str, Any]:
    """Classify a task deterministically without model calls or writes."""
    if authoritative_agent not in {"codex", "claude"}:
        raise ValueError("authoritative_agent must be codex or claude")
    normalized = " ".join(task.lower().split())
    if not normalized:
        raise ValueError("task must not be empty")

    task_class = "unverified-change"
    risk = "medium"
    route = "cloud-required"
    reasons = ["no-deterministic-verification"]
    model: str | None = None

    for candidate_class, candidate_risk, terms in CLOUD_RULES:
        if _matches(normalized, terms):
            task_class = candidate_class
            risk = candidate_risk
            reason = {
                "security-review": "security-critical",
                "destructive-operation": "destructive",
                "release-decision": "release-authority-required",
                "schema-migration": "schema-migration",
                "architecture": "architecture-risk",
            }[task_class]
            reasons = [reason]
            break
    else:
        for candidate_class, terms in LOCAL_RULES:
            if _matches(normalized, terms):
                task_class = candidate_class
                risk = "low"
                route = "local-shadow"
                reasons = ["read-only", "deterministic-verification-available"]
                model = local_model or str(current_model()["model"])
                break

    decision = {
        "schema": "mq.model-route-decision.v1",
        "decision_id": _decision_id(task, authoritative_agent),
        "task_class": task_class,
        "risk": risk,
        "recommended_route": route,
        "local_model": model,
        "authoritative_agent": authoritative_agent,
        "reason_codes": reasons,
        "escalation_conditions": [
            "schema-invalid",
            "verification-failed",
            "confidence-below-threshold",
            "policy-requires-cloud",
        ],
    }
    _validator("model_route_decision.schema.json").validate(decision)
    return decision


def _outcome(
    decision: dict[str, Any],
    *,
    attempted: bool = False,
    model_output_received: bool = False,
    schema_valid: bool = False,
    verification_status: str = "SKIPPED",
    verification_checks: list[str] | None = None,
    accepted_by_agent: bool = False,
    accepted_by_operator: bool = False,
    escalated: bool = False,
    escalation_reason: str | None = None,
) -> dict[str, Any]:
    """Build and validate one routing outcome without persisting it."""
    outcome = {
        "schema": "mq.model-route-outcome.v1",
        "decision_id": decision["decision_id"],
        "task_class": decision["task_class"],
        "selected_route": decision["recommended_route"],
        "local_model": decision["local_model"],
        "authoritative_agent": decision["authoritative_agent"],
        "attempted": attempted,
        "model_output_received": model_output_received,
        "schema_valid": schema_valid,
        "verification": {
            "status": verification_status,
            "checks": verification_checks or [],
        },
        "accepted_by_agent": accepted_by_agent,
        "accepted_by_operator": accepted_by_operator,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    _validator("model_route_outcome.schema.json").validate(outcome)
    return outcome


def _candidate_is_valid(candidate: Any, task_class: str) -> bool:
    if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_KEYS:
        return False
    if candidate.get("task_class") != task_class:
        return False
    if not isinstance(candidate.get("summary"), str) or not candidate["summary"].strip():
        return False
    for field in ("evidence", "suggestions"):
        values = candidate.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            return False
    return True


def _shadow_prompt(task: str, task_class: str) -> str:
    return (
        "Return only one JSON object with exactly these keys: task_class, summary, "
        "evidence, suggestions. task_class must be "
        f"{json.dumps(task_class)}. evidence and suggestions must be string arrays. "
        "Do not return commands or markdown. Task: "
        f"{json.dumps(task)}"
    )


def shadow_route(
    task: str,
    *,
    authoritative_agent: str = "codex",
    timeout: int = 30,
) -> dict[str, Any]:
    """Run an advisory local candidate and return a verified comparison record."""
    decision = inspect_route(task, authoritative_agent=authoritative_agent)
    if decision["recommended_route"] == "cloud-required":
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                verification_status="SKIPPED",
                escalated=True,
                escalation_reason="policy-requires-cloud",
            ),
        }

    if not shutil.which("ollama"):
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                verification_status="UNAVAILABLE",
                escalated=True,
                escalation_reason="model-unavailable",
            ),
        }

    try:
        response = _ollama_generate(
            str(decision["local_model"]),
            _shadow_prompt(task, str(decision["task_class"])),
            timeout,
            json_format=True,
            keep_alive=0,
        )
    except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                attempted=True,
                verification_status="UNAVAILABLE",
                escalated=True,
                escalation_reason="model-unavailable",
            ),
        }

    raw = str(response.get("response", ""))
    if not raw.strip():
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                attempted=True,
                verification_status="FAIL",
                escalated=True,
                escalation_reason="malformed-output",
            ),
        }
    try:
        candidate = json.loads(raw)
    except json.JSONDecodeError:
        candidate = None
    if not _candidate_is_valid(candidate, str(decision["task_class"])):
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                attempted=True,
                model_output_received=True,
                verification_status="FAIL",
                escalated=True,
                escalation_reason="malformed-output" if candidate is None else "schema-invalid",
            ),
        }

    return {
        "decision": decision,
        "candidate": candidate,
        "outcome": _outcome(
            decision,
            attempted=True,
            model_output_received=True,
            schema_valid=True,
            verification_status="PASS",
            verification_checks=["candidate-schema", "task-class-match"],
        ),
    }


def _read_records(source: Path) -> tuple[list[Any], int]:
    if not source.exists():
        return [], 0
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return [], 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        records: list[Any] = []
        for line in text.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append(None)
        return records, len(records)
    records = parsed if isinstance(parsed, list) else [parsed]
    return records, len(records)


def route_report(source: Path | None = None) -> dict[str, Any]:
    """Aggregate validated outcomes from a JSON or JSONL source, read-only."""
    path = source or Path(
        os.environ.get("MQ_AGENT_ROUTE_OUTCOMES", Path.home() / ".mq-agent/route-outcomes.jsonl")
    ).expanduser()
    records, total = _read_records(path)
    validator = _validator("model_route_outcome.schema.json")
    outcomes = [record for record in records if not list(validator.iter_errors(record))]
    by_task: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        task_class = str(outcome["task_class"])
        bucket = by_task.setdefault(
            task_class,
            {
                "outcomes": 0,
                "attempted": 0,
                "verified": 0,
                "accepted_by_agent": 0,
                "accepted_by_operator": 0,
                "escalated": 0,
            },
        )
        bucket["outcomes"] += 1
        bucket["attempted"] += int(outcome["attempted"])
        bucket["verified"] += int(outcome["verification"]["status"] == "PASS")
        bucket["accepted_by_agent"] += int(outcome["accepted_by_agent"])
        bucket["accepted_by_operator"] += int(outcome["accepted_by_operator"])
        bucket["escalated"] += int(outcome["escalated"])
    report_by_task: dict[str, dict[str, int | float]] = {}
    for task_class, counts in by_task.items():
        attempted = counts["attempted"]
        verified = counts["verified"]
        report_by_task[task_class] = {
            **counts,
            "verification_rate": round(verified / attempted, 3) if attempted else 0.0,
            "agent_acceptance_rate": (
                round(counts["accepted_by_agent"] / verified, 3) if verified else 0.0
            ),
        }
    return {
        "schema": "mq.model-route-report.v1",
        "source": str(path),
        "total_records": total,
        "valid_outcomes": len(outcomes),
        "invalid_records": total - len(outcomes),
        "attempted": sum(int(item["attempted"]) for item in outcomes),
        "model_output_received": sum(int(item["model_output_received"]) for item in outcomes),
        "schema_valid": sum(int(item["schema_valid"]) for item in outcomes),
        "verified": sum(int(item["verification"]["status"] == "PASS") for item in outcomes),
        "accepted_by_agent": sum(int(item["accepted_by_agent"]) for item in outcomes),
        "accepted_by_operator": sum(int(item["accepted_by_operator"]) for item in outcomes),
        "escalated": sum(int(item["escalated"]) for item in outcomes),
        "by_task_class": report_by_task,
    }
