"""F4 reviewable improvement candidates over immutable comparison evidence."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mq_agent.memory.cochange_observation import emit_observation

from .contracts import validate_candidate
from .store import (
    append_candidate,
    read_candidate_history,
    read_comparison_history,
)

_ALLOWED_REVIEW_STATES = {
    "deferred",
    "rejected",
    "approved-for-handoff",
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _effective_candidates(state_root: Path | None = None) -> dict[str, dict[str, Any]]:
    effective: dict[str, dict[str, Any]] = {}
    for item in read_candidate_history(state_root).records:
        effective[str(item.record["candidate_id"])] = item.record
    return effective


def _candidate_fingerprint(
    *,
    kind: str,
    task_class: str,
    current_strategy: str,
    proposed_strategy: str,
) -> str:
    payload = {
        "kind": kind,
        "task_class": task_class,
        "current_strategy": current_strategy,
        "proposed_strategy": proposed_strategy,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _metric_text(name: str, metric: dict[str, Any]) -> str:
    delta = metric.get("delta")
    return (
        f"{name}: active={metric.get('active')} shadow={metric.get('shadow')} "
        f"delta={delta} {metric.get('unit')}"
    )


def _preference(metric: dict[str, Any]) -> int:
    if metric.get("status") != "comparable" or not metric.get("material"):
        return 0
    delta = float(metric["delta"])
    direction = metric["direction"]
    if direction == "higher_is_better":
        return 1 if delta > 0 else -1
    if direction == "lower_is_better":
        return 1 if delta < 0 else -1
    return 0


def _window(comparisons: list[dict[str, Any]]) -> dict[str, str]:
    times = sorted(str(item["recorded_at"]) for item in comparisons)
    return {"from": times[0], "to": times[-1]}


def _proposal_from_comparisons(
    comparisons: list[dict[str, Any]],
    *,
    candidate_id: str,
    fingerprint: str,
    supersedes: list[str],
    state: str = "proposed",
    state_reason: str | None = None,
) -> dict[str, Any]:
    latest = comparisons[-1]
    gains = [
        _metric_text(name, metric)
        for name, metric in latest["metrics"].items()
        if _preference(metric) > 0
    ]
    regressions = [
        _metric_text(name, metric)
        for name, metric in latest["metrics"].items()
        if _preference(metric) < 0
    ]
    limitations = [
        "Proposal only; feedback candidates cannot activate policy.",
        f"Evidence is scoped to task class {latest['task_class']}; no cross-task generalization is claimed.",
        "Deleting feedback runtime state must not change production behavior.",
    ]
    if latest.get("advisory_evaluator") is not None:
        limitations.append(
            "Atlas/model evaluator output is advisory and did not determine the verdict."
        )

    record = {
        "schema": "mq.feedback-candidate.v1",
        "candidate_id": candidate_id,
        "fingerprint": fingerprint,
        "kind": "context-strategy",
        "task_class": latest["task_class"],
        "current_strategy": latest["active_strategy"],
        "proposed_strategy": latest["shadow_strategy"],
        "comparison_ids": [item["comparison_id"] for item in comparisons],
        "evidence_window": _window(comparisons),
        "rationale": (
            "Deterministic feedback evidence classified the proposed context "
            "strategy as CANDIDATE_BETTER; review per-metric gains and "
            "regressions before any future activation work."
        ),
        "gains": gains,
        "regressions": regressions,
        "limitations": limitations,
        "rollback_target": latest["active_strategy"],
        "state": state,
        "state_reason": state_reason,
        "supersedes": supersedes,
        "recorded_at": _now(),
    }
    validate_candidate(record)
    return record


def maybe_create_candidate(
    comparison: dict[str, Any],
    *,
    state_root: Path | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Create/update one proposal only for a deterministic better verdict."""
    if comparison["verdict"] != "CANDIDATE_BETTER":
        return None, False

    fingerprint = _candidate_fingerprint(
        kind="context-strategy",
        task_class=comparison["task_class"],
        current_strategy=comparison["active_strategy"],
        proposed_strategy=comparison["shadow_strategy"],
    )
    effective = _effective_candidates(state_root)
    same = next(
        (item for item in effective.values() if item["fingerprint"] == fingerprint),
        None,
    )
    history = read_comparison_history(state_root)
    if same is not None:
        ids = list(same["comparison_ids"])
        if comparison["comparison_id"] in ids:
            return same, False
        wanted = set(ids + [comparison["comparison_id"]])
        linked = [
            item.record
            for item in history.records
            if item.record["comparison_id"] in wanted
        ]
        updated = _proposal_from_comparisons(
            linked,
            candidate_id=same["candidate_id"],
            fingerprint=fingerprint,
            supersedes=list(same["supersedes"]),
            state=same["state"],
            state_reason=same.get("state_reason"),
        )
        append_candidate(updated, state_root)
        return updated, True

    superseded = [
        item
        for item in effective.values()
        if item["kind"] == "context-strategy"
        and item["task_class"] == comparison["task_class"]
        and item["current_strategy"] == comparison["active_strategy"]
        and item["state"] == "proposed"
    ]
    candidate_id = f"cand-{uuid.uuid4()}"
    for old in superseded:
        prior_comparisons = [
            item.record
            for item in history.records
            if item.record["comparison_id"] in set(old["comparison_ids"])
        ]
        transition = _proposal_from_comparisons(
            prior_comparisons,
            candidate_id=old["candidate_id"],
            fingerprint=old["fingerprint"],
            supersedes=list(old["supersedes"]),
            state="superseded",
            state_reason=f"superseded by {candidate_id}",
        )
        append_candidate(transition, state_root)

    record = _proposal_from_comparisons(
        [comparison],
        candidate_id=candidate_id,
        fingerprint=fingerprint,
        supersedes=[item["candidate_id"] for item in superseded],
    )
    append_candidate(record, state_root)
    return record, True


