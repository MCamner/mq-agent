"""Portable, allowlisted snapshot/verify/restore for MQ runtime state.

State Recovery v2 remains deliberately narrower than a backup system. It keeps
only recovery-relevant, sanitized or deterministic local state. Credentials,
environment secrets, generic free-form memory and remote vector-store contents
remain excluded.

v2 adds version-aware Notebook corpus recovery for local metadata/checkpoints
and the local disposable semantic index. Snapshot manifests are content
addressed and every copied file carries an explicit SHA-256 fingerprint.
Historical mq.state-snapshot.v1 manifests remain readable and restorable.
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

from mq_agent.tools.contract_validation import validate_contract

SCHEMA_V1 = "mq.state-snapshot.v1"
SCHEMA_V2 = "mq.state-snapshot.v2"
SCHEMA = SCHEMA_V2

V1_COMPONENTS = frozenset(
    {
        "feedback",
        "execution-outcomes",
        "review-receipts",
        "workflow-runs",
    }
)
NOTEBOOK_COMPONENTS = {
    "notebook-drive-inventory": ("inventory.json", "notebook-drive-inventory-checkpoint.v1"),
    "notebook-corpus-catalog": ("catalog.json", "notebook-corpus-index.v1"),
    "notebook-corpus-checkpoint": (
        "catalog.checkpoint.json",
        "notebook-corpus-build-checkpoint.v1",
    ),
    "notebook-sync-state": ("sync-state.json", "notebook-knowledge-sync-state.v1"),
    "notebook-semantic-index": (
        "semantic-index.json",
        "notebook-semantic-index-experiment.v1",
    ),
}
V2_COMPONENTS = frozenset({*V1_COMPONENTS, *NOTEBOOK_COMPONENTS})

_COMPONENT_META: dict[str, tuple[str, str | None]] = {
    "feedback": ("mixed-json-jsonl", None),
    "execution-outcomes": ("jsonl", "mq.execution-outcome.v1"),
    "review-receipts": ("json", "mq.review-receipt.v1"),
    "workflow-runs": ("json", None),
    **{
        name: ("json", schema)
        for name, (_filename, schema) in NOTEBOOK_COMPONENTS.items()
    },
}

EXCLUDED_DEFAULT = (
    "generic-memory",
    "hal-session-notes",
    "credentials-and-env",
    "remote-vector-store-state",
    "remote-vector-store-contents",
    "notebook-source-bodies",
)

_FORBIDDEN_NOTEBOOK_KEYS = {
    "access_token",
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token_secret",
}
_FORBIDDEN_SEMANTIC_PAYLOAD_KEYS = {
    "text",
    "raw_text",
    "source_body",
    "content",
    "excerpt",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest_id(manifest: dict[str, Any]) -> str:
    body = {key: value for key, value in manifest.items() if key != "snapshot_id"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


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
        if rel.endswith(".lock") or rel.startswith("."):
            continue
        files[rel] = path
    return files


def _notebook_state_root() -> Path:
    configured = os.getenv("MQ_AGENT_NOTEBOOK_STATE_DIR")
    return Path(configured).expanduser() if configured else Path(".mq/notebook-corpus")


def _single_file(path: Path, logical: str) -> dict[str, Path]:
    return {logical: path} if path.is_file() else {}


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

    notebook_root = _notebook_state_root()
    components: dict[str, dict[str, Path]] = {
        "feedback": _tree_files(feedback_root()),
        "execution-outcomes": execution,
        "review-receipts": _tree_files(receipt_directory()),
        "workflow-runs": _tree_files(default_workflows_dir()),
    }
    for name, (filename, _schema) in NOTEBOOK_COMPONENTS.items():
        components[name] = _single_file(notebook_root / filename, filename)
    return components


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
    if component in NOTEBOOK_COMPONENTS:
        expected, _schema = NOTEBOOK_COMPONENTS[component]
        if logical_path != expected:
            raise ValueError(f"{component} permits only logical path {expected}")
        return _notebook_state_root() / expected
    raise ValueError(f"unknown snapshot component: {component}")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            keys.extend(str(key).lower() for key in current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return keys


def _walk_strings(value: Any) -> list[str]:
    strings: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            strings.append(current)
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return strings


def _private_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith("/Users/")
        or normalized.startswith("/home/")
        or (
            len(normalized) > 3
            and normalized[1:3] == ":/"
            and "/Users/" in normalized
        )
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _validate_notebook_state(component: str, path: Path) -> None:
    if component not in NOTEBOOK_COMPONENTS:
        return
    _filename, expected_schema = NOTEBOOK_COMPONENTS[component]
    payload = _load_json_object(path, label=component)
    if payload.get("schema") != expected_schema:
        raise ValueError(
            f"{component} schema mismatch: expected {expected_schema}, "
            f"got {payload.get('schema')!r}"
        )

    keys = set(_walk_keys(payload))
    leaked = sorted(keys & _FORBIDDEN_NOTEBOOK_KEYS)
    if leaked:
        raise ValueError(
            f"{component} contains credential-like keys: {', '.join(leaked)}"
        )
    if any(_private_absolute_path(value) for value in _walk_strings(payload)):
        raise ValueError(f"{component} contains a private absolute machine path")

    if component == "notebook-corpus-catalog":
        from mq_agent.notebook_corpus import validate_catalog

        validate_catalog(payload)
    elif component == "notebook-semantic-index":
        if payload.get("canonical") is not False or payload.get("disposable") is not True:
            raise ValueError(
                "notebook semantic index must remain non-canonical and disposable"
            )
        chunks = payload.get("chunks")
        if not isinstance(chunks, list):
            raise ValueError("notebook semantic index chunks must be a list")
        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise ValueError("notebook semantic index chunk must be an object")
            forbidden = sorted(
                key for key in _FORBIDDEN_SEMANTIC_PAYLOAD_KEYS if key in chunk
            )
            if forbidden:
                raise ValueError(
                    "notebook semantic index contains raw source payload fields: "
                    + ", ".join(forbidden)
                )


def _file_row(path: Path) -> dict[str, Any]:
    digest = _sha256(path)
    return {
        "size_bytes": path.stat().st_size,
        "sha256": digest,
        "fingerprint": f"sha256:{digest}",
    }


def inventory() -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    for name, files in component_files().items():
        rows: list[dict[str, Any]] = []
        for logical, path in sorted(files.items()):
            _assert_regular(path)
            _validate_notebook_state(name, path)
            rows.append({"path": logical, **_file_row(path)})
        state_format, state_schema = _COMPONENT_META[name]
        components.append(
            {
                "name": name,
                "format": state_format,
                "state_schema": state_schema,
                "files": rows,
                "file_count": len(rows),
                "size_bytes": sum(row["size_bytes"] for row in rows),
            }
        )
    return {
        "kind": "mq-state-inventory",
        "schema": SCHEMA,
        "components": components,
        "excluded": list(EXCLUDED_DEFAULT),
        "file_count": sum(item["file_count"] for item in components),
        "size_bytes": sum(item["size_bytes"] for item in components),
    }


def snapshot(destination: Path) -> dict[str, Any]:
    destination = destination.expanduser()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("snapshot destination must be absent or empty")

    resolved = component_files()
    for name, files in resolved.items():
        for source in files.values():
            _assert_regular(source)
            _validate_notebook_state(name, source)

    destination.mkdir(parents=True, exist_ok=True)
    component_root = destination / "components"
    components: list[dict[str, Any]] = []

    for name, files in resolved.items():
        rows: list[dict[str, Any]] = []
        for logical, source in sorted(files.items()):
            target = component_root / name / logical
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
            _validate_notebook_state(name, target)
            rows.append({"path": logical, **_file_row(target)})
        state_format, state_schema = _COMPONENT_META[name]
        components.append(
            {
                "name": name,
                "format": state_format,
                "state_schema": state_schema,
                "files": rows,
            }
        )

    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "components": components,
        "excluded": list(EXCLUDED_DEFAULT),
    }
    manifest["snapshot_id"] = _manifest_id(manifest)
    validate_contract("state_snapshot.schema.json", manifest)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "
",
        encoding="utf-8",
    )
    return manifest


def _load_manifest(snapshot_dir: Path) -> dict[str, Any]:
    snapshot_dir = snapshot_dir.expanduser()
    manifest_path = snapshot_dir / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("snapshot manifest is missing or unsafe")
    manifest = _load_json_object(manifest_path, label="snapshot manifest")
    schema = manifest.get("schema")
    if schema == SCHEMA_V1:
        contract = "state_snapshot_v1.schema.json"
    elif schema == SCHEMA_V2:
        contract = "state_snapshot.schema.json"
    else:
        raise ValueError(
            "snapshot manifest schema is not mq.state-snapshot.v1 or "
            "mq.state-snapshot.v2"
        )
    try:
        validate_contract(contract, manifest)
    except Exception as exc:
        raise ValueError(f"snapshot manifest contract validation failed: {exc}") from exc
    if schema == SCHEMA_V2 and manifest.get("snapshot_id") != _manifest_id(manifest):
        raise ValueError("snapshot manifest fingerprint mismatch")
    return manifest


def verify(snapshot_dir: Path) -> dict[str, Any]:
    snapshot_dir = snapshot_dir.expanduser()
    manifest = _load_manifest(snapshot_dir)
    schema = str(manifest["schema"])
    allowed = V1_COMPONENTS if schema == SCHEMA_V1 else V2_COMPONENTS
    expected: set[str] = set()
    errors: list[str] = []

    for component in manifest["components"]:
        if not isinstance(component, dict) or not isinstance(component.get("name"), str):
            errors.append("invalid component entry")
            continue
        name = component["name"]
        if name not in allowed:
            errors.append(f"unknown component: {name}")
            continue
        if schema == SCHEMA_V2:
            expected_format, expected_schema = _COMPONENT_META[name]
            if component.get("format") != expected_format:
                errors.append(f"{name}: format mismatch")
            if component.get("state_schema") != expected_schema:
                errors.append(f"{name}: state schema mismatch")
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
                _restore_target(name, logical)
            except ValueError as exc:
                errors.append(f"{name}/{logical}: {exc}")
                continue
            rel = f"{name}/{logical}"
            expected.add(rel)
            path = snapshot_dir / "components" / name / logical
            if path.is_symlink() or not path.is_file():
                errors.append(f"{rel}: missing or unsafe")
                continue
            actual_sha = _sha256(path)
            if path.stat().st_size != row.get("size_bytes"):
                errors.append(f"{rel}: size mismatch")
            if actual_sha != row.get("sha256"):
                errors.append(f"{rel}: sha256 mismatch")
            if schema == SCHEMA_V2 and row.get("fingerprint") != f"sha256:{actual_sha}":
                errors.append(f"{rel}: fingerprint mismatch")
            try:
                _validate_notebook_state(name, path)
            except ValueError as exc:
                errors.append(f"{rel}: {exc}")

    actual: set[str] = set()
    components_root = snapshot_dir / "components"
    if components_root.exists():
        if components_root.is_symlink() or not components_root.is_dir():
            errors.append("components: unsafe root")
        else:
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
        "kind": "mq-state-snapshot-verification",
        "schema": schema,
        "snapshot_id": manifest.get("snapshot_id"),
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


def restore(snapshot_dir: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Restore only manifest-declared allowlisted files after strict verification.

    Existing unrelated files are never deleted. A dry run performs full
    verification and target resolution but writes nothing.
    """
    checked = verify(snapshot_dir)
    if checked["status"] != "PASS":
        raise ValueError("snapshot verification failed; restore refused")

    manifest = _load_manifest(snapshot_dir)
    planned: list[tuple[str, Path, Path]] = []
    for component in manifest["components"]:
        name = component["name"]
        for row in component["files"]:
            logical = row["path"]
            source = snapshot_dir / "components" / name / logical
            target = _restore_target(name, logical)
            planned.append((f"{name}/{logical}", source, target))

    if not dry_run:
        for _logical, source, target in planned:
            _atomic_copy(source, target)

    return {
        "kind": "mq-state-restore-result",
        "schema": manifest["schema"],
        "snapshot_id": manifest.get("snapshot_id"),
        "status": "WOULD_RESTORE" if dry_run else "RESTORED",
        "dry_run": dry_run,
        "restored_files": 0 if dry_run else len(planned),
        "planned_files": len(planned),
        "files": [logical for logical, _source, _target in planned],
        "deleted_files": 0,
    }
