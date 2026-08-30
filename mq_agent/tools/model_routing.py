"""Deterministic model routing and advisory Ollama shadow evaluation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import uuid
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from statistics import median
from typing import Any, cast

from jsonschema import Draft202012Validator

from mq_agent.tools.execution_outcome import SCHEMA_FILE as EXECUTION_SCHEMA_FILE
from mq_agent.tools.execution_outcome import SCHEMA_ID as EXECUTION_SCHEMA_ID
from mq_agent.tools.execution_outcome import outcome_path as execution_outcome_path
from mq_agent.tools.model_runtime import _ollama_generate, current_model

LOCAL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("diff-summary", ("diff", "change summary", "summarize changes")),
    ("docs-review", ("documentation", "docs", "readme")),
    ("repo-health", ("repo health", "repository health", "doctor", "status")),
    ("test-area-suggestions", ("test area", "tests", "testing")),
    ("review-finding-classification", ("review finding", "findings", "classify review")),
    ("context-pack-summary", ("context pack", "context-pack", "summarize context")),
)

CLOUD_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("security-review", "critical", ("security", "credential", "secret", "vulnerability")),
    ("destructive-operation", "critical", ("destructive", "delete", "remove data", "force push")),
    ("release-decision", "high", ("release decision", "approve release", "publish release")),
    ("schema-migration", "high", ("schema migration", "contract migration", "migrate schema")),
    ("architecture", "high", ("architecture", "cross-repo", "cross repository")),
)

_CANDIDATE_KEYS = {"task_class", "summary", "evidence", "suggestions"}
_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(_CANDIDATE_KEYS),
    "properties": {
        "task_class": {"type": "string"},
        "summary": {"type": "string", "minLength": 1, "maxLength": 600},
        # Ollama enforces this schema as a decoding grammar, so maxItems is a hard
        # bound on generation length: an unbounded evidence array made one 10 KB diff
        # generate ~2800 tokens in 100s+, and identical input varied 473 to 3143
        # tokens. Bounding the count and each quote limits generation. Truncating a
        # verbatim quote to 200 characters preserves a grounded substring and stays
        # well above the 12-character minimum enforced below.
        "evidence": {
            "type": "array",
            "items": {"type": "string", "maxLength": 200},
            "maxItems": 5,
        },
        "suggestions": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
}


def _outcome_path(destination: Path | None = None) -> Path:
    return destination or Path(
        os.environ.get("MQ_AGENT_ROUTE_OUTCOMES", Path.home() / ".mq-agent/route-outcomes.jsonl")
    ).expanduser()


def _schema_path(name: str) -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / name


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads(_schema_path(name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _decision_id(task: str, authoritative_agent: str) -> str:
    digest = hashlib.sha256(f"{authoritative_agent}\0{task.strip()}".encode()).hexdigest()[:16]
    return f"route-{digest}"


def _matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def inspect_route(
    task: str,
    *,
    authoritative_agent: str = "codex",
    local_model: str | None = None,
) -> dict[str, Any]:
    """Classify a task deterministically without model calls or writes."""
    if authoritative_agent not in {"codex", "claude"}:
        raise ValueError("authoritative_agent must be codex or claude")
    normalized = " ".join(task.lower().split())
    if not normalized:
        raise ValueError("task must not be empty")

    task_class = "unverified-change"
    risk = "medium"
    route = "cloud-required"
    reasons = ["no-deterministic-verification"]
    model: str | None = None

    for candidate_class, candidate_risk, terms in CLOUD_RULES:
        if _matches(normalized, terms):
            task_class = candidate_class
            risk = candidate_risk
            reason = {
                "security-review": "security-critical",
                "destructive-operation": "destructive",
                "release-decision": "release-authority-required",
                "schema-migration": "schema-migration",
                "architecture": "architecture-risk",
            }[task_class]
            reasons = [reason]
            break
    else:
        for candidate_class, terms in LOCAL_RULES:
            if _matches(normalized, terms):
                task_class = candidate_class
                risk = "low"
                route = "local-shadow"
                reasons = ["read-only", "deterministic-verification-available"]
                model = local_model or str(current_model()["model"])
                break

    decision = {
        "schema": "mq.model-route-decision.v1",
        "decision_id": _decision_id(task, authoritative_agent),
        "task_class": task_class,
        "risk": risk,
        "recommended_route": route,
        "local_model": model,
        "authoritative_agent": authoritative_agent,
        "reason_codes": reasons,
        "escalation_conditions": [
            "schema-invalid",
            "verification-failed",
            "confidence-below-threshold",
            "policy-requires-cloud",
        ],
    }
    _validator("model_route_decision.schema.json").validate(decision)
    return decision


def _outcome(
    decision: dict[str, Any],
    *,
    attempted: bool = False,
    model_output_received: bool = False,
    schema_valid: bool = False,
    verification_status: str = "SKIPPED",
    verification_checks: list[str] | None = None,
    accepted_by_agent: bool = False,
    accepted_by_operator: bool = False,
    escalated: bool = False,
    escalation_reason: str | None = None,
    grounding: tuple[int, int] | None = None,
    application: str | None = None,
    execution_run_id: str | None = None,
) -> dict[str, Any]:
    """Build and validate one routing outcome without persisting it.

    `application` says what the decision actually did — `advisory`, `shadow` or
    `applied` (ADR-010 D7). `execution_run_id` correlates the observation to the
    execution that enclosed it (D3); it is a different field from `run_id`,
    which identifies this observation, and must never be conflated with it.
    Both are omitted when not known, because absent means unrecorded.
    """
    outcome = {
        "schema": "mq.model-route-outcome.v1",
        "decision_id": decision["decision_id"],
        # decision_id is a hash of the task, so repeated runs of one task share it.
        # run_id keeps those runs distinguishable from duplicated records. It is
        # not the enclosing execution — that is `execution_run_id`.
        "run_id": str(uuid.uuid4()),
        "task_class": decision["task_class"],
        "selected_route": decision["recommended_route"],
        "local_model": decision["local_model"],
        "authoritative_agent": decision["authoritative_agent"],
        "attempted": attempted,
        "model_output_received": model_output_received,
        "schema_valid": schema_valid,
        "verification": {
            "status": verification_status,
            "checks": verification_checks or [],
        },
        "accepted_by_agent": accepted_by_agent,
        "accepted_by_operator": accepted_by_operator,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    if application is not None:
        outcome["application"] = application
    if execution_run_id is not None:
        outcome["execution_run_id"] = execution_run_id
    if grounding is not None:
        # Absent means unmeasured, never zero — so it is only set when measured.
        outcome["verification"]["grounding"] = {
            "grounded_items": grounding[0],
            "total_items": grounding[1],
        }
    _validator("model_route_outcome.schema.json").validate(outcome)
    return outcome


def _candidate_is_valid(candidate: Any, task_class: str) -> bool:
    if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_KEYS:
        return False
    if candidate.get("task_class") != task_class:
        return False
    if not isinstance(candidate.get("summary"), str) or not candidate["summary"].strip():
        return False
    for field in ("evidence", "suggestions"):
        values = candidate.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            return False
    return True


# Shorter strings match too much of any material to be treated as a citation.
_MIN_QUOTE_LENGTH = 12


def _normalize(text: str) -> str:
    return " ".join(text.split())


def evidence_grounding(evidence: list[str], context: str) -> tuple[int, int]:
    """Count how many evidence items are long-enough verbatim quotes.

    Counting rather than short-circuiting: the gate below still requires every
    item, but a bare pass/fail throws away the only number that explains it. A
    model paraphrasing one citation of five and a model inventing all five both
    recorded FAIL, which made the aggregate verification rate uninterpretable.
    """
    haystack = _normalize(context)
    grounded = 0
    for item in evidence:
        quote = _normalize(item)
        if len(quote) >= _MIN_QUOTE_LENGTH and quote in haystack:
            grounded += 1
    return grounded, len(evidence)


def _evidence_is_grounded(evidence: list[str], context: str) -> bool:
    """Every item must be verbatim. Empty evidence is not grounding."""
    grounded, total = evidence_grounding(evidence, context)
    return bool(total) and grounded == total


def _shadow_prompt(task: str, task_class: str, context: str | None = None) -> str:
    prompt = (
        "Return only one JSON object with exactly these keys: task_class, summary, "
        "evidence, suggestions. task_class must be "
        f"{json.dumps(task_class)}. evidence and suggestions must be string arrays. "
        "Do not return commands or markdown. Task: "
        f"{json.dumps(task)}"
    )
    if context is None:
        return prompt
    return (
        prompt + " Every entry in evidence must be copied verbatim from the material "
        "below, long enough to identify the line it came from. Do not paraphrase. "
        f"Material: {json.dumps(context)}"
    )


def shadow_route(
    task: str,
    *,
    authoritative_agent: str = "codex",
    timeout: int = 180,
    context: str | None = None,
) -> dict[str, Any]:
    """Run an advisory local candidate and return a verified comparison record."""
    decision = inspect_route(task, authoritative_agent=authoritative_agent)
    if decision["recommended_route"] == "cloud-required":
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                verification_status="SKIPPED",
                escalated=True,
                escalation_reason="policy-requires-cloud",
            ),
        }

    if not shutil.which("ollama"):
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                verification_status="UNAVAILABLE",
                escalated=True,
                escalation_reason="model-unavailable",
            ),
        }

    try:
        response = _ollama_generate(
            str(decision["local_model"]),
            _shadow_prompt(task, str(decision["task_class"]), context),
            timeout,
            json_format=_CANDIDATE_SCHEMA,
            keep_alive=0,
        )
    except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                attempted=True,
                verification_status="UNAVAILABLE",
                escalated=True,
                escalation_reason="model-unavailable",
            ),
        }

    raw = str(response.get("response", ""))
    if not raw.strip():
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                attempted=True,
                verification_status="FAIL",
                escalated=True,
                escalation_reason="malformed-output",
            ),
        }
    try:
        candidate = json.loads(raw)
    except json.JSONDecodeError:
        candidate = None
    if not _candidate_is_valid(candidate, str(decision["task_class"])):
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                attempted=True,
                model_output_received=True,
                verification_status="FAIL",
                escalated=True,
                escalation_reason="malformed-output" if candidate is None else "schema-invalid",
            ),
        }

    checks = ["candidate-schema", "task-class-match"]
    grounding: tuple[int, int] | None = None
    if context is not None:
        grounding = evidence_grounding(candidate["evidence"], context)
        grounded, total = grounding
        if not total or grounded != total:
            return {
                "decision": decision,
                "candidate": None,
                "outcome": _outcome(
                    decision,
                    attempted=True,
                    model_output_received=True,
                    schema_valid=True,
                    verification_status="FAIL",
                    escalated=True,
                    escalation_reason="verification-failed",
                    # Kept on the failure too: this is the record that explains
                    # how close the candidate came.
                    grounding=grounding,
                ),
            }
        checks.append("evidence-grounded")

    return {
        "decision": decision,
        "candidate": candidate,
        "outcome": _outcome(
            decision,
            attempted=True,
            model_output_received=True,
            schema_valid=True,
            verification_status="PASS",
            verification_checks=checks,
            grounding=grounding,
        ),
    }


def _read_records(source: Path) -> tuple[list[Any], int]:
    if not source.exists():
        return [], 0
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return [], 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        records: list[Any] = []
        for line in text.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append(None)
        return records, len(records)
    records = parsed if isinstance(parsed, list) else [parsed]
    return records, len(records)


def record_route_outcome(outcome: dict[str, Any], destination: Path | None = None) -> Path:
    """Append one schema-valid routing outcome to the local JSONL evidence store."""
    _validator("model_route_outcome.schema.json").validate(outcome)
    path = _outcome_path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(outcome, ensure_ascii=False) + "\n")
    return path


def _split_contracts(records: list[Any]) -> tuple[list[Any], list[Any], int]:
    """Sort records into route outcomes, execution outcomes, and genuine junk.

    Both contracts pin `schema` to a `const`, so no record can satisfy both and
    the split is unambiguous. An execution record found in a routing source is a
    valid record of another contract, not a broken one — counting it as invalid
    would make a healthy store look corrupt and bury real corruption in noise.
    """
    route_validator = _validator("model_route_outcome.schema.json")
    execution_validator = _validator(EXECUTION_SCHEMA_FILE)
    route: list[Any] = []
    execution: list[Any] = []
    invalid = 0
    for record in records:
        if not list(route_validator.iter_errors(record)):
            route.append(record)
        elif not list(execution_validator.iter_errors(record)):
            execution.append(record)
        else:
            invalid += 1
    return route, execution, invalid


def _execution_records(source: Path | None, from_source: list[Any]) -> tuple[list[Any], Path]:
    """Return the execution outcomes to present, and where they came from.

    An explicit `--source` is the operator naming one file, so both contracts
    are read out of it. With no source the two stores are separate files and
    each contract is read from its own.
    """
    if source is not None:
        return from_source, source
    path = execution_outcome_path()
    records, _ = _read_records(path)
    _, execution, _ = _split_contracts(records)
    return execution, path


def _metric(values: list[int], percentile: float | None = None) -> int | float | None:
    if not values:
        return None
    if percentile is None:
        value = median(values)
    else:
        ordered = sorted(values)
        value = ordered[max(0, ceil(percentile * len(ordered)) - 1)]
    return int(value) if float(value).is_integer() else value


def _execution_summary(records: list[Any], path: Path) -> dict[str, Any]:
    """Aggregate execution outcomes on their own terms.

    Deliberately counts only. A route verification rate says whether a local
    model could be trusted; an execution result says whether a run worked. One
    rate spanning both would mean neither — and a rate over executions alone is
    a judgement that belongs to the phase that acts on it, not to this report.
    """
    by_result = {"PASS": 0, "FAIL": 0, "SKIPPED": 0}
    by_task: dict[str, dict[str, Any]] = {}
    for record in records:
        result = str(record["result"])
        by_result[result] = by_result.get(result, 0) + 1
        bucket = by_task.setdefault(
            str(record["task_class"]),
            {"outcomes": 0, "PASS": 0, "FAIL": 0, "SKIPPED": 0, "by_route": {}},
        )
        bucket["outcomes"] += 1
        bucket[result] = bucket.get(result, 0) + 1
        route = str(record.get("route", {}).get("selected", "unreported"))
        route_bucket = bucket["by_route"].setdefault(
            route,
            {
                "outcomes": 0,
                "PASS": 0,
                "FAIL": 0,
                "SKIPPED": 0,
                "_latencies": [],
                "_tool_calls": [],
                "_retries": [],
                "_fallbacks": [],
                "_context_sizes": [],
            },
        )
        route_bucket["outcomes"] += 1
        route_bucket[result] = route_bucket.get(result, 0) + 1
        route_bucket["_latencies"].append(int(record["latency_ms"]))
        for field, private in (
            ("tool_calls", "_tool_calls"),
            ("retries", "_retries"),
            ("fallbacks", "_fallbacks"),
        ):
            if field in record:
                route_bucket[private].append(int(record[field]))
        if "context" in record:
            route_bucket["_context_sizes"].append(int(record["context"]["size"]))
    for task in by_task.values():
        for route_bucket in task["by_route"].values():
            outcomes = route_bucket["outcomes"]
            latencies = route_bucket.pop("_latencies")
            route_bucket["success_rate"] = round(route_bucket["PASS"] / outcomes, 3)
            route_bucket["median_latency_ms"] = _metric(latencies)
            route_bucket["p90_latency_ms"] = _metric(latencies, 0.9)
            route_bucket["median_context_size"] = _metric(
                route_bucket.pop("_context_sizes")
            )
            for field, private in (
                ("tool_calls", "_tool_calls"),
                ("retries", "_retries"),
                ("fallbacks", "_fallbacks"),
            ):
                measured = route_bucket.pop(private)
                route_bucket[field] = sum(measured) if measured else None
    return {
        "schema": EXECUTION_SCHEMA_ID,
        "source": str(path),
        "outcomes": len(records),
        "by_result": by_result,
        "by_task_class": by_task,
    }


def _window_records(
    records: list[Any], since: str | None, now: datetime | None = None
) -> list[Any]:
    if since is None:
        return records
    if since not in {"7d", "30d", "90d"}:
        raise ValueError("since must be one of 7d, 30d, or 90d")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=int(since[:-1]))
    return [
        record
        for record in records
        if datetime.fromisoformat(str(record["recorded_at"])) >= cutoff
    ]


def route_report(
    source: Path | None = None, *, since: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Aggregate validated outcomes from a JSON or JSONL source, read-only."""
    path = _outcome_path(source)
    records, total = _read_records(path)
    outcomes, execution_in_source, invalid = _split_contracts(records)
    execution, execution_path = _execution_records(source, execution_in_source)
    outcomes = _window_records(outcomes, since, now)
    execution = _window_records(execution, since, now)
    by_task: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        task_class = str(outcome["task_class"])
        bucket = by_task.setdefault(
            task_class,
            {
                "outcomes": 0,
                "attempted": 0,
                "model_output_received": 0,
                "verified": 0,
                "accepted_by_agent": 0,
                "accepted_by_operator": 0,
                "escalated": 0,
            },
        )
        bucket["outcomes"] += 1
        bucket["attempted"] += int(outcome["attempted"])
        bucket["model_output_received"] += int(outcome["model_output_received"])
        bucket["verified"] += int(outcome["verification"]["status"] == "PASS")
        bucket["accepted_by_agent"] += int(outcome["accepted_by_agent"])
        bucket["accepted_by_operator"] += int(outcome["accepted_by_operator"])
        bucket["escalated"] += int(outcome["escalated"])
    report_by_task: dict[str, dict[str, int | float]] = {}
    for task_class, counts in by_task.items():
        responded = counts["model_output_received"]
        verified = counts["verified"]
        report_by_task[task_class] = {
            **counts,
            "verification_rate": round(verified / responded, 3) if responded else 0.0,
            "agent_acceptance_rate": (
                round(counts["accepted_by_agent"] / verified, 3) if verified else 0.0
            ),
        }
    return {
        "schema": "mq.model-route-report.v1",
        "source": str(path),
        "window": since,
        "total_records": total,
        "valid_outcomes": len(outcomes),
        "invalid_records": invalid,
        "attempted": sum(int(item["attempted"]) for item in outcomes),
        "model_output_received": sum(int(item["model_output_received"]) for item in outcomes),
        "schema_valid": sum(int(item["schema_valid"]) for item in outcomes),
        "verified": sum(int(item["verification"]["status"] == "PASS") for item in outcomes),
        "accepted_by_agent": sum(int(item["accepted_by_agent"]) for item in outcomes),
        "accepted_by_operator": sum(int(item["accepted_by_operator"]) for item in outcomes),
        "escalated": sum(int(item["escalated"]) for item in outcomes),
        "by_task_class": report_by_task,
        # Presented beside the routing counts, never folded into them.
        "execution": _execution_summary(execution, execution_path),
    }