def list_candidates(state_root: Path | None = None) -> dict[str, Any]:
    history = read_candidate_history(state_root)
    effective = list(_effective_candidates(state_root).values())
    effective.sort(key=lambda item: str(item["recorded_at"]), reverse=True)
    return {
        "view": "feedback-candidates.v1",
        "candidates": effective,
        "count": len(effective),
        "invalid_records": len(history.issues),
    }


def candidate_detail(
    candidate_id: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    history = [
        item.record
        for item in read_candidate_history(state_root).records
        if item.record["candidate_id"] == candidate_id
    ]
    if not history:
        raise ValueError(f"feedback candidate not found: {candidate_id}")
    comparison_ids = set(history[-1]["comparison_ids"])
    comparisons = [
        item.record
        for item in read_comparison_history(state_root).records
        if item.record["comparison_id"] in comparison_ids
    ]
    return {
        "view": "feedback-candidate-detail.v1",
        "candidate": history[-1],
        "history": history,
        "comparisons": comparisons,
    }


def set_candidate_state(
    candidate_id: str,
    state: str,
    *,
    reason: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    if state not in _ALLOWED_REVIEW_STATES:
        raise ValueError("candidate state must be deferred, rejected, or approved-for-handoff")
    if not reason.strip():
        raise ValueError("candidate state change requires a reason")
    detail = candidate_detail(candidate_id, state_root)
    current = detail["candidate"]
    comparisons = detail["comparisons"]
    record = _proposal_from_comparisons(
        comparisons,
        candidate_id=current["candidate_id"],
        fingerprint=current["fingerprint"],
        supersedes=list(current["supersedes"]),
        state=state,
        state_reason=reason.strip()[:320],
    )
    append_candidate(record, state_root)
    return record


def memory_handoff(
    candidate_id: str,
    *,
    confidence: float,
    state_root: Path | None = None,
    vault: Path | None = None,
) -> dict[str, Any]:
    """Map an approved memory candidate into mqobsidian's existing observation inbox.

    This does not write durable memory and does not invoke promotion. mqobsidian's
    normal scoring/review/promotion path remains authoritative.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    detail = candidate_detail(candidate_id, state_root)
    candidate = detail["candidate"]
    if candidate["kind"] != "memory":
        raise ValueError("candidate is not a memory candidate")
    if candidate["state"] != "approved-for-handoff":
        raise ValueError("memory candidate requires approved-for-handoff state")
    comparisons = detail["comparisons"]
    if not comparisons:
        raise ValueError("memory candidate has no comparison evidence")
    repository = comparisons[-1]["repository"]
    observation = {
        "schema": "memory-observation.v1",
        "id": f"mo-feedback-{re.sub(r'[^A-Za-z0-9-]+', '-', candidate_id)}",
        "timestamp": _now(),
        "producer": "mq-agent",
        "repository": repository,
        "workflow": "feedback-candidate",
        "title": "Reviewed feedback learning candidate",
        "observation": candidate["rationale"],
        "category": "learning",
        "confidence": float(confidence),
        "evidence": [
            {
                "source": "mq.feedback-comparison.v1",
                "reference": comparison_id,
            }
            for comparison_id in candidate["comparison_ids"]
        ],
        "tags": ["feedback", "candidate", candidate["task_class"]],
        "proposed_memory_key": f"feedback-{candidate['fingerprint'][:16]}",
    }
    path = emit_observation(observation, vault=vault)
    if path is None:
        raise RuntimeError("mqobsidian observation handoff failed")
    return {
        "schema": "feedback-memory-handoff.v1",
        "candidate_id": candidate_id,
        "observation_id": observation["id"],
        "status": "submitted-for-review",
    }
