"""Emit `feedback-signal.v1` records for pack-usage events.

mqobsidian owns the vocabulary, the schema, and the promotion/downgrade policy
(`docs/FEEDBACK_LOOP.md`); mq-agent owns the mechanism. Records are appended to
the vault's gitignored `feedback/` surface, never committed, and never
hand-authored — there is no template for them.

The schema is read from the vault rather than vendored: this writer cannot run
without the vault anyway, so the owner's contract is always at hand.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from mq_agent.tools.context_export import default_vault

SCHEMA_ID = "feedback-signal.v1"
SIGNALS_FILE = "signals.jsonl"


def _load_schema(vault: Path) -> dict[str, Any]:
    path = vault / "schemas" / f"{SCHEMA_ID}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing {SCHEMA_ID} schema in vault: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {SCHEMA_ID} schema: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{SCHEMA_ID} schema must be a JSON object")
    return data


def record_feedback_signal(
    task: str,
    *,
    outcome: str,
    repo: str | None = None,
    judgments: list[tuple[str, str, str | None]] | None = None,
    notes: str | None = None,
    vault: Path | None = None,
) -> Path:
    """Append one validated pack-usage signal to the vault's local feedback log."""
    if not task.strip():
        raise ValueError("task must not be empty")
    vault = (vault or default_vault()).expanduser().resolve()
    schema = _load_schema(vault)

    record: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "task": task,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "outcome": outcome,
    }
    if repo:
        record["repo"] = repo
    if notes:
        record["notes"] = notes
    if judgments:
        entries: list[dict[str, str]] = []
        for block, judgment, reason in judgments:
            entry = {"block": block, "judgment": judgment}
            # An omitted reason stays absent: an empty string would read as a
            # recorded judgement with nothing behind it.
            if reason:
                entry["reason"] = reason
            entries.append(entry)
        record["judgments"] = entries

    errors = sorted(
        Draft202012Validator(schema).iter_errors(record),
        key=lambda err: list(err.absolute_path),
    )
    if errors:
        location = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
        raise ValueError(f"record violates {SCHEMA_ID} at {location}: {errors[0].message}")

    path = vault / "feedback" / SIGNALS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def count_signals(vault: Path | None = None) -> int:
    """How many signals the local surface holds, for a cheap progress read."""
    vault = (vault or default_vault()).expanduser().resolve()
    path = vault / "feedback" / SIGNALS_FILE
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