READINESS_THRESHOLDS = {
    "minimum_observations": 30,
    "minimum_candidate_routes": 2,
    "minimum_window_days": 14,
    "minimum_samples_per_route": 10,
}


def route_readiness(source: Path | None = None) -> dict[str, Any]:
    """Report evidence distance without recommending or changing a route.

    Reads **routing observations**, grouped by the **routing** task class, and
    counts only routes that were actually applied (ADR-010 D5 and D7).

    It used to read execution outcomes and group by the execution vocabulary —
    `audit`, `ci`, `docs` — asking whether an `audit` had two routes. An audit
    can contain several unrelated routing decisions, so that question had no
    answer. The question worth asking is whether `docs-review` has two applied
    routes.

    The filter comes first. An `advisory` or `shadow` observation is real
    evidence of routing behaviour and never evidence that a route was applied,
    so it must not reach the grouping step. An observation carrying no
    `application` at all is not applied either: absent means the mode was not
    recorded, and only an explicit `applied` counts.

    The thresholds keep their numbers and change their subject — they now
    describe a population of routing decisions rather than of operator actions.
    Whether that calibration still holds is an open question, reported beside
    the counts rather than implied away.
    """
    path = _outcome_path(source)
    records, _ = _read_records(path)
    observations, _, invalid = _split_contracts(records)
    applied = [
        record
        for record in observations
        if record.get("application") == "applied"
    ]
    by_task: dict[str, list[Any]] = {}
    for record in applied:
        by_task.setdefault(str(record["task_class"]), []).append(record)
    task_classes: dict[str, Any] = {}
    for task_class, task_records in sorted(by_task.items()):
        routes: dict[str, int] = {}
        for record in task_records:
            route = record.get("selected_route")
            if route:
                routes[str(route)] = routes.get(str(route), 0) + 1
        stamps = sorted(
            datetime.fromisoformat(str(record["recorded_at"]))
            for record in task_records
        )
        window_days = (stamps[-1] - stamps[0]).total_seconds() / 86400 if stamps else 0.0
        actual = {
            "observations": len(task_records),
            "candidate_routes": len(routes),
            "window_days": round(window_days, 3),
            "minimum_samples_per_route": min(routes.values()) if routes else 0,
        }
        gates = {
            "minimum_observations": actual["observations"] >= 30,
            "minimum_candidate_routes": actual["candidate_routes"] >= 2,
            "minimum_window_days": actual["window_days"] >= 14,
            "minimum_samples_per_route": actual["minimum_samples_per_route"] >= 10,
        }
        eligible = all(gates.values())
        task_classes[task_class] = {
            "eligible": eligible,
            "recommendation": (
                "AWAITING_OPERATOR_APPROVAL" if eligible else "NOT_ELIGIBLE"
            ),
            "actual": actual,
            "routes": routes,
            "gates": gates,
        }
    return {
        "schema": "mq.route-readiness.v1",
        "source": str(path),
        "thresholds": READINESS_THRESHOLDS,
        "threshold_calibration": (
            "Carried over from a per-execution population. Whether these numbers "
            "are right for a population of routing decisions is unreviewed."
        ),
        "invalid_records": invalid,
        "observations_considered": len(applied),
        "observations_ignored_not_applied": len(observations) - len(applied),
        # Readiness is an evidence report, never an authorization. Applying a
        # route requires an explicit operator allowlist and a safety check;
        # accumulating telemetry grants no execution rights on its own.
        "grants_eligibility": False,
        "automatic_routing_enabled": False,
        "operator_approval_required": True,
        "task_classes": task_classes,
    }


