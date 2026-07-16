"""Operator-triggered co-change inbox pipeline (CG-2).

ONE operator command that runs the autonomous learning loop end-to-end against the
MQ stack's own tools — but only when the operator asks. This is NOT auto-after-workflow
emission (every run emitting memory); it is operator-triggered one-command intake.

The stack boundary is preserved exactly:

    Bridget/CG-2 (mq-mcp) = evidence source only (run_cochange)
    mq-agent              = producer + ORCHESTRATOR (this module)
    mqobsidian            = inbox, scoring, quarantine, promotion-event, learn-writeback

mq-agent orchestrates by *delegating* to each owner; it never moves scoring or
writeback logic into itself. Scoring/writeback/status are invoked through mqobsidian's
own local-only CLI (`memory/commands/memory_cli.py`) so mqobsidian stays the sole
decision engine.

Stages (each surfaced to the operator):
    1. Bridget/CG-2 evidence  — run_cochange (read-only)
    2. mq-agent observation   — build + emit memory-observation.v1 (skipped if no cluster)
    3. mqobsidian scoring     — memory_cli score --apply (or --dry-run)
    4. learn-writeback        — memory_cli learn-writeback --apply (promoted only; skippable)
    5. memory status          — memory_cli status (read-only)

Best-effort and explicit: `--dry-run` writes nothing (Bridget still reads, but no
observation is appended and scoring/writeback run in --dry-run); `--no-writeback`
scores without touching durable memory.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..workflows.observation import default_vault
from .cochange_observation import (
    _DEFAULT_MIN_CONFIDENCE,
    _DEFAULT_MIN_SUPPORT,
    _DEFAULT_WINDOW,
    build_observation,
    emit_observation,
    observations_inbox,
    run_cochange,
)

_CLI_TIMEOUT = 120
_EXPORT_INDEX = Path("exports/truth-export-index.json")
_SURFACE_SCHEMAS = {
    "inbox": "inbox-manifest.v1",
    "scores": "memory-score-manifest.v1",
    "evidence": "memory-evidence-manifest.v1",
    "promotion-policy": "promotion-policy.v1",
}
_REQUIRED_FIELDS = {
    "truth-export-index.v1": {"schema": str, "source": str, "generated_at": str, "surfaces": list},
    "inbox-manifest.v1": {"schema": str, "source": str, "generated_at": str, "items": list},
    "memory-score-manifest.v1": {"schema": str, "source": str, "generated_at": str, "scores": dict},
    "memory-evidence-manifest.v1": {"schema": str, "source": str, "generated_at": str, "evidence": dict},
    "promotion-policy.v1": {
        "schema": str, "source": str, "generated_at": str, "weights": dict,
        "review_threshold": (int, float), "auto_threshold": (int, float),
        "min_supporting_factors": int, "block_negative_feedback": bool,
        "max_manifest_age_seconds": int,
    },
}


class ExportContractError(ValueError):
    """Canonical mqobsidian export discovery failed closed."""


def _non_negative_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportContractError(f"cannot read canonical export {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExportContractError(f"canonical export {path.name} must be an object")
    return value


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ExportContractError(f"invalid generated_at: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ExportContractError("generated_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_shape(document: dict, schema: str) -> None:
    required = _REQUIRED_FIELDS[schema]
    for field, expected in required.items():
        value = document.get(field)
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ExportContractError(f"{schema} has invalid or missing {field}")
    if document["schema"] != schema:
        raise ExportContractError(f"document schema mismatch: expected {schema}")
    allowed_top = {
        "truth-export-index.v1": {"schema", "source", "generated_at", "surfaces"},
        "inbox-manifest.v1": {"schema", "source", "generated_at", "items"},
        "memory-score-manifest.v1": {"schema", "source", "generated_at", "scores"},
        "memory-evidence-manifest.v1": {"schema", "source", "generated_at", "evidence"},
        "promotion-policy.v1": set(required),
    }[schema]
    unknown = set(document) - allowed_top
    if unknown:
        raise ExportContractError(f"{schema} has unknown fields: {sorted(unknown)}")
    if schema == "truth-export-index.v1":
        allowed = {"key", "schema", "path", "generated_at", "drift", "record_count", "description"}
        for entry in document["surfaces"]:
            if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ("key", "schema", "path")):
                raise ExportContractError("truth-export-index.v1 has malformed surface entry")
            if set(entry) - allowed:
                raise ExportContractError("truth-export-index.v1 surface entry has unknown fields")
    elif schema == "inbox-manifest.v1":
        allowed = {"id", "source", "state", "first_seen", "last_seen", "occurrences", "score", "evidence"}
        for item in document["items"]:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("id", "source", "state", "first_seen", "last_seen")):
                raise ExportContractError("inbox-manifest.v1 has malformed inbox item")
            if item["state"] not in {"observed", "candidate"} or set(item) - allowed:
                raise ExportContractError("inbox-manifest.v1 has invalid inbox item")
            for evidence in item.get("evidence", []):
                if not isinstance(evidence, dict) or not isinstance(evidence.get("ref"), str) or set(evidence) - {"ref", "kind"}:
                    raise ExportContractError("inbox-manifest.v1 has malformed evidence ref")
    elif schema == "memory-score-manifest.v1":
        allowed = {"schema", "memory_id", "timestamp", "status", "score", "factors", "observed_by", "feedback", "first_seen", "last_seen", "promoted_at"}
        for key, record in document["scores"].items():
            if (not isinstance(record, dict) or record.get("schema") != "memory-score.v1"
                    or record.get("memory_id") != key or not isinstance(record.get("timestamp"), str)
                    or record.get("status") not in {"observed", "candidate", "promoted", "deprecated", "archived"}
                    or not isinstance(record.get("score"), (int, float)) or isinstance(record.get("score"), bool)
                    or set(record) - allowed):
                raise ExportContractError("memory-score-manifest.v1 has malformed keyed score")
    elif schema == "memory-evidence-manifest.v1":
        allowed = {"ref", "producer", "schema_id", "candidate_id", "kind", "observed_at", "summary"}
        for key, record in document["evidence"].items():
            if (not isinstance(record, dict) or record.get("ref") != key
                    or not all(isinstance(record.get(field), str) and record[field]
                               for field in ("producer", "schema_id", "observed_at", "summary"))
                    or set(record) - allowed):
                raise ExportContractError("memory-evidence-manifest.v1 has malformed keyed evidence")
    elif schema == "promotion-policy.v1":
        weights = document.get("weights")
        expected_weights = {"frequency", "source_count", "confidence", "recency", "usage_score", "manual_boost"}
        if not isinstance(weights, dict) or set(weights) != expected_weights or not all(_non_negative_number(v) for v in weights.values()):
            raise ExportContractError("promotion-policy.v1 has invalid weights")
        if (not _non_negative_number(document["review_threshold"])
                or not _non_negative_number(document["auto_threshold"])
                or document["auto_threshold"] < document["review_threshold"]
                or document["min_supporting_factors"] < 2
                or document["max_manifest_age_seconds"] < 0):
            raise ExportContractError("promotion-policy.v1 has invalid bounds")


def load_canonical_exports(
    *, vault: str | Path | None = None, now: Callable[[], datetime] | None = None,
) -> dict[str, dict]:
    """Discover required inbox surfaces from mqobsidian's sole entrypoint.

    No raw-vault fallback is permitted. Paths must resolve below the vault and
    every required surface must match the schema declared by this consumer.
    """
    root = resolve_vault(vault).resolve()
    index = _read_json(root / _EXPORT_INDEX)
    if index.get("schema") != "truth-export-index.v1":
        raise ExportContractError("unexpected truth export index schema")
    _validate_shape(index, "truth-export-index.v1")
    entries = index.get("surfaces")
    if not isinstance(entries, list):
        raise ExportContractError("truth export index surfaces must be an array")
    by_key: dict[str, Mapping] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("key"), str):
            if entry["key"] in by_key:
                raise ExportContractError(f"duplicate surface key: {entry['key']}")
            by_key[entry["key"]] = entry

    documents: dict[str, dict] = {}
    generated: dict[str, str] = {}
    for key, schema in _SURFACE_SCHEMAS.items():
        entry = by_key.get(key)
        if entry is None:
            raise ExportContractError(f"missing canonical surface: {key}")
        if entry.get("schema") != schema:
            raise ExportContractError(f"unexpected schema for {key}")
        if entry.get("drift") is True:
            raise ExportContractError(f"canonical surface is drifted: {key}")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ExportContractError(f"invalid path for {key}")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ExportContractError(f"absolute canonical path for {key}")
        resolved = (root / relative).resolve()
        if resolved != root and root not in resolved.parents:
            raise ExportContractError(f"canonical path escapes vault for {key}")
        document = _read_json(resolved)
        try:
            _validate_shape(document, schema)
        except ExportContractError as exc:
            raise ExportContractError(f"invalid {key} surface: {exc}") from exc
        documents[key] = document
        generated[key] = document.get("generated_at") or entry.get("generated_at")

    policy = documents["promotion-policy"]
    max_age = policy.get("max_manifest_age_seconds")
    if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age < 0:
        raise ExportContractError("promotion policy has invalid max_manifest_age_seconds")
    current = (now or (lambda: datetime.now(timezone.utc)))()
    if current.tzinfo is None:
        raise ExportContractError("injected clock must be timezone-aware")
    current = current.astimezone(timezone.utc)
    generated["index"] = index["generated_at"]
    for key, stamp in generated.items():
        age = (current - _utc(stamp)).total_seconds()
        if age < 0:
            raise ExportContractError(f"canonical surface is future-dated: {key}")
        if age > max_age:
            raise ExportContractError(f"canonical surface is stale: {key}")
    return documents


def list_inbox_candidates(*, vault: str | Path | None = None,
                          now: Callable[[], datetime] | None = None) -> dict:
    exports = load_canonical_exports(vault=vault, now=now)
    items = exports["inbox"].get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ExportContractError("inbox items must be an array of objects")
    return {
        "schema": "inbox-candidate-list.v1", "source": exports["inbox"]["source"],
        "generated_at": exports["inbox"]["generated_at"],
        "count": len(items), "candidates": items,
    }


def read_inbox_candidate(memory_id: str, *, vault: str | Path | None = None,
                         now: Callable[[], datetime] | None = None) -> dict:
    listing = list_inbox_candidates(vault=vault, now=now)
    candidate = next((item for item in listing["candidates"] if item.get("id") == memory_id), None)
    return {
        "schema": "inbox-candidate-read.v1", "source": listing["source"],
        "generated_at": listing["generated_at"], "memory_id": memory_id,
        "found": candidate is not None, "candidate": candidate,
    }


def resolve_vault(vault: str | Path | None = None) -> Path:
    """--vault wins, then $MQ_OBSIDIAN_DIR, then the default (~/mqobsidian)."""
    if vault:
        return Path(vault).expanduser()
    env = os.environ.get("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser() if env else default_vault()


def mqobsidian_cli_path(vault: Path) -> Path:
    """mqobsidian's local-only operator CLI inside the vault checkout."""
    return vault / "memory" / "commands" / "memory_cli.py"


