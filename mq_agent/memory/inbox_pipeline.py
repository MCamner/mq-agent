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
from typing import Callable, Mapping, TypeGuard

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
_REQUIRED_FIELDS: dict[str, dict[str, type | tuple[type, ...]]] = {
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


def _non_negative_number(value: object) -> TypeGuard[float]:
    """True for a real JSON number >= 0. `bool` is an int in Python and is not one."""
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
        stamp = document.get("generated_at") or entry.get("generated_at")
        if not isinstance(stamp, str):
            raise ExportContractError(f"missing generated_at for {key}")
        generated[key] = stamp

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


# --- ranking (v1.22 Task 7) ------------------------------------------------------
# The formula and the routing are mq-agent code; the weights and thresholds are
# mqobsidian data, read from promotion-policy.v1. Nothing here is hardcoded.

RANKING_SCHEMA = "inbox_promotion_orchestration.v1"
BUCKETS = ("inbox", "review-needed", "auto-promotable")
_RANK_FACTORS = ("frequency", "source_count", "confidence", "recency", "usage_score", "manual_boost")


def _mapping(value: object) -> Mapping:
    """A Mapping, or an empty one. Missing owner data never becomes a guess."""
    return value if isinstance(value, Mapping) else {}


def _weighted(factors: Mapping, weights: Mapping) -> tuple[float, dict[str, float]]:
    """Policy-weighted sum. A factor the record omits contributes nothing."""
    contributions: dict[str, float] = {}
    for name in _RANK_FACTORS:
        raw = factors.get(name)
        value = float(raw) if _non_negative_number(raw) else 0.0
        weight = weights.get(name)
        contributions[name] = round(value * (float(weight) if _non_negative_number(weight) else 0.0), 6)
    return round(sum(contributions.values()), 6), contributions


def _provenance(item: Mapping, published: Mapping) -> tuple[list[dict], list[str]]:
    """Resolve the item's refs through the evidence manifest, deduplicated.

    An opaque ref never becomes provenance: evidence is only what mqobsidian
    actually published. Order follows the inbox, so output stays deterministic.
    """
    resolved: list[dict] = []
    reasons: list[str] = []
    seen: set[str] = set()
    refs = [e.get("ref") for e in item.get("evidence", []) if isinstance(e, dict)]
    for ref in refs:
        if not isinstance(ref, str) or ref in seen:
            continue
        seen.add(ref)
        record = published.get(ref)
        if not isinstance(record, Mapping):
            if "unresolved-evidence" not in reasons:
                reasons.append("unresolved-evidence")
            continue
        candidate_id = record.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id != item.get("id"):
            # The inbox says this ref supports X; the evidence says it supports Y.
            if "conflicting-evidence" not in reasons:
                reasons.append("conflicting-evidence")
            continue
        resolved.append({
            "ref": ref,
            "producer": str(record.get("producer", "")),
            "kind": str(record.get("kind", "")),
            "observed_at": str(record.get("observed_at", "")),
        })
    if not resolved and "unresolved-evidence" not in reasons and "conflicting-evidence" not in reasons:
        reasons.append("missing-evidence")
    return resolved, reasons


def _rank_one(item: Mapping, scores: Mapping, published: Mapping, policy: Mapping) -> dict:
    memory_id = item.get("id")
    score = scores.get(memory_id)
    provenance, reasons = _provenance(item, published)

    factors: Mapping = {}
    if not isinstance(score, Mapping):
        # Never guess a score: an inbox item with no score record is a broken
        # join, and is reported as one.
        reasons.append("missing-score-record")
    else:
        declared = score.get("factors")
        if isinstance(declared, Mapping):
            factors = declared

    ranked, contributions = _weighted(factors, _mapping(policy["weights"]))
    supporting = sum(1 for name in _RANK_FACTORS
                     if _non_negative_number(factors.get(name)) and factors[name] > 0)
    if supporting < policy["min_supporting_factors"]:
        reasons.append("insufficient-supporting-factors")

    feedback = _mapping(score.get("feedback")) if isinstance(score, Mapping) else {}
    negative = feedback.get("negative")
    if policy["block_negative_feedback"] and _non_negative_number(negative) and negative > 0:
        reasons.append("negative-feedback")

    if ranked >= policy["auto_threshold"]:
        bucket = "auto-promotable"
    elif ranked >= policy["review_threshold"]:
        bucket = "review-needed"
    else:
        bucket = "inbox"
    # A forced reason can only ever take a candidate *off* the auto path. It
    # never promotes a weak candidate into review: "auto-promotable" means
    # eligible for approval, so the only thing worth forcing is ineligibility.
    if reasons and bucket == "auto-promotable":
        bucket = "review-needed"

    return {
        "memory_id": str(memory_id),
        "state": str(item.get("state", "")),
        "bucket": bucket,
        "ranked_score": ranked,
        "contributions": contributions,
        "supporting_factors": supporting,
        "provenance": provenance,
        "review_reasons": reasons,
    }


def build_ranking(exports: Mapping) -> dict:
    """Rank canonical exports. Pure: same input, same output, no I/O."""
    policy = exports["promotion-policy"]
    items = exports["inbox"].get("items", [])
    scores = exports["scores"].get("scores", {})
    published = exports["evidence"].get("evidence", {})

    ranked = [_rank_one(item, scores, published, policy) for item in items
              if isinstance(item, Mapping)]
    # Highest first; memory_id breaks ties so the order never depends on dict
    # iteration or on the order mqobsidian happened to emit.
    ranked.sort(key=lambda c: (-c["ranked_score"], c["memory_id"]))

    counts = {bucket: 0 for bucket in BUCKETS}
    for candidate in ranked:
        counts[candidate["bucket"]] += 1

    return {
        "schema": RANKING_SCHEMA,
        "source": exports["inbox"]["source"],
        "generated_at": exports["inbox"]["generated_at"],
        "policy": {
            "review_threshold": policy["review_threshold"],
            "auto_threshold": policy["auto_threshold"],
            "min_supporting_factors": policy["min_supporting_factors"],
            "block_negative_feedback": policy["block_negative_feedback"],
            "weights": dict(policy["weights"]),
        },
        "counts": counts,
        "candidates": ranked,
    }


def rank_inbox(*, vault: str | Path | None = None,
               now: Callable[[], datetime] | None = None) -> dict:
    """Read the canonical bundle and rank it. Fails closed on any contract error."""
    return build_ranking(load_canonical_exports(vault=vault, now=now))


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


def run_learn_writeback(*, apply: bool = False, vault: str | Path | None = None,
                        cli_runner: Callable[..., tuple[int, str, str]] = run_mqobsidian_cli) -> dict:
    """Delegate to mqobsidian `learn-writeback` — materialise durable agent-readable
    memory for PROMOTED memories only (dry-run unless ``apply``).

    Stage 4 of inbox-cochange runs this as part of intake; this is the same verb on
    its own, for a promotion that landed some other way (promote-from-review, or a
    manual tier change). mqobsidian decides what is promoted; mq-agent only asks.
    """
    v = resolve_vault(vault)
    args = ["learn-writeback", "--apply" if apply else "--dry-run"]
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


# --- bounded transition delegators (v1.22 Task 9) --------------------------------
# One function per mqobsidian transition verb, in the same explicit style as the
# review delegators above: never a generic "run any mqobsidian command". Only the
# operator's intent crosses the boundary — id, reason, and validated evidence
# refs. mqobsidian reads its own scores, policy, and evidence; sending them would
# make mq-agent a second source of truth.


def _run_transition(verb: str, memory_id: str, *, reason: str, apply: bool,
                    evidence: list[str] | None,
                    vault: str | Path | None,
                    cli_runner: Callable[..., tuple[int, str, str]] | None) -> dict:
    # Resolved here, not bound as a default: a default is evaluated at import, so
    # the seam would be frozen and a caller that does not pass one explicitly
    # (the CLI) could never have it substituted.
    runner = cli_runner or run_mqobsidian_cli
    v = resolve_vault(vault)
    args = [verb, memory_id, "--reason", reason]
    for ref in evidence or []:
        args += ["--evidence", ref]
    if apply:
        args.append("--apply")
    stage = _cli_stage(runner, v, args)
    # mqobsidian's transition verbs speak JSON. Parse it for the caller, but never
    # let unparsable output raise: a crash there is a result to report, not an
    # exception to swallow the exit code with.
    try:
        parsed = json.loads(stage["stdout"]) if stage["stdout"] else None
    except json.JSONDecodeError:
        parsed = None
    return {"vault": str(v), "verb": verb, "result": parsed, **stage}


def run_promote(memory_id: str, *, reason: str, evidence: list[str] | None = None,
                apply: bool = False, vault: str | Path | None = None,
                cli_runner: Callable[..., tuple[int, str, str]] | None = None) -> dict:
    """Delegate `promote <id>` — candidate -> promoted. Preview unless ``apply``.

    Evidence refs must already resolve in memory-evidence-manifest.v1; mqobsidian
    refuses the transition if they do not, so an unresolvable ref cannot become
    justification here either.
    """
    return _run_transition("promote", memory_id, reason=reason, apply=apply,
                           evidence=evidence, vault=vault, cli_runner=cli_runner)


def run_reject(memory_id: str, *, reason: str, apply: bool = False,
               vault: str | Path | None = None,
               cli_runner: Callable[..., tuple[int, str, str]] | None = None) -> dict:
    """Delegate `reject <id>` — candidate -> archived. Preview unless ``apply``."""
    return _run_transition("reject", memory_id, reason=reason, apply=apply,
                           evidence=None, vault=vault, cli_runner=cli_runner)


def run_defer(memory_id: str, *, reason: str, apply: bool = False,
              vault: str | Path | None = None,
              cli_runner: Callable[..., tuple[int, str, str]] | None = None) -> dict:
    """Delegate `defer <id>` — candidate -> observed. Preview unless ``apply``."""
    return _run_transition("defer", memory_id, reason=reason, apply=apply,
                           evidence=None, vault=vault, cli_runner=cli_runner)


def run_rollback(memory_id: str, *, reason: str, apply: bool = False,
                 vault: str | Path | None = None,
                 cli_runner: Callable[..., tuple[int, str, str]] | None = None) -> dict:
    """Delegate `rollback <id>` — promoted -> candidate. Preview unless ``apply``."""
    return _run_transition("rollback", memory_id, reason=reason, apply=apply,
                           evidence=None, vault=vault, cli_runner=cli_runner)


def run_deprecate(memory_id: str, *, reason: str, apply: bool = False,
                  vault: str | Path | None = None,
                  cli_runner: Callable[..., tuple[int, str, str]] | None = None) -> dict:
    """Delegate `deprecate <id>` — promoted -> deprecated. Preview unless ``apply``."""
    return _run_transition("deprecate", memory_id, reason=reason, apply=apply,
                           evidence=None, vault=vault, cli_runner=cli_runner)
