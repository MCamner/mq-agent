"""Workflow run persistence (Phase 2).

Runs are stored as JSON files under, by default::

    ${XDG_STATE_HOME:-$HOME/.local/state}/mq-agent/workflows/
    ├── run_20260626_001.json
    ├── run_20260626_002.json
    └── latest.json            # pointer: {"run_id": "..."}

State is deliberately kept **outside any target repository and outside Git** —
it lives in the user state directory, never in the repo being orchestrated.

Writes are atomic (temp file in the same directory + ``os.replace``) so a crash
mid-write never leaves a half-written run file. Secrets and oversized output are
sanitized (see ``state.sanitize_run``) before anything touches disk. This module
performs persistence only — no tool execution.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import state as _state
from .state import WorkflowRun, WorkflowStateError

_LATEST = "latest.json"
_RUN_GLOB = "run_*.json"


def default_workflows_dir() -> Path:
    """Return the default state directory, honoring ``XDG_STATE_HOME``."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "mq-agent" / "workflows"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write ``payload`` as pretty JSON to ``path`` atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
        # Durability: fsync the containing directory so the rename itself
        # survives a crash on filesystems that require it.
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except BaseException:
        # Best-effort cleanup; never leave a stray temp file on failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class WorkflowStore:
    """Filesystem-backed store for workflow runs.

    Inject ``base_dir`` (e.g. a tmp path) in tests so state never lands in a
    real home directory or repo.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.dir = Path(base_dir) if base_dir is not None else default_workflows_dir()

    # -- paths ----------------------------------------------------------

    def _run_path(self, run_id: str) -> Path:
        return self.dir / f"{run_id}.json"

    def _latest_path(self) -> Path:
        return self.dir / _LATEST

    # -- ids ------------------------------------------------------------

    def generate_run_id(self, now: datetime | None = None) -> str:
        """Generate a date-sequenced run id like ``run_20260626_001``.

        The sequence is derived from existing run files on disk, so two ids
        generated around the same time never collide once the first is saved.
        """
        now = now or datetime.now(timezone.utc)
        date = now.strftime("%Y%m%d")
        prefix = f"run_{date}_"
        seq = 0
        if self.dir.exists():
            for p in self.dir.glob(f"{prefix}*.json"):
                tail = p.stem[len(prefix):]
                if tail.isdigit():
                    seq = max(seq, int(tail))
        return f"{prefix}{seq + 1:03d}"

    # -- write ----------------------------------------------------------

    def save_run(self, run: WorkflowRun) -> WorkflowRun:
        """Sanitize, stamp ``updated_at`` and atomically persist ``run``."""
        _state.sanitize_run(run)
        _state.touch(run)
        payload = run.model_dump(mode="json", by_alias=True)
        _atomic_write_json(self._run_path(run.run_id), payload)
        _atomic_write_json(self._latest_path(), {"run_id": run.run_id})
        return run

    # -- read -----------------------------------------------------------

    def _load_raw(self, run_id: str) -> WorkflowRun:
        path = self._run_path(run_id)
        if not path.exists():
            raise WorkflowStateError(f"no such run: {run_id!r} (looked in {path})")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowStateError(
                f"run file {path} is corrupt JSON: {exc}"
            ) from exc
        return WorkflowRun.model_validate(data)

    def load_run(self, run_id: str) -> WorkflowRun:
        """Load a run, reconciling a dead-process ``running`` run to ``paused``.

        If reconciliation changes the run, the corrected state is persisted so
        on-disk truth stays consistent.
        """
        run = self._load_raw(run_id)
        if _state.reconcile_dead_process(run):
            self.save_run(run)
        return run

    def list_runs(self) -> list[WorkflowRun]:
        """Return all parseable runs, newest first. Corrupt files are skipped."""
        if not self.dir.exists():
            return []
        runs: list[WorkflowRun] = []
        for p in sorted(self.dir.glob(_RUN_GLOB)):
            try:
                runs.append(self._load_raw(p.stem))
            except WorkflowStateError:
                continue  # a single bad file must not break listing
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs

    def latest_run(self) -> WorkflowRun | None:
        """Return the most recently saved run, or ``None`` if there is none."""
        latest = self._latest_path()
        if not latest.exists():
            return None
        try:
            pointer = json.loads(latest.read_text(encoding="utf-8"))
            run_id = pointer["run_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None
        try:
            return self.load_run(run_id)
        except WorkflowStateError:
            return None

    # -- transitions persisted -----------------------------------------

    def cancel_run(self, run_id: str) -> WorkflowRun:
        """Load, cancel and persist a run."""
        run = self.load_run(run_id)
        _state.cancel(run)
        return self.save_run(run)