def run_mqobsidian_cli(vault: Path, args: list[str]) -> tuple[int, str, str]:
    """Delegate to mqobsidian's own CLI. Best-effort: a missing CLI (vault is not an
    mqobsidian checkout) returns a clear error instead of raising. Injectable seam."""
    cli = mqobsidian_cli_path(vault)
    if not cli.exists():
        return 127, "", f"mqobsidian CLI not found at {cli}"
    try:
        result = subprocess.run(
            [sys.executable, str(cli), *args],
            capture_output=True, text=True, timeout=_CLI_TIMEOUT,
        )
        return result.returncode, result.stdout, result.stderr
    except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
        return 1, "", str(exc)


def _cli_stage(cli_runner: Callable[..., tuple[int, str, str]], vault: Path, args: list[str]) -> dict:
    rc, out, err = cli_runner(vault, args)
    return {"args": args, "rc": rc, "ok": rc == 0, "stdout": out.strip(), "stderr": err.strip()}


def run_pipeline(
    repo: str | Path,
    file: str,
    *,
    window: int = _DEFAULT_WINDOW,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    min_support: int = _DEFAULT_MIN_SUPPORT,
    vault: str | Path | None = None,
    dry_run: bool = False,
    no_writeback: bool = False,
    mq_mcp_dir: str | Path | None = None,
    runner: Callable[..., dict | None] = run_cochange,
    cli_runner: Callable[..., tuple[int, str, str]] = run_mqobsidian_cli,
) -> dict:
    """Run the full operator-triggered intake. Pure orchestration over injectable
    seams (``runner`` = Bridget evidence; ``cli_runner`` = mqobsidian CLI)."""
    v = resolve_vault(vault)

    # Stage 1 — Bridget/CG-2 evidence (read-only) + Stage 2 — build the observation.
    data = runner(repo, file, window=window, mq_mcp_dir=mq_mcp_dir)
    record = (
        build_observation(data, file, min_confidence=min_confidence, min_support=min_support)
        if data else None
    )
    run_id = (record.get("evidence") or [{}])[0].get("reference", "") if record else ""
    evidence = {"found": data is not None, "run_id": run_id}

    inbox = observations_inbox(v)
    if record is None:
        emit = {
            "status": "skipped",
            "detail": "no co-change cluster cleared the gate" if data else "co-change unavailable",
            "path": "",
        }
    elif dry_run:
        emit = {"status": "would-emit", "detail": "dry-run — nothing written", "path": str(inbox)}
    else:
        path = emit_observation(record, vault=v)
        emit = (
            {"status": "emitted", "detail": "observation appended", "path": str(path)}
            if path else {"status": "error", "detail": "emit failed", "path": ""}
        )

    # Stage 3 — mqobsidian scoring (delegated; dry-run writes nothing).
    score = _cli_stage(cli_runner, v, ["score", "--dry-run" if dry_run else "--apply"])

    # Stage 4 — learn-writeback (promoted only; skippable).
    if no_writeback:
        writeback = {"args": [], "rc": 0, "ok": True, "stdout": "", "stderr": "",
                     "skipped": "--no-writeback"}
    else:
        writeback = _cli_stage(cli_runner, v, ["learn-writeback", "--dry-run" if dry_run else "--apply"])

    # Stage 5 — status (read-only).
    status = _cli_stage(cli_runner, v, ["status"])

    ok = score["ok"] and writeback["ok"] and status["ok"]
    return {
        "vault": str(v), "dry_run": dry_run, "no_writeback": no_writeback,
        "evidence": evidence, "emit": emit,
        "score": score, "writeback": writeback, "status": status, "ok": ok,
    }


