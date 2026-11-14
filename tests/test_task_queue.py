"""Real Git and process tests for cooperative queue ownership and receipts."""
from __future__ import annotations

import json
import multiprocessing
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from mq_agent.task_queue import TaskQueue, TaskQueueError
from mq_agent.verify_changes import verify
from mq_agent.workflows.state import new_run
from mq_agent.workflows.storage import WorkflowStore
from mq_agent.workflows.templates import instantiate


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "queue@example.invalid")
    git(root, "config", "user.name", "Queue Fixture")
    (root / ".mq").mkdir()
    (root / "value.txt").write_text("before\n")
    (root / "check.sh").write_text("exit 0\n")
    config = {"schema": "mq.verification-config.v1", "checks": [
        {"id": "fixture-check", "runner": "bash", "targets": ["check.sh"],
         "paths": ["*"], "timeout_seconds": 3}
    ]}
    (root / ".mq/verification.json").write_text(json.dumps(config))
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root


@pytest.fixture
def queue(tmp_path: Path) -> TaskQueue:
    return TaskQueue(tmp_path / "queue")


def test_list_empty_does_not_create_state(tmp_path):
    queue = TaskQueue(tmp_path / "absent")
    assert queue.list() == []
    assert not (tmp_path / "absent").exists()


def test_persistence_and_isolated_worktree(queue, repo):
    task = queue.add("Fix the fixture", repo, budget_minutes=30)
    assert task["status"] == "queued"
    assert task["base_commit"] == git(repo, "rev-parse", "HEAD")
    claimed = queue.claim(task["id"], "codex")
    worktree = Path(claimed["worktree"])
    assert worktree != repo
    assert git(worktree, "rev-parse", "HEAD") == task["base_commit"]
    assert claimed["branch"] != git(repo, "branch", "--show-current")
    assert claimed["owner"] == "codex"
    assert claimed["budget_minutes"] == 30
    assert TaskQueue(queue.dir).show(task["id"]) == claimed


def test_two_tasks_get_separate_worktrees(queue, repo):
    first = queue.claim(queue.add("First", repo)["id"], "codex")
    second = queue.claim(queue.add("Second", repo)["id"], "claude")
    assert first["worktree"] != second["worktree"]
    assert first["branch"] != second["branch"]


def test_pause_keeps_reservation_and_same_owner_can_resume(queue, repo):
    task = queue.claim(queue.add("First", repo)["id"], "codex")
    queue.pause(task["id"], "codex")
    other = queue.add("Second", repo)
    with pytest.raises(TaskQueueError, match="reserved"):
        queue.claim(other["id"], "claude", Path(task["worktree"]))
    with pytest.raises(TaskQueueError, match="owner"):
        queue.claim(task["id"], "claude")
    resumed = queue.claim(task["id"], "codex")
    assert resumed["status"] == "active"
    assert resumed["worktree"] == task["worktree"]


def test_reject_main_worktree_wrong_repo_and_detached(queue, repo, tmp_path):
    task = queue.add("Task", repo)
    with pytest.raises(TaskQueueError, match="separate"):
        queue.claim(task["id"], "codex", repo)
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    git(wrong, "init", "-q")
    with pytest.raises(TaskQueueError):
        queue.claim(task["id"], "codex", wrong)
    detached = tmp_path / "detached"
    git(repo, "worktree", "add", "--detach", str(detached))
    with pytest.raises(TaskQueueError, match="branch"):
        queue.claim(task["id"], "codex", detached)


def _claim_once(directory: str, task_id: str, worktree: str, owner: str) -> str:
    try:
        TaskQueue(Path(directory)).claim(task_id, owner, Path(worktree))
        return "claimed"
    except TaskQueueError:
        return "refused"


def test_concurrent_processes_cannot_claim_same_task(queue, repo, tmp_path):
    task = queue.add("One task", repo)
    paths = [tmp_path / "worker1", tmp_path / "worker2"]
    for i, path in enumerate(paths):
        git(repo, "worktree", "add", "-b", f"worker-{i}", str(path))
    with ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(_claim_once, str(queue.dir), task["id"], str(p), owner)
                   for p, owner in zip(paths, ["codex", "claude"])]
        assert sorted(f.result(timeout=30) for f in futures) == ["claimed", "refused"]


def test_verification_required_current_and_bound_to_base(queue, repo):
    task = queue.claim(queue.add("Change", repo)["id"], "codex")
    worktree = Path(task["worktree"])
    with pytest.raises(TaskQueueError, match="verification"):
        queue.complete(task["id"], "codex")
    (worktree / "value.txt").write_text("after\n")
    assert verify(worktree, base=task["base_commit"])["status"] == "PASS"
    (worktree / "value.txt").write_text("changed again\n")
    with pytest.raises(TaskQueueError, match="STALE"):
        queue.complete(task["id"], "codex")
    verify(worktree, base=task["base_commit"])
    done = queue.complete(task["id"], "codex")
    assert done["status"] == "completed"
    assert done["verification"]["status"] == "PASS"
    with pytest.raises(TaskQueueError):
        queue.claim(task["id"], "codex")
    assert worktree.exists()


def test_handoff_records_actual_state_and_requires_receiving_agent(queue, repo):
    task = queue.claim(queue.add("Implement then review", repo)["id"], "codex")
    worktree = Path(task["worktree"])
    (worktree / "value.txt").write_text("review this\n")
    handed = queue.handoff(task["id"], "codex", "claude", "Implementation ready", "Review edge cases")
    note = handed["handoffs"][-1]
    assert note["from_owner"] == "codex"
    assert note["to_owner"] == "claude"
    assert note["remaining"] == "Review edge cases"
    assert note["verification"]["status"] == "MISSING"
    assert note["approval_status"] == "not_granted"
    assert "value.txt" in note["changed_files"]
    assert note["head"] == git(worktree, "rev-parse", "HEAD")
    with pytest.raises(TaskQueueError):
        queue.claim(task["id"], "someone-else")
    with pytest.raises(TaskQueueError, match="separate"):
        queue.claim(task["id"], "claude", worktree)
    accepted = queue.claim(task["id"], "claude")
    assert accepted["owner"] == "claude"
    assert accepted["worktree"] != task["worktree"]
    assert accepted["handoffs"] == handed["handoffs"]
    assert accepted["verification"] is None
    assert (worktree / "value.txt").read_text() == "review this\n"


