"""Append-only local storage for feedback engine runtime evidence.

The store is runtime evidence, not durable MQ memory. It lives outside Git,
contains bounded identifiers/provenance only, and is safe to delete without
changing production behavior.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import fcntl
from jsonschema.exceptions import ValidationError

from .contracts import validate_candidate, validate_comparison
from .models import validate_experiment

STATE_ENV = "MQ_AGENT_FEEDBACK_DIR"
MAX_BYTES_ENV = "MQ_AGENT_FEEDBACK_MAX_BYTES"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
MAX_ROTATED_FILES = 3
EXPERIMENTS_FILE = "experiments.jsonl"
COMPARISONS_FILE = "comparisons.jsonl"
CANDIDATES_FILE = "candidates.jsonl"
LOCK_FILE = ".store.lock"

_PROHIBITED_KEYS = frozenset(
    {
        "prompt",
        "raw_prompt",
        "task",
        "task_text",
        "diff",
        "source_body",
        "source_content",
        "stdout",
        "stderr",
        "password",
        "secret",
        "credential",
        "credentials",
        "api_key",
    }
)
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
)
_HOME_PATTERNS = (
    re.compile(r"/(?:Users|home)/[^/\s]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
)


@dataclass(frozen=True)
class FeedbackStoreIssue:
    line: int
    reason: str
    source: str = EXPERIMENTS_FILE


@dataclass(frozen=True)
class FeedbackReadResult:
    records: list[dict[str, Any]]
    issues: list[FeedbackStoreIssue]


@dataclass(frozen=True)
class StoredFeedbackRecord:
    record: dict[str, Any]
    source: str
    line: int


@dataclass(frozen=True)
class FeedbackHistoryResult:
    records: list[StoredFeedbackRecord]
    issues: list[FeedbackStoreIssue]


Validator = Callable[[dict[str, Any]], None]


def feedback_root(root: Path | None = None) -> Path:
    if root is not None:
        return root.expanduser()
    configured = os.environ.get(STATE_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mq" / "feedback"


def experiments_path(root: Path | None = None) -> Path:
    return feedback_root(root) / EXPERIMENTS_FILE


def comparisons_path(root: Path | None = None) -> Path:
    return feedback_root(root) / COMPARISONS_FILE


def candidates_path(root: Path | None = None) -> Path:
    return feedback_root(root) / CANDIDATES_FILE


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _sanitize_string(value: str) -> str:
    sanitized = value
    home = str(Path.home())
    if home and home != "/":
        sanitized = sanitized.replace(home, "$HOME")
    for pattern in _HOME_PATTERNS:
        sanitized = pattern.sub("$HOME", sanitized)
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def sanitize_feedback_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized deep copy or reject forbidden payload channels."""

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, nested in value.items():
                normalized = _normalized_key(str(key))
                if normalized in _PROHIBITED_KEYS:
                    raise ValueError(f"feedback record contains forbidden field: {key}")
                cleaned[str(key)] = walk(nested)
            return cleaned
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str):
            return _sanitize_string(value)
        return value

    cleaned = walk(record)
    if not isinstance(cleaned, dict):
        raise ValueError("feedback record must be an object")
    return cleaned


def _ensure_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    runs = root / "runs"
    runs.mkdir(exist_ok=True)
    os.chmod(root, 0o700)
    os.chmod(runs, 0o700)


@contextmanager
def _exclusive_lock(root: Path) -> Iterator[None]:
    """Writer lock; creating the local runtime surface is allowed here."""
    _ensure_root(root)
    lock_path = root / LOCK_FILE
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a+b", closefd=True) as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _shared_lock(root: Path) -> Iterator[None]:
    """Read lock without creating the feedback root or lock file."""
    lock_path = root / LOCK_FILE
    try:
        fd = os.open(lock_path, os.O_RDONLY)
    except FileNotFoundError:
        yield
        return

    with os.fdopen(fd, "rb", closefd=True) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _configured_max_bytes() -> int:
    raw = os.environ.get(MAX_BYTES_ENV)
    if raw is None:
        return DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{MAX_BYTES_ENV} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{MAX_BYTES_ENV} must be >= 0")
    return value


def _rotate_if_needed(path: Path, *, incoming_bytes: int, max_bytes: int) -> None:
    if max_bytes <= 0:
        return
    if incoming_bytes > max_bytes:
        raise ValueError("feedback record exceeds configured store size")
    if not path.exists() or path.stat().st_size + incoming_bytes <= max_bytes:
        return
    for index in range(MAX_ROTATED_FILES, 0, -1):
        older = Path(f"{path}.{index}")
        if index == MAX_ROTATED_FILES:
            older.unlink(missing_ok=True)
        previous = path if index == 1 else Path(f"{path}.{index - 1}")
        if previous.exists():
            previous.replace(older)


