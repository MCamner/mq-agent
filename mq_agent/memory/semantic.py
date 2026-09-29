"""Semantic repository memory helpers for mq-agent.

Status distinguishes configuration, reachability, and freshness. Refresh never
uploads a competing authoritative generation silently; vector-store cleanup is
an explicit operator action at the CLI boundary.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SemanticMemoryStatus:
    enabled: bool
    configured: bool
    reachable: bool | None
    fresh: bool | None
    freshness: str
    vector_store_id: str
    vector_store_source: str
    repo_path: str
    repo_signal_available: bool
    status: str
    current_source_revision: str = ""
    stored_source_revision: str = ""
    authoritative_active_count: int | None = None
    non_authoritative_retrieval_count: int | None = None
    latest_upload: str = ""
    reachability_error: str = ""


@dataclass(frozen=True)
class SemanticRefreshResult:
    returncode: int
    vector_store_id: str
    source_revision: str
    stdout: str = ""
    stderr: str = ""
    file_id: str = ""
    uploaded: bool = False
    cleanup_stale: bool = False
    detached: tuple[str, ...] = field(default_factory=tuple)
    postcondition_status: str = "UNKNOWN"
    authoritative_active_count: int | None = None
    non_authoritative_retrieval_count: int | None = None
    freshness: str = "unknown"
    error: str = ""


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


@dataclass(frozen=True)
class _IdentityInspection:
    authoritative_files: tuple[Any, ...]
    authoritative_active_count: int
    known_non_authoritative_retrieval_count: int
    non_authoritative_scope_complete: bool
    freshness: str
    stored_source_revision: str
    latest_upload: str


@dataclass
class _FilenameIndex:
    names: dict[str, str] = field(default_factory=dict)
    loaded: bool = False


CANONICAL_VECTOR_STORE_ID = "vs_69ffa9a4ef5c81919d7d237c3ecdc260"

# macos-scripts has a tracked regression test proving its shell consumers were
# migrated away from this retired store. Other legacy stores are deliberately
# not assumed retired: mq-mcp still documents repo-knowledge as used by ask.
RETIRED_VECTOR_STORE_IDS_BY_REPO: dict[str, tuple[str, ...]] = {
    "macos-scripts": ("vs_69f93de12f508191bd6a36ea3b825beb",),
}

_UPLOAD_FILE_RE = re.compile(r"OpenAI file:\s*\x60([^\x60]+)\x60")


_POSTCONDITION_ATTEMPTS = 5
_POSTCONDITION_DELAY_SECONDS = 0.5


def resolve_vector_store_id() -> tuple[str, str]:
    """Return the authoritative store and where its id came from."""
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


def _openai_client() -> Any | None:
    """Build a hermetic OpenAI client, or None when no process key exists."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _git_value(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _source_revision(repo: Path) -> str:
    return _git_value(repo, "rev-parse", "HEAD")


def _repo_name(repo: Path) -> str:
    root = _git_value(repo, "rev-parse", "--show-toplevel")
    return Path(root).name if root else repo.name


