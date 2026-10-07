"""Evidence-gated feedback approval, activation and rollback control plane.

This module is deliberately narrow:
- approval is bound to one immutable candidate/evidence window and expires;
- activation is task-class isolated and requires post-approval canary evidence;
- policy changes are append-only events;
- rollback appends a new event and never rewrites history;
- MQ_FEEDBACK_ACTIVATION=off is a kill switch that restores baseline behavior
  without deleting evidence.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .candidates import candidate_detail
from .contracts import validate_approval, validate_policy_event
from .readiness import activation_readiness
from .store import (
    append_approval,
    append_policy_event,
    read_approval_history,
    read_comparison_history,
    read_policy_event_history,
)

KILL_SWITCH_ENV = "MQ_FEEDBACK_ACTIVATION"

BASELINE_POLICIES = {
    "repo-review": "context-pack-v1",
}
STRATEGY_CODEGRAPH = {
    "context-pack-v1": "off",
    "context-pack-v1+codegraph-guidance": "on",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def approval_receipt(
    candidate_id: str,
    *,
    reason: str,
    expires_hours: int = 24,
    root: Path | None = None,
) -> dict[str, Any]:
    """Create a content-bound human approval receipt after readiness passes."""
    if not reason.strip():
        raise ValueError("approval requires a reason")
    if expires_hours < 1 or expires_hours > 168:
        raise ValueError("expires_hours must be between 1 and 168")

    readiness = activation_readiness(candidate_id, root)
    if readiness["status"] != "READY_FOR_HUMAN_APPROVAL":
        raise ValueError(
            f"candidate is not ready for approval: {readiness['status']}"
        )
    candidate = candidate_detail(candidate_id, root)["candidate"]
    now = _now()
    record = {
        "schema": "mq.feedback-approval.v1",
        "approval_id": f"approval-{uuid.uuid4()}",
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate["fingerprint"],
        "task_class": candidate["task_class"],
        "current_strategy": candidate["current_strategy"],
        "proposed_strategy": candidate["proposed_strategy"],
        "rollback_target": candidate["rollback_target"],
        "evidence_window": {
            "from": candidate["evidence_window"]["from"],
            "to": candidate["evidence_window"]["to"],
            "comparison_ids": list(candidate["comparison_ids"]),
        },
        "approved_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=expires_hours)),
        "reason": reason.strip()[:320],
    }
    validate_approval(record)
    append_approval(record, root)
    return record


def _approval(approval_id: str, root: Path | None = None) -> dict[str, Any]:
    history = read_approval_history(root)
    if history.issues:
        raise ValueError("approval store contains invalid records")
    matches = [
        item.record
        for item in history.records
        if item.record.get("approval_id") == approval_id
    ]
    if len(matches) != 1:
        raise ValueError("approval must resolve to exactly one receipt")
    record = matches[0]
    validate_approval(record)
    return record


def _comparison(comparison_id: str, root: Path | None = None) -> dict[str, Any]:
    matches = [
        item.record
        for item in read_comparison_history(root).records
        if item.record.get("comparison_id") == comparison_id
    ]
    if len(matches) != 1:
        raise ValueError("canary comparison must resolve exactly once")
    return matches[0]


def validate_canary(
    candidate_id: str,
    approval_id: str,
    comparison_id: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate one explicit post-approval comparison as canary evidence."""
    candidate = candidate_detail(candidate_id, root)["candidate"]
    approval = _approval(approval_id, root)
    comparison = _comparison(comparison_id, root)

    if approval["candidate_id"] != candidate_id:
        raise ValueError("approval is bound to another candidate")
    if approval["candidate_fingerprint"] != candidate["fingerprint"]:
        raise ValueError("approval expired because candidate fingerprint changed")
    if datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00")) <= _now():
        raise ValueError("approval receipt has expired")
    if comparison["recorded_at"] <= approval["approved_at"]:
        raise ValueError("canary comparison must be recorded after approval")
    if comparison["task_class"] != candidate["task_class"]:
        raise ValueError("canary task class does not match candidate")
    if comparison["active_strategy"] != candidate["current_strategy"]:
        raise ValueError("canary active strategy does not match approved current strategy")
    if comparison["shadow_strategy"] != candidate["proposed_strategy"]:
        raise ValueError("canary shadow strategy does not match approved proposed strategy")
    if not comparison["valid"] or comparison["verdict"] != "CANDIDATE_BETTER":
        raise ValueError("canary comparison must be valid CANDIDATE_BETTER evidence")
    return {
        "kind": "feedback-canary-validation",
        "status": "PASS",
        "candidate_id": candidate_id,
        "approval_id": approval_id,
        "comparison_id": comparison_id,
        "snapshot": comparison["snapshot"],
    }


