"""Semantic repository memory helpers for mq-agent.

Conservative by design: never uploads silently, always reports state explicitly.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SemanticMemoryStatus:
    enabled: bool
    vector_store_id: str | None
    repo_path: str
    repo_signal_available: bool
    status: str


def get_vector_store_id() -> str | None:
    value = os.getenv("OPENAI_VECTOR_STORE_ID")
    return value.strip() if value and value.strip() else None


def repo_signal_available() -> bool:
    try:
        result = subprocess.run(
            ["repo-signal", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def status(repo_path: str | Path = ".") -> SemanticMemoryStatus:
    repo = Path(repo_path).resolve()
    vector_store_id = get_vector_store_id()
    has_repo_signal = repo_signal_available()

    if not vector_store_id:
        state = "missing-vector-store"
    elif not has_repo_signal:
        state = "missing-repo-signal"
    else:
        state = "ready"

    return SemanticMemoryStatus(
        enabled=state == "ready",
        vector_store_id=vector_store_id,
        repo_path=str(repo),
        repo_signal_available=has_repo_signal,
        status=state,
    )


def build(
    repo_path: str | Path = ".",
    dry_run: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Upload semantic repo memory through repo-signal. Dry-run by default."""
    repo = Path(repo_path).resolve()
    cmd = ["repo-signal", "semantic-upload"]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
