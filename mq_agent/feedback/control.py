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

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .candidates import candidate_detail
from .contracts import (
    validate_approval,
    validate_policy_event,
    validate_policy_snapshot,
)
from .readiness import activation_readiness
from .store import (
    append_approval,
    append_policy_event,
    append_policy_snapshot,
    read_approval_history,
    read_comparison_history,
    read_policy_event_history,
    read_policy_snapshot_history,
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
        "readiness_fingerprint": readiness["evidence_fingerprint"],
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
    current_readiness = activation_readiness(candidate_id, root)
    if current_readiness["status"] != "READY_FOR_HUMAN_APPROVAL":
        raise ValueError(
            "approval expired because candidate readiness/state changed: "
            + str(current_readiness["status"])
        )
    if approval["candidate_fingerprint"] != candidate["fingerprint"]:
        raise ValueError("approval expired because candidate fingerprint changed")
    if approval.get("readiness_fingerprint") is None:
        raise ValueError(
            "approval predates outcome-bound readiness; issue a new approval"
        )
    if approval["readiness_fingerprint"] != current_readiness["evidence_fingerprint"]:
        raise ValueError(
            "approval expired because task-class readiness evidence changed"
        )
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


def _policy_snapshots(root: Path | None = None) -> list[dict[str, Any]]:
    history = read_policy_snapshot_history(root)
    if history.issues:
        raise ValueError("policy snapshot store contains invalid records")
    return [item.record for item in history.records]


def _snapshot_fingerprint(record: dict[str, Any]) -> str:
    basis = {key: value for key, value in record.items() if key != "fingerprint"}
    raw = json.dumps(
        basis,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _build_policy_snapshot(
    task_class: str,
    *,
    effective_strategy_value: str,
    event_count: int,
    last_event_id: str | None,
    source_event_id: str | None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": "mq.feedback-policy-snapshot.v1",
        "snapshot_id": snapshot_id or f"snapshot-{uuid.uuid4()}",
        "task_class": task_class,
        "baseline_strategy": BASELINE_POLICIES.get(task_class, "context-pack-v1"),
        "effective_strategy": effective_strategy_value,
        "event_count": event_count,
        "last_event_id": last_event_id,
        "source_event_id": source_event_id,
        "recorded_at": _iso(_now()),
    }
    record["fingerprint"] = _snapshot_fingerprint(record)
    validate_policy_snapshot(record)
    return record


def _policy_snapshot(snapshot_id: str, root: Path | None = None) -> dict[str, Any]:
    matches = [
        record
        for record in _policy_snapshots(root)
        if record.get("snapshot_id") == snapshot_id
    ]
    if len(matches) != 1:
        raise ValueError("policy snapshot must resolve exactly once")
    record = matches[0]
    validate_policy_snapshot(record)
    if _snapshot_fingerprint(record) != record["fingerprint"]:
        raise ValueError("policy snapshot fingerprint mismatch")
    return record


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
    canary_id: str,
    reason: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Activate one task class and bind the event to immutable policy snapshots."""
    if not reason.strip():
        raise ValueError("activation requires a reason")
    from .canary import require_passing_canary

    candidate = candidate_detail(candidate_id, root)["candidate"]
    canary = require_passing_canary(
        canary_id,
        candidate_id=candidate_id,
        approval_id=approval_id,
        root=root,
    )
    task_class = candidate["task_class"]
    current = effective_strategy(task_class, root)
    if current != candidate["current_strategy"]:
        raise ValueError(
            f"active policy changed since approval: {current} != {candidate['current_strategy']}"
        )

    task_events = [x for x in _policy_events(root) if x["task_class"] == task_class]
    previous_event_id = task_events[-1]["event_id"] if task_events else None
    event_id = f"policy-{uuid.uuid4()}"
    before_snapshot = _build_policy_snapshot(
        task_class,
        effective_strategy_value=current,
        event_count=len(task_events),
        last_event_id=previous_event_id,
        source_event_id=previous_event_id,
    )
    after_snapshot = _build_policy_snapshot(
        task_class,
        effective_strategy_value=candidate["proposed_strategy"],
        event_count=len(task_events) + 1,
        last_event_id=event_id,
        source_event_id=event_id,
    )
    record = {
        "schema": "mq.feedback-policy-event.v1",
        "event_id": event_id,
        "event_type": "ACTIVATION",
        "task_class": task_class,
        "from_strategy": current,
        "to_strategy": candidate["proposed_strategy"],
        "candidate_id": candidate_id,
        "approval_id": approval_id,
        "canary_id": canary_id,
        "canary_comparison_id": (
            canary["comparison_ids"][-1] if canary["comparison_ids"] else None
        ),
        "before_snapshot_id": before_snapshot["snapshot_id"],
        "after_snapshot_id": after_snapshot["snapshot_id"],
        "rollback_of_event_id": None,
        "rollback_target_snapshot_id": before_snapshot["snapshot_id"],
        "recorded_at": _iso(_now()),
        "reason": reason.strip()[:320],
    }
    validate_policy_event(record)

    # Snapshot records are written before the event so an event can never point
    # at a not-yet-persisted snapshot. Orphan snapshots are inert if a later
    # append fails; policy state changes only when the event is appended.
    append_policy_snapshot(before_snapshot, root)
    append_policy_snapshot(after_snapshot, root)
    append_policy_event(record, root)
    return record


def rollback(
    activation_id: str,
    *,
    reason: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Rollback one exact currently-active activation event."""
    if not reason.strip():
        raise ValueError("rollback requires a reason")

    all_events = _policy_events(root)
    matches = [event for event in all_events if event["event_id"] == activation_id]
    if len(matches) != 1:
        raise ValueError("activation-id must resolve to exactly one policy event")
    activation = matches[0]
    if activation["event_type"] != "ACTIVATION":
        raise ValueError("rollback target is not an activation event")

    task_class = activation["task_class"]
    task_events = [event for event in all_events if event["task_class"] == task_class]
    if not task_events or task_events[-1]["event_id"] != activation_id:
        raise ValueError("activation is no longer the active latest policy event")

    current = effective_strategy(task_class, root)
    if current != activation["to_strategy"]:
        raise ValueError("effective policy no longer matches the activation to roll back")

    before_snapshot_id = activation.get("before_snapshot_id")
    after_snapshot_id = activation.get("after_snapshot_id")
    if not isinstance(before_snapshot_id, str) or not isinstance(after_snapshot_id, str):
        raise ValueError("activation predates Policy Registry v2 snapshot binding")

    rollback_target = _policy_snapshot(before_snapshot_id, root)
    active_snapshot = _policy_snapshot(after_snapshot_id, root)
    if rollback_target["task_class"] != task_class:
        raise ValueError("rollback target snapshot task class mismatch")
    if rollback_target["effective_strategy"] != activation["from_strategy"]:
        raise ValueError("rollback target snapshot strategy mismatch")
    if active_snapshot["effective_strategy"] != activation["to_strategy"]:
        raise ValueError("activation after-snapshot strategy mismatch")
    if active_snapshot["last_event_id"] != activation_id:
        raise ValueError("activation after-snapshot event mismatch")

    event_id = f"policy-{uuid.uuid4()}"
    after_rollback = _build_policy_snapshot(
        task_class,
        effective_strategy_value=rollback_target["effective_strategy"],
        event_count=len(task_events) + 1,
        last_event_id=event_id,
        source_event_id=event_id,
    )
    record = {
        "schema": "mq.feedback-policy-event.v1",
        "event_id": event_id,
        "event_type": "ROLLBACK",
        "task_class": task_class,
        "from_strategy": current,
        "to_strategy": rollback_target["effective_strategy"],
        "candidate_id": None,
        "approval_id": None,
        "canary_id": None,
        "canary_comparison_id": None,
        "before_snapshot_id": active_snapshot["snapshot_id"],
        "after_snapshot_id": after_rollback["snapshot_id"],
        "rollback_of_event_id": activation_id,
        "rollback_target_snapshot_id": rollback_target["snapshot_id"],
        "recorded_at": _iso(_now()),
        "reason": reason.strip()[:320],
    }
    validate_policy_event(record)
    append_policy_snapshot(after_rollback, root)
    append_policy_event(record, root)
    return record


def post_activation_check(
    task_class: str,
    comparison_id: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Interpret one comparison from the current active policy's perspective."""
    comparison = _comparison(comparison_id, root)
    current = effective_strategy(task_class, root)
    if comparison["task_class"] != task_class:
        raise ValueError("comparison task class does not match policy")
    if comparison["active_strategy"] != current:
        raise ValueError("comparison was not measured against the current active strategy")
    if not comparison["valid"] or comparison.get("relevance_fixture") is None:
        return {
            "kind": "feedback-post-activation-check",
            "status": "INSUFFICIENT_EVIDENCE",
            "task_class": task_class,
            "active_strategy": current,
            "comparison_id": comparison_id,
            "regressions": [],
        }

    regressions: list[str] = []
    for name, metric in comparison["metrics"].items():
        if not metric.get("material") or metric.get("status") != "comparable":
            continue
        delta = metric.get("delta")
        direction = metric.get("direction")
        if not isinstance(delta, (int, float)):
            continue
        shadow_better = (
            direction == "higher_is_better" and delta > 0
        ) or (
            direction == "lower_is_better" and delta < 0
        )
        if shadow_better:
            regressions.append(name)

    return {
        "kind": "feedback-post-activation-check",
        "status": "REGRESSION" if regressions else "PASS",
        "task_class": task_class,
        "active_strategy": current,
        "baseline_shadow_strategy": comparison["shadow_strategy"],
        "comparison_id": comparison_id,
        "regressions": sorted(regressions),
    }


def policy_status(task_class: str, root: Path | None = None) -> dict[str, Any]:
    events = [x for x in _policy_events(root) if x["task_class"] == task_class]
    snapshots = [x for x in _policy_snapshots(root) if x["task_class"] == task_class]
    current_snapshot = None
    if events and isinstance(events[-1].get("after_snapshot_id"), str):
        current_snapshot = _policy_snapshot(events[-1]["after_snapshot_id"], root)
    return {
        "kind": "feedback-policy-status",
        "task_class": task_class,
        "baseline_strategy": BASELINE_POLICIES.get(task_class, "context-pack-v1"),
        "effective_strategy": effective_strategy(task_class, root),
        "kill_switch": os.environ.get(KILL_SWITCH_ENV, "on"),
        "events": len(events),
        "snapshots": len(snapshots),
        "last_event": events[-1] if events else None,
        "current_snapshot": current_snapshot,
    }