def _policy_events(root: Path | None = None) -> list[dict[str, Any]]:
    history = read_policy_event_history(root)
    if history.issues:
        raise ValueError("policy event store contains invalid records")
    return [item.record for item in history.records]


def effective_strategy(task_class: str, root: Path | None = None) -> str:
    """Return current strategy, honoring the global feedback kill switch."""
    baseline = BASELINE_POLICIES.get(task_class, "context-pack-v1")
    if os.environ.get(KILL_SWITCH_ENV, "on").strip().lower() in {"0", "off", "false", "no"}:
        return baseline
    current = baseline
    for event in _policy_events(root):
        if event["task_class"] == task_class:
            current = event["to_strategy"]
    return current


def strategy_codegraph(strategy: str) -> str:
    try:
        return STRATEGY_CODEGRAPH[strategy]
    except KeyError as exc:
        raise ValueError(f"unsupported context strategy: {strategy}") from exc


def activate(
    candidate_id: str,
    *,
    approval_id: str,
    canary_comparison_id: str,
    reason: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Activate exactly one approved task-class strategy."""
    if not reason.strip():
        raise ValueError("activation requires a reason")
    candidate = candidate_detail(candidate_id, root)["candidate"]
    validate_canary(
        candidate_id, approval_id, canary_comparison_id, root=root
    )
    current = effective_strategy(candidate["task_class"], root)
    if current != candidate["current_strategy"]:
        raise ValueError(
            f"active policy changed since approval: {current} != {candidate['current_strategy']}"
        )
    record = {
        "schema": "mq.feedback-policy-event.v1",
        "event_id": f"policy-{uuid.uuid4()}",
        "event_type": "ACTIVATION",
        "task_class": candidate["task_class"],
        "from_strategy": current,
        "to_strategy": candidate["proposed_strategy"],
        "candidate_id": candidate_id,
        "approval_id": approval_id,
        "canary_comparison_id": canary_comparison_id,
        "recorded_at": _iso(_now()),
        "reason": reason.strip()[:320],
    }
    validate_policy_event(record)
    append_policy_event(record, root)
    return record


def rollback(
    task_class: str,
    *,
    reason: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Append a deterministic rollback to the immediately prior strategy."""
    if not reason.strip():
        raise ValueError("rollback requires a reason")
    events = [x for x in _policy_events(root) if x["task_class"] == task_class]
    current = effective_strategy(task_class, root)
    target = BASELINE_POLICIES.get(task_class, "context-pack-v1")
    if events:
        latest = events[-1]
        target = latest["from_strategy"]
    if current == target:
        raise ValueError("policy is already at its rollback target")
    record = {
        "schema": "mq.feedback-policy-event.v1",
        "event_id": f"policy-{uuid.uuid4()}",
        "event_type": "ROLLBACK",
        "task_class": task_class,
        "from_strategy": current,
        "to_strategy": target,
        "candidate_id": None,
        "approval_id": None,
        "canary_comparison_id": None,
        "recorded_at": _iso(_now()),
        "reason": reason.strip()[:320],
    }
    validate_policy_event(record)
    append_policy_event(record, root)
    return record


def policy_status(task_class: str, root: Path | None = None) -> dict[str, Any]:
    events = [x for x in _policy_events(root) if x["task_class"] == task_class]
    return {
        "kind": "feedback-policy-status",
        "task_class": task_class,
        "baseline_strategy": BASELINE_POLICIES.get(task_class, "context-pack-v1"),
        "effective_strategy": effective_strategy(task_class, root),
        "kill_switch": os.environ.get(KILL_SWITCH_ENV, "on"),
        "events": len(events),
        "last_event": events[-1] if events else None,
    }
