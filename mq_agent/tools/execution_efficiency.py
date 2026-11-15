"""Descriptive resource/quality coverage; never grants policy or routing rights."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mq_agent.tools.execution_outcome import (
    KNOWN_TASK_CLASSES, MAX_ROTATED_FILES, execution_is_complete_success, outcome_path,
)
from mq_agent.tools.model_routing import _outcome_path, _read_records, _split_contracts

SCHEMA = "mq.execution-efficiency.v1"
_LOCAL_SCOPE = "metrics-scope:mq-agent-local"


def _read(paths: list[Path], contract: str, issues: list[str]) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    ignored = 0
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            issues.append(f"{contract}: unsafe source entry")
            continue
        raw, _ = _read_records(path)
        routes, executions, invalid = _split_contracts(raw)
        records.extend(executions if contract == "execution" else routes)
        ignored += len(routes if contract == "execution" else executions)
        if invalid:
            issues.append(f"{contract}: {invalid} invalid record(s)")
    return records, ignored


def _stamp(record: dict[str, Any]) -> datetime:
    value = datetime.fromisoformat(record["recorded_at"])
    if value.tzinfo is None:
        raise ValueError("timezone missing")
    return value.astimezone(UTC)


def _window(records: list[dict[str, Any]], since: str | None, now: datetime,
            issues: list[str], contract: str) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=int(since[:-1])) if since else None
    kept = []
    for record in records:
        try:
            stamp = _stamp(record)
        except (ValueError, TypeError, OverflowError):
            issues.append(f"{contract}: invalid timestamp")
            continue
        if stamp > now:
            issues.append(f"{contract}: future timestamp")
            continue
        cost = record.get("cost")
        if isinstance(cost, float) and not math.isfinite(cost):
            issues.append(f"{contract}: non-finite cost")
            continue
        if cutoff is None or stamp >= cutoff:
            kept.append(record)
    return kept


def _deduplicate(records: list[dict[str, Any]], issues: list[str],
                 contract: str = "execution") -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unidentified = []
    for record in records:
        if "run_id" not in record:
            unidentified.append(record)
        else:
            by_id[record["run_id"]].append(record)
    unique = list(unidentified)
    identical = conflicting = 0
    for values in by_id.values():
        variants = {json.dumps(value, sort_keys=True) for value in values}
        if len(variants) > 1:
            conflicting += 1
        else:
            unique.append(values[0])
            identical += len(values)-1
    if identical or conflicting:
        issues.append(f"{contract}: duplicate run ids; conflicting records excluded")
    return unique, {"identical": identical, "conflicting_ids": conflicting,
                    "missing_ids": len(unidentified)}


def _metric(values: list[int | float], population: int) -> dict[str, Any]:
    ordered = sorted(values)
    count = len(ordered)
    total = sum(ordered) if count else None
    if isinstance(total, float) and not math.isfinite(total):
        total = None
    middle = count // 2
    median = (ordered[middle] if count % 2 else
              ordered[middle-1] / 2 + ordered[middle] / 2) if count else None
    return {
        "measured": count, "missing": population-count,
        "coverage": round(count/population, 3) if population else None,
        "measured_total": total,
        "total": total if count == population and population else None,
        "median": median, "p90": ordered[max(0, math.ceil(count*0.9)-1)] if count else None,
    }


def _scope(record: dict[str, Any]) -> str:
    return "mq-agent-local" if any(e["kind"] == _LOCAL_SCOPE for e in record.get("events", [])) else "unspecified"


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(records)
    measured = sum("completeness" in r for r in records)
    complete = sum(execution_is_complete_success(r) for r in records)
    resources = {key: _metric([r[key] for r in records if key in r], count)
                 for key in ("latency_ms", "tool_calls", "retries", "fallbacks", "cost")}
    for direction in ("input", "output"):
        resources[f"tokens_{direction}"] = _metric(
            [r["tokens"][direction] for r in records if direction in r.get("tokens", {})], count,
        )
    scopes = sorted({_scope(r) for r in records})
    if len(scopes) > 1:
        for key in ("tool_calls", "tokens_input", "tokens_output"):
            resources[key].update(measured_total=None, total=None, median=None, p90=None,
                                  aggregation="unavailable-mixed-scopes")
    stamps = sorted(_stamp(r) for r in records)
    return {
        "outcomes": count,
        "oldest_recorded_at": stamps[0].isoformat() if stamps else None,
        "newest_recorded_at": stamps[-1].isoformat() if stamps else None,
        "quality": {
            "reported_passes": sum(r["result"] == "PASS" for r in records),
            "reported_failures": sum(r["result"] == "FAIL" for r in records),
            "reported_skipped": sum(r["result"] == "SKIPPED" for r in records),
            "completeness_measured": measured, "completeness_missing": count-measured,
            "complete_successes": complete,
            "complete_success_rate": round(complete/measured, 3) if measured else None,
            "complete_success_rate_denominator": measured,
        },
        "resources": resources, "metric_scopes": scopes,
        "rework": {"status": "unavailable", "value": None,
                   "reason": "No measured rework signal; retries are not rework."},
    }


def _routing(records: list[dict[str, Any]], selected_ids: set[str]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["task_class"], record["selected_route"], record.get("application", "unreported"))].append(record)
    rows = []
    for (task, route, application), values in sorted(groups.items()):
        rows.append({"task_class": task, "route": route, "application": application,
                     "observations": len(values), "escalated": sum(r["escalated"] for r in values)})
    count = len(records)
    escalated = sum(r["escalated"] for r in records)
    linked = sum(r.get("execution_run_id") in selected_ids for r in records)
    return {
        "population": "Independent routing observations; execution task-class filter does not filter routing.",
        "observations": count, "escalated": escalated,
        "escalation_rate": round(escalated/count, 3) if count else None,
        "escalation_rate_denominator": count,
        "linked_selected_executions": linked,
        "unlinked_or_outside_execution_filter": count-linked, "groups": rows,
    }


def execution_efficiency(
    source: Path | None = None, *, routing_source: Path | None = None,
    since: str | None = None, task_class: str | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """Read existing stores, keeping operational quality and resources separate.

    Missing measurements never become zero. Reported PASS is not model-answer
    quality, and historical records without completeness do not become complete.
    """
    if since is not None and since not in {"7d", "30d", "90d"}:
        raise ValueError("since must be 7d, 30d or 90d")
    if task_class is not None and task_class not in KNOWN_TASK_CLASSES | {"unclassified"}:
        raise ValueError("Unknown execution task class; routing classes are separate")
    checked = now or datetime.now(UTC)
    if checked.tzinfo is None:
        raise ValueError("Report time requires a timezone")
    path, route_path = outcome_path(source), _outcome_path(routing_source)
    paths = [*(Path(f"{path}.{i}") for i in range(MAX_ROTATED_FILES, 0, -1)), path]
    issues: list[str] = []
    records, other_execution = _read(paths, "execution", issues)
    routes, other_routing = _read([route_path], "routing", issues)
    records, duplicates = _deduplicate(records, issues)
    routes, route_duplicates = _deduplicate(routes, issues, "routing")
    records = _window(records, since, checked, issues, "execution")
    routes = _window(routes, since, checked, issues, "routing")
    if task_class is not None:
        records = [r for r in records if r["task_class"] == task_class]
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        identity = record.get("runtime_fingerprint", {})
        key = (record["task_class"], record["runtime"], record.get("model"),
               identity.get("version"), identity.get("commit"), _scope(record))
        grouped[key].append(record)
    cohorts = []
    for key, values in sorted(grouped.items(), key=lambda item: str(item[0])):
        task, runtime, model, version, commit, scope = key
        cohorts.append({"task_class": task, "runtime": runtime, "model": model,
                        "producer_version": version, "producer_commit": commit,
                        "metric_scope": scope, **_summary(values)})
    return {
        "schema": SCHEMA, "status": "DEGRADED" if issues else "OK" if records or routes else "EMPTY",
        "checked_at": checked.isoformat(), "source": str(path), "routing_source": str(route_path),
        "window": since, "execution_task_class": task_class,
        "issues": issues, "duplicates": duplicates,
        "ignored_other_contracts": {"execution_source": other_execution, "routing_source": other_routing},
        "execution": {**_summary(records), "cohorts": cohorts},
        "routing": {**_routing(routes, {r["run_id"] for r in records}),
                    "duplicates": route_duplicates},
        "recommendation": None,
        "limitations": [
            "Complete successful executions measure runtime coverage, not model-answer correctness.",
            "Local metric scope excludes backend/internal tool work and external agents.",
            "Cost is producer-reported in unspecified contract units; no price estimates or currency conversion.",
            "Different cohorts/scopes are descriptive populations, not a controlled comparison.",
        ],
    }
