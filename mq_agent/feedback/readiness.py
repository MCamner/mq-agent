"""Read-only evidence gate for controlled feedback activation.

The original gate used one global floor: two comparisons from two Git snapshots.
That proved repetition, but it did not prove that the candidate evidence came
from real task executions or that the same amount of evidence made sense for
every task class.

This gate now derives bounded promotion criteria from real execution outcomes
that are explicitly correlated by feedback experiments. The feedback task class
remains authoritative; mq.execution-outcome.v1 uses a different execution-class
vocabulary, so this module never invents a repo-review -> audit mapping.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from mq_agent.tools.execution_outcome import (
    execution_outcome_fingerprint,
    read_execution_outcomes,
)

from .candidates import candidate_detail
from .contracts import validate_activation_readiness
from .store import (
    read_candidate_history,
    read_comparison_history,
    read_experiment_history,
)

SCHEMA_ID = "mq.feedback-activation-readiness.v1"

# These are calibration bounds, not one global promotion threshold. Four real
# outcomes are the minimum needed to have three timing intervals from which a
# cadence can be derived. The candidate sample then grows sub-linearly with the
# task class's observed population and is bounded so readiness cannot demand an
# ever-growing replay of history.
MIN_CALIBRATION_OUTCOMES = 4
MIN_DERIVED_SAMPLE = 3
MAX_DERIVED_SAMPLE = 8


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


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _span_days(records: list[dict[str, Any]]) -> float:
    stamps = sorted(_parse_time(str(record["recorded_at"])) for record in records)
    if len(stamps) < 2:
        return 0.0
    return round((stamps[-1] - stamps[0]).total_seconds() / 86400, 6)


def _distinct_days(records: list[dict[str, Any]]) -> int:
    return len({_parse_time(str(record["recorded_at"])).date() for record in records})


def _success_rate(records: list[dict[str, Any]]) -> float | None:
    if not records:
        return None
    successful = sum(
        1
        for record in records
        if record["result"] == "PASS" and record["exit_status"] == "ok"
    )
    return round(successful / len(records), 6)


def _median_gap_days(records: list[dict[str, Any]]) -> float:
    stamps = sorted(
        {
            _parse_time(str(record["recorded_at"]))
            for record in records
        }
    )
    if len(stamps) < 2:
        return 0.0
    gaps = [
        (right - left).total_seconds() / 86400
        for left, right in zip(stamps, stamps[1:])
    ]
    return round(float(statistics.median(gaps)), 6)


def _sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _task_class_evidence(
    task_class: str,
    comparisons: list[dict[str, Any]],
    state_root: Path | None,
) -> dict[str, Any]:
    experiments = read_experiment_history(state_root)
    outcomes, outcome_issues = read_execution_outcomes()

    experiment_by_feedback: dict[str, list[dict[str, Any]]] = {}
    for item in experiments.records:
        experiment_by_feedback.setdefault(
            str(item.record["feedback_run_id"]), []
        ).append(item.record)

    outcome_by_run: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        outcome_by_run.setdefault(str(outcome["run_id"]), []).append(outcome)

    population_by_run: dict[str, dict[str, Any]] = {}
    population_experiments: list[str] = []
    for item in experiments.records:
        experiment = item.record
        if (
            experiment.get("task_class") != task_class
            or experiment.get("state") != "completed"
        ):
            continue
        execution_run_id = experiment.get("execution_run_id")
        if not isinstance(execution_run_id, str):
            continue
        matches = outcome_by_run.get(execution_run_id, [])
        if len(matches) != 1:
            continue
        population_by_run.setdefault(execution_run_id, matches[0])
        population_experiments.append(str(experiment["feedback_run_id"]))

    population = list(population_by_run.values())
    population.sort(key=lambda record: (str(record["recorded_at"]), str(record["run_id"])))

    linked_by_run: dict[str, dict[str, Any]] = {}
    linked_refs: list[dict[str, str]] = []
    unresolved_feedback_runs: list[str] = []
    for comparison in comparisons:
        feedback_run_id = str(comparison["feedback_run_id"])
        experiment_matches = experiment_by_feedback.get(feedback_run_id, [])
        if len(experiment_matches) != 1:
            unresolved_feedback_runs.append(feedback_run_id)
            continue
        experiment = experiment_matches[0]
        if experiment.get("task_class") != task_class:
            unresolved_feedback_runs.append(feedback_run_id)
            continue
        execution_run_id = experiment.get("execution_run_id")
        if not isinstance(execution_run_id, str):
            unresolved_feedback_runs.append(feedback_run_id)
            continue
        outcome_matches = outcome_by_run.get(execution_run_id, [])
        if len(outcome_matches) != 1:
            unresolved_feedback_runs.append(feedback_run_id)
            continue
        outcome = outcome_matches[0]
        linked_by_run.setdefault(execution_run_id, outcome)
        linked_refs.append(
            {
                "feedback_run_id": feedback_run_id,
                "execution_run_id": execution_run_id,
                "fingerprint": execution_outcome_fingerprint(outcome),
            }
        )

    linked = list(linked_by_run.values())
    linked.sort(key=lambda record: (str(record["recorded_at"]), str(record["run_id"])))

    population_count = len(population)
    population_days = _distinct_days(population)
    required_linked = min(
        MAX_DERIVED_SAMPLE,
        max(MIN_DERIVED_SAMPLE, math.ceil(math.sqrt(population_count))),
    )
    required_distinct_days = min(
        required_linked,
        max(2, math.ceil(math.sqrt(population_days))) if population_days else 2,
    )
    median_gap = _median_gap_days(population)
    required_window_days = round(
        min(_span_days(population), median_gap * 2),
        6,
    )

    population_rate = _success_rate(population)
    linked_rate = _success_rate(linked)

    calibration_basis = [
        {
            "run_id": str(record["run_id"]),
            "fingerprint": execution_outcome_fingerprint(record),
        }
        for record in population
    ]
    criteria = {
        "derivation": "sqrt-population+task-class-baseline+observed-cadence",
        "calibration_outcomes": population_count,
        "calibration_distinct_days": population_days,
        "calibration_window_days": _span_days(population),
        "calibration_median_gap_days": median_gap,
        "calibration_success_rate": population_rate,
        "required_linked_outcomes": required_linked,
        "required_distinct_days": required_distinct_days,
        "required_window_days": required_window_days,
        "required_success_rate": population_rate,
        "calibration_fingerprint": _sha256(calibration_basis),
    }

    linked_run_ids = [str(record["run_id"]) for record in linked]
    evidence = {
        "execution_store_issues": sorted(outcome_issues),
        "experiment_store_issues": [
            f"{issue.filename}:{issue.line_number}:{issue.error}"
            for issue in experiments.issues
        ],
        "population_outcome_count": population_count,
        "population_feedback_run_count": len(set(population_experiments)),
        "linked_outcome_count": len(linked),
        "linked_distinct_days": _distinct_days(linked),
        "linked_window_days": _span_days(linked),
        "linked_success_rate": linked_rate,
        "linked_execution_run_ids": linked_run_ids,
        "linked_outcome_fingerprints": [
            execution_outcome_fingerprint(record) for record in linked
        ],
        "linked_refs": sorted(
            linked_refs,
            key=lambda item: (item["feedback_run_id"], item["execution_run_id"]),
        ),
        "unresolved_feedback_run_ids": sorted(set(unresolved_feedback_runs)),
    }
    fingerprint_basis = {
        "task_class": task_class,
        "criteria": criteria,
        "linked_refs": evidence["linked_refs"],
        "unresolved_feedback_run_ids": evidence["unresolved_feedback_run_ids"],
    }
    return {
        "criteria": criteria,
        "evidence": evidence,
        "evidence_fingerprint": _sha256(fingerprint_basis),
    }


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

    real = _task_class_evidence(
        str(candidate["task_class"]),
        comparisons,
        state_root,
    )
    criteria = real["criteria"]
    real_evidence = real["evidence"]
    linked_rate = real_evidence["linked_success_rate"]
    required_rate = criteria["required_success_rate"]

    requirements = [
        {
            "id": "store-integrity",
            "status": (
                "PASS"
                if (
                    not candidate_history.issues
                    and not comparison_history.issues
                    and not real_evidence["experiment_store_issues"]
                    and not real_evidence["execution_store_issues"]
                )
                else "FAIL"
            ),
            "detail": (
                "candidate, comparison, experiment and execution histories parsed without invalid records"
                if (
                    not candidate_history.issues
                    and not comparison_history.issues
                    and not real_evidence["experiment_store_issues"]
                    and not real_evidence["execution_store_issues"]
                )
                else (
                    "invalid records: "
                    f"candidates={len(candidate_history.issues)} "
                    f"comparisons={len(comparison_history.issues)} "
                    f"experiments={len(real_evidence['experiment_store_issues'])} "
                    f"outcomes={len(real_evidence['execution_store_issues'])}"
                )
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
            "id": "task-class-calibration",
            "status": (
                "PASS"
                if (
                    criteria["calibration_outcomes"] >= MIN_CALIBRATION_OUTCOMES
                    and criteria["calibration_distinct_days"] >= 2
                )
                else "FAIL"
            ),
            "detail": (
                f"real_outcomes={criteria['calibration_outcomes']} "
                f"distinct_days={criteria['calibration_distinct_days']}; "
                f"need >= {MIN_CALIBRATION_OUTCOMES} outcomes across >= 2 UTC days"
            ),
            "class": "evidence",
        },
        {
            "id": "real-outcome-links-complete",
            "status": (
                "PASS"
                if not real_evidence["unresolved_feedback_run_ids"]
                else "FAIL"
            ),
            "detail": (
                "every comparison resolves through one experiment to one execution outcome"
                if not real_evidence["unresolved_feedback_run_ids"]
                else "unresolved=" + ",".join(real_evidence["unresolved_feedback_run_ids"])
            ),
            "class": "evidence",
        },
        {
            "id": "derived-sample-size",
            "status": (
                "PASS"
                if real_evidence["linked_outcome_count"] >= criteria["required_linked_outcomes"]
                else "FAIL"
            ),
            "detail": (
                f"linked_real_outcomes={real_evidence['linked_outcome_count']} "
                f"required={criteria['required_linked_outcomes']} "
                f"from population={criteria['calibration_outcomes']}"
            ),
            "class": "evidence",
        },
        {
            "id": "derived-temporal-coverage",
            "status": (
                "PASS"
                if (
                    real_evidence["linked_distinct_days"] >= criteria["required_distinct_days"]
                    and real_evidence["linked_window_days"] >= criteria["required_window_days"]
                )
                else "FAIL"
            ),
            "detail": (
                f"days={real_evidence['linked_distinct_days']}/"
                f"{criteria['required_distinct_days']} "
                f"window_days={real_evidence['linked_window_days']}/"
                f"{criteria['required_window_days']}"
            ),
            "class": "evidence",
        },
        {
            "id": "task-class-success-baseline",
            "status": (
                "PASS"
                if (
                    linked_rate is not None
                    and required_rate is not None
                    and linked_rate >= required_rate
                )
                else "FAIL"
            ),
            "detail": (
                f"linked_success_rate={linked_rate} "
                f"task_class_baseline={required_rate}"
            ),
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
            "real_outcomes": real_evidence,
        },
        "promotion_criteria": criteria,
        "evidence_fingerprint": real["evidence_fingerprint"],
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
