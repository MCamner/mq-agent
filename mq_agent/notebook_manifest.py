"""Reconciled NotebookLM manifest overlay for the Drive corpus projection.

The Drive inventory owns provider identities and change cursors. The reconciled
Takeout/archive manifest owns content hashes and the verified corpus accounting.
This module joins the two by archive-relative path and fails closed when an
explicitly supplied manifest does not describe the projected corpus.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping

from mq_agent.notebook_corpus import classify_path

OVERLAY_PROVENANCE = "notebooklm-manifest.reconciled:v1"


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _projected_archive_path(
    item: Mapping[str, Any],
    notebook_titles: Mapping[str, str],
) -> str:
    explicit = _normalize_path(item.get("archive_relative_path"))
    if explicit:
        return explicit
    notebook_id = str(item.get("notebook_drive_item_id", ""))
    title = notebook_titles.get(notebook_id, "")
    relative = _normalize_path(item.get("relative_path"))
    return _normalize_path(f"{title}/{relative}")


def apply_reconciled_manifest(
    document: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Overlay verified hashes/roles and assert the projected corpus is whole."""

    summary = manifest.get("summary") or {}
    reconciliation = manifest.get("reconciliation") or {}
    if reconciliation and int(reconciliation.get("unknown_count", 0)) != 0:
        raise ValueError("reconciled manifest still contains unknown items")

    records = list(manifest.get("files") or [])
    expected_items = int(summary.get("processed_file_count", len(records)))
    expected_notebooks = int(
        summary.get("notebook_count", len(document.get("notebooks") or []))
    )
    if len(records) != expected_items:
        raise ValueError(
            "manifest file count does not match manifest summary: "
            f"{len(records)} != {expected_items}"
        )

    by_path: dict[str, Mapping[str, Any]] = {}
    for record in records:
        path = _normalize_path(record.get("destination_path"))
        if not path:
            raise ValueError("manifest item has empty destination_path")
        if path in by_path:
            raise ValueError(f"duplicate manifest destination_path: {path}")
        by_path[path] = record

    notebooks = [dict(row) for row in (document.get("notebooks") or [])]
    items = [dict(row) for row in (document.get("items") or [])]
    if len(notebooks) != expected_notebooks:
        raise ValueError(
            "Drive projection notebook count differs from reconciled manifest: "
            f"{len(notebooks)} != {expected_notebooks}"
        )
    if len(items) != expected_items:
        raise ValueError(
            "Drive projection item count differs from reconciled manifest: "
            f"{len(items)} != {expected_items}"
        )

    notebook_titles = {
        str(row.get("drive_item_id", "")): str(row.get("title", ""))
        for row in notebooks
    }
    matched_paths: set[str] = set()
    hashes_applied = 0
    roles: Counter[str] = Counter()

    for item in items:
        archive_path = _projected_archive_path(item, notebook_titles)
        record = by_path.get(archive_path)
        if record is None:
            raise ValueError(
                "Drive projection item missing from reconciled manifest: "
                f"{archive_path}"
            )
        matched_paths.add(archive_path)

        classification = classify_path(item.get("relative_path"))
        role = classification["role"]
        if role == "unknown":
            raise ValueError(
                "Drive projection produced unknown role for manifest item: "
                f"{archive_path}"
            )
        roles[role] += 1
        item["override_role"] = role
        item["override_provenance"] = OVERLAY_PROVENANCE

        digest = record.get("sha256")
        if _is_sha256(digest):
            item["content_sha256"] = str(digest)
            hashes_applied += 1

    unmatched_manifest = sorted(set(by_path) - matched_paths)
    if unmatched_manifest:
        raise ValueError(
            "reconciled manifest contains items absent from Drive projection: "
            f"{len(unmatched_manifest)}"
        )

    expected_roles = {
        str(key): int(value)
        for key, value in (summary.get("role_counts") or {}).items()
    }
    actual_roles = dict(sorted(roles.items()))
    if expected_roles and actual_roles != dict(sorted(expected_roles.items())):
        raise ValueError(
            "Drive projection role counts differ from reconciled manifest: "
            f"{actual_roles} != {dict(sorted(expected_roles.items()))}"
        )

    enriched = dict(document)
    enriched["notebooks"] = notebooks
    enriched["items"] = items
    report = {
        "manifest_sha256": _canonical_sha(manifest),
        "matched_items": len(matched_paths),
        "hashes_applied": hashes_applied,
        "metadata_signature_items": len(items) - hashes_applied,
        "notebooks": len(notebooks),
        "roles": actual_roles,
        "unknown": actual_roles.get("unknown", 0),
        "provenance": OVERLAY_PROVENANCE,
    }
    return enriched, report
