"""Co-change memory-observation emission (CG-2).

mq-agent is the **producer** that turns Bridget/CG-2 co-change *evidence* into one
sanitized ``memory-observation.v1`` proposal for mqobsidian's Phase-12
cross-producer scoring engine. The locked producer boundary:

    Bridget/CG-2 = evidence source (derives co-change; `bridget --co-change --json`)
    mq-agent     = producer (this module; evidence.source = "bridget/cg-2")
    mqobsidian   = scores, promotes, audits (sole owner of memory-score.v1)

An observation is a *proposal, not a memory* (ADR-008: frequency never
auto-promotes). mq-agent only appends to the local-only, gitignored inbox; it owns
no scoring. Emission is best-effort and explicit (driven by an operator CLI
command, never automatically) — and emits nothing when there is no real signal,
mirroring repo-signal's memory_emit.py.

The record is public-safe: repository is a basename, paths are repo-relative, and
no prompts/stdout/secrets are included.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..workflows.observation import default_vault

SCHEMA_ID = "memory-observation.v1"
PRODUCER = "mq-agent"
EVIDENCE_SOURCE = "bridget/cg-2"

_DEFAULT_WINDOW = 300
# Co-change confidence is a weak-signal metric: useful ratios are often ~0.05–0.1
# over a 300-commit window. This is observation *intake*, not promotion — emit
# useful weak signals and let mqobsidian scoring filter later (ADR-008).
_DEFAULT_MIN_CONFIDENCE = 0.05
_DEFAULT_MIN_SUPPORT = 2
_COCHANGE_TIMEOUT = 30


def observations_inbox(vault: Path | None = None) -> Path:
    """Local-only inbox for mq-agent memory observations."""
    return (vault or default_vault()) / "memory" / "observations" / "mq-agent.observations.jsonl"


def _mq_mcp_dir(mq_mcp_dir: str | Path | None = None) -> Path:
    if mq_mcp_dir:
        return Path(mq_mcp_dir).expanduser()
    env = os.environ.get("MQ_MCP_DIR")
    return Path(env).expanduser() if env else Path.home() / "mq-mcp"


def run_cochange(
    repo: str | Path,
    target: str,
    *,
    window: int = _DEFAULT_WINDOW,
    mq_mcp_dir: str | Path | None = None,
) -> dict | None:
    """Run Bridget as the evidence source and return its parsed --json output.

    Best-effort: returns None on any subprocess error, non-zero exit, or output
    that does not parse as the expected co-change JSON. This is the injectable
    seam — tests pass a fake runner instead.
    """
    project = _mq_mcp_dir(mq_mcp_dir) / "mq-mcp"
    # Pass an ABSOLUTE target. bridge.py must run from the mq-mcp project (so it
    # can spawn server.py), so `uv --directory` makes cwd the mq-mcp project, NOT
    # `repo`. Bridget resolves the analyzed repo from the target file's git
    # toplevel — a *relative* target would resolve against the wrong repo (the
    # mq-mcp project), silently yielding an empty/false "no cluster". An absolute
    # path resolves to the correct repo regardless of cwd.
    target_arg = str(Path(repo).expanduser() / target)
    cmd = [
        "uv", "--directory", str(project), "run", "python", "bridge.py",
        "--co-change", target_arg, "--window", str(window), "--json",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=_COCHANGE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) and "rows" in data else None


def _slug(target: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", target.strip().lower()).strip("-")
    return s or "target"


def build_observation(
    cochange_json: dict,
    target: str,
    *,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    min_support: int = _DEFAULT_MIN_SUPPORT,
) -> dict | None:
    """Build a ``memory-observation.v1`` record from co-change evidence (pure).

    Gates on the strongest co-changer; returns None when there is no row or none
    clears the gate, so a weak/empty signal emits nothing. Only schema-allowed
    keys are produced (additionalProperties:false).
    """
    rows = cochange_json.get("rows") or []
    strong = [
        r for r in rows
        if float(r.get("confidence", 0)) >= min_confidence
        and int(r.get("count", 0)) >= min_support
    ]
    if not strong:
        return None

    top = strong[0]
    confidence = max(0.0, min(1.0, float(top["confidence"])))
    cluster = [r["path"] for r in strong]
    # Prefer Bridget's repo-relative target for human-facing text + keys, so an
    # absolute input path (passed to fix repo resolution in run_cochange) never
    # leaks into the stored record.
    rel_target = cochange_json.get("target") or target
    repo = cochange_json.get("repo") or Path(rel_target).parts[0]
    run_id = cochange_json.get("run_id", "")
    now = datetime.now(timezone.utc)

    return {
        "schema": SCHEMA_ID,
        "id": f"mo-cochange-{_slug(rel_target)}-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "producer": PRODUCER,
        "repository": Path(repo).name or repo,
        "workflow": "co-change",
        "title": "Co-change cluster detected",
        "observation": (
            f"When touching {rel_target}, also check: {', '.join(cluster)} "
            "— they tend to change together."
        ),
        "category": "pattern",
        "confidence": confidence,
        "evidence": [
            {
                "source": EVIDENCE_SOURCE,
                "reference": run_id,
                "excerpt": (
                    f"{top['path']} co-changed {top['count']}/{top['base']} "
                    f"commits (confidence {confidence:.2f})"
                ),
            }
        ],
        "tags": ["co-change", "codegraph", "bridget"],
        "proposed_memory_key": f"cochange-{_slug(rel_target)}",
    }


def emit_observation(record: dict, *, vault: Path | None = None) -> Path | None:
    """Append one observation to the inbox. Best-effort: returns None on failure."""
    try:
        path = observations_inbox(vault)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path
    except Exception:  # noqa: BLE001 — emission must never break the caller
        return None


def emit_cochange(
    repo: str | Path,
    target: str,
    *,
    window: int = _DEFAULT_WINDOW,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    min_support: int = _DEFAULT_MIN_SUPPORT,
    runner: Callable[..., dict | None] = run_cochange,
    mq_mcp_dir: str | Path | None = None,
    vault: Path | None = None,
) -> Path | None:
    """Run co-change → build → emit. Returns the inbox path, or None when nothing
    was emitted (no evidence, or no cluster cleared the gate)."""
    data = runner(repo, target, window=window, mq_mcp_dir=mq_mcp_dir)
    if not data:
        return None
    record = build_observation(
        data, target, min_confidence=min_confidence, min_support=min_support
    )
    if record is None:
        return None
    return emit_observation(record, vault=vault)
