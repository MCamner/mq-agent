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
    vector_store_id: str
    vector_store_source: str
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


#: The store mq-agent owns. Declared here rather than recovered from the
#: machine: the id used to live only in gitignored `.env` files, so with none
#: present mq-agent had no memory at all while the macos-scripts shell
#: consumers fell back to a different store. A store id is an addressable
#: name, not a credential — the API key stays out of the repository.
CANONICAL_VECTOR_STORE_ID = "vs_69ffa9a4ef5c81919d7d237c3ecdc260"


def resolve_vector_store_id() -> tuple[str, str]:
    """Return the store to use and where its id came from.

    An explicit ``OPENAI_VECTOR_STORE_ID`` wins; anything unset, empty or
    whitespace-only means the canonical store. The process environment is the
    only input — no ``.env`` discovery and no shell-out — so the answer does
    not change with the directory a command happens to run in.
    """
    value = os.getenv("OPENAI_VECTOR_STORE_ID", "").strip()
    if value:
        return value, "OPENAI_VECTOR_STORE_ID"
    return CANONICAL_VECTOR_STORE_ID, "canonical"


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
    vector_store_id, vector_store_source = resolve_vector_store_id()
    has_repo_signal = repo_signal_available()

    # There is no missing-vector-store state: resolution always yields a store.
    state = "ready" if has_repo_signal else "missing-repo-signal"

    return SemanticMemoryStatus(
        enabled=state == "ready",
        vector_store_id=vector_store_id,
        vector_store_source=vector_store_source,
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

    # Reported, never failed: an unset override is the normal case, and the
    # only thing a reader needs is which store answered and why.
    vs_id, vs_source = resolve_vector_store_id()
    items.append(DiagnosticItem(
        ok=True,
        label="vector store",
        detail=f"{vs_id} ({vs_source})",
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
