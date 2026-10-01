"""Read-only operator views over retained feedback experiment evidence."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .store import (
    FeedbackHistoryResult,
    StoredFeedbackRecord,
    feedback_root,
    read_candidate_history,
    read_comparison_history,
    read_experiment_history,
)

REPORT_SCHEMA_ID = "mq.feedback-report.v1"
REPORT_SCHEMA_FILE = "feedback_report.schema.json"
_MAX_RECENT = 200
_MAX_SINCE_DAYS = 3650
_SINCE_RE = re.compile(r"^([1-9][0-9]{0,3})d$")

_METRIC_NAMES = (
    "context_lines",
    "context_bytes",
    "context_tokens",
    "retrieval_latency_ms",
    "source_count",
    "deduplicated_source_count",
    "provenance_coverage",
    "stale_source_rate",
    "external_api_calls",
    "cost",
)


def _report_schema_path() -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / REPORT_SCHEMA_FILE
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / REPORT_SCHEMA_FILE


def report_validator() -> Draft202012Validator:
    schema = json.loads(_report_schema_path().read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_report(report: dict[str, Any]) -> None:
    report_validator().validate(report)


def _entry(item: StoredFeedbackRecord) -> dict[str, Any]:
    return {
        "record": item.record,
        "store_ref": {
            "file": item.source,
            "line": item.line,
        },
    }


def _parse_time(value: object) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _since_cutoff(since: str | None, now: datetime | None = None) -> datetime | None:
    if since is None:
        return None
    match = _SINCE_RE.fullmatch(since)
    if match is None:
        raise ValueError("since must be a positive day window such as 7d or 30d")
    days = int(match.group(1))
    if days > _MAX_SINCE_DAYS:
        raise ValueError(f"since must be <= {_MAX_SINCE_DAYS}d")
    return (now or datetime.now(UTC)) - timedelta(days=days)


def _analysis(history: FeedbackHistoryResult) -> dict[str, Any]:
    ids = Counter(str(item.record["feedback_run_id"]) for item in history.records)
    duplicate_ids = sorted(run_id for run_id, count in ids.items() if count > 1)

    timestamp_issues: list[dict[str, Any]] = []
    usable: list[StoredFeedbackRecord] = []
    for item in history.records:
        try:
            _parse_time(item.record["recorded_at"])
        except (TypeError, ValueError) as exc:
            timestamp_issues.append(
                {
                    "file": item.source,
                    "line": item.line,
                    "reason": f"invalid recorded_at: {exc}",
                }
            )
            continue
        usable.append(item)

    reasons: list[str] = []
    if history.issues:
        reasons.append(f"{len(history.issues)} corrupt or invalid retained record(s)")
    if timestamp_issues:
        reasons.append(f"{len(timestamp_issues)} record(s) have unusable timestamps")
    if duplicate_ids:
        reasons.append(
            f"{len(duplicate_ids)} duplicate feedback_run_id value(s) violate immutability"
        )

    if reasons:
        health = "DEGRADED"
    elif usable:
        health = "HEALTHY"
    else:
        health = "EMPTY"

    return {
        "health": health,
        "usable": usable,
        "duplicate_ids": duplicate_ids,
        "timestamp_issues": timestamp_issues,
        "degraded_reasons": reasons,
        "invalid_records": len(history.issues) + len(timestamp_issues),
    }


def feedback_status(root: Path | None = None) -> dict[str, Any]:
    """Summarize retained feedback storage without writing to it."""
    history = read_experiment_history(root)
    comparisons = read_comparison_history(root)
    candidates = read_candidate_history(root)
    analysis = _analysis(history)
    records = analysis["usable"]
    task_classes = Counter(str(item.record["task_class"]) for item in records)
    states = Counter(str(item.record["state"]) for item in records)
    sources: list[str] = []
    for item in records:
        if item.source not in sources:
            sources.append(item.source)
    for issue in history.issues:
        if issue.source not in sources:
            sources.append(issue.source)

    newest = str(records[-1].record["recorded_at"]) if records else None
    return {
        "view": "feedback-status.v1",
        "source_root": str(feedback_root(root)),
        "health": (
            "DEGRADED"
            if comparisons.issues or candidates.issues
            else analysis["health"]
        ),
        "valid_records": len(records),
        "invalid_records": (
            analysis["invalid_records"] + len(comparisons.issues) + len(candidates.issues)
        ),
        "comparison_records": len(comparisons.records),
        "candidate_events": len(candidates.records),
        "newest_recorded_at": newest,
        "task_classes": dict(sorted(task_classes.items())),
        "states": dict(sorted(states.items())),
        "generations": sources,
        "duplicate_feedback_run_ids": analysis["duplicate_ids"],
        "degraded_reasons": [
            *analysis["degraded_reasons"],
            *(
                [f"{len(comparisons.issues)} invalid comparison record(s)"]
                if comparisons.issues else []
            ),
            *(
                [f"{len(candidates.issues)} invalid candidate record(s)"]
                if candidates.issues else []
            ),
        ],
    }


def feedback_recent(
    root: Path | None = None,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded newest-first view of retained immutable experiments."""
    if limit < 1 or limit > _MAX_RECENT:
        raise ValueError(f"limit must be between 1 and {_MAX_RECENT}")

    history = read_experiment_history(root)
    analysis = _analysis(history)
    records = list(reversed(analysis["usable"]))
    selected = records[:limit]
    return {
        "view": "feedback-recent.v1",
        "source_root": str(feedback_root(root)),
        "health": analysis["health"],
        "matched": len(records),
        "returned": len(selected),
        "invalid_records": analysis["invalid_records"],
        "degraded_reasons": analysis["degraded_reasons"],
        "entries": [_entry(item) for item in selected],
    }


