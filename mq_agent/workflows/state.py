"""Workflow run state — the in-memory state model and pure transitions (Phase 2).

A ``WorkflowRun`` is an envelope around a Phase 1 ``WorkflowPlan``. The plan is
the immutable-shaped contract (`mq-workflow-plan.v1`); the run adds the runtime
bookkeeping the plan deliberately excludes: ``created_at``, ``updated_at`` and the
owning process id (used to detect a run abandoned by a dead process).

This module is pure: it performs **no** I/O and **no** tool execution. It models
*which state a run is in* and the legal transitions between states. Persistence
lives in ``storage.py``; the runner that actually calls tools arrives in Phase 4.

Resume rules locked here (roadmap Phase 2):
  * ``passed`` steps never re-run.
  * ``failed`` steps re-run only on an explicit resume.
  * a ``running`` run whose process died becomes ``paused``.
  * a ``cancelled`` run cannot be resumed without a new run.
  * a *mutating* step is never re-run automatically.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    StepApproval,
    StepStatus,
    WorkflowPlan,
    WorkflowStatus,
)

#: Result fields/keys that must never be persisted verbatim.
_SECRET_KEY_HINTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "credential",
    "private_key",
    "session",
    "cookie",
    "env",
)
_REDACTED = "***redacted***"

#: Hard cap on any single string persisted into run state. Raw output must not
#: become workflow truth; only a bounded, sanitized summary is kept.
_MAX_STR_LEN = 2000


class WorkflowStateError(Exception):
    """Raised on an illegal state transition or unusable persisted state."""


class WorkflowRun(BaseModel):
    """Runtime envelope around a workflow plan. Carries no execution logic."""

    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    updated_at: datetime
    #: PID of the process that last set the run ``running``; ``None`` otherwise.
    pid: int | None = None
    plan: WorkflowPlan

    # Convenience pass-throughs --------------------------------------------

    @property
    def run_id(self) -> str:
        return self.plan.run_id

    @property
    def status(self) -> WorkflowStatus:
        return self.plan.status

    @property
    def current_step(self) -> str | None:
        return self.plan.current_step


# --- construction ----------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_run(plan: WorkflowPlan) -> WorkflowRun:
    """Create a fresh run envelope for ``plan`` at status ``planned``."""
    now = _now()
    return WorkflowRun(created_at=now, updated_at=now, pid=None, plan=plan)


def touch(run: WorkflowRun) -> WorkflowRun:
    """Bump ``updated_at`` to now. Returns the same instance for chaining."""
    run.updated_at = _now()
    return run


# --- transitions -----------------------------------------------------------


_TERMINAL: frozenset[WorkflowStatus] = frozenset(
    {WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED}
)


def _is_mutating(approval: StepApproval) -> bool:
    """A step is mutating when its approval level implies side effects."""
    return approval in (StepApproval.STEP, StepApproval.FORBIDDEN)


def pause(run: WorkflowRun) -> WorkflowRun:
    """Pause a running run. A non-mutating in-flight step is reset to pending."""
    if run.plan.status is not WorkflowStatus.RUNNING:
        raise WorkflowStateError(
            f"cannot pause run in status {run.plan.status.value!r}"
        )
    run.plan.status = WorkflowStatus.PAUSED
    run.pid = None
    for step in run.plan.steps:
        if step.status is StepStatus.RUNNING and not _is_mutating(step.approval):
            step.status = StepStatus.PENDING
    return touch(run)


def resume(run: WorkflowRun) -> WorkflowRun:
    """Resume a paused or failed run.

    Only a ``paused`` or ``failed`` run can be resumed — resuming a ``running``
    or ``planned`` run would reset steps outside a real resume path.

    Passed steps are preserved. Failed/in-flight *non-mutating* steps are reset
    to ``pending`` so the runner can pick them up again; mutating steps are left
    as-is and never re-run automatically. A cancelled run cannot be resumed.
    """
    if run.plan.status is WorkflowStatus.CANCELLED:
        raise WorkflowStateError("a cancelled run cannot be resumed; start a new run")
    if run.plan.status not in (WorkflowStatus.PAUSED, WorkflowStatus.FAILED):
        raise WorkflowStateError(
            f"only paused or failed runs can be resumed, not {run.plan.status.value!r}"
        )

    for step in run.plan.steps:
        if step.status is StepStatus.PASSED:
            continue  # passed never re-runs
        if _is_mutating(step.approval):
            continue  # mutating step never re-runs automatically
        if step.status in (
            StepStatus.FAILED,
            StepStatus.RUNNING,
            StepStatus.AWAITING_APPROVAL,
        ):
            step.status = StepStatus.PENDING
            step.error = None

    # Clear any stale owning pid; a runner re-claims the run when it starts
    # executing. Otherwise a dead pid left over from before would let
    # reconcile_dead_process immediately re-pause the just-resumed run on load.
    run.pid = None
    run.plan.status = WorkflowStatus.RUNNING
    return touch(run)


def cancel(run: WorkflowRun) -> WorkflowRun:
    """Cancel a run. Non-terminal steps become ``cancelled``; history is kept."""
    if run.plan.status is WorkflowStatus.CANCELLED:
        return run
    if run.plan.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
        raise WorkflowStateError(
            f"cannot cancel run already in terminal status {run.plan.status.value!r}"
        )
    run.plan.status = WorkflowStatus.CANCELLED
    run.pid = None
    for step in run.plan.steps:
        if step.status in (
            StepStatus.PENDING,
            StepStatus.BLOCKED,
            StepStatus.AWAITING_APPROVAL,
            StepStatus.RUNNING,
        ):
            step.status = StepStatus.CANCELLED
    return touch(run)


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check for ``pid`` on POSIX."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    except OSError:
        return False
    return True


def reconcile_dead_process(run: WorkflowRun) -> bool:
    """Demote a ``running`` run to ``paused`` if its owning process is gone.

    Returns ``True`` if the run was changed. A running step owned by the dead
    process is reset to ``pending`` (unless mutating) so it can be resumed.

    A ``running`` run with no recorded ``pid`` (e.g. just resumed, awaiting the
    runner to claim it) is left alone — "dead process" means a pid was recorded
    and is now gone, not merely that ownership is not yet established.
    """
    if run.plan.status is not WorkflowStatus.RUNNING:
        return False
    if run.pid is None or _pid_alive(run.pid):
        return False
    run.plan.status = WorkflowStatus.PAUSED
    run.pid = None
    for step in run.plan.steps:
        if step.status is StepStatus.RUNNING and not _is_mutating(step.approval):
            step.status = StepStatus.PENDING
    touch(run)
    return True


# --- sanitization ----------------------------------------------------------


def _looks_secret(key: str) -> bool:
    low = key.lower()
    return any(hint in low for hint in _SECRET_KEY_HINTS)


def sanitize_result(value: Any) -> Any:
    """Recursively redact secret-looking keys and bound oversized strings.

    Secrets and raw environment must never reach persisted run state, and raw
    output must not become workflow truth — only a bounded summary is kept.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _looks_secret(str(k)):
                out[k] = _REDACTED
            else:
                out[k] = sanitize_result(v)
        return out
    if isinstance(value, list):
        return [sanitize_result(v) for v in value]
    if isinstance(value, str) and len(value) > _MAX_STR_LEN:
        return value[:_MAX_STR_LEN] + "…[truncated]"
    return value


def sanitize_run(run: WorkflowRun) -> WorkflowRun:
    """Sanitize every step's args, result and error in-place before persisting.

    Secrets can ride in tool ``args`` (e.g. a token passed as an argument) and in
    ``error`` (secret-bearing stderr), not only in ``result`` — all three are
    sanitized. Note: redaction is key-name based; value-pattern redaction of
    secrets embedded in free-text strings is a tracked follow-up.
    """
    for step in run.plan.steps:
        step.args = sanitize_result(step.args)
        if step.result is not None:
            step.result = sanitize_result(step.result)
        if step.error is not None:
            step.error = sanitize_result(step.error)
    return run