def execution_report(
    source: Path | None = None,
    *,
    since: str | None = None,
    task_class: str | None = None,
) -> dict[str, Any]:
    """Return execution-only metrics without shadow-routing records."""
    path = execution_outcome_path(source)
    records, total = _read_records(path)
    _, executions, invalid = _split_contracts(records)
    executions = _window_records(executions, since)
    if task_class is not None:
        executions = [r for r in executions if r["task_class"] == task_class]
    summary = _execution_summary(executions, path)
    return {
        **summary,
        "schema": "mq.execution-report.v1",
        "window": since,
        "task_class": task_class,
        "total_records": total,
        "invalid_records": invalid,
    }


def execution_compare(
    task_class: str,
    left_route: str,
    right_route: str,
    source: Path | None = None,
    *,
    since: str | None = None,
) -> dict[str, Any]:
    """Place two observed routes side by side; make no winner recommendation."""
    report = execution_report(source, since=since, task_class=task_class)
    routes = report["by_task_class"].get(task_class, {}).get("by_route", {})
    compared = {
        left_route: routes.get(left_route),
        right_route: routes.get(right_route),
    }
    return {
        "schema": "mq.execution-compare.v1",
        "source": report["source"],
        "window": since,
        "task_class": task_class,
        "routes": compared,
        "comparable": all(value is not None for value in compared.values()),
        "recommendation": None,
    }


