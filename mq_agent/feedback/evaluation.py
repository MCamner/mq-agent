"""F3 deterministic feedback comparison and verdict evaluation."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import validate_comparison
from .store import (
    append_comparison,
    read_comparison_history,
    read_experiment_history,
)

DIRECTIONS: dict[str, str] = {
    "context_lines": "lower_is_better",
    "context_bytes": "lower_is_better",
    "context_tokens": "lower_is_better",
    "retrieval_latency_ms": "lower_is_better",
    "source_count": "neutral",
    "deduplicated_source_count": "neutral",
    "provenance_coverage": "higher_is_better",
    "stale_source_rate": "lower_is_better",
    "external_api_calls": "lower_is_better",
    "cost": "lower_is_better",
    "relevance_precision": "higher_is_better",
    "relevance_recall": "higher_is_better",
    "negative_query_correctness": "higher_is_better",
    "contradicted_source_rate": "lower_is_better",
}
UNITS: dict[str, str] = {
    "context_lines": "lines",
    "context_bytes": "bytes",
    "context_tokens": "tokens",
    "retrieval_latency_ms": "ms",
    "source_count": "sources",
    "deduplicated_source_count": "sources",
    "provenance_coverage": "ratio",
    "stale_source_rate": "ratio",
    "external_api_calls": "calls",
    "cost": "cost-units",
    "relevance_precision": "ratio",
    "relevance_recall": "ratio",
    "negative_query_correctness": "ratio",
    "contradicted_source_rate": "ratio",
}
QUALITY_METRICS = frozenset(
    {
        "relevance_precision",
        "relevance_recall",
        "negative_query_correctness",
        "provenance_coverage",
        "stale_source_rate",
        "contradicted_source_rate",
    }
)
OPERATIONAL_METRICS = frozenset(
    {
        "context_lines",
        "context_bytes",
        "context_tokens",
        "retrieval_latency_ms",
        "external_api_calls",
        "cost",
    }
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _material(name: str, active: float, shadow: float) -> bool:
    delta = shadow - active
    if delta == 0:
        return False
    if name == "retrieval_latency_ms":
        baseline = max(abs(active), 1.0)
        return abs(delta) >= 5.0 and abs(delta) / baseline >= 0.10
    if name in {"context_lines", "context_bytes", "context_tokens"}:
        baseline = max(abs(active), 1.0)
        return abs(delta) / baseline >= 0.05
    if name.endswith("_rate") or name in {
        "provenance_coverage",
        "relevance_precision",
        "relevance_recall",
        "negative_query_correctness",
    }:
        return abs(delta) >= 0.01
    return True


def metric_pair(
    name: str,
    active: float | int | None,
    shadow: float | int | None,
) -> dict[str, Any]:
    direction = DIRECTIONS[name]
    unit = UNITS[name]
    if active is None or shadow is None:
        return {
            "status": "unavailable",
            "direction": direction,
            "unit": unit,
            "active": None,
            "shadow": None,
            "delta": None,
            "material": False,
        }
    active_value = float(active)
    shadow_value = float(shadow)
    return {
        "status": "comparable",
        "direction": direction,
        "unit": unit,
        "active": active_value,
        "shadow": shadow_value,
        "delta": round(shadow_value - active_value, 6),
        "material": (
            False
            if direction == "neutral"
            else _material(name, active_value, shadow_value)
        ),
    }


def _preference(metric: dict[str, Any]) -> int:
    """Return +1 shadow better, -1 shadow worse, 0 no material preference."""
    if metric["status"] != "comparable" or not metric["material"]:
        return 0
    delta = float(metric["delta"])
    if metric["direction"] == "higher_is_better":
        return 1 if delta > 0 else -1
    if metric["direction"] == "lower_is_better":
        return 1 if delta < 0 else -1
    return 0


def _base_metrics(
    active_metrics: dict[str, float | int | None],
    shadow_metrics: dict[str, float | int | None],
) -> dict[str, dict[str, Any]]:
    names = list(DIRECTIONS)
    return {
        name: metric_pair(name, active_metrics.get(name), shadow_metrics.get(name))
        for name in names
        if name in active_metrics or name in shadow_metrics
    }


def build_operational_comparison(
    experiment: dict[str, Any],
    *,
    active_metrics: dict[str, float | int | None],
    shadow_metrics: dict[str, float | int | None],
    active_sources: list[str],
    shadow_sources: list[str],
) -> dict[str, Any]:
    """Build the F2 comparison. No relevance labels means no better verdict."""
    evidence_refs = [
        f"experiment:{experiment['feedback_run_id']}",
        *(f"active-source:{item}" for item in active_sources),
        *(f"shadow-source:{item}" for item in shadow_sources),
    ]
    record = {
        "schema": "mq.feedback-comparison.v1",
        "comparison_id": f"cmp-{uuid.uuid4()}",
        "feedback_run_id": experiment["feedback_run_id"],
        "task_class": experiment["task_class"],
        "repository": experiment["repository"],
        "active_strategy": experiment["active_strategy"],
        "shadow_strategy": experiment["shadow_strategy"],
        "snapshot": experiment["snapshot"],
        "valid": True,
        "blocked_reasons": [],
        "verdict": "INSUFFICIENT_EVIDENCE",
        "metrics": _base_metrics(active_metrics, shadow_metrics),
        "sources": {
            "active": list(dict.fromkeys(active_sources)),
            "shadow": list(dict.fromkeys(shadow_sources)),
        },
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "relevance_fixture": None,
        "advisory_evaluator": None,
        "recorded_at": _now(),
    }
    validate_comparison(record)
    return record


def load_relevance_fixture(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        fixture = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid relevance fixture JSON") from exc
    if not isinstance(fixture, dict):
        raise ValueError("relevance fixture must be an object")
    fixture_id = fixture.get("id")
    expected = fixture.get("expected_sources")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ValueError("relevance fixture requires id")
    if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
        raise ValueError("relevance fixture expected_sources must be strings")
    for field in ("stale_sources", "contradicted_sources"):
        value = fixture.get(field, [])
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"relevance fixture {field} must be strings")
    negative = fixture.get("negative", False)
    if not isinstance(negative, bool):
        raise ValueError("relevance fixture negative must be boolean")
    if negative and expected:
        raise ValueError("negative relevance fixture cannot declare expected_sources")
    return fixture, digest


def _relevance_values(
    sources: list[str],
    fixture: dict[str, Any],
) -> dict[str, float | None]:
    retrieved = set(sources)
    expected = set(fixture["expected_sources"])
    stale = set(fixture.get("stale_sources", []))
    contradicted = set(fixture.get("contradicted_sources", []))
    negative = bool(fixture.get("negative", False))

    if negative:
        precision = None
        recall = None
        negative_correctness = 1.0 if not retrieved else 0.0
    else:
        hits = len(retrieved & expected)
        precision = hits / len(retrieved) if retrieved else (1.0 if not expected else 0.0)
        recall = hits / len(expected) if expected else 1.0
        negative_correctness = None

    stale_rate = len(retrieved & stale) / len(retrieved) if retrieved else 0.0
    contradicted_rate = (
        len(retrieved & contradicted) / len(retrieved) if retrieved else 0.0
    )
    return {
        "relevance_precision": precision,
        "relevance_recall": recall,
        "negative_query_correctness": negative_correctness,
        "stale_source_rate": stale_rate,
        "contradicted_source_rate": contradicted_rate,
    }


def _verdict(
    metrics: dict[str, dict[str, Any]],
    *,
    valid: bool,
    relevance_fixture_present: bool,
) -> str:
    if not valid:
        return "BLOCKED"
    comparable = [m for m in metrics.values() if m["status"] == "comparable"]
    if not comparable:
        return "NO_DATA"
    if not relevance_fixture_present:
        return "INSUFFICIENT_EVIDENCE"

    quality_preferences = [
        _preference(metrics[name])
        for name in QUALITY_METRICS
        if name in metrics and metrics[name]["status"] == "comparable"
    ]
    quality_preferences = [value for value in quality_preferences if value]
    better = any(value > 0 for value in quality_preferences)
    worse = any(value < 0 for value in quality_preferences)

    if better and worse:
        return "CONFLICTING_EVIDENCE"
    if worse:
        return "CANDIDATE_WORSE"
    if better:
        op_worse = any(
            _preference(metrics[name]) < 0
            for name in OPERATIONAL_METRICS
            if name in metrics
        )
        return "CONFLICTING_EVIDENCE" if op_worse else "CANDIDATE_BETTER"

    material = any(metric["material"] for metric in comparable)
    return "INSUFFICIENT_EVIDENCE" if material else "NO_MATERIAL_DIFFERENCE"


def _load_advisory_evaluator(
    path: Path | None,
    *,
    observed_refs: set[str],
) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Atlas evaluation JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Atlas evaluation must be an object")
    if data.get("schema") != "atlas.feedback-evaluation.v1":
        raise ValueError("Atlas evaluation schema must be atlas.feedback-evaluation.v1")
    refs = data.get("evidence_refs")
    if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
        raise ValueError("Atlas evaluation evidence_refs must be strings")
    missing = sorted(set(refs) - observed_refs)
    if missing:
        raise ValueError("Atlas evaluation references unobserved evidence")
    assessment = data.get("assessment")
    if not isinstance(assessment, str) or not assessment.strip():
        raise ValueError("Atlas evaluation requires assessment")
    return {
        "source": "atlas-core",
        "assessment": assessment[:160],
        "evidence_refs": list(dict.fromkeys(refs)),
    }


def _experiment_for_run(feedback_run_id: str, state_root: Path | None) -> dict[str, Any]:
    matches = [
        item.record
        for item in read_experiment_history(state_root).records
        if item.record["feedback_run_id"] == feedback_run_id
    ]
    if len(matches) != 1:
        raise ValueError("feedback run must resolve to exactly one experiment")
    return matches[0]


def _operational_comparison_for_run(
    feedback_run_id: str,
    state_root: Path | None,
) -> dict[str, Any]:
    matches = [
        item.record
        for item in read_comparison_history(state_root).records
        if item.record["feedback_run_id"] == feedback_run_id
        and item.record.get("relevance_fixture") is None
    ]
    if not matches:
        raise ValueError("feedback run has no F2 operational comparison")
    return matches[-1]


def compare_feedback_run(
    feedback_run_id: str,
    *,
    fixture_path: Path,
    atlas_evaluation: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Derive and append one F3 comparison from stored F2 evidence."""
    experiment = _experiment_for_run(feedback_run_id, state_root)
    base = _operational_comparison_for_run(feedback_run_id, state_root)
    fixture, fixture_hash = load_relevance_fixture(fixture_path)

    blocked_reasons: list[str] = []
    if experiment["state"] != "completed":
        blocked_reasons.append("experiment-not-completed")
    if experiment["snapshot"] != base["snapshot"]:
        blocked_reasons.append("snapshot-mismatch")
    if experiment["task_class"] != base["task_class"]:
        blocked_reasons.append("task-class-mismatch")
    if experiment["repository"] != base["repository"]:
        blocked_reasons.append("repository-mismatch")
    if experiment["active_strategy"] != base["active_strategy"]:
        blocked_reasons.append("active-strategy-mismatch")
    if experiment["shadow_strategy"] != base["shadow_strategy"]:
        blocked_reasons.append("shadow-strategy-mismatch")
    expected_experiment_ref = f"experiment:{feedback_run_id}"
    if expected_experiment_ref not in set(base["evidence_refs"]):
        blocked_reasons.append("missing-experiment-provenance")
    valid = not blocked_reasons

    active_values = _relevance_values(base["sources"]["active"], fixture)
    shadow_values = _relevance_values(base["sources"]["shadow"], fixture)
    metrics = dict(base["metrics"])
    for name in (
        "relevance_precision",
        "relevance_recall",
        "negative_query_correctness",
        "stale_source_rate",
        "contradicted_source_rate",
    ):
        metrics[name] = metric_pair(
            name,
            active_values.get(name),
            shadow_values.get(name),
        )

    fixture_ref = f"fixture:sha256:{fixture_hash}"
    observed_refs = set(base["evidence_refs"]) | {fixture_ref}
    advisory = _load_advisory_evaluator(
        atlas_evaluation,
        observed_refs=observed_refs,
    )
    evidence_refs = list(base["evidence_refs"]) + [
        f"comparison:{base['comparison_id']}",
        fixture_ref,
    ]
    if advisory is not None:
        evidence_refs.extend(f"atlas-evidence:{ref}" for ref in advisory["evidence_refs"])

    record = {
        "schema": "mq.feedback-comparison.v1",
        "comparison_id": f"cmp-{uuid.uuid4()}",
        "feedback_run_id": feedback_run_id,
        "task_class": base["task_class"],
        "repository": base["repository"],
        "active_strategy": base["active_strategy"],
        "shadow_strategy": base["shadow_strategy"],
        "snapshot": base["snapshot"],
        "valid": valid,
        "blocked_reasons": blocked_reasons,
        "verdict": _verdict(
            metrics,
            valid=valid,
            relevance_fixture_present=True,
        ),
        "metrics": metrics,
        "sources": base["sources"],
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "relevance_fixture": {
            "id": fixture["id"],
            "sha256": fixture_hash,
            "negative": bool(fixture.get("negative", False)),
            "expected_sources": len(fixture["expected_sources"]),
        },
        "advisory_evaluator": advisory,
        "recorded_at": _now(),
    }
    validate_comparison(record)
    append_comparison(record, state_root)
    return record


def latest_comparison(
    feedback_run_id: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    matches = [
        item.record
        for item in read_comparison_history(state_root).records
        if item.record["feedback_run_id"] == feedback_run_id
    ]
    if not matches:
        raise ValueError(f"feedback comparison not found: {feedback_run_id}")
    return matches[-1]
