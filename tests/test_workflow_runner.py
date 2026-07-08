"""Read-only runner tests (Phase 4 + Phase 6).

Tool execution AND tool policy are injected — no mq-mcp, no network.
"""
from __future__ import annotations

import time

import pytest

from mq_agent.workflows import (
    SCHEMA_ID,
    PolicyProvider,
    Runner,
    WorkflowStatus,
    new_run,
    resume,
    validate_plan,
)
from mq_agent.workflows.models import StepStatus, WorkflowStep
from mq_agent.workflows.storage import WorkflowStore


# --- helpers ---------------------------------------------------------------


class FakeExecutor:
    """Records calls and returns a canned raw result per tool."""

    def __init__(self, results=None, sleep: float = 0.0):
        self.results = results or {}
        self.sleep = sleep
        self.calls: list[str] = []

    def __call__(self, tool, args, repo):
        self.calls.append(tool)
        if self.sleep:
            time.sleep(self.sleep)
        return self.results.get(tool, {"ok": True, "summary": f"{tool} ok"})


def _policy(name, *, workflow_allowed=True, approval="plan", write=False, retry_safe=True):
    return {
        "name": name, "class": "D", "write": write, "subprocess": True,
        "network": False, "side_effects": [], "approval": approval,
        "workflow_allowed": workflow_allowed, "idempotent": not write,
        "retry_safe": retry_safe,
    }


_MQLAUNCH = ["run_mqlaunch_doctor", "run_mqlaunch_selftest", "run_mqlaunch_release_check"]


def _provider(policies=None):
    pols = policies if policies is not None else [_policy(t) for t in _MQLAUNCH]
    return PolicyProvider(fetcher=lambda: list(pols))


def _step(step_id, tool, *, depends_on=None, condition="always", approval="none"):
    return {
        "id": step_id, "name": f"Step {step_id}", "tool": tool, "args": {},
        "depends_on": depends_on or [], "condition": condition, "approval": approval,
        "status": "pending", "attempt": 0, "result": None, "error": None,
    }


def _plan(steps, *, max_steps=6):
    return validate_plan({
        "schema": SCHEMA_ID, "run_id": "run_20260626_001", "template": "repo-preflight",
        "task": "t", "repo": "/Users/mansys/macos-scripts", "status": "planned",
        "current_step": None, "max_steps": max_steps, "max_replans": 0, "steps": steps,
    })


def _preflight_steps():
    return [
        _step("doctor", "run_mqlaunch_doctor"),
        _step("selftest", "run_mqlaunch_selftest", depends_on=["doctor"], condition="all_deps_passed"),
        _step("release_check", "run_mqlaunch_release_check", depends_on=["selftest"], condition="all_deps_passed"),
    ]


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(base_dir=tmp_path / "wf")


def _runner(store, ex, **kw):
    kw.setdefault("policy_provider", _provider())
    return Runner(store, ex, **kw)


# --- happy path ------------------------------------------------------------


def test_steps_run_in_dependency_order(store):
    ex = FakeExecutor()
    run = new_run(_plan(_preflight_steps()))
    _runner(store, ex).run(run)
    assert ex.calls == _MQLAUNCH
    assert run.status is WorkflowStatus.COMPLETED
    assert all(s.status is StepStatus.PASSED for s in run.plan.steps)


def test_persistent_state_has_three_clear_steps(store):
    run = new_run(_plan(_preflight_steps()))
    _runner(store, FakeExecutor()).run(run)
    loaded = store.load_run(run.run_id)
    assert len(loaded.plan.steps) == 3
    assert loaded.summary["ok"] is True
    assert loaded.summary["passed"] == 3
    assert loaded.summary["policy"]["source"] == "policy"


# --- failure / dependencies ------------------------------------------------


def test_failure_stops_workflow_and_blocks_dependents(store):
    ex = FakeExecutor({"run_mqlaunch_selftest": {"ok": False, "summary": "tests failed"}})
    run = new_run(_plan(_preflight_steps()))
    _runner(store, ex).run(run)
    assert run.status is WorkflowStatus.FAILED
    assert run.plan.steps[0].status is StepStatus.PASSED
    assert run.plan.steps[1].status is StepStatus.FAILED
    assert run.plan.steps[2].status is StepStatus.PENDING
    assert "run_mqlaunch_release_check" not in ex.calls


def test_condition_skips_when_dependency_not_passed(store):
    ex = FakeExecutor({"run_mqlaunch_doctor": {"ok": False, "summary": "doctor fail"}})
    run = new_run(_plan(_preflight_steps()))
    _runner(store, ex, stop_on_failure=False).run(run)
    assert run.plan.steps[0].status is StepStatus.FAILED
    assert run.plan.steps[1].status is StepStatus.SKIPPED
    assert run.plan.steps[2].status is StepStatus.SKIPPED
    assert run.status is WorkflowStatus.FAILED