def _append_bytes(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("feedback append wrote zero bytes")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _append_record(
    record: dict[str, Any],
    *,
    filename: str,
    validator: Validator,
    root: Path | None = None,
) -> Path:
    sanitized = sanitize_feedback_record(record)
    validator(sanitized)
    encoded = (json.dumps(sanitized, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    state_root = feedback_root(root)
    path = state_root / filename
    with _exclusive_lock(state_root):
        _rotate_if_needed(
            path,
            incoming_bytes=len(encoded),
            max_bytes=_configured_max_bytes(),
        )
        _append_bytes(path, encoded)
    return path


def append_experiment(record: dict[str, Any], root: Path | None = None) -> Path:
    return _append_record(
        record,
        filename=EXPERIMENTS_FILE,
        validator=validate_experiment,
        root=root,
    )


def append_comparison(record: dict[str, Any], root: Path | None = None) -> Path:
    return _append_record(
        record,
        filename=COMPARISONS_FILE,
        validator=validate_comparison,
        root=root,
    )


def append_candidate(record: dict[str, Any], root: Path | None = None) -> Path:
    return _append_record(
        record,
        filename=CANDIDATES_FILE,
        validator=validate_candidate,
        root=root,
    )


def _parse_lines(
    raw_lines: list[bytes],
    source: str,
    validator: Validator,
) -> FeedbackHistoryResult:
    records: list[StoredFeedbackRecord] = []
    issues: list[FeedbackStoreIssue] = []
    for line_number, raw in enumerate(raw_lines, start=1):
        try:
            text = raw.decode("utf-8")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("record is not a JSON object")
            sanitized = sanitize_feedback_record(parsed)
            if sanitized != parsed:
                raise ValueError("record contains data that requires redaction")
            validator(parsed)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            issues.append(
                FeedbackStoreIssue(
                    line=line_number,
                    reason=str(exc),
                    source=source,
                )
            )
            continue
        records.append(
            StoredFeedbackRecord(
                record=parsed,
                source=source,
                line=line_number,
            )
        )
    return FeedbackHistoryResult(records=records, issues=issues)


def _history_paths(root: Path, filename: str) -> list[Path]:
    current = root / filename
    return [
        *(Path(f"{current}.{index}") for index in range(MAX_ROTATED_FILES, 0, -1)),
        current,
    ]


def _read_history(
    *,
    filename: str,
    validator: Validator,
    root: Path | None = None,
) -> FeedbackHistoryResult:
    state_root = feedback_root(root)
    if not state_root.exists():
        return FeedbackHistoryResult(records=[], issues=[])

    snapshots: list[tuple[str, list[bytes]]] = []
    with _shared_lock(state_root):
        for path in _history_paths(state_root, filename):
            if path.is_file():
                snapshots.append((path.name, path.read_bytes().splitlines()))

    records: list[StoredFeedbackRecord] = []
    issues: list[FeedbackStoreIssue] = []
    for source, raw_lines in snapshots:
        parsed = _parse_lines(raw_lines, source, validator)
        records.extend(parsed.records)
        issues.extend(parsed.issues)
    return FeedbackHistoryResult(records=records, issues=issues)


def read_experiment_history(root: Path | None = None) -> FeedbackHistoryResult:
    return _read_history(
        filename=EXPERIMENTS_FILE,
        validator=validate_experiment,
        root=root,
    )


def read_comparison_history(root: Path | None = None) -> FeedbackHistoryResult:
    return _read_history(
        filename=COMPARISONS_FILE,
        validator=validate_comparison,
        root=root,
    )


def read_candidate_history(root: Path | None = None) -> FeedbackHistoryResult:
    return _read_history(
        filename=CANDIDATES_FILE,
        validator=validate_candidate,
        root=root,
    )


def read_experiments(root: Path | None = None) -> FeedbackReadResult:
    """Read valid current-generation experiment records."""
    state_root = feedback_root(root)
    path = state_root / EXPERIMENTS_FILE
    if not path.exists():
        return FeedbackReadResult(records=[], issues=[])

    with _shared_lock(state_root):
        raw_lines = path.read_bytes().splitlines()
    parsed = _parse_lines(raw_lines, path.name, validate_experiment)
    return FeedbackReadResult(
        records=[item.record for item in parsed.records],
        issues=parsed.issues,
    )


def purge_feedback_state(root: Path | None = None) -> int:
    """Delete known feedback runtime artifacts without removing unrelated files."""
    state_root = feedback_root(root)
    if not state_root.exists():
        return 0

    deleted = 0
    with _exclusive_lock(state_root):
        for name in (
            EXPERIMENTS_FILE,
            COMPARISONS_FILE,
            CANDIDATES_FILE,
            "activations.jsonl",
        ):
            base = state_root / name
            candidates = [
                base,
                *(Path(f"{base}.{i}") for i in range(1, MAX_ROTATED_FILES + 1)),
            ]
            for candidate in candidates:
                if candidate.is_file():
                    candidate.unlink()
                    deleted += 1
        runs = state_root / "runs"
        if runs.is_dir():
            for candidate in runs.iterdir():
                if candidate.is_file():
                    candidate.unlink()
                    deleted += 1
    return deleted
