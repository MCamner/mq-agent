"""Semantic repository memory helpers for mq-agent.

Conservative by design: never uploads silently, always reports state explicitly.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# The canonical cross-repo semantic memory, declared here so mq-agent owns its
# own identity. It is named in mq-mcp/docs/global/GLOBAL_VECTOR_STORE_POLICY.md
# under "Store IDs"; a vector-store ID is an addressable name, not a secret.
#
# Declaring it in tracked code is the point: it previously existed only in
# gitignored .env files, so any consumer that lost that file either had no
# memory or fell back to a store of its own choosing.
CANONICAL_VECTOR_STORE_ID = "vs_69ffa9a4ef5c81919d7d237c3ecdc260"
CANONICAL_VECTOR_STORE_NAME = "semantic repository memory"


@dataclass(frozen=True)
class SemanticMemoryStatus:
    enabled: bool
    vector_store_id: str | None
    repo_path: str
    repo_signal_available: bool
    status: str
    vector_store_source: str = "canonical"


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
    """Return the explicitly configured store, or None. Does not fall back."""
    value = os.getenv("OPENAI_VECTOR_STORE_ID")
    return value.strip() if value and value.strip() else None


def resolve_vector_store_id() -> tuple[str, str]:
    """Return the store mq-agent will actually use, and where it came from.

    An explicit OPENAI_VECTOR_STORE_ID always wins, so a repo can point at its
    own store. Otherwise the canonical store applies — mq-agent is never
    without a memory, and never guesses which one.
    """
    configured = get_vector_store_id()
    if configured:
        return configured, "env"
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
    vector_store_id, source = resolve_vector_store_id()
    has_repo_signal = repo_signal_available()

    state = "ready" if has_repo_signal else "missing-repo-signal"

    return SemanticMemoryStatus(
        enabled=state == "ready",
        vector_store_id=vector_store_id,
        repo_path=str(repo),
        repo_signal_available=has_repo_signal,
        status=state,
        vector_store_source=source,
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

    vs_id, source = resolve_vector_store_id()
    if source == "env":
        detail = f"{vs_id} (OPENAI_VECTOR_STORE_ID)"
    else:
        detail = f"{vs_id} ({CANONICAL_VECTOR_STORE_NAME}, canonical default)"
    items.append(DiagnosticItem(ok=True, label="vector store", detail=detail))

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