def route_history(
    source: Path | None = None,
    *,
    decision_id: str | None = None,
    task_class: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List validated outcomes newest first, read-only, without aggregating them.

    `route_report` collapses outcomes into counts; this keeps each decision
    separate so an operator can explain a single one. A non-positive `limit`
    returns every match.
    """
    path = _outcome_path(source)
    records, total = _read_records(path)
    outcomes, execution_in_source, invalid = _split_contracts(records)
    execution, execution_path = _execution_records(source, execution_in_source)
    matched = [
        outcome
        for outcome in outcomes
        if (decision_id is None or outcome["decision_id"] == decision_id)
        and (task_class is None or outcome["task_class"] == task_class)
    ]
    matched.sort(key=lambda outcome: str(outcome["recorded_at"]), reverse=True)
    entries = matched if limit <= 0 else matched[:limit]

    # A decision id names one routing decision, and no execution record carries
    # one, so that filter empties this list rather than being ignored.
    execution_matched = [
        record
        for record in execution
        if decision_id is None and (task_class is None or record["task_class"] == task_class)
    ]
    execution_matched.sort(key=lambda record: str(record["recorded_at"]), reverse=True)
    execution_entries = (
        execution_matched if limit <= 0 else execution_matched[:limit]
    )
    return {
        "schema": "mq.model-route-history.v1",
        "source": str(path),
        "total_records": total,
        "valid_outcomes": len(outcomes),
        "invalid_records": invalid,
        "filters": {"decision_id": decision_id, "task_class": task_class},
        "matched": len(matched),
        "returned": len(entries),
        "entries": entries,
        # Listed beside the routing decisions, never interleaved with them.
        "execution": {
            "schema": EXECUTION_SCHEMA_ID,
            "source": str(execution_path),
            "matched": len(execution_matched),
            "returned": len(execution_entries),
            "entries": execution_entries,
        },
    }


def review_route_evidence(task_class: str, source: Path | None = None) -> dict[str, Any]:
    """Evaluate one task class against the promotion evidence gate, read-only."""
    outcome_schema = cast(
        dict[str, Any], _validator("model_route_outcome.schema.json").schema
    )
    allowed = outcome_schema["properties"]["task_class"]["enum"]
    if task_class not in allowed:
        raise ValueError(f"unknown task class: {task_class}")

    path = _outcome_path(source)
    records, total = _read_records(path)
    validator = _validator("model_route_outcome.schema.json")
    valid = [record for record in records if not list(validator.iter_errors(record))]
    outcomes = [record for record in valid if record["task_class"] == task_class]
    attempted = sum(int(item["attempted"]) for item in outcomes)
    responded = sum(int(item["model_output_received"]) for item in outcomes)
    verified = sum(int(item["verification"]["status"] == "PASS") for item in outcomes)
    # Attempts the model never answered are Ollama availability, not model quality,
    # so they belong in attempted_outcomes but not in the success-rate denominator.
    verification_rate = round(verified / responded, 3) if responded else 0.0
    malformed = [
        item
        for item in outcomes
        if item["escalation_reason"] in {"malformed-output", "schema-invalid"}
    ]
    malformed_escalated = sum(int(item["escalated"]) for item in malformed)
    unavailable_proven = any(
        item["verification"]["status"] == "UNAVAILABLE"
        and item["escalated"]
        and item["escalation_reason"] == "model-unavailable"
        for item in outcomes
    )
    unauthorized_writes = sum(int(item["selected_route"] == "approved-local") for item in outcomes)
    safety_violations = sum(
        int(
            (item["accepted_by_agent"] or item["accepted_by_operator"])
            and item["verification"]["status"] != "PASS"
        )
        for item in outcomes
    ) + sum(int(not item["escalated"]) for item in malformed) + unauthorized_writes
    accepted = sum(
        int(item["accepted_by_agent"] or item["accepted_by_operator"]) for item in outcomes
    )
    passing = [item for item in outcomes if item["verification"]["status"] == "PASS"]
    distinct_verified = len({str(item["decision_id"]) for item in passing})
    grounded = sum(
        int("evidence-grounded" in item["verification"]["checks"]) for item in passing
    )

    # A gate is vacuous when the evidence holds no observation that could have failed
    # it. Such a gate passes by construction, so reporting it as met would overstate
    # what the evidence proves.
    gate_values = (
        ("minimum-verified-outcomes", verified >= 50, verified, ">= 50", False),
        (
            "verification-success-rate",
            verification_rate >= 0.9,
            verification_rate,
            ">= 0.9",
            responded == 0,
        ),
        ("valid-outcome-records", total == len(valid), total - len(valid), "0 invalid", total == 0),
        (
            "zero-unauthorized-writes",
            unauthorized_writes == 0,
            unauthorized_writes,
            "0",
            not any(item["selected_route"] == "approved-local" for item in outcomes),
        ),
        (
            "zero-safety-contract-violations",
            safety_violations == 0,
            safety_violations,
            "0",
            accepted == 0 and not malformed and unauthorized_writes == 0,
        ),
        (
            "all-malformed-outputs-escalated",
            len(malformed) == malformed_escalated,
            f"{malformed_escalated}/{len(malformed)}",
            "all",
            not malformed,
        ),
        ("ollama-unavailable-path-proven", unavailable_proven, unavailable_proven, True, False),
        # Volume alone can come from one task run many times, and a structurally valid
        # candidate can still be invented, so coverage and grounding are separate bars.
        ("distinct-verified-tasks", distinct_verified >= 10, distinct_verified, ">= 10", False),
        (
            "verified-outcomes-are-grounded",
            grounded == verified,
            f"{grounded}/{verified}",
            "all",
            verified == 0,
        ),
    )
    gates = [
        {
            "id": gate_id,
            "passed": passed,
            "actual": actual,
            "required": required,
            "vacuous": vacuous,
        }
        for gate_id, passed, actual, required, vacuous in gate_values
    ]
    failed = [gate["id"] for gate in gates if not gate["passed"]]
    vacuous_gates = [gate["id"] for gate in gates if gate["vacuous"]]
    # Counted over whatever measured it: an outcome without grounding predates
    # the field, so it must not drag the rate toward zero.
    measured = [
        item["verification"]["grounding"]
        for item in outcomes
        if "grounding" in item["verification"]
    ]
    grounded_items = sum(int(item["grounded_items"]) for item in measured)
    items_measured = sum(int(item["total_items"]) for item in measured)
    review = {
        "schema": "mq.model-route-evidence-review.v1",
        "task_class": task_class,
        "source": str(path),
        "decision": "NOT_ELIGIBLE" if failed else "AWAITING_OPERATOR_APPROVAL",
        "automatic_routing_enabled": False,
        "operator_approval_required": True,
        "valid_outcomes": len(outcomes),
        "verified_outcomes": verified,
        "distinct_verified_tasks": distinct_verified,
        "grounded_verified_outcomes": grounded,
        "attempted_outcomes": attempted,
        "responded_outcomes": responded,
        "verification_success_rate": verification_rate,
        "grounded_items": grounded_items,
        "grounding_items_measured": items_measured,
        # None, not 0.0: nothing measured is not the same as nothing grounded.
        "grounding_item_rate": (
            round(grounded_items / items_measured, 3) if items_measured else None
        ),
        "unauthorized_writes": unauthorized_writes,
        "safety_contract_violations": safety_violations,
        "malformed_outputs": len(malformed),
        "malformed_outputs_escalated": malformed_escalated,
        "ollama_unavailable_path_proven": unavailable_proven,
        "gates": gates,
        "failed_gates": failed,
        "vacuous_gates": vacuous_gates,
    }
    _validator("model_route_evidence_review.schema.json").validate(review)
    return review
