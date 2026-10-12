"""Approval lifecycle: one read-only status evaluation and append-only revocation.

Every approval consumer (canary plan, canary run, legacy canary check and
activation) goes through ``require_valid_approval`` so a revocation, expiry,
evidence drift, policy drift or repo/commit mismatch blocks all of them alike.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .candidates import candidate_detail
from .contracts import (
    APPROVAL_REVOCATION_SCHEMA_ID,
    APPROVAL_V2_SCHEMA_ID,
    validate_approval,
    validate_approval_revocation,
)
from .readiness import activation_readiness
from .store import (
    append_approval_revocation,
    read_approval_history,
    read_approval_revocation_history,
)

# Promotion approvals share the revocation contract and store; the prefix keeps
# them distinct from canary approvals, whose ids are approval-<uuid4>.
PROMOTION_APPROVAL_PREFIX = "approval-promotion-"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve(approval_id: str, root: Path | None) -> dict[str, Any]:
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


def _revocation(approval_id: str, root: Path | None) -> dict[str, Any] | None:
    history = read_approval_revocation_history(root)
    if history.issues:
        raise ValueError("approval revocation store contains invalid records")
    matches = [
        item.record
        for item in history.records
        if item.record.get("approval_id") == approval_id
    ]
    return matches[0] if matches else None


def _evaluate(
    approval_id: str, root: Path | None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return (status payload, candidate). The first failing check sets status."""
    checks = {
        "resolved": False,
        "revoked": False,
        "expired": False,
        "candidate_match": False,
        "readiness_match": False,
        "commit_match": False,
        "policy_match": False,
    }
    payload: dict[str, Any] = {
        "kind": "feedback-approval-status",
        "approval_id": approval_id,
        "status": "INVALID",
        "reason": None,
        "approval_schema": None,
        "candidate_id": None,
        "task_class": None,
        "expires_at": None,
        "evidence_snapshots": None,
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
        approval = _resolve(approval_id, root)
        revocation = _revocation(approval_id, root)
    except ValueError as exc:
        return fail("INVALID", str(exc))
    checks["resolved"] = True
    payload.update(
        approval_schema=approval["schema"],
        candidate_id=approval["candidate_id"],
        task_class=approval["task_class"],
        expires_at=approval["expires_at"],
        evidence_snapshots=approval.get("evidence_snapshots"),
        revocation=revocation,
    )

    if revocation is not None:
        checks["revoked"] = True
        return fail("REVOKED", "approval receipt has been revoked")
    if _parse_time(approval["expires_at"]) <= _now():
        checks["expired"] = True
        return fail("EXPIRED", "approval receipt has expired")

    try:
        candidate = candidate_detail(approval["candidate_id"], root)["candidate"]
        readiness = activation_readiness(approval["candidate_id"], root)
    except (KeyError, ValueError) as exc:
        return fail("INVALID", f"approval candidate cannot be evaluated: {exc}")

    if readiness["status"] != "READY_FOR_HUMAN_APPROVAL":
        return fail(
            "STALE_READINESS",
            "approval expired because candidate readiness/state changed: "
            + str(readiness["status"]),
        )
    if approval["candidate_fingerprint"] != candidate["fingerprint"]:
        return fail(
            "STALE_CANDIDATE", "approval expired because candidate fingerprint changed"
        )
    for field, label in (
        ("task_class", "task class"),
        ("current_strategy", "current strategy"),
        ("proposed_strategy", "proposed strategy"),
    ):
        if approval[field] != candidate[field]:
            return fail("STALE_CANDIDATE", f"approval {label} does not match candidate")
    checks["candidate_match"] = True

    if approval.get("readiness_fingerprint") is None:
        return fail(
            "STALE_READINESS",
            "approval predates outcome-bound readiness; issue a new approval",
        )
    if approval["readiness_fingerprint"] != readiness["evidence_fingerprint"]:
        return fail(
            "STALE_READINESS",
            "approval expired because task-class readiness evidence changed",
        )
    checks["readiness_match"] = True

    if approval["schema"] != APPROVAL_V2_SCHEMA_ID:
        return fail(
            "INVALID",
            "approval predates repo/commit binding; issue a new approval",
        )
    if approval["evidence_snapshots"] != readiness["evidence"]["snapshots"]:
        return fail(
            "COMMIT_MISMATCH",
            "approval repo/commit binding does not match readiness evidence",
        )
    checks["commit_match"] = True

    from . import control

    if control.effective_strategy(approval["task_class"], root) != approval[
        "current_strategy"
    ]:
        return fail(
            "STALE_POLICY",
            "effective policy no longer matches approved current strategy",
        )
    checks["policy_match"] = True

    payload["status"] = "VALID"
    return payload, candidate


def approval_status(approval_id: str, root: Path | None = None) -> dict[str, Any]:
    """Report the current validity of one approval. Never writes."""
    payload, _candidate = _evaluate(approval_id, root)
    return payload


def require_valid_approval(
    candidate_id: str,
    approval_id: str,
    root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed unless the approval is VALID for exactly this candidate."""
    payload, candidate = _evaluate(approval_id, root)
    if payload["checks"]["resolved"] and payload["candidate_id"] != candidate_id:
        raise ValueError("approval is bound to another candidate")
    if payload["status"] != "VALID" or candidate is None:
        raise ValueError(str(payload["reason"]))
    return candidate, _resolve(approval_id, root)


def revoke_approval(
    approval_id: str,
    *,
    reason: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Append one revocation for a canary or promotion approval.

    The approval record itself is never modified.
    """
    if not reason.strip():
        raise ValueError("revocation requires a reason")
    if approval_id.startswith(PROMOTION_APPROVAL_PREFIX):
        from .promotion import resolve_promotion

        resolve_promotion(approval_id, root)
    else:
        _resolve(approval_id, root)
    if _revocation(approval_id, root) is not None:
        raise ValueError("approval is already revoked")
    record = {
        "schema": APPROVAL_REVOCATION_SCHEMA_ID,
        "approval_id": approval_id,
        "revoked_at": _iso(_now()),
        "reason": reason.strip()[:320],
    }
    validate_approval_revocation(record)
    append_approval_revocation(record, root)
    return record