def _iso_from_epoch(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _page_items(page: Any) -> list[Any]:
    """Materialize SDK auto-pagination while staying simple to fake in tests."""
    try:
        return list(page)
    except TypeError:
        return list(getattr(page, "data", []) or [])


def _attributes(item: Any) -> dict[str, Any]:
    value = getattr(item, "attributes", None)
    return dict(value) if isinstance(value, dict) else {}


def _load_filename_index(client: Any, index: _FilenameIndex) -> bool:
    """Load OpenAI file id -> filename once for legacy identity fallback."""
    if index.loaded:
        return True

    try:
        files = _page_items(client.files.list(limit=10_000, order="desc"))
    except Exception:
        return False

    index.names.update(
        {
            str(getattr(item, "id", "")): str(getattr(item, "filename", ""))
            for item in files
            if getattr(item, "id", None)
        }
    )
    index.loaded = True
    return True


def _matches_identity(
    client: Any,
    item: Any,
    repo_name: str,
    filename_index: _FilenameIndex,
) -> tuple[bool, bool]:
    """Return (matches, known) for repo + symbol-memory identity."""
    attrs = _attributes(item)
    repo_attr = attrs.get("repo")
    artifact_type = attrs.get("artifact_type")
    memory_type = attrs.get("memory_type")

    if repo_attr is not None and str(repo_attr) != repo_name:
        return False, True

    if str(repo_attr or "") == repo_name and (
        artifact_type == "symbol-memory"
        or memory_type in {"symbols", "repository_symbols"}
    ):
        return True, True

    file_id = str(getattr(item, "id", ""))
    if not file_id:
        return False, False

    if not _load_filename_index(client, filename_index):
        return False, False

    filename = filename_index.names.get(file_id)
    if filename is None:
        return False, False

    return filename == f"{repo_name}-symbol-memory.md", True


def _identity_files(
    client: Any,
    store_id: str,
    repo_name: str,
    filename_index: _FilenameIndex,
) -> tuple[list[Any], bool]:
    try:
        page = client.vector_stores.files.list(store_id, limit=100, order="desc")
        candidates = _page_items(page)
    except Exception:
        return [], False

    matches: list[Any] = []
    complete = True
    for item in candidates:
        is_match, known = _matches_identity(client, item, repo_name, filename_index)
        complete = complete and known
        if is_match:
            matches.append(item)
    return matches, complete


def _inspect_identity(
    client: Any,
    repo: Path,
    authoritative_store_id: str,
    current_revision: str,
) -> _IdentityInspection:
    repo_name = _repo_name(repo)
    filename_index = _FilenameIndex()

    authoritative, authoritative_complete = _identity_files(
        client,
        authoritative_store_id,
        repo_name,
        filename_index,
    )
    active = [
        item
        for item in authoritative
        if getattr(item, "status", "") == "completed"
    ]

    stored_revision = ""
    if len(active) == 1:
        stored_revision = str(_attributes(active[0]).get("source_revision", ""))

    latest_upload = ""
    if authoritative:
        latest = max(
            authoritative,
            key=lambda item: int(getattr(item, "created_at", 0) or 0),
        )
        latest_upload = _iso_from_epoch(getattr(latest, "created_at", None))

    known_non_authoritative = 0
    non_authoritative_complete = True
    try:
        stores = _page_items(client.vector_stores.list(limit=100, order="desc"))
    except Exception:
        stores = []
        non_authoritative_complete = False

    for store in stores:
        store_id = str(getattr(store, "id", ""))
        if not store_id or store_id == authoritative_store_id:
            continue
        files, complete = _identity_files(
            client,
            store_id,
            repo_name,
            filename_index,
        )
        non_authoritative_complete = non_authoritative_complete and complete
        known_non_authoritative += sum(
            1
            for item in files
            if getattr(item, "status", "") == "completed"
        )

    scope_complete = authoritative_complete and non_authoritative_complete

    if len(active) != 1 or known_non_authoritative > 0:
        freshness = "stale"
    elif not scope_complete:
        freshness = "unknown"
    elif not current_revision or not stored_revision:
        freshness = "unknown"
    elif current_revision == stored_revision:
        freshness = "fresh"
    else:
        freshness = "stale"

    return _IdentityInspection(
        authoritative_files=tuple(authoritative),
        authoritative_active_count=len(active),
        known_non_authoritative_retrieval_count=known_non_authoritative,
        non_authoritative_scope_complete=scope_complete,
        freshness=freshness,
        stored_source_revision=stored_revision,
        latest_upload=latest_upload,
    )


def status(repo_path: str | Path = ".") -> SemanticMemoryStatus:
    repo = Path(repo_path).resolve()
    vector_store_id, vector_store_source = resolve_vector_store_id()
    configured = bool(vector_store_id)
    has_repo_signal = repo_signal_available()
    current_revision = _source_revision(repo)

    reachable: bool | None = None
    inspection: _IdentityInspection | None = None
    reachability_error = ""

    client = _openai_client()
    if client is not None:
        try:
            client.vector_stores.retrieve(vector_store_id)
            inspection = _inspect_identity(
                client,
                repo,
                vector_store_id,
                current_revision,
            )
            reachable = True
        except Exception as exc:
            reachable = False
            reachability_error = f"{type(exc).__name__}: {exc}"

    freshness = inspection.freshness if inspection else "unknown"
    fresh = (
        True
        if freshness == "fresh"
        else False
        if freshness == "stale"
        else None
    )

    if not configured or reachable is False:
        state = "unavailable"
    elif reachable is True and freshness == "fresh" and has_repo_signal:
        state = "ready"
    else:
        state = "degraded"

    non_authoritative_count: int | None = None
    if inspection and inspection.non_authoritative_scope_complete:
        non_authoritative_count = inspection.known_non_authoritative_retrieval_count

    return SemanticMemoryStatus(
        enabled=state == "ready",
        configured=configured,
        reachable=reachable,
        fresh=fresh,
        freshness=freshness,
        vector_store_id=vector_store_id,
        vector_store_source=vector_store_source,
        repo_path=str(repo),
        repo_signal_available=has_repo_signal,
        status=state,
        current_source_revision=current_revision,
        stored_source_revision=inspection.stored_source_revision if inspection else "",
        authoritative_active_count=(
            inspection.authoritative_active_count if inspection else None
        ),
        non_authoritative_retrieval_count=non_authoritative_count,
        latest_upload=inspection.latest_upload if inspection else "",
        reachability_error=reachability_error,
    )


def build(
    repo_path: str | Path = ".",
    dry_run: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Build/upload through repo-signal, pinning the store mq-agent reported."""
    repo = Path(repo_path).resolve()
    vector_store_id, _ = resolve_vector_store_id()
    cmd = [
        "repo-signal",
        "semantic-upload",
        "--vector-store-id",
        vector_store_id,
    ]
    if dry_run:
        cmd.append("--dry-run")

    return subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def _upload_file_id(stdout: str) -> str:
    match = _UPLOAD_FILE_RE.search(stdout)
    return match.group(1) if match else ""


def _detach_stale_generations(
    client: Any,
    repo: Path,
    authoritative_store_id: str,
    keep_file_id: str,
) -> tuple[str, ...]:
    """Detach stale retrieval generations without deleting Storage file objects."""
    repo_name = _repo_name(repo)
    filename_index = _FilenameIndex()
    detached: list[str] = []

    authoritative, _ = _identity_files(
        client,
        authoritative_store_id,
        repo_name,
        filename_index,
    )
    for item in authoritative:
        file_id = str(getattr(item, "id", ""))
        if not file_id or file_id == keep_file_id:
            continue
        client.vector_stores.files.delete(
            file_id,
            vector_store_id=authoritative_store_id,
        )
        detached.append(f"{authoritative_store_id}:{file_id}")

    for retired_store_id in RETIRED_VECTOR_STORE_IDS_BY_REPO.get(repo_name, ()):
        files, _ = _identity_files(
            client,
            retired_store_id,
            repo_name,
            filename_index,
        )
        for item in files:
            file_id = str(getattr(item, "id", ""))
            if not file_id:
                continue
            client.vector_stores.files.delete(
                file_id,
                vector_store_id=retired_store_id,
            )
            detached.append(f"{retired_store_id}:{file_id}")

    return tuple(detached)


def _postcondition_state(
    inspection: _IdentityInspection,
) -> tuple[str, int | None]:
    non_authoritative_count = (
        inspection.known_non_authoritative_retrieval_count
        if inspection.non_authoritative_scope_complete
        else None
    )
    status = (
        "PASS"
        if inspection.authoritative_active_count == 1
        and non_authoritative_count == 0
        and inspection.freshness == "fresh"
        else "UNKNOWN"
        if non_authoritative_count is None or inspection.freshness == "unknown"
        else "FAIL"
    )
    return status, non_authoritative_count


def _wait_for_postcondition(
    client: Any,
    repo: Path,
    authoritative_store_id: str,
    current_revision: str,
    *,
    attempts: int = _POSTCONDITION_ATTEMPTS,
    delay_seconds: float = _POSTCONDITION_DELAY_SECONDS,
) -> tuple[_IdentityInspection, int | None, str]:
    """Wait briefly for vector-store list/delete visibility to converge."""
    last: _IdentityInspection | None = None
    last_count: int | None = None
    last_status = "UNKNOWN"

    for attempt in range(max(1, attempts)):
        last = _inspect_identity(
            client,
            repo,
            authoritative_store_id,
            current_revision,
        )
        last_status, last_count = _postcondition_state(last)
        if last_status == "PASS":
            return last, last_count, last_status

        if attempt + 1 < max(1, attempts):
            time.sleep(delay_seconds)

    assert last is not None
    return last, last_count, last_status


def refresh(
    repo_path: str | Path = ".",
    *,
    cleanup_stale: bool = False,
) -> SemanticRefreshResult:
    """Refresh one symbol-memory identity against mq.semantic-refresh.v1."""
    repo = Path(repo_path).resolve()
    vector_store_id, _ = resolve_vector_store_id()
    revision = _source_revision(repo)

    if not revision:
        return SemanticRefreshResult(
            returncode=2,
            vector_store_id=vector_store_id,
            source_revision="",
            cleanup_stale=cleanup_stale,
            error="source revision unavailable; refresh requires a git HEAD",
        )

    client = _openai_client()
    if client is None:
        return SemanticRefreshResult(
            returncode=2,
            vector_store_id=vector_store_id,
            source_revision=revision,
            cleanup_stale=cleanup_stale,
            error="OPENAI_API_KEY is unavailable in the process environment",
        )

    try:
        client.vector_stores.retrieve(vector_store_id)
        before = _inspect_identity(
            client,
            repo,
            vector_store_id,
            revision,
        )
    except Exception as exc:
        return SemanticRefreshResult(
            returncode=2,
            vector_store_id=vector_store_id,
            source_revision=revision,
            cleanup_stale=cleanup_stale,
            error=f"vector store preflight failed: {type(exc).__name__}: {exc}",
        )

    if before.freshness == "fresh" and not cleanup_stale:
        return SemanticRefreshResult(
            returncode=0,
            vector_store_id=vector_store_id,
            source_revision=revision,
            uploaded=False,
            cleanup_stale=False,
            postcondition_status="PASS",
            authoritative_active_count=before.authoritative_active_count,
            non_authoritative_retrieval_count=(
                before.known_non_authoritative_retrieval_count
                if before.non_authoritative_scope_complete
                else None
            ),
            freshness="fresh",
        )

    existing_retrieval = (
        before.authoritative_active_count > 0
        or before.known_non_authoritative_retrieval_count > 0
        or not before.non_authoritative_scope_complete
    )
    if existing_retrieval and not cleanup_stale:
        return SemanticRefreshResult(
            returncode=2,
            vector_store_id=vector_store_id,
            source_revision=revision,
            cleanup_stale=False,
            postcondition_status="FAIL",
            authoritative_active_count=before.authoritative_active_count,
            non_authoritative_retrieval_count=(
                before.known_non_authoritative_retrieval_count
                if before.non_authoritative_scope_complete
                else None
            ),
            freshness=before.freshness,
            error=(
                "latest-only refresh would create or preserve competing retrieval "
                "generations; rerun with --cleanup-stale for explicit replacement"
            ),
        )

    upload = build(repo, dry_run=False)
    if upload.returncode != 0:
        return SemanticRefreshResult(
            returncode=upload.returncode,
            vector_store_id=vector_store_id,
            source_revision=revision,
            stdout=upload.stdout,
            stderr=upload.stderr,
            cleanup_stale=cleanup_stale,
            error="repo-signal semantic-upload failed",
        )

    file_id = _upload_file_id(upload.stdout)
    if not file_id:
        return SemanticRefreshResult(
            returncode=2,
            vector_store_id=vector_store_id,
            source_revision=revision,
            stdout=upload.stdout,
            stderr=upload.stderr,
            uploaded=True,
            cleanup_stale=cleanup_stale,
            error="upload completed without an OpenAI file id; refusing cleanup",
        )

    try:
        attached = client.vector_stores.files.retrieve(
            file_id,
            vector_store_id=vector_store_id,
        )
        attrs = _attributes(attached)
        attrs.update(
            {
                "repo": _repo_name(repo),
                "memory_type": "symbols",
                "source": "repo-signal",
                "artifact_type": "symbol-memory",
                "source_revision": revision,
                "generation_id": file_id,
            }
        )
        attached = client.vector_stores.files.update(
            file_id,
            vector_store_id=vector_store_id,
            attributes=attrs,
        )
        if getattr(attached, "status", "") != "completed":
            raise RuntimeError(
                f"new generation status is {getattr(attached, 'status', 'unknown')}"
            )
    except Exception as exc:
        return SemanticRefreshResult(
            returncode=2,
            vector_store_id=vector_store_id,
            source_revision=revision,
            stdout=upload.stdout,
            stderr=upload.stderr,
            file_id=file_id,
            uploaded=True,
            cleanup_stale=cleanup_stale,
            error=f"new generation verification failed: {type(exc).__name__}: {exc}",
        )

    detached: tuple[str, ...] = ()
    if cleanup_stale:
        try:
            detached = _detach_stale_generations(
                client,
                repo,
                vector_store_id,
                file_id,
            )
        except Exception as exc:
            return SemanticRefreshResult(
                returncode=2,
                vector_store_id=vector_store_id,
                source_revision=revision,
                stdout=upload.stdout,
                stderr=upload.stderr,
                file_id=file_id,
                uploaded=True,
                cleanup_stale=True,
                detached=detached,
                error=f"stale-generation cleanup failed: {type(exc).__name__}: {exc}",
            )

    after, non_authoritative_count, postcondition = _wait_for_postcondition(
        client,
        repo,
        vector_store_id,
        revision,
    )
    returncode = 0 if postcondition == "PASS" else 3

    return SemanticRefreshResult(
        returncode=returncode,
        vector_store_id=vector_store_id,
        source_revision=revision,
        stdout=upload.stdout,
        stderr=upload.stderr,
        file_id=file_id,
        uploaded=True,
        cleanup_stale=cleanup_stale,
        detached=detached,
        postcondition_status=postcondition,
        authoritative_active_count=after.authoritative_active_count,
        non_authoritative_retrieval_count=non_authoritative_count,
        freshness=after.freshness,
        error="" if returncode == 0 else "semantic refresh postcondition did not pass",
    )


def doctor(repo_path: str | Path = ".") -> DoctorReport:
    """Diagnose semantic memory environment and return actionable findings."""
    repo = Path(repo_path).resolve()
    items: list[DiagnosticItem] = []

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
