"""Portable, allowlisted snapshot/verify/restore for MQ agent runtime state.

This is not a home-directory backup. Only state stores with an established
sanitization/provenance boundary are included by default:
- feedback evidence/control records;
- execution-outcome telemetry;
- exact-code review receipts;
- sanitized workflow run state.

Generic memory.json, HAL free-form session notes, credentials, environment
files and remote vector-store contents are deliberately excluded.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "mq.state-snapshot.v1"
EXCLUDED_DEFAULT = (
    "generic-memory",
    "hal-session-notes",
    "credentials-and-env",
    "remote-vector-store-state",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_regular(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"state snapshot refuses symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"state snapshot expected regular file: {path}")


def _tree_files(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"state component root is not a real directory: {root}")
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"state snapshot refuses symlink: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        # Lockfiles are process coordination, not durable state.
        if rel.endswith(".lock") or rel.startswith("."):
            continue
        files[rel] = path
    return files


def component_files() -> dict[str, dict[str, Path]]:
    """Resolve the allowlisted state components against the current environment."""
    from mq_agent.core.review_receipts import receipt_directory
    from mq_agent.feedback.store import feedback_root
    from mq_agent.tools.execution_outcome import outcome_path
    from mq_agent.workflows.storage import default_workflows_dir

    outcome = outcome_path()
    execution: dict[str, Path] = {}
    if outcome.is_file():
        execution["current"] = outcome
    for index in range(1, 4):
        rotated = Path(f"{outcome}.{index}")
        if rotated.is_file():
            execution[f"rotation-{index}"] = rotated

    return {
        "feedback": _tree_files(feedback_root()),
        "execution-outcomes": execution,
        "review-receipts": _tree_files(receipt_directory()),
        "workflow-runs": _tree_files(default_workflows_dir()),
    }


def _restore_target(component: str, logical_path: str) -> Path:
    from mq_agent.core.review_receipts import receipt_directory
    from mq_agent.feedback.store import feedback_root
    from mq_agent.tools.execution_outcome import outcome_path
    from mq_agent.workflows.storage import default_workflows_dir

    rel = Path(logical_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("snapshot contains unsafe logical path")

    if component == "feedback":
        return feedback_root() / rel
    if component == "review-receipts":
        return receipt_directory() / rel
    if component == "workflow-runs":
        return default_workflows_dir() / rel
    if component == "execution-outcomes":
        base = outcome_path()
        if logical_path == "current":
            return base
        if logical_path.startswith("rotation-") and logical_path[9:].isdigit():
            return Path(f"{base}.{int(logical_path[9:])}")
        raise ValueError("snapshot contains invalid execution-outcome logical path")
    raise ValueError(f"unknown snapshot component: {component}")


def inventory() -> dict[str, Any]:
    components = []
    for name, files in component_files().items():
        rows = []
        for logical, path in sorted(files.items()):
            _assert_regular(path)
            rows.append(
                {
                    "path": logical,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        components.append(
            {
                "name": name,
                "files": rows,
                "file_count": len(rows),
                "size_bytes": sum(row["size_bytes"] for row in rows),
            }
        )
    return {
        "schema": "mq.state-inventory.v1",
        "components": components,
        "excluded": list(EXCLUDED_DEFAULT),
        "file_count": sum(item["file_count"] for item in components),
        "size_bytes": sum(item["size_bytes"] for item in components),
    }


def snapshot(destination: Path) -> dict[str, Any]:
    destination = destination.expanduser()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("snapshot destination must be absent or empty")
    destination.mkdir(parents=True, exist_ok=True)
    component_root = destination / "components"
    components = []

    for name, files in component_files().items():
        rows = []
        for logical, source in sorted(files.items()):
            _assert_regular(source)
            target = component_root / name / logical
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
            rows.append(
                {
                    "path": logical,
                    "size_bytes": target.stat().st_size,
                    "sha256": _sha256(target),
                }
            )
        components.append({"name": name, "files": rows})

    manifest = {
        "schema": SCHEMA,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "components": components,
        "excluded": list(EXCLUDED_DEFAULT),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _load_manifest(snapshot_dir: Path) -> dict[str, Any]:
    snapshot_dir = snapshot_dir.expanduser()
    manifest_path = snapshot_dir / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("snapshot manifest is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("snapshot manifest is invalid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("snapshot manifest schema is not mq.state-snapshot.v1")
    if not isinstance(manifest.get("components"), list):
        raise ValueError("snapshot manifest components must be a list")
    return manifest


def verify(snapshot_dir: Path) -> dict[str, Any]:
    snapshot_dir = snapshot_dir.expanduser()
    manifest = _load_manifest(snapshot_dir)
    expected: set[str] = set()
    errors: list[str] = []

    for component in manifest["components"]:
        if not isinstance(component, dict) or not isinstance(component.get("name"), str):
            errors.append("invalid component entry")
            continue
        name = component["name"]
        if name not in {"feedback", "execution-outcomes", "review-receipts", "workflow-runs"}:
            errors.append(f"unknown component: {name}")
            continue
        rows = component.get("files")
        if not isinstance(rows, list):
            errors.append(f"{name}: files must be a list")
            continue
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                errors.append(f"{name}: invalid file entry")
                continue
            logical = row["path"]
            try:
                _restore_target(name, logical)  # validates logical path only
            except ValueError as exc:
                errors.append(f"{name}/{logical}: {exc}")
                continue
            rel = f"{name}/{logical}"
            expected.add(rel)
            path = snapshot_dir / "components" / name / logical
            if path.is_symlink() or not path.is_file():
                errors.append(f"{rel}: missing or unsafe")
                continue
            if path.stat().st_size != row.get("size_bytes"):
                errors.append(f"{rel}: size mismatch")
            if _sha256(path) != row.get("sha256"):
                errors.append(f"{rel}: sha256 mismatch")

    actual: set[str] = set()
    components_root = snapshot_dir / "components"
    if components_root.exists():
        for path in components_root.rglob("*"):
            if path.is_symlink():
                errors.append(
                    f"{path.relative_to(components_root).as_posix()}: symlink not allowed"
                )
                continue
            if path.is_file():
                actual.add(path.relative_to(components_root).as_posix())
    for extra in sorted(actual - expected):
        errors.append(f"{extra}: unexpected file")

    return {
        "schema": "mq.state-snapshot-verification.v1",
        "status": "PASS" if not errors else "FAIL",
        "files": len(expected),
        "errors": errors,
    }


def _atomic_copy(source: Path, target: Path) -> None:
    if target.exists() and target.is_symlink():
        raise ValueError(f"restore target is a symlink: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".restore"
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copyfile(source, tmp)
        os.chmod(tmp, 0o600)
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def restore(snapshot_dir: Path) -> dict[str, Any]:
    """Restore only manifest-declared files after strict verification.

    Existing unrelated files are never deleted. Restore is intentionally
    additive/replace-by-name; the CLI owns the explicit --approve gate.
    """
    checked = verify(snapshot_dir)
    if checked["status"] != "PASS":
        raise ValueError("snapshot verification failed; restore refused")

    manifest = _load_manifest(snapshot_dir)
    restored: list[str] = []
    for component in manifest["components"]:
        name = component["name"]
        for row in component["files"]:
            logical = row["path"]
            source = snapshot_dir / "components" / name / logical
            target = _restore_target(name, logical)
            _atomic_copy(source, target)
            restored.append(f"{name}/{logical}")
    return {
        "schema": "mq.state-restore-result.v1",
        "status": "RESTORED",
        "restored_files": len(restored),
        "files": restored,
        "deleted_files": 0,
    }
