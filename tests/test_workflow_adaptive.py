"""Limited adaptive planning tests (Phase 10).

Proves the safety boundary: the validator denies every forbidden move, allows the
four permitted ones only under their conditions, the DefaultReplanner makes only
the two evidence-free moves, and the runner applies at most one validated move
while staying inside every existing gate. ``max_replans=0`` is a regression lock
on Phase 6 behavior.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mq_agent.workflows import (
    SCHEMA_ID,
    DefaultReplanner,
    PolicyProvider,
    ReplanMove,
    ReplanProposal,
    Runner,
    WorkflowStatus,
    apply_replan,
    new_run,
    validate_plan,
    validate_replan,
)
from mq_agent.workflows.models import StepStatus
from mq_agent.workflows.storage import WorkflowStore


# --- helpers ---------------------------------------------------------------


class FakeExecutor:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls: list[str] = []

    def __call__(self, tool, args, repo):
        self.calls.append(tool)
        return self.results.get(tool, {"ok": True, "summary": f"{tool} ok"})


def _policy(name, *, approval="plan", write=False):
    return {
        "name": name, "class": "A" if not write else "C", "write": write,
        "subprocess": True, "network": False, "side_effects": [],
        "approval": approval, "workflow_allowed": True, "idempotent": not write,
        "retry_safe": True,
    }


def _provider(*names, extra=None):
    pols = [_policy(n) for n in names] + list(extra or [])
    return PolicyProvider(fetcher=lambda: pols)


def _step(step_id, tool, *, depends_on=None, condition="always", approval="none", status="pending"):
    return {
        "id": step_id, "name": f"Step {step_id}", "tool": tool, "args": {},
        "depends_on": depends_on or [], "condition": condition, "approval": approval,
        "status": status, "attempt": 0, "result": None, "error": None,
    }


def _plan(steps, *, max_steps=6, max_replans=1):
    return validate_plan({
        "schema": SCHEMA_ID, "run_id": "run_20260628_001", "template": "repo-preflight",
        "task": "t", "repo": "/repo", "status": "planned", "current_step": None,
        "max_steps": max_steps, "max_replans": max_replans, "steps": steps,
    })


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(base_dir=tmp_path / "wf")


# --- schema / model cap ----------------------------------------------------


def test_max_replans_one_accepted_two_rejected():
    _plan([_step("a", "git_status")], max_replans=1)  # ok
    with pytest.raises(ValidationError):
        _plan([_step("a", "git_status")], max_replans=2)


# --- validator: global budget ----------------------------------------------


def test_disabled_when_max_replans_zero():
    plan = _plan([_step("a", "git_status")], max_replans=0)
    run = new_run(plan)
    d = validate_replan(ReplanProposal(move=ReplanMove.STOP_EARLY), plan, run, policy_provider=_provider("git_status"))
    assert not d.allowed and "disabled" in d.reason


def test_budget_exhausted():
    plan = _plan([_step("a", "git_status")], max_replans=1)
    run = new_run(plan)
    run.replans_used = 1
    d = validate_replan(ReplanProposal(move=ReplanMove.STOP_EARLY), plan, run, policy_provider=_provider("git_status"))
    assert not d.allowed and "budget" in d.reason


# --- validator: SKIP_STEP --------------------------------------------------


def test_skip_unknown_step_denied():
    plan = _plan([_step("a", "git_status")])
    d = validate_replan(ReplanProposal(move=ReplanMove.SKIP_STEP, step_id="nope"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert not d.allowed and "unknown step" in d.reason


def test_skip_non_pending_denied():
    plan = _plan([_step("a", "git_status", status="passed")])
    d = validate_replan(ReplanProposal(move=ReplanMove.SKIP_STEP, step_id="a"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert not d.allowed and "pending" in d.reason


def test_skip_step_declaring_step_approval_denied():
    # Policy is read-only, but the step itself declares step-level approval.
    plan = _plan([_step("a", "git_status", approval="step")])
    d = validate_replan(ReplanProposal(move=ReplanMove.SKIP_STEP, step_id="a"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert not d.allowed and "read-only" in d.reason


def test_skip_mutating_step_denied():
    plan = _plan([_step("a", "update_repo_file")])
    prov = _provider(extra=[_policy("update_repo_file", approval="step", write=True)])
    d = validate_replan(ReplanProposal(move=ReplanMove.SKIP_STEP, step_id="a"), plan, new_run(plan), policy_provider=prov)
    assert not d.allowed


def test_skip_read_only_step_allowed():
    plan = _plan([_step("a", "git_status")])
    d = validate_replan(ReplanProposal(move=ReplanMove.SKIP_STEP, step_id="a"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert d.allowed


# --- validator: ADD_DIAGNOSTIC ---------------------------------------------


def test_add_non_diagnostic_tool_denied():
    plan = _plan([_step("a", "git_status")])
    new = _step("diag", "run_tests")
    d = validate_replan(ReplanProposal(move=ReplanMove.ADD_DIAGNOSTIC, step=new), plan, new_run(plan), policy_provider=_provider("git_status", "run_tests"))
    assert not d.allowed and "diagnostic tool" in d.reason


def test_add_approval_escalation_denied():
    plan = _plan([_step("a", "git_status")])
    new = _step("diag", "git_diff", approval="step")
    d = validate_replan(ReplanProposal(move=ReplanMove.ADD_DIAGNOSTIC, step=new), plan, new_run(plan), policy_provider=_provider("git_status", "git_diff"))
    assert not d.allowed and "escalate" in d.reason


def test_add_shell_exec_denied():
    plan = _plan([_step("a", "git_status")])
    new = _step("diag", "shell_exec")
    d = validate_replan(ReplanProposal(move=ReplanMove.ADD_DIAGNOSTIC, step=new), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert not d.allowed and "invalid diagnostic step" in d.reason


def test_add_exceeding_max_steps_denied():
    steps = [_step("a", "git_status"), _step("b", "git_diff"), _step("c", "repo_signal_status")]
    plan = _plan(steps, max_steps=3)
    new = _step("d", "git_status")
    d = validate_replan(ReplanProposal(move=ReplanMove.ADD_DIAGNOSTIC, step=new), plan, new_run(plan), policy_provider=_provider("git_status", "git_diff", "repo_signal_status"))
    assert not d.allowed and "invalid" in d.reason


def test_add_diagnostic_allowed():
    plan = _plan([_step("a", "git_status")], max_steps=4)
    new = _step("diag", "git_diff")
    d = validate_replan(ReplanProposal(move=ReplanMove.ADD_DIAGNOSTIC, step=new), plan, new_run(plan), policy_provider=_provider("git_status", "git_diff"))
    assert d.allowed


# --- validator: CHOOSE_TEMPLATE / STOP_EARLY -------------------------------


def test_choose_unknown_template_denied():
    plan = _plan([_step("a", "git_status")])
    d = validate_replan(ReplanProposal(move=ReplanMove.CHOOSE_TEMPLATE, template="nope"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert not d.allowed and "unknown template" in d.reason


def test_choose_after_execution_denied():
    plan = _plan([_step("a", "git_status", status="passed")])
    d = validate_replan(ReplanProposal(move=ReplanMove.CHOOSE_TEMPLATE, template="release-ready"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert not d.allowed and "before execution" in d.reason


def test_choose_known_template_allowed():
    plan = _plan([_step("a", "git_status")])
    d = validate_replan(ReplanProposal(move=ReplanMove.CHOOSE_TEMPLATE, template="release-ready"), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert d.allowed


def test_stop_early_allowed():
    plan = _plan([_step("a", "git_status")])
    d = validate_replan(ReplanProposal(move=ReplanMove.STOP_EARLY), plan, new_run(plan), policy_provider=_provider("git_status"))
    assert d.allowed


# --- apply -----------------------------------------------------------------


def test_apply_skip_increments_budget_and_marks_skipped():
    plan = _plan([_step("a", "git_status")])
    run = new_run(plan)
    apply_replan(ReplanProposal(move=ReplanMove.SKIP_STEP, step_id="a"), plan, run)
    assert plan.steps[0].status is StepStatus.SKIPPED
    assert run.replans_used == 1


def test_apply_stop_early_skips_all_pending():
    plan = _plan([_step("a", "git_status", status="passed"), _step("b", "git_diff")])
    run = new_run(plan)
    apply_replan(ReplanProposal(move=ReplanMove.STOP_EARLY), plan, run)
    assert plan.steps[0].status is StepStatus.PASSED  # untouched
    assert plan.steps[1].status is StepStatus.SKIPPED
    assert run.replans_used == 1


def test_apply_choose_template_raises():
    plan = _plan([_step("a", "git_status")])
    with pytest.raises(ValueError):
        apply_replan(ReplanProposal(move=ReplanMove.CHOOSE_TEMPLATE, template="release-ready"), plan, new_run(plan))


# --- DefaultReplanner ------------------------------------------------------


def test_default_proposes_skip_for_redundant_diagnostic():
    plan = _plan([_step("a", "git_status", status="passed"), _step("b", "git_status")])
    p = DefaultReplanner().propose(new_run(plan), plan, plan.steps[0])
    assert p is not None and p.move is ReplanMove.SKIP_STEP and p.step_id == "b"


def test_default_proposes_stop_when_nothing_runnable():
    # b depends on a which was skipped → b can never satisfy all_deps_passed.
    plan = _plan([
        _step("a", "git_status", status="skipped"),
        _step("b", "git_diff", depends_on=["a"], condition="all_deps_passed"),
    ])
    p = DefaultReplanner().propose(new_run(plan), plan, None)
    assert p is not None and p.move is ReplanMove.STOP_EARLY


def test_default_returns_none_when_budget_used():
    plan = _plan([_step("a", "git_status", status="passed"), _step("b", "git_status")])
    run = new_run(plan)
    run.replans_used = 1
    assert DefaultReplanner().propose(run, plan, None) is None


def test_default_never_proposes_add_or_choose():
    plan = _plan([_step("a", "git_status", status="passed"), _step("b", "run_tests")])
    p = DefaultReplanner().propose(new_run(plan), plan, plan.steps[0])
    assert p is None  # run_tests is not a diagnostic tool → no redundant-skip


# --- runner integration ----------------------------------------------------


def test_runner_applies_one_safe_move(store):
    plan = _plan([_step("a", "git_status"), _step("b", "git_status")], max_steps=4)
    run = new_run(plan)
    ex = FakeExecutor()
    runner = Runner(store, ex, policy_provider=_provider("git_status"), replanner=DefaultReplanner())
    runner.run(run)
    assert run.plan.status is WorkflowStatus.COMPLETED
    assert ex.calls == ["git_status"]  # second git_status was skipped, not run
    assert run.plan.steps[1].status is StepStatus.SKIPPED
    assert run.replans_used == 1
    assert run.summary is not None
    assert run.summary["adaptive"]["replans_used"] == 1


def test_runner_no_adaptivity_when_disabled(store):
    plan = _plan([_step("a", "git_status"), _step("b", "git_status")], max_steps=4, max_replans=0)
    run = new_run(plan)
    ex = FakeExecutor()
    runner = Runner(store, ex, policy_provider=_provider("git_status"), replanner=DefaultReplanner())
    runner.run(run)
    assert run.plan.status is WorkflowStatus.COMPLETED
    assert ex.calls == ["git_status", "git_status"]  # both ran — no replan
    assert run.replans_used == 0


def test_runner_static_when_no_replanner(store):
    plan = _plan([_step("a", "git_status"), _step("b", "git_status")], max_steps=4)
    run = new_run(plan)
    ex = FakeExecutor()
    Runner(store, ex, policy_provider=_provider("git_status")).run(run)
    assert ex.calls == ["git_status", "git_status"]  # Phase 6 behavior unchanged
    assert run.replans_used == 0
