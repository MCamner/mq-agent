"""Local, cooperative task ownership; never starts an agent or grants approval.

SQLite serializes claims across processes. Paused and offered tasks retain their
worktree reservation. Git worktrees and branches are always retained, including
when a claim fails after Git creation: recovery must never discard user work.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mq_agent.verify_changes import check_receipt
from mq_agent.workflows.state import WorkflowStateError
from mq_agent.workflows.storage import WorkflowStore, default_workflows_dir

_RESERVED = {"active", "paused", "handoff"}
_TERMINAL = {"completed", "cancelled"}
_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_TASK_ID = re.compile(r"task-[0-9a-f]{32}\Z")


class TaskQueueError(ValueError):
    """Invalid task transition, ownership conflict or unavailable local state."""


def _git(repo: Path, *args: str, strip: bool = True) -> str:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.PIPE,
            timeout=30,
        ).decode("utf-8", errors="surrogateescape")
        return output.strip() if strip else output
    except (OSError, subprocess.SubprocessError) as exc:
        raise TaskQueueError("Git operation failed; check repository, worktree and branch") from exc


def _root(path: Path) -> Path:
    return Path(_git(path, "rev-parse", "--show-toplevel")).resolve()


def _common(path: Path) -> Path:
    value = Path(_git(path, "rev-parse", "--git-common-dir"))
    return (value if value.is_absolute() else path / value).resolve()


def _text(value: str, name: str, limit: int = 4000) -> str:
    value = value.strip()
    if not value or len(value) > limit or "\x00" in value:
        raise TaskQueueError(f"{name} must contain 1 to {limit} characters without NUL")
    return value


def _owner(value: str) -> str:
    if not _OWNER.fullmatch(value):
        raise TaskQueueError("owner must be 1-64 letters, digits, underscores or hyphens")
    return value


def _stamp() -> str:
    return datetime.now(UTC).isoformat()


class TaskQueue:
    """One shared local queue, alongside existing WorkflowStore state."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.dir = Path(base_dir) if base_dir is not None else default_workflows_dir().parent / "queue"
        self.path = self.dir / "tasks.sqlite3"

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            connection = sqlite3.connect(self.path, timeout=30)
        except sqlite3.Error as exc:
            raise TaskQueueError("Queue database unavailable or corrupt") from exc
        try:
            self.path.chmod(0o600)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, worktree TEXT, status TEXT NOT NULL,
                payload TEXT NOT NULL)""")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS reserved_worktree
                ON tasks(worktree) WHERE status IN ('active', 'paused', 'handoff')""")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise TaskQueueError("Queue database unavailable or corrupt") from exc
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list(self) -> list[dict[str, Any]]:
        """Read persisted tasks without creating or reconciling state."""
        if not self.path.exists():
            return []
        try:
            connection = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
            try:
                return [json.loads(row[0]) for row in connection.execute(
                    "SELECT payload FROM tasks ORDER BY rowid"
                )]
            finally:
                connection.close()
        except (sqlite3.Error, ValueError) as exc:
            raise TaskQueueError("Queue database unavailable or corrupt") from exc

    def show(self, task_id: str) -> dict[str, Any]:
        self._validate_id(task_id)
        for task in self.list():
            if task["id"] == task_id:
                return task
        raise TaskQueueError("No such task")

    @staticmethod
    def _validate_id(task_id: str) -> None:
        if not _TASK_ID.fullmatch(task_id):
            raise TaskQueueError("Invalid task id")

    def _load(self, connection: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        self._validate_id(task_id)
        row = connection.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskQueueError("No such task")
        try:
            return json.loads(row[0])
        except ValueError as exc:
            raise TaskQueueError("Task record is corrupt") from exc

    @staticmethod
    def _save(connection: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
        task["updated_at"] = _stamp()
        connection.execute(
            "INSERT INTO tasks(id, worktree, status, payload) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET worktree=excluded.worktree, "
            "status=excluded.status, payload=excluded.payload",
            (task["id"], task["worktree"], task["status"], json.dumps(task)),
        )
        return task

    def add(self, goal: str, repo: Path, budget_minutes: int = 60) -> dict[str, Any]:
        goal = _text(goal, "goal")
        if type(budget_minutes) is not int or not 1 <= budget_minutes <= 1440:
            raise TaskQueueError("budget_minutes must be between 1 and 1440")
        root = _root(Path(repo).resolve())
        task: dict[str, Any] = {
            "id": f"task-{uuid.uuid4().hex}", "goal": goal, "repo": str(root),
            "base_commit": _git(root, "rev-parse", "HEAD"),
            "git_common_dir": str(_common(root)), "status": "queued", "owner": None,
            "worktree": None, "branch": None, "budget_minutes": budget_minutes,
            "workflow_run_id": None, "verification": None, "handoffs": [],
            "created_at": _stamp(),
        }
        with self._transaction() as connection:
            return self._save(connection, task)

    @staticmethod
    def _owned(task: dict[str, Any], owner: str, statuses: set[str]) -> None:
        _owner(owner)
        if task["owner"] != owner:
            raise TaskQueueError("Task owner mismatch")
        if task["status"] not in statuses:
            raise TaskQueueError(f"Task is {task['status']}; action is not allowed")

    @staticmethod
    def _worktree(task: dict[str, Any], path: Path) -> tuple[Path, str]:
        root = _root(path)
        if root == Path(task["repo"]) or not (root / ".git").is_file():
            raise TaskQueueError("A separate linked worktree is required")
        if str(_common(root)) != task["git_common_dir"]:
            raise TaskQueueError("Worktree belongs to a different repository")
        registered = {
            Path(field.removeprefix("worktree ")).resolve()
            for field in _git(root, "worktree", "list", "--porcelain", "-z", strip=False).split("\0")
            if field.startswith("worktree ")
        }
        if root not in registered:
            raise TaskQueueError("Worktree is not registered with Git")
        branch = _git(root, "branch", "--show-current")
        if not branch:
            raise TaskQueueError("Worktree must have its own branch")
        if str(root) == task["worktree"] and branch != task["branch"]:
            raise TaskQueueError("Reserved worktree branch has changed")
        _git(root, "merge-base", "--is-ancestor", task["base_commit"], "HEAD")
        return root, branch

    def claim(self, task_id: str, owner: str, worktree: Path | None = None) -> dict[str, Any]:
        owner = _owner(owner)
        with self._transaction() as connection:
            task = self._load(connection, task_id)
            status = task["status"]
            target: Path | None
            if status == "paused":
                self._owned(task, owner, {"paused"})
                if worktree is not None and worktree.resolve() != Path(task["worktree"]):
                    raise TaskQueueError("Resume must use the reserved worktree")
                target = Path(task["worktree"])
            elif status == "handoff":
                if task["handoffs"][-1]["to_owner"] != owner:
                    raise TaskQueueError("Only the receiving owner can accept this handoff")
                self._worktree(task, Path(task["worktree"]))
                note = task["handoffs"][-1]
                current = self._diff_state(task)
                if any(current[key] != note[key] for key in ("head", "branch", "changed_files", "diff_sha256")):
                    raise TaskQueueError("Handoff source changed; sender must refresh the handoff")
                target = worktree
                if target is not None and target.resolve() == Path(task["worktree"]):
                    raise TaskQueueError("Receiving agent needs a separate worktree")
            elif status == "queued":
                target = worktree
            else:
                raise TaskQueueError(f"Task is {status}; it cannot be claimed")

            if target is None:
                target = (self.dir / "worktrees" / task_id / owner).resolve()
                branch = f"mq-task/{task_id}/{owner}"
                if target.exists():
                    raise TaskQueueError(f"Worktree path already exists: {target}; inspect before retry")
                target.parent.mkdir(parents=True, exist_ok=True)
                start = task["handoffs"][-1]["head"] if status == "handoff" else task["base_commit"]
                _git(Path(task["repo"]), "worktree", "add", "-b", branch, str(target), start)
            root, branch = self._worktree(task, target)
            if status == "handoff" and str(root) == task["worktree"]:
                raise TaskQueueError("Receiving agent needs a separate worktree")
            if status == "handoff" and _git(root, "rev-parse", "HEAD") != task["handoffs"][-1]["head"]:
                raise TaskQueueError("Receiving worktree must start at the recorded handoff HEAD")
            reserved = connection.execute(
                "SELECT id FROM tasks WHERE worktree = ? AND id != ? AND status IN ('active','paused','handoff')",
                (str(root), task_id),
            ).fetchone()
            if reserved is not None:
                raise TaskQueueError(f"Worktree is reserved by {reserved[0]}")
            task.update(status="active", owner=owner, worktree=str(root), branch=branch)
            if status != "paused":
                task.update(verification=None, workflow_run_id=None)
            return self._save(connection, task)

    def pause(self, task_id: str, owner: str) -> dict[str, Any]:
        with self._transaction() as connection:
            task = self._load(connection, task_id)
            self._owned(task, owner, {"active"})
            task["status"] = "paused"
            return self._save(connection, task)

    @staticmethod
    def _verification(task: dict[str, Any]) -> dict[str, Any]:
        try:
            receipt = check_receipt(Path(task["worktree"]), base=task["base_commit"])
        except (OSError, ValueError) as exc:
            raise TaskQueueError("Invalid verification receipt; run verify-changes again") from exc
        return {key: receipt[key] for key in (
            "status", "receipt_id", "head", "base", "completed_at", "fingerprint"
        ) if key in receipt}

    @staticmethod
    def _diff_state(task: dict[str, Any]) -> dict[str, Any]:
        root = Path(task["worktree"])
        tracked = _git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", task["base_commit"], "--", strip=False)
        untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", strip=False)
        names = sorted(set(filter(None, (tracked + "\0" + untracked).split("\0"))))
        diff = _git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", task["base_commit"], "--", strip=False)
        entries: list[list[Any]] = []
        for name in filter(None, untracked.split("\0")):
            path = root / name
            if path.is_symlink():
                entries.append([name, "symlink", str(path.readlink())])
            elif path.is_file():
                content = hashlib.sha256()
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(65536), b""):
                        content.update(block)
                entries.append([name, "file", bool(path.stat().st_mode & 0o111), content.hexdigest()])
            else:
                entries.append([name, "other"])
        # Frame each file independently: concatenated names/contents can alias
        # different source states without any SHA-256 collision.
        identity = {"diff": hashlib.sha256(diff.encode("utf-8", errors="surrogateescape")).hexdigest(),
                    "untracked": entries}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode())
        return {
            "head": _git(root, "rev-parse", "HEAD"), "branch": _git(root, "branch", "--show-current"),
            "worktree": str(root), "changed_files": names,
            "diff_sha256": digest.hexdigest(),
            "diff_stat": _git(root, "diff", "--no-ext-diff", "--no-textconv", "--stat", task["base_commit"], "--"),
        }

    def handoff(self, task_id: str, owner: str, to_owner: str, summary: str, remaining: str) -> dict[str, Any]:
        _owner(to_owner)
        if owner == to_owner:
            raise TaskQueueError("Handoff requires a different receiving owner")
        summary, remaining = _text(summary, "summary"), _text(remaining, "remaining")
        with self._transaction() as connection:
            task = self._load(connection, task_id)
            self._owned(task, owner, {"active", "paused", "handoff"})
            self._worktree(task, Path(task["worktree"]))
            receipt = self._verification(task)
            task["handoffs"].append({
                **self._diff_state(task), "from_owner": owner, "to_owner": to_owner,
                "summary": summary, "remaining": remaining, "goal": task["goal"],
                "verification": receipt, "workflow_run_id": task["workflow_run_id"],
                "approval_status": "not_granted", "created_at": _stamp(),
            })
            task.update(status="handoff", verification=receipt)
            return self._save(connection, task)

    def link_run(self, task_id: str, owner: str, run_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise TaskQueueError("Invalid workflow run id")
        with self._transaction() as connection:
            task = self._load(connection, task_id)
            self._owned(task, owner, {"active", "paused"})
            store = WorkflowStore(self.dir.parent / "workflows")
            try:
                run = store.load_run(run_id)
            except (WorkflowStateError, ValueError, OSError) as exc:
                raise TaskQueueError("Linked workflow run is missing or invalid") from exc
            if Path(run.plan.repo).resolve() != Path(task["worktree"]):
                raise TaskQueueError("Workflow run must target the task worktree")
            task["workflow_run_id"] = run_id
            return self._save(connection, task)

    def complete(self, task_id: str, owner: str) -> dict[str, Any]:
        with self._transaction() as connection:
            task = self._load(connection, task_id)
            self._owned(task, owner, {"active", "paused"})
            self._worktree(task, Path(task["worktree"]))
            receipt = self._verification(task)
            if receipt["status"] != "PASS":
                raise TaskQueueError(f"Current PASS verification required; status is {receipt['status']}")
            task.update(status="completed", verification=receipt)
            return self._save(connection, task)

    def cancel(self, task_id: str, owner: str | None = None) -> dict[str, Any]:
        with self._transaction() as connection:
            task = self._load(connection, task_id)
            if task["status"] in _TERMINAL:
                raise TaskQueueError(f"Task is already {task['status']}")
            if task["owner"] is not None:
                self._owned(task, owner or "", _RESERVED)
            task["status"] = "cancelled"
            return self._save(connection, task)