def feedback_inspect(
    feedback_run_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Explain one experiment plus its immutable comparison/candidate chain."""
    if not feedback_run_id.strip():
        raise ValueError("feedback_run_id must not be empty")

    history = read_experiment_history(root)
    analysis = _analysis(history)
    matches = [
        item
        for item in analysis["usable"]
        if str(item.record["feedback_run_id"]) == feedback_run_id
    ]
    if not matches:
        raise ValueError(f"feedback run not found: {feedback_run_id}")

    duplicate = len(matches) > 1
    reasons = list(analysis["degraded_reasons"])
    if duplicate and not any("duplicate feedback_run_id" in reason for reason in reasons):
        reasons.append("feedback_run_id occurs more than once")

    comparison_history = read_comparison_history(root)
    comparisons = [
        _entry(item)
        for item in comparison_history.records
        if item.record["feedback_run_id"] == feedback_run_id
    ]
    comparison_ids = {
        item["record"]["comparison_id"]
        for item in comparisons
    }

    candidate_history = read_candidate_history(root)
    effective: dict[str, dict[str, Any]] = {}
    for item in candidate_history.records:
        if comparison_ids.intersection(item.record["comparison_ids"]):
            effective[item.record["candidate_id"]] = _entry(item)
    candidate_entries = list(effective.values())
    candidate_entries.sort(
        key=lambda item: str(item["record"]["recorded_at"]),
        reverse=True,
    )

    return {
        "view": "feedback-inspect.v1",
        "source_root": str(feedback_root(root)),
        "feedback_run_id": feedback_run_id,
        "health": (
            "DEGRADED"
            if duplicate
            or analysis["health"] == "DEGRADED"
            or comparison_history.issues
            or candidate_history.issues
            else "HEALTHY"
        ),
        "experiment": _entry(matches[0]) if len(matches) == 1 else None,
        "duplicate_records": [_entry(item) for item in matches] if duplicate else [],
        "comparison": (
            comparisons[-1]
            if comparisons
            else {
                "status": "unavailable",
                "reason": "no comparison is recorded for this experiment",
            }
        ),
        "comparison_history": comparisons,
        "candidate": (
            candidate_entries[0]
            if candidate_entries
            else {
                "status": "unavailable",
                "reason": "no improvement candidate is linked to this experiment",
            }
        ),
        "degraded_reasons": [
            *reasons,
            *(
                [f"{len(comparison_history.issues)} invalid comparison record(s)"]
                if comparison_history.issues else []
            ),
            *(
                [f"{len(candidate_history.issues)} invalid candidate record(s)"]
                if candidate_history.issues else []
            ),
        ],
    }

def _unavailable_metrics() -> dict[str, dict[str, object]]:
    return {
        name: {"status": "unavailable", "value": None}
        for name in _METRIC_NAMES
    }


def feedback_report(
    root: Path | None = None,
    *,
    task_class: str | None = None,
    since: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate retained F0/F1 evidence without deriving a winner."""
    cutoff = _since_cutoff(since, now)
    history = read_experiment_history(root)
    analysis = _analysis(history)
    all_records: list[StoredFeedbackRecord] = analysis["usable"]
    comparison_history = read_comparison_history(root)

    matched: list[StoredFeedbackRecord] = []
    for item in all_records:
        if task_class is not None and item.record["task_class"] != task_class:
            continue
        if cutoff is not None and _parse_time(item.record["recorded_at"]) < cutoff:
            continue
        matched.append(item)

    task_counts = Counter(str(item.record["task_class"]) for item in matched)
    state_counts = Counter(str(item.record["state"]) for item in matched)
    repositories = sorted({str(item.record["repository"]) for item in matched})
    active = sorted({str(item.record["active_strategy"]) for item in matched})
    shadow = sorted({str(item.record["shadow_strategy"]) for item in matched})
    backends = sorted(
        {
            str(backend)
            for item in matched
            for backend in item.record.get("network_backends", [])
        }
    )

    matched_run_ids = {
        str(item.record["feedback_run_id"])
        for item in matched
    }
    matched_comparisons = [
        item.record
        for item in comparison_history.records
        if item.record["feedback_run_id"] in matched_run_ids
    ]
    latest_comparison = matched_comparisons[-1] if matched_comparisons else None
    metric_surface = _unavailable_metrics()
    if latest_comparison is not None:
        for name in _METRIC_NAMES:
            metric = latest_comparison["metrics"].get(name)
            if isinstance(metric, dict) and metric.get("status") == "comparable":
                metric_surface[name] = {
                    "status": "measured",
                    "value": metric.get("delta"),
                }

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA_ID,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_root": str(feedback_root(root)),
        "health": analysis["health"],
        "filter": {
            "task_class": task_class,
            "since": since,
        },
        "total_records": len(all_records),
        "matched_records": len(matched),
        "invalid_records": analysis["invalid_records"] + len(comparison_history.issues),
        "newest_recorded_at": (
            str(matched[-1].record["recorded_at"]) if matched else None
        ),
        "by_task_class": dict(sorted(task_counts.items())),
        "by_state": dict(sorted(state_counts.items())),
        "repositories": repositories,
        "active_strategies": active,
        "shadow_strategies": shadow,
        "network_backends": backends,
        "metrics": metric_surface,
        "comparison": {
            "status": "available" if latest_comparison is not None else "unavailable",
            "records": len(matched_comparisons) if latest_comparison is not None else None,
            "reason": (
                str(latest_comparison["verdict"])
                if latest_comparison is not None
                else "no comparison evidence matches the report filter"
            ),
        },
        "degraded_reasons": [
            *analysis["degraded_reasons"],
            *(
                [f"{len(comparison_history.issues)} invalid comparison record(s)"]
                if comparison_history.issues else []
            ),
        ],
    }
    validate_report(report)
    return report
