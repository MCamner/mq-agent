"""Semantic repository memory helpers for mq-agent.

Conservative by design: never uploads silently, always reports state explicitly.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SemanticMemoryStatus:
    enabled: bool
    vector_store_id: str | None
    repo_path: str
    repo_signal_available: bool
    status: str


@dataclass(frozen=True)
class DiagnosticItem:
    ok: bool
    label: str
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class DoctorReport:
    items: list[DiagnosticItem] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(item.ok for item in self.items)


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


def doctor(repo_path: str | Path = ".") -> DoctorReport:
    """Diagnose semantic memory environment and return actionable findings."""
    repo = Path(repo_path).resolve()
    items: list[DiagnosticItem] = []

    vs_id = get_vector_store_id()
    if vs_id:
        items.append(DiagnosticItem(ok=True, label="OPENAI_VECTOR_STORE_ID", detail=vs_id))
    else:
        raw = os.getenv("OPENAI_VECTOR_STORE_ID", "")
        detail = "(whitespace-only)" if raw.strip() == "" and raw else "(not set)"
        items.append(DiagnosticItem(
            ok=False,
            label="OPENAI_VECTOR_STORE_ID",
            detail=detail,
            fix="export OPENAI_VECTOR_STORE_ID=vs_...",
        ))

    has_rs = repo_signal_available()
    if has_rs:
        items.append(DiagnosticItem(ok=True, label="repo-signal", detail="available"))
    else:
        items.append(DiagnosticItem(
            ok=False,
            label="repo-signal",
            detail="not found",
            fix="uv pip install repo-signal",
        ))

    repo_ok = repo.exists() and repo.is_dir()
    items.append(DiagnosticItem(
        ok=repo_ok,
        label="repo path",
        detail=str(repo),
        fix="" if repo_ok else f"path does not exist: {repo}",
    ))

    return DoctorReport(items=items)
