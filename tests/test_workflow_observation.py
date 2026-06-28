"""Workflow observation emission tests.

mq-agent emits one sanitized ``workflow-observation.v1`` record after a terminal
run. Proves the record shape, public-safety (basename repo, known keys only),
best-effort emission, and the runner integration (emitted once on a terminal run,
never when no observer is wired).
"""
from __future__ import annotations

import json
from pathlib import Path

from mq_agent.workflows import (
    SCHEMA_ID,
    PolicyProvider,
    Runner,
    build_observation,
    emit_observation,
    inbox_path,
    new_run,
    validate_plan,
)
from mq_agent.workflows.models import StepStatus, WorkflowStatus
from mq_agent.workflows.storage import WorkflowStore


# --- helpers ---------------------------------------------------------------


class FakeExecutor:
    def __init__(self, results=None):
        self.results = results or {}

    def __call__(self, tool, args, repo):
        return self.results.get(tool, {"ok": True, "summary": f"{tool} ok"})


def _policy(name):
    return {
        "name": name, "class": "A", "write": False, "subprocess": True,
        "network": False, "side_effects": [], "approval": "plan",
        "workflow_allowed": True, "idempotent": True, "retry_safe": True,
    }


def _provider(*names):
    return PolicyProvider(fetcher=lambda: [_policy(n) for n in names])


def _step(step_id, tool, *, depends_on=None, condition="always", status="pending"):
    return {
        "id": step_id, "name": f"Step {step_id}", "tool": tool, "args": {},
        "depends_on": depends_on or [], "condition": condition, "approval": "plan",
        "status": status, "attempt": 0, "result": None, "error": None,
    }


def _plan(steps, *, template="repo-preflight", status="planned", repo="/Users/mansys/macos-scripts"):
    return validate_plan({
        "schema": SCHEMA_ID, "run_id": "run_20260628_001", "template": template,
        "task": "t", "repo": repo, "status": status, "current_step": None,
        "max_steps": 6, "max_replans": 0, "steps": steps,
    })


_REQUIRED = {
    "schema", "id", "timestamp", "producer", "repository",
    "workflow_id", "template", "task_type", "tool_sequence", "outcome",
}
_OPTIONAL = {"failed_step", "duration_ms", "approval_count", "tags", "metadata"}


# --- build_observation -----------------------------------------------------


def test_build_completed_record_shape():
    plan = _plan([
        _step("a", "git_status", status="passed"),
        _step("b", "git_diff", status="passed"),
    ], status="completed")
    rec = build_observation(new_run(plan), duration_ms=1234.6, approval_count=1)
    assert rec["schema"] == "workflow-observation.v1"
    assert rec["producer"] == "mq-agent"
    assert rec["repository"] == "macos-scripts"  # basename, not abs path
    assert rec["template"] == "repo-preflight"
    assert rec["task_type"] == "preflight"
    assert rec["tool_sequence"] == ["git_status", "git_diff"]
    assert rec["outcome"] == "completed"
    assert rec["duration_ms"] == 1235  # rounded
    assert rec["approval_count"] == 1
    assert "failed_step" not in rec


def test_build_excludes_skipped_steps():
    plan = _plan([
        _step("a", "git_status", status="passed"),
        _step("b", "git_diff", status="skipped"),
    ], status="completed")
    rec = build_observation(new_run(plan))
    assert rec["tool_sequence"] == ["git_status"]


def test_build_failed_sets_failed_step_and_outcome():
    plan = _plan([
        _step("a", "git_status", status="passed"),
        _step("b", "git_diff", status="failed"),
    ], status="failed")
    rec = build_observation(new_run(plan))
    assert rec["outcome"] == "failed"
    assert rec["failed_step"] == "b"


def test_task_type_falls_back_to_template_name():
    plan = _plan([_step("a", "git_status", status="passed")], template="custom-thing", status="completed")
    rec = build_observation(new_run(plan))
    assert rec["task_type"] == "custom-thing"


def test_record_is_public_safe():
    plan = _plan([_step("a", "git_status", status="passed")], status="completed")
    rec = build_observation(new_run(plan), duration_ms=10, approval_count=1)
    assert set(rec) <= _REQUIRED | _OPTIONAL  # only known keys
    blob = json.dumps(rec)
    assert "/Users/" not in blob  # no absolute path leaks


# --- emit_observation ------------------------------------------------------


def test_emit_appends_jsonl_to_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(tmp_path))
    plan = _plan([_step("a", "git_status", status="passed")], status="completed")
    path = emit_observation(new_run(plan), duration_ms=5, approval_count=1)
    assert path == inbox_path()
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["schema"] == "workflow-observation.v1"

    # A second emission appends, not overwrites.
    emit_observation(new_run(plan), duration_ms=6, approval_count=1)
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_emit_is_best_effort(tmp_path, monkeypatch):
    # Point the vault at a path whose parent is a file → mkdir fails → returns None.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(blocker))
    plan = _plan([_step("a", "git_status", status="passed")], status="completed")
    assert emit_observation(new_run(plan)) is None  # no raise


# --- runner integration ----------------------------------------------------


def test_runner_calls_observer_once_on_terminal_run(tmp_path):
    store = WorkflowStore(base_dir=tmp_path / "wf")
    plan = _plan([_step("a", "git_status"), _step("b", "git_status")])
    run = new_run(plan)
    seen = []
    Runner(
        store, FakeExecutor(), policy_provider=_provider("git_status"),
        observer=lambda r, meta: seen.append((r.status, meta)),
    ).run(run)
    assert run.plan.status is WorkflowStatus.COMPLETED
    assert len(seen) == 1
    status, meta = seen[0]
    assert status is WorkflowStatus.COMPLETED
    assert meta["approval_count"] == 1  # plan approval fired (default approver)
    assert meta["duration_ms"] is not None


def test_runner_no_observer_is_noop(tmp_path):
    store = WorkflowStore(base_dir=tmp_path / "wf")
    plan = _plan([_step("a", "git_status")])
    run = new_run(plan)
    Runner(store, FakeExecutor(), policy_provider=_provider("git_status")).run(run)
    assert run.plan.status is WorkflowStatus.COMPLETED  # unchanged behavior


def test_runner_emits_through_real_emitter(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(tmp_path))
    store = WorkflowStore(base_dir=tmp_path / "wf")
    plan = _plan([_step("a", "git_status")])
    run = new_run(plan)
    Runner(
        store, FakeExecutor(), policy_provider=_provider("git_status"),
        observer=lambda r, meta: emit_observation(
            r, duration_ms=meta["duration_ms"], approval_count=meta["approval_count"]
        ),
    ).run(run)
    rec = json.loads(inbox_path().read_text(encoding="utf-8").strip())
    assert rec["tool_sequence"] == ["git_status"]
    assert rec["outcome"] == "completed"


# --- schema cross-check (best-effort, no hard cross-repo dependency) --------


def test_record_matches_mqobsidian_schema_if_present():
    schema_file = Path.home() / "mqobsidian" / "schemas" / "workflow-observation.v1.json"
    if not schema_file.exists():
        return  # skip silently when the vault isn't checked out
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    plan = _plan([
        _step("a", "git_status", status="passed"),
        _step("b", "git_diff", status="failed"),
    ], status="failed")
    rec = build_observation(new_run(plan), duration_ms=100, approval_count=1)
    assert list(Draft202012Validator(schema).iter_errors(rec)) == []
