"""Bounded deterministic Canary v2 control evidence."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .candidates import candidate_detail
from .contracts import validate_approval, validate_canary_record
from .engine import (
    DEFAULT_MAX_CONTEXT_BYTES,
    DEFAULT_MAX_SOURCES,
    DEFAULT_TIMEOUT_MS,
    run_context_experiment,
)
from .evaluation import compare_feedback_run
from .readiness import activation_readiness
from .store import (
    append_canary,
    read_approval_history,
    read_canary_history,
)

SCHEMA_ID = "mq.feedback-canary.v1"
DEFAULT_EXECUTION_BUDGET = 3
DEFAULT_MIN_EXECUTIONS = 3
DEFAULT_MAX_DURATION_SECONDS = 300
DEFAULT_MAX_FAILURE_RATE = 0.0


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sha256(value: dict[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _policy_snapshot(task_class: str, root: Path | None) -> dict[str, Any]:
    from .control import policy_status

    status = policy_status(task_class, root)
    last = status.get("last_event")
    return {
        "effective_strategy": status["effective_strategy"],
        "event_count": int(status["events"]),
        "last_event_id": (
            str(last["event_id"])
            if isinstance(last, dict) and last.get("event_id")
            else None
        ),
    }


def _approval(approval_id: str, root: Path | None) -> dict[str, Any]:
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


def _validate_candidate_approval(
    candidate_id: str,
    approval_id: str,
    root: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = candidate_detail(candidate_id, root)["candidate"]
    approval = _approval(approval_id, root)
    readiness = activation_readiness(candidate_id, root)
    if readiness["status"] != "READY_FOR_HUMAN_APPROVAL":
        raise ValueError(
            "approval expired because candidate readiness/state changed: "
            + str(readiness["status"])
        )
    if approval["candidate_id"] != candidate_id:
        raise ValueError("approval is bound to another candidate")
    if approval["candidate_fingerprint"] != candidate["fingerprint"]:
        raise ValueError("approval expired because candidate fingerprint changed")
    if approval["task_class"] != candidate["task_class"]:
        raise ValueError("approval task class does not match candidate")
    if approval["current_strategy"] != candidate["current_strategy"]:
        raise ValueError("approval current strategy does not match candidate")
    if approval["proposed_strategy"] != candidate["proposed_strategy"]:
        raise ValueError("approval proposed strategy does not match candidate")
    if _parse_time(approval["expires_at"]) <= datetime.now(UTC):
        raise ValueError("approval receipt has expired")
    return candidate, approval


def _plan_basis(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"plan_sha256"}
    }


def create_canary_plan(
    candidate_id: str,
    *,
    approval_id: str,
    execution_budget: int = DEFAULT_EXECUTION_BUDGET,
    min_executions: int = DEFAULT_MIN_EXECUTIONS,
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
    max_failure_rate: float = DEFAULT_MAX_FAILURE_RATE,
    root: Path | None = None,
) -> dict[str, Any]:
    """Append one immutable canary plan bound to candidate, approval and policy."""
    if execution_budget < 1 or execution_budget > 20:
        raise ValueError("execution_budget must be between 1 and 20")
    if min_executions < 1 or min_executions > execution_budget:
        raise ValueError("min_executions must be between 1 and execution_budget")
    if max_duration_seconds < 1 or max_duration_seconds > 3600:
        raise ValueError("max_duration_seconds must be between 1 and 3600")
    if not 0.0 <= max_failure_rate <= 1.0:
        raise ValueError("max_failure_rate must be between 0 and 1")

    candidate, _approval_record = _validate_candidate_approval(
        candidate_id, approval_id, root
    )
    policy = _policy_snapshot(candidate["task_class"], root)
    if policy["effective_strategy"] != candidate["current_strategy"]:
        raise ValueError("effective policy no longer matches approved current strategy")

    record: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "record_type": "PLAN",
        "canary_id": f"canary-{uuid.uuid4()}",
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate["fingerprint"],
        "approval_id": approval_id,
        "task_class": candidate["task_class"],
        "current_strategy": candidate["current_strategy"],
        "proposed_strategy": candidate["proposed_strategy"],
        "policy_snapshot": policy,
        "plan": {
            "execution_budget": execution_budget,
            "min_executions": min_executions,
            "max_duration_seconds": max_duration_seconds,
            "max_failure_rate": float(max_failure_rate),
        },
        "created_at": _now(),
    }
    record["plan_sha256"] = _sha256(_plan_basis(record))
    validate_canary_record(record)
    append_canary(record, root)
    return record


def _records(canary_id: str, root: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    history = read_canary_history(root)
    if history.issues:
        raise ValueError("canary store contains invalid records")
    records = [
        item.record
        for item in history.records
        if item.record.get("canary_id") == canary_id
    ]
    plans = [record for record in records if record["record_type"] == "PLAN"]
    results = [record for record in records if record["record_type"] == "RESULT"]
    if len(plans) != 1:
        raise ValueError("canary must resolve to exactly one PLAN")
    if len(results) > 1:
        raise ValueError("canary has duplicate RESULT records")
    plan = plans[0]
    if _sha256(_plan_basis({k: v for k, v in plan.items() if k != "plan_sha256"})) != plan["plan_sha256"]:
        raise ValueError("canary plan hash mismatch")
    return plan, results[0] if results else None


def canary_status(canary_id: str, root: Path | None = None) -> dict[str, Any]:
    plan, result = _records(canary_id, root)
    return {
        "kind": "feedback-canary-status",
        "canary_id": canary_id,
        "state": "COMPLETED" if result is not None else "PLANNED",
        "plan": plan,
        "result": result,
    }


def _candidate_regressions(comparison: dict[str, Any]) -> list[str]:
    regressions: list[str] = []
    for name, metric in comparison.get("metrics", {}).items():
        if metric.get("status") != "comparable" or not metric.get("material"):
            continue
        delta = metric.get("delta")
        if not isinstance(delta, (int, float)):
            continue
        direction = metric.get("direction")
        worse = (
            direction == "higher_is_better" and delta < 0
        ) or (
            direction == "lower_is_better" and delta > 0
        )
        if worse:
            regressions.append(f"{comparison['comparison_id']}:{name}")
    return regressions


def _mean_delta(
    comparisons: list[dict[str, Any]],
    names: tuple[str, ...],
) -> float | None:
    values: list[float] = []
    for comparison in comparisons:
        for name in names:
            metric = comparison.get("metrics", {}).get(name)
            if not isinstance(metric, dict):
                continue
            delta = metric.get("delta")
            if metric.get("status") == "comparable" and isinstance(delta, (int, float)):
                values.append(float(delta))
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def run_canary(
    canary_id: str,
    *,
    task: str,
    fixture_path: Path,
    repo: Path = Path("."),
    vault: Path | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
    max_sources: int = DEFAULT_MAX_SOURCES,
    root: Path | None = None,
) -> dict[str, Any]:
    """Execute one bounded zero-effect canary plan and append one RESULT."""
    if not task.strip():
        raise ValueError("task must not be empty")
    plan, existing = _records(canary_id, root)
    if existing is not None:
        raise ValueError("canary already has a RESULT")

    candidate, _approval_record = _validate_candidate_approval(
        plan["candidate_id"], plan["approval_id"], root
    )
    if candidate["fingerprint"] != plan["candidate_fingerprint"]:
        raise ValueError("canary plan candidate fingerprint is stale")
    current_policy = _policy_snapshot(plan["task_class"], root)
    if current_policy != plan["policy_snapshot"]:
        raise ValueError("canary plan policy snapshot is stale")

    budget = plan["plan"]
    execution_budget = int(budget["execution_budget"])
    min_executions = int(budget["min_executions"])
    max_duration = float(budget["max_duration_seconds"])
    max_failure_rate = float(budget["max_failure_rate"])

    started_wall = _now()
    started = time.perf_counter()
    feedback_run_ids: list[str] = []
    comparison_ids: list[str] = []
    comparisons: list[dict[str, Any]] = []
    snapshots: list[dict[str, str]] = []
    blocked_reasons: list[str] = []
    successes = 0
    failures = 0
    inconclusive = 0
    completed = 0

    for _index in range(execution_budget):
        elapsed = time.perf_counter() - started
        remaining = max_duration - elapsed
        if remaining <= 0:
            blocked_reasons.append("max-duration-exhausted")
            break

        # run_context_experiment performs active and shadow collection, each with
        # its own timeout. Split remaining wall-clock budget across both.
        bounded_timeout_ms = min(
            timeout_ms,
            max(1, int((remaining * 1000) / 2)),
        )
        experiment_result = run_context_experiment(
            task,
            repo,
            task_class=plan["task_class"],
            vault=vault,
            state_root=root,
            timeout_ms=bounded_timeout_ms,
            max_context_bytes=max_context_bytes,
            max_sources=max_sources,
        )
        completed += 1
        experiment = experiment_result["experiment"]
        feedback_run_ids.append(experiment["feedback_run_id"])
        snapshot = experiment["snapshot"]
        if snapshot not in snapshots:
            snapshots.append(snapshot)

        if experiment_result["status"] != "PASS":
            failures += 1
            blocked_reasons.append(
                str(experiment_result.get("reason") or "experiment-blocked")[:200]
            )
            continue

        comparison = compare_feedback_run(
            experiment["feedback_run_id"],
            fixture_path=fixture_path,
            state_root=root,
        )
        comparison_ids.append(comparison["comparison_id"])
        comparisons.append(comparison)

        if (
            comparison["active_strategy"] != plan["current_strategy"]
            or comparison["shadow_strategy"] != plan["proposed_strategy"]
        ):
            failures += 1
            blocked_reasons.append("strategy-pair-drift")
            continue

        verdict = comparison["verdict"]
        if verdict == "CANDIDATE_BETTER":
            successes += 1
        elif verdict in {"CANDIDATE_WORSE", "CONFLICTING_EVIDENCE", "BLOCKED"}:
            failures += 1
        else:
            inconclusive += 1

    final_policy = _policy_snapshot(plan["task_class"], root)
    policy_drift = final_policy != plan["policy_snapshot"]
    if policy_drift:
        blocked_reasons.append("policy-snapshot-drift")

    approval_invalid = False
    try:
        _validate_candidate_approval(
            plan["candidate_id"], plan["approval_id"], root
        )
    except ValueError as exc:
        approval_invalid = True
        blocked_reasons.append(
            ("approval-invalid-after-run:" + str(exc))[:200]
        )

    regressions = sorted(
        set(
            regression
            for comparison in comparisons
            for regression in _candidate_regressions(comparison)
        )
    )
    failure_rate = round(failures / completed, 6) if completed else None

    if (
        regressions
        or policy_drift
        or approval_invalid
        or (failure_rate is not None and failure_rate > max_failure_rate)
    ):
        verdict = "FAIL"
    elif completed < min_executions or successes < min_executions:
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "PASS"

    duration_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
    result = {
        **{key: value for key, value in plan.items() if key != "record_type"},
        "record_type": "RESULT",
        "started_at": started_wall,
        "completed_at": _now(),
        "duration_ms": duration_ms,
        "verdict": verdict,
        "executions_requested": execution_budget,
        "executions_completed": completed,
        "successes": successes,
        "failures": failures,
        "inconclusive": inconclusive,
        "failure_rate": failure_rate,
        "feedback_run_ids": feedback_run_ids,
        "comparison_ids": comparison_ids,
        "snapshots": snapshots,
        "metrics": {
            "latency_delta_ms": _mean_delta(
                comparisons, ("retrieval_latency_ms",)
            ),
            "grounding_delta": _mean_delta(
                comparisons, ("relevance_precision", "relevance_recall")
            ),
            "context_delta_bytes": _mean_delta(
                comparisons, ("context_bytes",)
            ),
            "fallback_delta": None,
        },
        "regressions": regressions,
        "blocked_reasons": sorted(set(blocked_reasons)),
    }
    validate_canary_record(result)
    append_canary(result, root)
    return result


def require_passing_canary(
    canary_id: str,
    *,
    candidate_id: str,
    approval_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Fail closed unless the exact Canary v2 result is still activation-safe."""
    plan, result = _records(canary_id, root)
    if result is None:
        raise ValueError("canary has no RESULT")
    if result["verdict"] != "PASS":
        raise ValueError(f"canary verdict is not PASS: {result['verdict']}")
    if plan["candidate_id"] != candidate_id or result["candidate_id"] != candidate_id:
        raise ValueError("canary is bound to another candidate")
    if plan["approval_id"] != approval_id or result["approval_id"] != approval_id:
        raise ValueError("canary is bound to another approval")
    candidate, _approval_record = _validate_candidate_approval(
        candidate_id, approval_id, root
    )
    if result["candidate_fingerprint"] != candidate["fingerprint"]:
        raise ValueError("canary candidate fingerprint is stale")
    if result["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("canary RESULT is not bound to the exact PLAN")
    if _policy_snapshot(plan["task_class"], root) != plan["policy_snapshot"]:
        raise ValueError("canary policy snapshot is stale")
    if result["task_class"] != candidate["task_class"]:
        raise ValueError("canary task class does not match candidate")
    if result["current_strategy"] != candidate["current_strategy"]:
        raise ValueError("canary current strategy does not match candidate")
    if result["proposed_strategy"] != candidate["proposed_strategy"]:
        raise ValueError("canary proposed strategy does not match candidate")
    return result
