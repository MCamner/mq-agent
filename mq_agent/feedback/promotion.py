"""Promotion approval: permission to activate, separate from canary approval.

A canary approval only permits testing. Activation additionally requires a
promotion approval issued after a PASS Canary v2 RESULT and bound to that exact
RESULT, candidate, strategy pair and policy snapshot. The two receipts are never
interchangeable.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .approvals import PROMOTION_APPROVAL_PREFIX, _revocation
from .candidates import candidate_detail
from .contracts import PROMOTION_APPROVAL_SCHEMA_ID, validate_promotion_approval
from .store import append_promotion_approval, read_promotion_approval_history


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def resolve_promotion(promotion_approval_id: str, root: Path | None) -> dict[str, Any]:
    history = read_promotion_approval_history(root)
    if history.issues:
        raise ValueError("promotion approval store contains invalid records")
    matches = [
        item.record
        for item in history.records
        if item.record.get("promotion_approval_id") == promotion_approval_id
    ]
    if len(matches) != 1:
        raise ValueError("promotion approval must resolve to exactly one receipt")
    record = matches[0]
    validate_promotion_approval(record)
    return record


def _passing_canary(
    candidate_id: str, canary_id: str, root: Path | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .canary import _records, require_passing_canary

    plan, _result = _records(canary_id, root)
    result = require_passing_canary(
        canary_id,
        candidate_id=candidate_id,
        approval_id=plan["approval_id"],
        root=root,
    )
    return plan, result


def promotion_approve(
    candidate_id: str,
    *,
    canary_id: str,
    reason: str,
    expires_hours: int = 24,
    root: Path | None = None,
) -> dict[str, Any]:
    """Issue a promotion approval for one exact PASS Canary v2 RESULT."""
    from .canary import _sha256

    if not reason.strip():
        raise ValueError("promotion approval requires a reason")
    if expires_hours < 1 or expires_hours > 168:
        raise ValueError("expires_hours must be between 1 and 168")

    plan, result = _passing_canary(candidate_id, canary_id, root)
    candidate = candidate_detail(candidate_id, root)["candidate"]
    now = _now()
    record = {
        "schema": PROMOTION_APPROVAL_SCHEMA_ID,
        "promotion_approval_id": f"{PROMOTION_APPROVAL_PREFIX}{uuid.uuid4()}",
        "canary_approval_id": plan["approval_id"],
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate["fingerprint"],
        "canary_id": canary_id,
        "canary_result_fingerprint": _sha256(result),
        "task_class": candidate["task_class"],
        "current_strategy": candidate["current_strategy"],
        "proposed_strategy": candidate["proposed_strategy"],
        "policy_snapshot": plan["policy_snapshot"],
        "approved_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=expires_hours)),
        "reason": reason.strip()[:320],
    }
    validate_promotion_approval(record)
    append_promotion_approval(record, root)
    return record


def _evaluate(
    promotion_approval_id: str, root: Path | None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return (status payload, record). The first failing check sets status."""
    from .canary import _policy_snapshot, _sha256

    checks = {
        "resolved": False,
        "revoked": False,
        "expired": False,
        "candidate_match": False,
        "policy_match": False,
        "canary_match": False,
    }
    payload: dict[str, Any] = {
        "kind": "feedback-promotion-status",
        "promotion_approval_id": promotion_approval_id,
        "status": "INVALID",
        "reason": None,
        "candidate_id": None,
        "canary_id": None,
        "canary_approval_id": None,
        "task_class": None,
        "expires_at": None,
        "revocation": None,
        "checks": checks,
        "read_only": True,
        "activation_available": False,
    }

    def fail(status: str, reason: str) -> tuple[dict[str, Any], None]:
        payload["status"] = status
        payload["reason"] = reason
        return payload, None

    try:
        record = resolve_promotion(promotion_approval_id, root)
        revocation = _revocation(promotion_approval_id, root)
    except ValueError as exc:
        return fail("INVALID", str(exc))
    checks["resolved"] = True
    payload.update(
        candidate_id=record["candidate_id"],
        canary_id=record["canary_id"],
        canary_approval_id=record["canary_approval_id"],
        task_class=record["task_class"],
        expires_at=record["expires_at"],
        revocation=revocation,
    )

    if revocation is not None:
        checks["revoked"] = True
        return fail("REVOKED", "promotion approval has been revoked")
    if _parse_time(record["expires_at"]) <= _now():
        checks["expired"] = True
        return fail("EXPIRED", "promotion approval has expired")

    try:
        candidate = candidate_detail(record["candidate_id"], root)["candidate"]
    except (KeyError, ValueError) as exc:
        return fail("INVALID", f"promotion candidate cannot be evaluated: {exc}")
    if record["candidate_fingerprint"] != candidate["fingerprint"]:
        return fail("STALE_CANDIDATE", "promotion candidate fingerprint changed")
    for field in ("task_class", "current_strategy", "proposed_strategy"):
        if record[field] != candidate[field]:
            return fail(
                "STALE_CANDIDATE",
                f"promotion {field.replace('_', ' ')} does not match candidate",
            )
    checks["candidate_match"] = True

    if _policy_snapshot(record["task_class"], root) != record["policy_snapshot"]:
        return fail("STALE_POLICY", "promotion approval policy snapshot is stale")
    checks["policy_match"] = True

    try:
        plan, result = _passing_canary(record["candidate_id"], record["canary_id"], root)
    except ValueError as exc:
        return fail("STALE_CANARY", str(exc))
    if plan["approval_id"] != record["canary_approval_id"]:
        return fail("STALE_CANARY", "canary is bound to another canary approval")
    if _sha256(result) != record["canary_result_fingerprint"]:
        return fail("STALE_CANARY", "canary RESULT changed since promotion approval")
    checks["canary_match"] = True

    payload["status"] = "VALID"
    return payload, record


def promotion_status(
    promotion_approval_id: str, root: Path | None = None
) -> dict[str, Any]:
    """Report whether one promotion approval may still activate. Never writes."""
    payload, _record = _evaluate(promotion_approval_id, root)
    return payload


def require_valid_promotion(
    promotion_approval_id: str,
    *,
    candidate_id: str,
    canary_id: str,
    canary_approval_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Fail closed unless a separate, VALID promotion approval binds this activation."""
    if promotion_approval_id == canary_approval_id or not promotion_approval_id.startswith(
        PROMOTION_APPROVAL_PREFIX
    ):
        raise ValueError(
            "activation requires a separate promotion approval, not the canary approval"
        )
    payload, record = _evaluate(promotion_approval_id, root)
    if payload["checks"]["resolved"]:
        if payload["candidate_id"] != candidate_id:
            raise ValueError("promotion approval is bound to another candidate")
        if payload["canary_id"] != canary_id:
            raise ValueError("promotion approval is bound to another canary")
        if payload["canary_approval_id"] != canary_approval_id:
            raise ValueError("promotion approval is bound to another canary approval")
    if payload["status"] != "VALID" or record is None:
        raise ValueError(str(payload["reason"]))
    return record
