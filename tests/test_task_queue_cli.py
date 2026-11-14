"""Exercise the queue through the public Typer application, with isolated state."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")
    (root / "a.txt").write_text("baseline\n")
    (root / ".mq").mkdir()
    (root / "tests").mkdir()
    (root / "tests/check.sh").write_text("#!/bin/bash\nexit 0\n")
    config = {"schema": "mq.verification-config.v1", "checks": [
        {"id": "fixture", "runner": "bash", "targets": ["tests/check.sh"],
         "paths": ["a.txt", "tests/*", ".mq/verification.json"], "timeout_seconds": 2}
    ]}
    (root / ".mq/verification.json").write_text(json.dumps(config))
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root


def test_queue_is_discoverable_in_help():
    result = runner.invoke(app, ["queue", "--help"])
    assert result.exit_code == 0, result.output
    for command in ("add", "claim", "handoff", "complete", "link-run"):
        assert command in result.output


def invoke_json(*args: str) -> Any:
    result = runner.invoke(app, ["queue", *args, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_add_list_and_show_share_persisted_state(repo):
    task = invoke_json("add", "Fix the fixture", "--repo", str(repo), "--budget-minutes", "25")
    assert task["status"] == "queued"
    assert task["goal"] == "Fix the fixture"
    assert task["budget_minutes"] == 25
    assert task["base_commit"] == git(repo, "rev-parse", "HEAD")
    shown = invoke_json("show", task["id"])
    assert shown == task
    assert invoke_json("list") == [task]


def test_claim_pause_resume_and_ownership_errors(repo):
    task = invoke_json("add", "Fix the fixture", "--repo", str(repo))
    task_id = task["id"]
    active = invoke_json("claim", task_id, "--owner", "codex")
    assert active["status"] == "active"
    assert active["owner"] == "codex"
    worktree = Path(active["worktree"])
    assert worktree.resolve() != repo.resolve()
    assert (worktree / "a.txt").read_text() == "baseline\n"
    rejected = runner.invoke(app, ["queue", "pause", task_id, "--owner", "claude", "--json"])
    assert rejected.exit_code == 1
    assert rejected.stderr.strip()
    assert rejected.stdout == ""
    assert invoke_json("pause", task_id, "--owner", "codex")["status"] == "paused"
    resumed = invoke_json("claim", task_id, "--owner", "codex")
    assert resumed["status"] == "active"
    assert resumed["worktree"] == str(worktree)


def test_complete_refuses_missing_verification_and_retains_reservation(repo):
    task = invoke_json("add", "Fix the fixture", "--repo", str(repo))
    active = invoke_json("claim", task["id"], "--owner", "codex")
    result = runner.invoke(app, ["queue", "complete", task["id"], "--owner", "codex", "--json"])
    assert result.exit_code == 1
    assert result.stderr.strip()
    assert invoke_json("show", task["id"])["status"] == "active"
    cancelled = invoke_json("cancel", task["id"], "--owner", "codex")
    assert cancelled["status"] == "cancelled"
    assert Path(active["worktree"]).is_dir()


def test_handoff_acceptance_requires_named_agent_and_new_worktree(repo):
    task = invoke_json("add", "Fix the fixture", "--repo", str(repo))
    active = invoke_json("claim", task["id"], "--owner", "codex")
    handoff = invoke_json(
        "handoff", task["id"], "--owner", "codex", "--to", "claude",
        "--summary", "Inspected fixture", "--remaining", "Implement and verify the change",
    )
    assert handoff["status"] == "handoff"
    accepted = invoke_json("claim", task["id"], "--owner", "claude")
    assert accepted["status"] == "active"
    assert accepted["owner"] == "claude"
    assert accepted["worktree"] != active["worktree"]
    assert accepted["handoffs"]


def test_invalid_budget_and_unknown_task_have_clean_errors(repo):
    result = runner.invoke(app, [
        "queue", "add", "Task", "--repo", str(repo), "--budget-minutes", "0", "--json",
    ])
    assert result.exit_code == 1
    assert result.stderr.strip()
    assert result.stdout == ""
    result = runner.invoke(app, ["queue", "show", "missing-task", "--json"])
    assert result.exit_code == 1
    assert result.stderr.strip()
    assert result.stdout == ""


def test_plain_empty_queue_is_readable(repo):
    result = runner.invoke(app, ["queue", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "No tasks."



def test_verify_changes_cli_receipt_completes_task(repo):
    task = invoke_json("add", "Fix the fixture", "--repo", str(repo))
    active = invoke_json("claim", task["id"], "--owner", "codex")
    (Path(active["worktree"]) / "a.txt").write_text("fixed\n")
    result = runner.invoke(app, [
        "verify-changes", active["worktree"], "--base", task["base_commit"], "--json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "PASS"
    completed = invoke_json("complete", task["id"], "--owner", "codex")
    assert completed["status"] == "completed"
    assert completed["verification"]["status"] == "PASS"


def test_link_run_uses_existing_workflow_state(repo):
    from mq_agent.workflows.state import new_run
    from mq_agent.workflows.storage import WorkflowStore
    from mq_agent.workflows.templates import instantiate

    task = invoke_json("add", "Fix the fixture", "--repo", str(repo))
    active = invoke_json("claim", task["id"], "--owner", "codex")
    store = WorkflowStore()
    run_id = store.generate_run_id()
    plan = instantiate("review-and-test", repo=active["worktree"], run_id=run_id)
    store.save_run(new_run(plan))
    linked = invoke_json("link-run", task["id"], run_id, "--owner", "codex")
    assert linked["workflow_run_id"] == run_id
    assert store.load_run(run_id).status.value == "planned"


def test_database_open_error_is_reported_on_stderr(repo):
    from mq_agent.task_queue import TaskQueue

    queue = TaskQueue()
    queue.path.mkdir(parents=True)
    result = runner.invoke(app, ["queue", "add", "Task", "--repo", str(repo), "--json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "database" in result.stderr.lower()
