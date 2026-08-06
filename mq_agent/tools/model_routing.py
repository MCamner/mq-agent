"""Deterministic model routing and advisory Ollama shadow evaluation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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
_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(_CANDIDATE_KEYS),
    "properties": {
        "task_class": {"type": "string"},
        "summary": {"type": "string", "minLength": 1},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
}


def _outcome_path(destination: Path | None = None) -> Path:
    return destination or Path(
        os.environ.get("MQ_AGENT_ROUTE_OUTCOMES", Path.home() / ".mq-agent/route-outcomes.jsonl")
    ).expanduser()


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
        # decision_id is a hash of the task, so repeated runs of one task share it.
        # run_id keeps those runs distinguishable from duplicated records.
        "run_id": str(uuid.uuid4()),
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


# Shorter strings match too much of any material to be treated as a citation.
_MIN_QUOTE_LENGTH = 12


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _evidence_is_grounded(evidence: list[str], context: str) -> bool:
    """Check every evidence item is a long-enough verbatim quote from the material."""
    if not evidence:
        return False
    haystack = _normalize(context)
    for item in evidence:
        quote = _normalize(item)
        if len(quote) < _MIN_QUOTE_LENGTH or quote not in haystack:
            return False
    return True


def _shadow_prompt(task: str, task_class: str, context: str | None = None) -> str:
    prompt = (
        "Return only one JSON object with exactly these keys: task_class, summary, "
        "evidence, suggestions. task_class must be "
        f"{json.dumps(task_class)}. evidence and suggestions must be string arrays. "
        "Do not return commands or markdown. Task: "
        f"{json.dumps(task)}"
    )
    if context is None:
        return prompt
    return (
        prompt + " Every entry in evidence must be copied verbatim from the material "
        "below, long enough to identify the line it came from. Do not paraphrase. "
        f"Material: {json.dumps(context)}"
    )


def shadow_route(
    task: str,
    *,
    authoritative_agent: str = "codex",
    timeout: int = 30,
    context: str | None = None,
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
            _shadow_prompt(task, str(decision["task_class"]), context),
            timeout,
            json_format=_CANDIDATE_SCHEMA,
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

    checks = ["candidate-schema", "task-class-match"]
    if context is not None:
        if not _evidence_is_grounded(candidate["evidence"], context):
            return {
                "decision": decision,
                "candidate": None,
                "outcome": _outcome(
                    decision,
                    attempted=True,
                    model_output_received=True,
                    schema_valid=True,
                    verification_status="FAIL",
                    escalated=True,
                    escalation_reason="verification-failed",
                ),
            }
        checks.append("evidence-grounded")

    return {
        "decision": decision,
        "candidate": candidate,
        "outcome": _outcome(
            decision,
            attempted=True,
            model_output_received=True,
            schema_valid=True,
            verification_status="PASS",
            verification_checks=checks,
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


def record_route_outcome(outcome: dict[str, Any], destination: Path | None = None) -> Path:
    """Append one schema-valid routing outcome to the local JSONL evidence store."""
    _validator("model_route_outcome.schema.json").validate(outcome)
    path = _outcome_path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(outcome, ensure_ascii=False) + "\n")
    return path


def route_report(source: Path | None = None) -> dict[str, Any]:
    """Aggregate validated outcomes from a JSON or JSONL source, read-only."""
    path = _outcome_path(source)
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
                "model_output_received": 0,
                "verified": 0,
                "accepted_by_agent": 0,
                "accepted_by_operator": 0,
                "escalated": 0,
            },
        )
        bucket["outcomes"] += 1
        bucket["attempted"] += int(outcome["attempted"])
        bucket["model_output_received"] += int(outcome["model_output_received"])
        bucket["verified"] += int(outcome["verification"]["status"] == "PASS")
        bucket["accepted_by_agent"] += int(outcome["accepted_by_agent"])
        bucket["accepted_by_operator"] += int(outcome["accepted_by_operator"])
        bucket["escalated"] += int(outcome["escalated"])
    report_by_task: dict[str, dict[str, int | float]] = {}
    for task_class, counts in by_task.items():
        responded = counts["model_output_received"]
        verified = counts["verified"]
        report_by_task[task_class] = {
            **counts,
            "verification_rate": round(verified / responded, 3) if responded else 0.0,
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


def review_route_evidence(task_class: str, source: Path | None = None) -> dict[str, Any]:
    """Evaluate one task class against the promotion evidence gate, read-only."""
    outcome_schema = cast(
        dict[str, Any], _validator("model_route_outcome.schema.json").schema
    )
    allowed = outcome_schema["properties"]["task_class"]["enum"]
    if task_class not in allowed:
        raise ValueError(f"unknown task class: {task_class}")

    path = _outcome_path(source)
    records, total = _read_records(path)
    validator = _validator("model_route_outcome.schema.json")
    valid = [record for record in records if not list(validator.iter_errors(record))]
    outcomes = [record for record in valid if record["task_class"] == task_class]
    attempted = sum(int(item["attempted"]) for item in outcomes)
    responded = sum(int(item["model_output_received"]) for item in outcomes)
    verified = sum(int(item["verification"]["status"] == "PASS") for item in outcomes)
    # Attempts the model never answered are Ollama availability, not model quality,
    # so they belong in attempted_outcomes but not in the success-rate denominator.
    verification_rate = round(verified / responded, 3) if responded else 0.0
    malformed = [
        item
        for item in outcomes
        if item["escalation_reason"] in {"malformed-output", "schema-invalid"}
    ]
    malformed_escalated = sum(int(item["escalated"]) for item in malformed)
    unavailable_proven = any(
        item["verification"]["status"] == "UNAVAILABLE"
        and item["escalated"]
        and item["escalation_reason"] == "model-unavailable"
        for item in outcomes
    )
    unauthorized_writes = sum(int(item["selected_route"] == "approved-local") for item in outcomes)
    safety_violations = sum(
        int(
            (item["accepted_by_agent"] or item["accepted_by_operator"])
            and item["verification"]["status"] != "PASS"
        )
        for item in outcomes
    ) + sum(int(not item["escalated"]) for item in malformed) + unauthorized_writes
    accepted = sum(
        int(item["accepted_by_agent"] or item["accepted_by_operator"]) for item in outcomes
    )
    passing = [item for item in outcomes if item["verification"]["status"] == "PASS"]
    distinct_verified = len({str(item["decision_id"]) for item in passing})
    grounded = sum(
        int("evidence-grounded" in item["verification"]["checks"]) for item in passing
    )

    # A gate is vacuous when the evidence holds no observation that could have failed
    # it. Such a gate passes by construction, so reporting it as met would overstate
    # what the evidence proves.
    gate_values = (
        ("minimum-verified-outcomes", verified >= 50, verified, ">= 50", False),
        (
            "verification-success-rate",
            verification_rate >= 0.9,
            verification_rate,
            ">= 0.9",
            responded == 0,
        ),
        ("valid-outcome-records", total == len(valid), total - len(valid), "0 invalid", total == 0),
        (
            "zero-unauthorized-writes",
            unauthorized_writes == 0,
            unauthorized_writes,
            "0",
            not any(item["selected_route"] == "approved-local" for item in outcomes),
        ),
        (
            "zero-safety-contract-violations",
            safety_violations == 0,
            safety_violations,
            "0",
            accepted == 0 and not malformed and unauthorized_writes == 0,
        ),
        (
            "all-malformed-outputs-escalated",
            len(malformed) == malformed_escalated,
            f"{malformed_escalated}/{len(malformed)}",
            "all",
            not malformed,
        ),
        ("ollama-unavailable-path-proven", unavailable_proven, unavailable_proven, True, False),
        # Volume alone can come from one task run many times, and a structurally valid
        # candidate can still be invented, so coverage and grounding are separate bars.
        ("distinct-verified-tasks", distinct_verified >= 10, distinct_verified, ">= 10", False),
        (
            "verified-outcomes-are-grounded",
            grounded == verified,
            f"{grounded}/{verified}",
            "all",
            verified == 0,
        ),
    )
    gates = [
        {
            "id": gate_id,
            "passed": passed,
            "actual": actual,
            "required": required,
            "vacuous": vacuous,
        }
        for gate_id, passed, actual, required, vacuous in gate_values
    ]
    failed = [gate["id"] for gate in gates if not gate["passed"]]
    vacuous_gates = [gate["id"] for gate in gates if gate["vacuous"]]
    review = {
        "schema": "mq.model-route-evidence-review.v1",
        "task_class": task_class,
        "source": str(path),
        "decision": "NOT_ELIGIBLE" if failed else "AWAITING_OPERATOR_APPROVAL",
        "automatic_routing_enabled": False,
        "operator_approval_required": True,
        "valid_outcomes": len(outcomes),
        "verified_outcomes": verified,
        "distinct_verified_tasks": distinct_verified,
        "grounded_verified_outcomes": grounded,
        "attempted_outcomes": attempted,
        "responded_outcomes": responded,
        "verification_success_rate": verification_rate,
        "unauthorized_writes": unauthorized_writes,
        "safety_contract_violations": safety_violations,
        "malformed_outputs": len(malformed),
        "malformed_outputs_escalated": malformed_escalated,
        "ollama_unavailable_path_proven": unavailable_proven,
        "gates": gates,
        "failed_gates": failed,
        "vacuous_gates": vacuous_gates,
    }
    _validator("model_route_evidence_review.schema.json").validate(review)
    return review
