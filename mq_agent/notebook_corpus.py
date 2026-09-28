"""Deterministic materializer for the Drive-backed NotebookLM corpus index.

D3 owns materialization only. It consumes normalized metadata supplied by a
future Drive adapter and emits the canonical notebook-corpus-index.v1 shape plus
a local deterministic checkpoint. It never reads file bodies or mutates Drive.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_NAME = "notebook-corpus-index.v1"
CHECKPOINT_SCHEMA = "notebook-corpus-build-checkpoint.v1"
_PROVIDER = "google-drive"
_ALLOWED_OVERRIDE_ROLES = {
    "source",
    "derived",
    "derived-note",
    "interaction",
    "metadata-or-other",
    "unknown",
}


def _stable_id(prefix: str, provider_id: str) -> str:
    if not provider_id:
        raise ValueError("provider identity must be non-empty")
    digest = hashlib.sha256(
        f"{_PROVIDER}\0{prefix}\0{provider_id}".encode("utf-8")
    ).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _schema_path() -> Path:
    packaged = Path(__file__).with_name("schemas") / "notebook_corpus_index.schema.json"
    if packaged.is_file():
        return packaged
    repo_copy = Path(__file__).resolve().parents[1] / "schemas" / "notebook_corpus_index.schema.json"
    if repo_copy.is_file():
        return repo_copy
    raise FileNotFoundError("vendored notebook-corpus-index.v1 schema not found")


def validate_catalog(catalog: Mapping[str, Any]) -> None:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(catalog), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"catalog does not match {SCHEMA_NAME}: {details}")


def classify_path(
    relative_path: str | None,
    *,
    override_role: str | None = None,
    override_provenance: str | None = None,
) -> dict[str, str]:
    """Classify an archive item without inspecting its body."""

    if override_role is not None:
        if override_role not in _ALLOWED_OVERRIDE_ROLES:
            raise ValueError(f"unsupported override role: {override_role}")
        if not override_provenance:
            raise ValueError("override_provenance is required for an override")
        return {
            "role": override_role,
            "method": "override",
            "override_provenance": override_provenance,
        }

    if not relative_path:
        return {"role": "unknown", "method": "unknown"}

    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        return {"role": "unknown", "method": "unknown"}

    parts = normalized.split("/")
    if len(parts) == 1:
        return {"role": "metadata-or-other", "method": "structural"}

    role_by_folder = {
        "Sources": "source",
        "Artifacts": "derived",
        "Notes": "derived-note",
        "Chat History": "interaction",
    }
    role = role_by_folder.get(parts[0])
    if role is None:
        return {"role": "unknown", "method": "unknown"}
    return {"role": role, "method": "structural"}


def _normalized_source(
    corpus_key: str,
    snapshot_at: str,
    notebooks: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "corpus_key": corpus_key,
        "snapshot_at": snapshot_at,
        "notebooks": sorted(
            (dict(notebook) for notebook in notebooks),
            key=lambda value: str(value.get("drive_item_id", "")),
        ),
        "items": sorted(
            (dict(item) for item in items),
            key=lambda value: str(value.get("drive_item_id", "")),
        ),
    }


def build_catalog(
    *,
    corpus_key: str,
    snapshot_at: str,
    notebooks: Sequence[Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build deterministic catalog and checkpoint from normalized metadata."""

    if not corpus_key:
        raise ValueError("corpus_key must be non-empty")
    if not snapshot_at:
        raise ValueError("snapshot_at must be non-empty")

    notebook_by_drive_id: dict[str, dict[str, str]] = {}
    notebook_drive_ids: set[str] = set()
    for raw in notebooks:
        drive_item_id = str(raw.get("drive_item_id", ""))
        if not drive_item_id:
            raise ValueError("notebook drive_item_id must be non-empty")
        if drive_item_id in notebook_drive_ids:
            raise ValueError(f"duplicate notebook drive_item_id: {drive_item_id}")
        notebook_drive_ids.add(drive_item_id)
        notebook_by_drive_id[drive_item_id] = {
            "notebook_id": _stable_id("nb", drive_item_id),
            "drive_item_id": drive_item_id,
            "title": str(raw.get("title", "")),
        }

    seen_item_ids: set[str] = set()
    output_items: list[dict[str, Any]] = []
    excluded_reasons: dict[str, int] = {}

    for raw in items:
        drive_item_id = str(raw.get("drive_item_id", ""))
        if not drive_item_id:
            raise ValueError("item drive_item_id must be non-empty")
        if drive_item_id in seen_item_ids:
            raise ValueError(f"duplicate item drive_item_id: {drive_item_id}")
        seen_item_ids.add(drive_item_id)

        notebook_drive_item_id = raw.get("notebook_drive_item_id")
        if not notebook_drive_item_id or str(notebook_drive_item_id) not in notebook_by_drive_id:
            excluded_reasons["unmapped_notebook"] = (
                excluded_reasons.get("unmapped_notebook", 0) + 1
            )
            continue

        notebook = notebook_by_drive_id[str(notebook_drive_item_id)]
        classification = classify_path(
            raw.get("relative_path"),
            override_role=raw.get("override_role"),
            override_provenance=raw.get("override_provenance"),
        )

        output: dict[str, Any] = {
            "item_id": _stable_id("item", drive_item_id),
            "drive_item_id": drive_item_id,
            "notebook_id": notebook["notebook_id"],
            "parent_drive_item_id": str(raw.get("parent_drive_item_id", "")),
            "title": str(raw.get("title", "")),
            "mime_type": str(raw.get("mime_type", "")),
            "size_bytes": int(raw.get("size_bytes", 0)),
            "modified_time": str(raw.get("modified_time", "")),
            "origin_provider": str(raw.get("origin_provider", "")),
            "classification": classification,
        }
        content_sha256 = raw.get("content_sha256")
        if content_sha256 is not None:
            output["content_sha256"] = str(content_sha256)
        output_items.append(output)

    catalog = {
        "schema": SCHEMA_NAME,
        "corpus": {"key": corpus_key, "provider": _PROVIDER},
        "snapshot_at": snapshot_at,
        "notebooks": sorted(
            notebook_by_drive_id.values(),
            key=lambda value: value["notebook_id"],
        ),
        "items": sorted(output_items, key=lambda value: value["item_id"]),
    }
    validate_catalog(catalog)

    source = _normalized_source(corpus_key, snapshot_at, notebooks, items)
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "source_snapshot_at": snapshot_at,
        "source_fingerprint": hashlib.sha256(_canonical_bytes(source)).hexdigest(),
        "catalog_sha256": hashlib.sha256(_canonical_bytes(catalog)).hexdigest(),
        "included_notebooks": len(catalog["notebooks"]),
        "included_items": len(catalog["items"]),
        "excluded_items": sum(excluded_reasons.values()),
        "excluded_reasons": dict(sorted(excluded_reasons.items())),
    }
    return catalog, checkpoint


def build_from_document(document: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_catalog(
        corpus_key=str(document.get("corpus_key", "")),
        snapshot_at=str(document.get("snapshot_at", "")),
        notebooks=document.get("notebooks") or [],
        items=document.get("items") or [],
    )


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def materialize(
    document: Mapping[str, Any],
    *,
    catalog_path: Path,
    checkpoint_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog, checkpoint = build_from_document(document)
    _atomic_json_write(checkpoint_path, checkpoint)
    _atomic_json_write(catalog_path, catalog)
    return catalog, checkpoint