def test_link_existing_workflow_only_for_task_worktree(queue, repo):
    task = queue.claim(queue.add("Review", repo)["id"], "codex")
    store = WorkflowStore(queue.dir.parent / "workflows")
    for run_id, target in [("run_wrong", repo), ("run_right", Path(task["worktree"]))]:
        store.save_run(new_run(instantiate("repo-preflight", repo=str(target), run_id=run_id)))
    with pytest.raises(TaskQueueError, match="worktree"):
        queue.link_run(task["id"], "codex", "run_wrong")
    assert queue.link_run(task["id"], "codex", "run_right")["workflow_run_id"] == "run_right"


def test_cancel_requires_owner_and_retains_worktree(queue, repo):
    task = queue.claim(queue.add("Cancel", repo)["id"], "codex")
    with pytest.raises(TaskQueueError, match="owner"):
        queue.cancel(task["id"], "claude")
    assert queue.cancel(task["id"], "codex")["status"] == "cancelled"
    assert Path(task["worktree"]).exists()


@pytest.mark.parametrize("goal,budget", [("", 60), ("Task", 0), ("Task", -1)])
def test_invalid_add_leaves_no_task(queue, repo, goal, budget):
    with pytest.raises(TaskQueueError):
        queue.add(goal, repo, budget_minutes=budget)
    assert queue.list() == []


def test_concurrent_tasks_cannot_reserve_same_worktree(queue, repo, tmp_path):
    ids = [queue.add(goal, repo)["id"] for goal in ["First", "Second"]]
    worktree = tmp_path / "shared"
    git(repo, "worktree", "add", "-b", "shared", str(worktree))
    with ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(_claim_once, str(queue.dir), task_id, str(worktree), owner)
                   for task_id, owner in zip(ids, ["codex", "claude"])]
        assert sorted(f.result(timeout=30) for f in futures) == ["claimed", "refused"]
    assert len(queue.list()) == 2


def test_missing_workflow_is_queue_error(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    with pytest.raises(TaskQueueError, match="workflow"):
        queue.link_run(task["id"], "codex", "run_missing")


def test_handoff_acceptance_requires_recorded_head(queue, repo, tmp_path):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    root = Path(task["worktree"])
    (root / "value.txt").write_text("committed implementation\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "implementation")
    queue.handoff(task["id"], "codex", "claude", "Done", "Review")
    old = tmp_path / "old-base"
    git(repo, "worktree", "add", "-b", "old-base", str(old), task["base_commit"])
    with pytest.raises(TaskQueueError, match="handoff"):
        queue.claim(task["id"], "claude", old)


def test_changed_handoff_source_is_refused(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    queue.handoff(task["id"], "codex", "claude", "Done", "Review")
    (Path(task["worktree"]) / "value.txt").write_text("new unreviewed edit\n")
    with pytest.raises(TaskQueueError, match="changed"):
        queue.claim(task["id"], "claude")
    assert queue.show(task["id"])["status"] == "handoff"


def test_switched_branch_cannot_resume_or_complete(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    queue.pause(task["id"], "codex")
    root = Path(task["worktree"])
    git(root, "switch", "-qc", "unexpected-branch")
    with pytest.raises(TaskQueueError, match="branch"):
        queue.claim(task["id"], "codex")
    with pytest.raises(TaskQueueError, match="branch"):
        queue.complete(task["id"], "codex")


def test_sender_can_refresh_changed_handoff(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    queue.handoff(task["id"], "codex", "claude", "First", "Review")
    (Path(task["worktree"]) / "value.txt").write_text("updated\n")
    refreshed = queue.handoff(task["id"], "codex", "claude", "Updated", "Review again")
    assert len(refreshed["handoffs"]) == 2
    assert queue.claim(task["id"], "claude")["status"] == "active"


def test_handoff_preserves_unusual_filename_and_untracked_identity(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    name = " leading-space.txt"
    (Path(task["worktree"]) / name).write_text("untracked\n")
    note = queue.handoff(task["id"], "codex", "claude", "Ready", "Review")["handoffs"][-1]
    assert note["changed_files"] == [name]
    (Path(task["worktree"]) / name).write_text("changed untracked\n")
    with pytest.raises(TaskQueueError, match="changed"):
        queue.claim(task["id"], "claude")


def test_handoff_cannot_reuse_sender_worktree_via_subdirectory(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    queue.handoff(task["id"], "codex", "claude", "Ready", "Review")
    with pytest.raises(TaskQueueError, match="separate"):
        queue.claim(task["id"], "claude", Path(task["worktree"]) / ".mq")
    assert queue.show(task["id"])["owner"] == "codex"


def test_handoff_identity_frames_untracked_file_boundaries(queue, repo):
    task = queue.claim(queue.add("Task", repo)["id"], "codex")
    root = Path(task["worktree"])
    (root / "a").write_text("XbY")
    (root / "b").write_text("Z")
    queue.handoff(task["id"], "codex", "claude", "Ready", "Review")
    (root / "a").write_text("X")
    (root / "b").write_text("YbZ")
    with pytest.raises(TaskQueueError, match="changed"):
        queue.claim(task["id"], "claude")
