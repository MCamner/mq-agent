"""Workflow-run observation emission.

After an actual workflow run reaches a terminal state, mq-agent emits one
sanitized ``workflow-observation.v1`` record into mqobsidian's local-only,
gitignored inbox. mqobsidian owns the vocabulary and renders views; mq-agent only
produces the evidence trail (no mutation, no Phase 11 behavior).

The record is inherently public-safe: only sanitized tool names and run metrics —
no prompts, no stdout, no secrets, and the repository as a basename, never an
absolute path. Emission is best-effort: a missing vault or unwritable inbox never
breaks a run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import StepStatus, WorkflowStatus
from .state import WorkflowRun

DEFAULT_VAULT_DIR = Path.home() / "mqobsidian"

#: Coarse intent per known template; falls back to the template name.
_TASK_TYPE: dict[str, str] = {
    "repo-preflight": "preflight",
    "review-and-test": "review",
    "release-ready": "release",
}

_OUTCOME: dict[WorkflowStatus, str] = {
    WorkflowStatus.COMPLETED: "completed",
    WorkflowStatus.FAILED: "failed",
    WorkflowStatus.CANCELLED: "cancelled",
}

#: Steps whose tool actually executed (skipped/pending/blocked excluded).
_RAN = frozenset({StepStatus.PASSED, StepStatus.FAILED})


def default_vault() -> Path:
    env = os.environ.get("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_VAULT_DIR


def inbox_path(vault: Path | None = None) -> Path:
    return (vault or default_vault()) / "memory" / "workflows" / "inbox" / "workflow-observations.jsonl"


def is_terminal(run: WorkflowRun) -> bool:
    return run.plan.status in _OUTCOME


def build_observation(
    run: WorkflowRun, *, duration_ms: float | None = None, approval_count: int = 0
) -> dict[str, Any]:
    """Build a ``workflow-observation.v1`` record from a finished run (pure)."""
    plan = run.plan
    ran = [s for s in plan.steps if s.status in _RAN]
    record: dict[str, Any] = {
        "schema": "workflow-observation.v1",
        "id": f"wfo-{run.run_id}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "producer": "mq-agent",
        # basename only — never leak the absolute local path.
        "repository": Path(plan.repo).name or plan.repo,
        "workflow_id": run.run_id,
        "template": plan.template,
        "task_type": _TASK_TYPE.get(plan.template, plan.template),
        "tool_sequence": [s.tool for s in ran],
        "outcome": _OUTCOME.get(plan.status, "failed"),
        "approval_count": int(approval_count),
    }
    if duration_ms is not None:
        record["duration_ms"] = round(float(duration_ms))
    if record["outcome"] == "failed":
        failed = next((s for s in plan.steps if s.status is StepStatus.FAILED), None)
        if failed is not None:
            record["failed_step"] = failed.id
    return record


def emit_observation(
    run: WorkflowRun,
    *,
    duration_ms: float | None = None,
    approval_count: int = 0,
    vault: Path | None = None,
) -> Path | None:
    """Append one observation to the inbox. Best-effort: returns None on failure."""
    try:
        record = build_observation(
            run, duration_ms=duration_ms, approval_count=approval_count
        )
        path = inbox_path(vault)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path
    except Exception:  # noqa: BLE001 — emission must never break a run
        return None
