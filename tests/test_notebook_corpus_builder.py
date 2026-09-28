from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mq_agent.notebook_corpus import (
    build_from_document,
    classify_path,
    materialize,
)


def _document() -> dict:
    return {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-28T16:32:50Z",
        "notebooks": [
            {"drive_item_id": "drive-nb-b", "title": "Second"},
            {"drive_item_id": "drive-nb-a", "title": "First"},
        ],
        "items": [
            {
                "drive_item_id": "drive-item-b",
                "notebook_drive_item_id": "drive-nb-b",
                "parent_drive_item_id": "folder-b",
                "relative_path": "Artifacts/report.pdf",
                "title": "report.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 20,
                "modified_time": "2026-09-27T11:00:00Z",
                "origin_provider": "notebooklm",
                "content_sha256": "b" * 64,
            },
            {
                "drive_item_id": "drive-item-a",
                "notebook_drive_item_id": "drive-nb-a",
                "parent_drive_item_id": "folder-a",
                "relative_path": "Sources/source.html",
                "title": "source.html",
                "mime_type": "text/html",
                "size_bytes": 10,
                "modified_time": "2026-09-27T10:00:00Z",
                "origin_provider": "takeout",
                "content_sha256": "a" * 64,
            },
        ],
    }


def test_reordered_metadata_builds_same_logical_catalog_and_checkpoint():
    first = _document()
    second = _document()
    second["notebooks"].reverse()
    second["items"].reverse()

    catalog_a, checkpoint_a = build_from_document(first)
    catalog_b, checkpoint_b = build_from_document(second)

    assert catalog_a == catalog_b
    assert checkpoint_a == checkpoint_b


def test_notebook_identity_survives_display_title_change():
    before = _document()
    after = _document()
    after["notebooks"][1]["title"] = "Renamed First"

    catalog_before, _ = build_from_document(before)
    catalog_after, _ = build_from_document(after)

    ids_before = {
        row["drive_item_id"]: row["notebook_id"] for row in catalog_before["notebooks"]
    }
    ids_after = {
        row["drive_item_id"]: row["notebook_id"] for row in catalog_after["notebooks"]
    }
    assert ids_before == ids_after


@pytest.mark.parametrize(
    ("path", "role", "method"),
    [
        ("Sources/a.pdf", "source", "structural"),
        ("Artifacts/a.pdf", "derived", "structural"),
        ("Notes/a.md", "derived-note", "structural"),
        ("Chat History/a.json", "interaction", "structural"),
        ("metadata.json", "metadata-or-other", "structural"),
        ("Other/a.txt", "unknown", "unknown"),
        (None, "unknown", "unknown"),
    ],
)
def test_structural_classification(path, role, method):
    assert classify_path(path) == {"role": role, "method": method}


def test_override_requires_provenance():
    with pytest.raises(ValueError, match="override_provenance"):
        classify_path("Sources/a.pdf", override_role="derived")


def test_override_records_provenance():
    assert classify_path(
        "Sources/a.pdf",
        override_role="derived",
        override_provenance="operator-reviewed-2026-09-29",
    ) == {
        "role": "derived",
        "method": "override",
        "override_provenance": "operator-reviewed-2026-09-29",
    }


def test_unmapped_manifest_record_is_excluded_not_repaired():
    document = _document()
    document["items"].append(
        {
            "drive_item_id": "orphan-root-metadata",
            "notebook_drive_item_id": "",
            "parent_drive_item_id": "corpus-root",
            "relative_path": None,
            "title": "metadata.json",
            "mime_type": "application/json",
            "size_bytes": 5,
            "modified_time": "2026-09-27T09:00:00Z",
            "origin_provider": "takeout",
        }
    )

    catalog, checkpoint = build_from_document(document)

    assert len(catalog["items"]) == 2
    assert checkpoint["excluded_items"] == 1
    assert checkpoint["excluded_reasons"] == {"unmapped_notebook": 1}
    assert all(row["drive_item_id"] != "orphan-root-metadata" for row in catalog["items"])


def test_duplicate_provider_item_identity_fails_closed():
    document = _document()
    document["items"].append(dict(document["items"][0]))

    with pytest.raises(ValueError, match="duplicate item drive_item_id"):
        build_from_document(document)


def test_duplicate_hashes_remain_separate_items():
    document = _document()
    document["items"][1]["content_sha256"] = document["items"][0]["content_sha256"]

    catalog, _ = build_from_document(document)

    assert len(catalog["items"]) == 2
    assert {row["content_sha256"] for row in catalog["items"]} == {"b" * 64}


def test_output_validates_against_vendored_canonical_schema():
    catalog, _ = build_from_document(_document())
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "notebook_corpus_index.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    assert list(validator.iter_errors(catalog)) == []


def test_materialize_writes_reproducible_files(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    checkpoint_path = tmp_path / "checkpoint.json"

    materialize(
        _document(),
        catalog_path=catalog_path,
        checkpoint_path=checkpoint_path,
    )
    first_catalog = catalog_path.read_bytes()
    first_checkpoint = checkpoint_path.read_bytes()

    materialize(
        _document(),
        catalog_path=catalog_path,
        checkpoint_path=checkpoint_path,
    )

    assert catalog_path.read_bytes() == first_catalog
    assert checkpoint_path.read_bytes() == first_checkpoint
