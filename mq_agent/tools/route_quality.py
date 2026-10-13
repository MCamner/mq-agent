"""Read-only execution linkage for complete docs-review quality populations."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


def complete_execution_quality(
    observations: list[Any], source: Path | None,
) -> tuple[list[Any], dict[str, int], Path]:
    """Require one exact execution, retaining invalid candidates to detect ambiguity.

    docs-audit records execution task_class=docs and routing task_class=docs-review.
    This is that producer's association, not a translation of feedback classes.
    An explicit source is self-contained; canonical stores are used only by default.
    """
    from mq_agent.tools.model_routing import (
        EXECUTION_SCHEMA_FILE, EXECUTION_SCHEMA_ID, _read_records, _validator,
        execution_outcome_path,
    )

    path = source if source is not None else execution_outcome_path()
    records, _ = _read_records(path)
    by_id: dict[str, list[dict]] = {}
    for record in records:
        if isinstance(record, dict) and record.get("schema") == EXECUTION_SCHEMA_ID:
            identity = record.get("run_id")
            if isinstance(identity, str):
                by_id.setdefault(identity, []).append(record)
    validator = _validator(EXECUTION_SCHEMA_FILE)
    included = []
    excluded: Counter[str] = Counter()
    for observation in observations:
        reason = None
        identity = observation.get("execution_run_id")
        candidates = by_id.get(identity, []) if isinstance(identity, str) else []
        if observation.get("application") != "applied":
            reason = "not-applied"
        elif observation.get("task_class") != "docs-review":
            reason = "unsupported-task-class"
        elif not identity:
            reason = "missing-execution-run-id"
        elif not candidates:
            reason = "missing-execution"
        elif len(candidates) != 1:
            reason = "ambiguous-execution"
        else:
            execution = candidates[0]
            completeness = execution.get("completeness")
            if list(validator.iter_errors(execution)):
                reason = "invalid-execution"
            elif execution["task_class"] != "docs":
                reason = "execution-task-class-mismatch"
            elif completeness is None:
                reason = "unmeasured-completeness"
            elif completeness["status"] != "complete":
                reason = "partial-completeness"
            elif execution["result"] != "PASS" or execution["exit_status"] != "ok":
                reason = "unsuccessful-execution"
            else:
                steps = completeness["steps"]
                if (
                    not steps
                    or any(step["status"] != "complete" for step in steps)
                    or len({step["step"] for step in steps}) != len(steps)
                    or any(
                        step.get("source_item_count") != step.get("executed_call_count")
                        for step in steps
                    )
                ):
                    reason = "inconsistent-completeness"
        if reason:
            excluded[reason] += 1
        else:
            included.append(observation)
    return included, dict(sorted(excluded.items())), path


def current_docs_quality(
    observations: list[Any], source: Path | None,
) -> tuple[list[Any], dict[str, int], Path, str]:
    """Current complete-audit quality; all-history safety stays with the caller."""
    from mq_agent.tools.analysis_cohort import select_cohort

    cohort = select_cohort(observations, task_class="docs-review")
    quality, exclusions, path = complete_execution_quality(cohort.included, source)
    for reason, count in (
        ("earlier-era", cohort.excluded_earlier_era),
        ("not-applied", cohort.excluded_not_applied),
        ("other-task-class", cohort.excluded_other_task_class),
        ("undated", cohort.excluded_undated),
    ):
        if count:
            exclusions[reason] = count
    return quality, dict(sorted(exclusions.items())), path, cohort.era.name
