"""The `mq.execution-outcome.v1` evidence store.

One record per agent run. Routing is a field on the record rather than its
subject, so route evaluation, skill evaluation and tool performance read the
same contract instead of growing separate telemetry formats.

Two rules hold everywhere this module is called:

1. Telemetry observes; it never changes a run. `emit_execution_outcome` cannot
   raise, and a broken evidence store costs a record, never the run.
2. A counter the runtime does not measure is absent, not zero. A zero would
   read as "no retries happened" instead of "nobody counted".
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_ID = "mq.execution-outcome.v1"
SCHEMA_FILE = "execution_outcome.schema.json"

# Kept in step with the enum in the schema. An operator can name a swarm
# anything, and a run must not fail because the enum has not caught up, so an
# unrecognized class is recorded as `unclassified` rather than dropped.
KNOWN_TASK_CLASSES = frozenset(
    {"audit", "ci", "docs", "release", "release-check", "signal"}
)
UNCLASSIFIED = "unclassified"

_OFF_VALUES = frozenset({"0", "off", "false", "no"})


def telemetry_enabled() -> bool:
    """Execution telemetry is on unless the operator turns it off."""
    return os.environ.get("MQ_AGENT_TELEMETRY", "on").strip().lower() not in _OFF_VALUES


def outcome_path(destination: Path | None = None) -> Path:
    return destination or Path(
        os.environ.get(
            "MQ_AGENT_EXECUTION_OUTCOMES",
            Path.home() / ".mq-agent/execution-outcomes.jsonl",
        )
    ).expanduser()


def _schema_path() -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / SCHEMA_FILE
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / SCHEMA_FILE


def _validator() -> Draft202012Validator:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def build_execution_outcome(
    *,
    runtime: str,
    task_class: str,
    result: str,
    exit_status: str,
    latency_ms: int,
    run_id: str | None = None,
    route: dict[str, Any] | None = None,
    model: str | None = None,
    agents: list[dict[str, Any]] | None = None,
    skills: list[str] | None = None,
    tool_calls: int | None = None,
    retries: int | None = None,
    fallbacks: int | None = None,
    tokens: dict[str, int] | None = None,
    cost: float | None = None,
    events: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build and validate one execution outcome without persisting it."""
    outcome: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "run_id": run_id or str(uuid.uuid4()),
        "runtime": runtime,
        "task_class": task_class if task_class in KNOWN_TASK_CLASSES else UNCLASSIFIED,
        "result": result,
        "exit_status": exit_status,
        "latency_ms": max(0, int(latency_ms)),
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    # Only measured values are written. None means "not measured" and is left
    # out of the record entirely.
    optional: dict[str, Any] = {
        "route": route,
        "model": model,
        "agents": agents,
        "skills": skills,
        "tool_calls": tool_calls,
        "retries": retries,
        "fallbacks": fallbacks,
        "tokens": tokens,
        "cost": cost,
        "events": events,
    }
    outcome.update({key: value for key, value in optional.items() if value is not None})

    _validator().validate(outcome)
    return outcome


def record_execution_outcome(
    outcome: dict[str, Any], destination: Path | None = None
) -> Path:
    """Append one schema-valid execution outcome to the local JSONL store."""
    _validator().validate(outcome)
    path = outcome_path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(outcome, ensure_ascii=False) + "\n")
    return path


def emit_execution_outcome(
    destination: Path | None = None, **fields: Any
) -> Path | None:
    """Build and append one outcome, swallowing every failure.

    This is the call site for execution paths. It returns the path it wrote, or
    `None` when telemetry is off or anything at all went wrong. It never raises:
    an invalid record, an unwritable store or a full disk must not be able to
    fail a run that otherwise succeeded.
    """
    if not telemetry_enabled():
        return None

    try:
        return record_execution_outcome(build_execution_outcome(**fields), destination)
    except Exception as exc:  # noqa: BLE001 — telemetry must not raise into a run
        print(f"[telemetry] execution outcome not recorded: {exc}")
        return None
