"""Tool-policy provider + runner policy-gate tests (Phase 6). No network."""
from __future__ import annotations

import pytest

from mq_agent.workflows import (
    SCHEMA_ID,
    PolicyProvider,
    Runner,
    WorkflowStatus,
    diff_policies,
    new_run,
    resume,
    validate_plan,
)
from mq_agent.workflows.models import StepStatus
from mq_agent.workflows.storage import WorkflowStore


def _policy(name, **over):
    p = {
        "name": name, "class": "D", "write": False, "subprocess": True,
        "network": False, "side_effects": [], "approval": "plan",
        "workflow_allowed": True, "idempotent": True, "retry_safe": True,
    }
    p.update(over)
    return p


def _step(tool, status="pending"):
    return {
        "id": "s1", "name": "s1", "tool": tool, "args": {}, "depends_on": [],
        "condition": "always", "approval": "none", "status": status,
        "attempt": 0, "result": None, "error": None,
    }


def _plan(tool, status="planned", step_status="pending"):
    return validate_plan({
        "schema": SCHEMA_ID, "run_id": "run_20260626_001", "template": "t",
        "task": "t", "repo": "/tmp/x", "status": status, "current_step": None,
        "max_steps": 6, "max_replans": 0, "steps": [_step(tool, step_status)],
    })


def _step_obj(tool, approval="plan"):
    from mq_agent.workflows.models import WorkflowStep
    return WorkflowStep.model_validate(_step(tool))


class FakeExecutor:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def __call__(self, tool, args, repo):
        self.calls.append(tool)
        return self.results.get(tool, {"ok": True, "summary": "ok"})


# --- provider loading ------------------------------------------------------


def test_load_success_uses_policy_source():
    p = PolicyProvider(fetcher=lambda: [_policy("git_status")])
    p.load()
    assert p.source == "policy"
    assert "git_status" in p.snapshot()


def test_load_unavailable_falls_back():
    def boom():
        raise ConnectionError("mq-mcp not reachable")

    p = PolicyProvider(fetcher=boom)
    p.load()
    assert p.source == "fallback"
    assert p.error and "not reachable" in p.error
    assert p.snapshot() == {}


def test_load_malformed_response_falls_back():
    p = PolicyProvider(fetcher=lambda: [{"no_name": 1}])  # KeyError on 'name'
    p.load()
    assert p.source == "fallback"


def test_load_empty_policy_falls_back():
    p = PolicyProvider(fetcher=lambda: [])
    p.load()
    assert p.source == "fallback"


# --- decisions (policy mode) ----------------------------------------------


def test_decide_allows_read_only_plan_tool():
    p = PolicyProvider(fetcher=lambda: [_policy("git_status")])
    p.load()
    d = p.decide(_step_obj("git_status"))
    assert d.allowed and d.approval == "plan" and d.source == "policy"


def test_decide_denies_unknown_tool():
    p = PolicyProvider(fetcher=lambda: [_policy("git_status")])
    p.load()
    d = p.decide(_step_obj("mystery"))
    assert not d.allowed and "no policy" in d.reason


def test_decide_denies_not_workflow_allowed():
    p = PolicyProvider(fetcher=lambda: [_policy("t", workflow_allowed=False)])
    p.load()
    assert p.decide(_step_obj("t")).allowed is False


def test_decide_denies_forbidden():
    p = PolicyProvider(fetcher=lambda: [_policy("t", approval="forbidden")])
    p.load()
    assert p.decide(_step_obj("t")).allowed is False


def test_decide_denies_mutation_in_read_only():
    p = PolicyProvider(fetcher=lambda: [_policy("t", write=True, approval="step")])
    p.load()
    assert p.decide(_step_obj("t"), read_only=True).allowed is False


# --- decisions (fallback mode) --------------------------------------------


def test_fallback_allows_allowlisted_tool():
    p = PolicyProvider(fetcher=lambda: (_ for _ in ()).throw(RuntimeError("down")))
    p.load()
    d = p.decide(_step_obj("run_mqlaunch_doctor"))  # in ALLOWED_TOOLS
    assert d.allowed and d.source == "fallback" and d.approval == "plan"


def test_fallback_denies_shell_exec():
    p = PolicyProvider(fetcher=lambda: (_ for _ in ()).throw(RuntimeError("down")))
    p.load()
    from mq_agent.workflows.models import WorkflowStep
    step = WorkflowStep.model_construct(tool="shell_exec")
    assert p.decide(step).allowed is False


def test_fallback_denies_unknown_tool():
    p = PolicyProvider(fetcher=lambda: (_ for _ in ()).throw(RuntimeError("down")))
    p.load()
    assert p.decide(_step_obj("mystery")).allowed is False


# --- diff_policies ---------------------------------------------------------


def test_diff_detects_changed_policy():
    snap = {"t": _policy("t", approval="plan")}
    cur = {"t": _policy("t", approval="none")}
    assert diff_policies(snap, cur, {"t"}) == ["t"]


def test_diff_ignores_unchanged():
    snap = {"t": _policy("t")}
    cur = {"t": _policy("t")}
    assert diff_policies(snap, cur, {"t"}) == []


def test_diff_ignores_tool_missing_from_current():
    snap = {"t": _policy("t")}
    assert diff_policies(snap, {}, {"t"}) == []  # became unavailable, not "drift"


# --- runner integration: drift stops a resumed run -------------------------


def test_policy_drift_stops_resumed_run(tmp_path):
    store = WorkflowStore(base_dir=tmp_path / "wf")
    # First run fails so resume is valid; snapshot captured under policy v1.
    p1 = PolicyProvider(fetcher=lambda: [_policy("run_mqlaunch_doctor")])
    run = new_run(_plan("run_mqlaunch_doctor"))
    ex = FakeExecutor({"run_mqlaunch_doctor": {"ok": False, "summary": "fail"}})
    Runner(store, ex, policy_provider=p1).run(run)
    assert run.status is WorkflowStatus.FAILED
    assert run.policy_snapshot  # snapshot taken

    # Resume with a CHANGED policy for the same tool -> drift -> stop.
    resume(run)
    store.save_run(run)
    p2 = PolicyProvider(fetcher=lambda: [_policy("run_mqlaunch_doctor", approval="none")])
    ex2 = FakeExecutor()
    Runner(store, ex2, policy_provider=p2).run(run)
    assert run.status is WorkflowStatus.FAILED
    assert ex2.calls == []  # never executed after detecting drift
    assert "policy changed" in (run.summary.get("error") or "")
