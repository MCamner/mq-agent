"""Canonical target identity, independent of launcher and MCP working directories."""

from __future__ import annotations

from pathlib import Path
import subprocess

from .state import WorkflowRun


def resolve_target(repo: str) -> dict[str, str]:
    path = Path(repo).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError("workflow target must be a Git repository directory")
    try:
        root = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except subprocess.SubprocessError as exc:
        raise ValueError(
            "workflow target must have a readable Git root and HEAD"
        ) from exc
    return {"root": str(Path(root).resolve()), "commit": commit}


def bind_target(run: WorkflowRun) -> None:
    identity = resolve_target(run.plan.repo)
    run.plan.repo = identity["root"]
    run.repo_identity = identity
    if run.runtime_identity is None:
        from importlib.metadata import version

        source_root = Path(__file__).resolve().parents[2]
        try:
            runtime_commit = resolve_target(str(source_root))["commit"]
        except (ValueError, OSError):
            runtime_commit = None
        run.runtime_identity = {
            "name": "mq-agent",
            "version": version("mq-agent"),
            "commit": runtime_commit,
        }


def verify_target(run: WorkflowRun) -> None:
    if run.repo_identity is None:
        raise ValueError("legacy run has no bound target; start a new run")
    if resolve_target(run.plan.repo) != run.repo_identity:
        raise ValueError("workflow target root or commit changed; start a new run")
