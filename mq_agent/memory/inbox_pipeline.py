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
import subprocess
import sys
from pathlib import Path
from typing import Callable

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