def test_timeout_marks_step_failed(store):
    ex = FakeExecutor(sleep=0.5)
    run = new_run(_plan([_step("doctor", "run_mqlaunch_doctor")]))
    _runner(store, ex, step_timeout=0.05).run(run)
    assert run.plan.steps[0].status is StepStatus.FAILED
    assert run.plan.steps[0].result is not None
    assert run.plan.steps[0].result["code"] == "TIMEOUT"


# --- policy gate (Phase 6) -------------------------------------------------


def test_tool_without_policy_is_denied_before_any_call(store):
    ex = FakeExecutor()
    run = new_run(_plan([_step("x", "totally_made_up_tool")]))
    _runner(store, ex).run(run)  # provider has no policy for that tool
    assert run.status is WorkflowStatus.FAILED
    assert run.plan.steps[0].status is StepStatus.FAILED
    assert ex.calls == []


def test_not_workflow_allowed_is_denied(store):
    ex = FakeExecutor()
    pol = [_policy("blocked_tool", workflow_allowed=False)]
    run = new_run(_plan([_step("x", "blocked_tool")]))
    Runner(store, ex, policy_provider=_provider(pol)).run(run)
    assert ex.calls == []
    assert run.status is WorkflowStatus.FAILED


def test_mutating_tool_denied_in_readonly_runner(store):
    ex = FakeExecutor()
    pol = [_policy("write_tool", write=True, approval="step")]
    run = new_run(_plan([_step("w", "write_tool")]))
    Runner(store, ex, policy_provider=_provider(pol)).run(run)
    assert ex.calls == []
    assert run.status is WorkflowStatus.FAILED


def test_shell_exec_denied_via_policy(store):
    # Bypass the contract (which forbids shell_exec) to prove the runner's gate.
    ex = FakeExecutor()
    run = new_run(_plan([_step("doctor", "run_mqlaunch_doctor")]))
    run.plan.steps[0] = WorkflowStep.model_construct(
        id="evil", name="evil", tool="shell_exec", args={}, depends_on=[],
        condition=run.plan.steps[0].condition, approval=run.plan.steps[0].approval,
        status=StepStatus.PENDING, attempt=0, result=None, error=None,
    )
    _runner(store, ex).run(run)
    assert ex.calls == []
    assert run.status is WorkflowStatus.FAILED


def test_runner_executes_at_most_max_steps(store):
    ex = FakeExecutor()
    steps = [_step(f"s{i}", "run_mqlaunch_doctor") for i in range(7)]
    run = new_run(_plan(steps, max_steps=7))
    _runner(store, ex, max_steps=6).run(run)
    assert len(ex.calls) == 6
    assert run.status is WorkflowStatus.FAILED


# --- plan approval (Phase 6) ----------------------------------------------


def test_plan_approval_denied_blocks_execution(store):
    ex = FakeExecutor()
    run = new_run(_plan(_preflight_steps()))
    Runner(store, ex, policy_provider=_provider(), plan_approver=lambda s: False).run(run)
    assert ex.calls == []
    assert run.status is WorkflowStatus.AWAITING_APPROVAL
    assert run.summary is not None
    assert run.summary["policy"]["plan_approved"] is False


def test_plan_approval_granted_runs(store):
    ex = FakeExecutor()
    run = new_run(_plan(_preflight_steps()))
    Runner(store, ex, policy_provider=_provider(), plan_approver=lambda s: True).run(run)
    assert ex.calls == _MQLAUNCH
    assert run.status is WorkflowStatus.COMPLETED


def test_no_approval_needed_when_all_steps_approval_none(store):
    ex = FakeExecutor()
    pol = [_policy("read_tool", approval="none")]
    run = new_run(_plan([_step("r", "read_tool")]))
    # plan_approver would deny, but it must not be consulted (no plan approval needed)
    Runner(store, ex, policy_provider=_provider(pol), plan_approver=lambda s: False).run(run)
    assert ex.calls == ["read_tool"]
    assert run.status is WorkflowStatus.COMPLETED


# --- resume ----------------------------------------------------------------


def test_resume_does_not_repeat_passed_steps(store):
    fail_ex = FakeExecutor({"run_mqlaunch_selftest": {"ok": False, "summary": "fail"}})
    run = new_run(_plan(_preflight_steps()))
    _runner(store, fail_ex).run(run)
    assert run.status is WorkflowStatus.FAILED

    resume(run)
    store.save_run(run)
    ok_ex = FakeExecutor()
    _runner(store, ok_ex).run(run)

    assert run.status is WorkflowStatus.COMPLETED
    assert "run_mqlaunch_doctor" not in ok_ex.calls
    assert ok_ex.calls == ["run_mqlaunch_selftest", "run_mqlaunch_release_check"]
    assert all(s.status is StepStatus.PASSED for s in run.plan.steps)