# --- review / resolution surface -------------------------------------------------
# Lets an operator inspect the scoring review state and ACTION the two human-review
# queues (promotion-review, superseding) while preserving the boundary: mqlaunch ->
# mq-agent (orchestrator) -> mqobsidian's local-only CLI. These are EXPLICIT delegators
# (one per verb), deliberately NOT a generic "pass any mqobsidian command through".


def run_review_status(*, vault: str | Path | None = None,
                      cli_runner: Callable[..., tuple[int, str, str]] = run_mqobsidian_cli) -> dict:
    """Delegate to mqobsidian `status` — tier tally + held review queues (read-only)."""
    v = resolve_vault(vault)
    return {"vault": str(v), **_cli_stage(cli_runner, v, ["status"])}


def run_promote_from_review(memory_id: str, *, apply: bool = False, vault: str | Path | None = None,
                            cli_runner: Callable[..., tuple[int, str, str]] = run_mqobsidian_cli) -> dict:
    """Delegate to mqobsidian `promote-from-review <id>` — approve a held promotion
    proposal (dry-run unless ``apply``). Co-change never auto-promotes; this lands it."""
    v = resolve_vault(vault)
    args = ["promote-from-review", memory_id, *(["--apply"] if apply else [])]
    return {"vault": str(v), **_cli_stage(cli_runner, v, args)}


def run_resolve_supersede(memory_id: str, *, accept: bool, apply: bool = False,
                          vault: str | Path | None = None,
                          cli_runner: Callable[..., tuple[int, str, str]] = run_mqobsidian_cli) -> dict:
    """Delegate to mqobsidian `resolve-supersede <id> --accept|--reject` — action a deep
    conflict (dry-run unless ``apply``)."""
    v = resolve_vault(vault)
    args = ["resolve-supersede", memory_id, "--accept" if accept else "--reject",
            *(["--apply"] if apply else [])]
    return {"vault": str(v), **_cli_stage(cli_runner, v, args)}
