"""Read-only evidence gate for future controlled feedback activation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidates import candidate_detail
from .contracts import validate_activation_readiness
from .store import read_candidate_history, read_comparison_history

SCHEMA_ID = "mq.feedback-activation-readiness.v1"
MIN_COMPARISONS = 2
MIN_DISTINCT_SNAPSHOTS = 2


def _preference(metric: dict[str, Any]) -> int:
    if metric.get("status") != "comparable" or not metric.get("material"):
        return 0
    delta = metric.get("delta")
    if not isinstance(delta, (int, float)):
        return 0
    direction = metric.get("direction")
    if direction == "higher_is_better":
        return 1 if delta > 0 else -1
    if direction == "lower_is_better":
        return 1 if delta < 0 else -1
    return 0


def activation_readiness(
    candidate_id: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Evaluate whether evidence is ready to be presented for human approval.

    This function is read-only. READY_FOR_HUMAN_APPROVAL is not approval and
    does not make an activation path available.
    """
    detail = candidate_detail(candidate_id, state_root)
    candidate = detail["candidate"]
    comparisons = detail["comparisons"]

    candidate_history = read_candidate_history(state_root)
    comparison_history = read_comparison_history(state_root)

    linked_ids = list(candidate["comparison_ids"])
    found_ids = [str(item["comparison_id"]) for item in comparisons]
    snapshots = {
        f"{item['repository']}@{item['snapshot']['commit']}"
        for item in comparisons
    }
    material_regressions = [
        f"{item['comparison_id']}:{name}"
        for item in comparisons
        for name, metric in item["metrics"].items()
        if _preference(metric) < 0
    ]

    requirements = [
        {
            "id": "store-integrity",
            "status": "PASS" if not candidate_history.issues and not comparison_history.issues else "FAIL",
            "detail": (
                "candidate and comparison histories parsed without invalid records"
                if not candidate_history.issues and not comparison_history.issues
                else f"invalid records: candidates={len(candidate_history.issues)} comparisons={len(comparison_history.issues)}"
            ),
            "class": "blocker",
        },
        {
            "id": "supported-kind",
            "status": "PASS" if candidate["kind"] == "context-strategy" else "FAIL",
            "detail": f"kind={candidate['kind']}; first activation gate supports context-strategy only",
            "class": "blocker",
        },
        {
            "id": "candidate-state",
            "status": "PASS" if candidate["state"] == "proposed" else "FAIL",
            "detail": f"state={candidate['state']}; only an effective proposed candidate may proceed",
            "class": "blocker",
        },
        {
            "id": "comparison-links-complete",
            "status": "PASS" if set(found_ids) == set(linked_ids) and len(found_ids) == len(linked_ids) else "FAIL",
            "detail": f"linked={len(linked_ids)} resolved={len(found_ids)}",
            "class": "blocker",
        },
        {
            "id": "task-class-isolated",
            "status": "PASS" if comparisons and all(item["task_class"] == candidate["task_class"] for item in comparisons) else "FAIL",
            "detail": f"task_class={candidate['task_class']}; cross-task activation is forbidden",
            "class": "blocker",
        },
        {
            "id": "strategy-pair-exact",
            "status": "PASS" if comparisons and all(
                item["active_strategy"] == candidate["current_strategy"]
                and item["shadow_strategy"] == candidate["proposed_strategy"]
                for item in comparisons
            ) else "FAIL",
            "detail": f"{candidate['current_strategy']} -> {candidate['proposed_strategy']}",
            "class": "blocker",
        },
        {
            "id": "all-comparisons-valid",
            "status": "PASS" if comparisons and all(item["valid"] for item in comparisons) else "FAIL",
            "detail": f"valid={sum(1 for item in comparisons if item['valid'])}/{len(comparisons)}",
            "class": "blocker",
        },
        {
            "id": "all-verdicts-candidate-better",
            "status": "PASS" if comparisons and all(item["verdict"] == "CANDIDATE_BETTER" for item in comparisons) else "FAIL",
            "detail": ", ".join(f"{item['comparison_id']}={item['verdict']}" for item in comparisons) or "no comparisons",
            "class": "blocker",
        },
        {
            "id": "no-material-regressions",
            "status": "PASS" if not material_regressions else "FAIL",
            "detail": "none" if not material_regressions else ", ".join(material_regressions),
            "class": "blocker",
        },
        {
            "id": "rollback-target-exact",
            "status": "PASS" if candidate["rollback_target"] == candidate["current_strategy"] else "FAIL",
            "detail": f"rollback={candidate['rollback_target']} current={candidate['current_strategy']}",
            "class": "blocker",
        },
        {
            "id": "repeated-evidence",
            "status": "PASS" if len(comparisons) >= MIN_COMPARISONS else "FAIL",
            "detail": f"comparisons={len(comparisons)} required={MIN_COMPARISONS}",
            "class": "evidence",
        },
        {
            "id": "distinct-snapshots",
            "status": "PASS" if len(snapshots) >= MIN_DISTINCT_SNAPSHOTS else "FAIL",
            "detail": f"distinct_snapshots={len(snapshots)} required={MIN_DISTINCT_SNAPSHOTS}",
            "class": "evidence",
        },
    ]

    blocker_failed = any(
        item["status"] == "FAIL" and item["class"] == "blocker"
        for item in requirements
    )
    evidence_failed = any(
        item["status"] == "FAIL" and item["class"] == "evidence"
        for item in requirements
    )
    if blocker_failed:
        status = "BLOCKED"
    elif evidence_failed:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        status = "READY_FOR_HUMAN_APPROVAL"

    payload = {
        "schema": SCHEMA_ID,
        "candidate_id": candidate_id,
        "status": status,
        "task_class": candidate["task_class"],
        "candidate_state": candidate["state"],
        "kind": candidate["kind"],
        "current_strategy": candidate["current_strategy"],
        "proposed_strategy": candidate["proposed_strategy"],
        "rollback_target": candidate["rollback_target"],
        "scope": {
            "task_class": candidate["task_class"],
            "cross_task_activation": False,
        },
        "evidence": {
            "comparison_count": len(comparisons),
            "distinct_snapshot_count": len(snapshots),
            "comparison_ids": found_ids,
            "snapshots": sorted(snapshots),
            "material_regressions": material_regressions,
        },
        "requirements": requirements,
        "human_approval_required": True,
        "canary_required": True,
        "activation_available": False,
        "next_action": (
            "request-human-approval"
            if status == "READY_FOR_HUMAN_APPROVAL"
            else "collect-more-evidence"
            if status == "INSUFFICIENT_EVIDENCE"
            else "resolve-blockers"
        ),
    }
    validate_activation_readiness(payload)
    return payload
