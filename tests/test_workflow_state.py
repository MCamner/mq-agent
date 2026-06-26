"""State-model and transition tests for workflow runs (Phase 2).

Pure state only — no filesystem, no tool execution.
"""
from __future__ import annotations

import pytest

from mq_agent.workflows import (
    SCHEMA_ID,
    StepStatus,
    WorkflowStateError,
    WorkflowStatus,
    cancel,
    new_run,
    pause,
    reconcile_dead_process,
    resume,
    sanitize_result,
    validate_plan,
)


def _step(step_id, *, approval="none", status="pending", depends_on=None, **over):
    s = {
        "id": step_id,
        "name": f"Step {step_id}",
        "tool": "run_mqlaunch_doctor",
        "args": {},
        "depends_on": depends_on or [],
        "condition": "always",
        "approval": approval,
        "status": status,
        "attempt": 0,
        "result": None,
        "error": None,
    }
    s.update(over)
    return s


def _plan(*, steps=None, status="planned", **over):
    data = {
        "schema": SCHEMA_ID,
        "run_id": "run_20260626_001",
        "template": "repo-preflight",
        "task": "Verify repository readiness",
        "repo": "/Users/mansys/macos-scripts",
        "status": status,
        "current_step": None,
        "max_steps": 6,
        "max_replans": 0,
        "steps": steps if steps is not None else [_step("s1")],
    }
    data.update(over)
    return validate_plan(data)


def _run(**kw):
    return new_run(_plan(**kw))


# --- construction ----------------------------------------------------------


def test_new_run_is_planned_with_timestamps():
    run = _run()
    assert run.status is WorkflowStatus.PLANNED
    assert run.created_at == run.updated_at
    assert run.pid is None
    assert run.run_id == "run_20260626_001"


# --- pause / resume / cancel ----------------------------------------------


def test_pause_requires_running():
    run = _run()  # planned
    with pytest.raises(WorkflowStateError):
        pause(run)


def test_pause_running_resets_in_flight_step():
    run = _run(status="running", steps=[_step("s1", status="running")])
    run.pid = 12345
    pause(run)
    assert run.status is WorkflowStatus.PAUSED
    assert run.pid is None
    assert run.plan.steps[0].status is StepStatus.PENDING


def test_resume_skips_passed_steps_and_resets_failed():
    steps = [_step("s1", status="passed"), _step("s2", status="failed")]
    run = _run(status="paused", steps=steps)
    resume(run)
    assert run.status is WorkflowStatus.RUNNING
    assert run.plan.steps[0].status is StepStatus.PASSED  # never re-runs
    assert run.plan.steps[1].status is StepStatus.PENDING  # reset for re-run
    assert run.plan.steps[1].error is None


def test_resume_never_reruns_mutating_step():
    steps = [_step("s1", status="failed", approval="step")]
    run = _run(status="paused", steps=steps)
    resume(run)
    assert run.plan.steps[0].status is StepStatus.FAILED  # mutating: left as-is


def test_cancelled_run_cannot_be_resumed():
    run = _run(status="cancelled")
    with pytest.raises(WorkflowStateError):
        resume(run)


def test_completed_run_cannot_be_resumed():
    run = _run(status="completed")
    with pytest.raises(WorkflowStateError):
        resume(run)


def test_cancel_marks_non_terminal_steps_cancelled():
    steps = [
        _step("s1", status="passed"),
        _step("s2", status="running"),
        _step("s3", status="pending"),
    ]
    run = _run(status="running", steps=steps)
    cancel(run)
    assert run.status is WorkflowStatus.CANCELLED
    assert run.plan.steps[0].status is StepStatus.PASSED  # history preserved
    assert run.plan.steps[1].status is StepStatus.CANCELLED
    assert run.plan.steps[2].status is StepStatus.CANCELLED


def test_cancel_is_idempotent():
    run = _run(status="cancelled")
    assert cancel(run).status is WorkflowStatus.CANCELLED


# --- dead-process reconciliation ------------------------------------------


def test_dead_process_running_becomes_paused():
    run = _run(status="running", steps=[_step("s1", status="running")])
    run.pid = 2**31 - 1  # a pid that does not exist
    changed = reconcile_dead_process(run)
    assert changed is True
    assert run.status is WorkflowStatus.PAUSED
    assert run.plan.steps[0].status is StepStatus.PENDING


def test_live_process_running_is_left_alone():
    import os

    run = _run(status="running")
    run.pid = os.getpid()  # this test process is alive
    changed = reconcile_dead_process(run)
    assert changed is False
    assert run.status is WorkflowStatus.RUNNING


def test_reconcile_noop_when_not_running():
    run = _run(status="paused")
    assert reconcile_dead_process(run) is False


def test_reconcile_leaves_running_run_with_no_pid_alone():
    # Just-resumed run: running but not yet claimed by a runner process.
    run = _run(status="running")
    run.pid = None
    assert reconcile_dead_process(run) is False
    assert run.status is WorkflowStatus.RUNNING


# --- sanitization ----------------------------------------------------------


def test_sanitize_redacts_secret_keys():
    out = sanitize_result({"api_key": "sk-secret", "summary": "ok", "TOKEN": "abc"})
    assert out["api_key"] == "***redacted***"
    assert out["TOKEN"] == "***redacted***"
    assert out["summary"] == "ok"


def test_sanitize_redacts_nested_secrets():
    out = sanitize_result({"data": {"password": "hunter2", "code": "PASS"}})
    assert out["data"]["password"] == "***redacted***"
    assert out["data"]["code"] == "PASS"


def test_sanitize_truncates_oversized_strings():
    big = "x" * 5000
    out = sanitize_result({"stdout": big})
    assert out["stdout"].endswith("…[truncated]")
    assert len(out["stdout"]) < len(big)
