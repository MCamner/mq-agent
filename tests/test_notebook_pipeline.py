"""Tests for the operational NotebookLM P0-P5 pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_pipeline import (
    atlas_evidence_bundle,
    build_catalog_stage,
    build_sync_state,
    diff_sync_state,
    incremental_semantic_sync,
    pipeline_status,
    sync_catalog,
)

runner = CliRunner()


def _d3(items: list[dict] | None = None) -> dict:
    rows = items or [
        {
            "drive_item_id": "source-a",
            "notebook_drive_item_id": "nb-a",
            "parent_drive_item_id": "sources-a",
            "relative_path": "Sources/MCP Python.md",
            "title": "MCP Python",
            "mime_type": "text/markdown",
            "size_bytes": 20,
            "modified_time": "2026-09-29T00:00:00Z",
            "origin_provider": "google-drive",
            "content_sha256": "a" * 64,
        }
    ]
    return {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-29T18:00:00Z",
        "notebooks": [{"drive_item_id": "nb-a", "title": "Notebook A"}],
        "items": rows,
    }


class FakeTextProvider:
    def __init__(self, texts: dict[str, str]):
        self.texts = texts
        self.calls: list[str] = []

    def fetch_text(self, drive_item_id, mime_type, *, max_bytes):
        self.calls.append(drive_item_id)
        text = self.texts[drive_item_id][:max_bytes]
        return {
            "status": "ok",
            "text": text,
            "bytes_fetched": len(text.encode("utf-8")),
        }


class FakeEmbeddings:
    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        values = list(texts)
        self.calls.append(values)
        return [[float(len(text)), 1.0] for text in values]


def test_p0_materializes_catalog_and_status(tmp_path: Path):
    d3 = tmp_path / "d3.json"
    catalog = tmp_path / "catalog.json"
    checkpoint = tmp_path / "checkpoint.json"
    state = tmp_path / "sync.json"
    d3.write_text(json.dumps(_d3()), encoding="utf-8")

    report = build_catalog_stage(
        d3_input=d3,
        catalog=catalog,
        checkpoint=checkpoint,
    )
    assert report["stage"] == "P0"
    assert report["notebooks"] == 1
    assert report["items"] == 1

    sync = sync_catalog(catalog_path=catalog, state_path=state, write=True)
    assert sync["added"] == ["source-a"]
    assert sync["hash_backed_items"] == 1

    status = pipeline_status(
        catalog_path=catalog,
        semantic_path=tmp_path / "semantic.json",
        state_path=state,
    )
    assert status["status"] == "READY"
    assert status["notebooks"] == 1
    assert status["items"] == 1
    assert status["unknown"] == 0


def test_p3_prefers_sha256_and_detects_changed_removed_added():
    first, _ = build_from_document(_d3())
    first_state = build_sync_state(first)

    rows = [
        {
            "drive_item_id": "source-a",
            "notebook_drive_item_id": "nb-a",
            "parent_drive_item_id": "sources-a",
            "relative_path": "Sources/MCP Python.md",
            "title": "MCP Python",
            "mime_type": "text/markdown",
            "size_bytes": 21,
            "modified_time": "2026-09-29T01:00:00Z",
            "origin_provider": "google-drive",
            "content_sha256": "b" * 64,
        },
        {
            "drive_item_id": "source-b",
            "notebook_drive_item_id": "nb-a",
            "parent_drive_item_id": "sources-a",
            "relative_path": "Sources/Agents.md",
            "title": "Agents",
            "mime_type": "text/markdown",
            "size_bytes": 10,
            "modified_time": "2026-09-29T01:00:00Z",
            "origin_provider": "google-drive",
            "content_sha256": "c" * 64,
        },
    ]
    second, _ = build_from_document(_d3(rows))
    diff = diff_sync_state(first_state, build_sync_state(second))

    assert diff["changed"] == ["source-a"]
    assert diff["added"] == ["source-b"]
    assert diff["removed"] == []


def test_incremental_semantic_sync_reuses_unchanged_vectors(tmp_path: Path):
    rows = [
        {
            "drive_item_id": "source-a",
            "notebook_drive_item_id": "nb-a",
            "parent_drive_item_id": "sources-a",
            "relative_path": "Sources/A.md",
            "title": "A",
            "mime_type": "text/markdown",
            "size_bytes": 10,
            "modified_time": "2026-09-29T00:00:00Z",
            "origin_provider": "google-drive",
            "content_sha256": "a" * 64,
        },
        {
            "drive_item_id": "source-b",
            "notebook_drive_item_id": "nb-a",
            "parent_drive_item_id": "sources-a",
            "relative_path": "Sources/B.md",
            "title": "B",
            "mime_type": "text/markdown",
            "size_bytes": 10,
            "modified_time": "2026-09-29T00:00:00Z",
            "origin_provider": "google-drive",
            "content_sha256": "b" * 64,
        },
    ]
    catalog, _ = build_from_document(_d3(rows))
    item_a = next(row for row in catalog["items"] if row["drive_item_id"] == "source-a")
    previous = {
        "chunks": [
            {
                "chunk_id": f"{item_a['item_id']}:0",
                "item_id": item_a["item_id"],
                "drive_item_id": "source-a",
                "notebook_id": item_a["notebook_id"],
                "notebook_title": "Notebook A",
                "title": "A",
                "source_role": "source",
                "claim_eligible": True,
                "modified_time": item_a["modified_time"],
                "content_sha256": item_a["content_sha256"],
                "start_char": 0,
                "end_char": 4,
                "vector": [4.0, 1.0],
            }
        ]
    }
    provider = FakeTextProvider({"source-b": "new semantic material"})
    embeddings = FakeEmbeddings()

    report = incremental_semantic_sync(
        catalog,
        previous,
        {
            "added": ["source-b"],
            "changed": [],
            "removed": [],
            "unchanged": ["source-a"],
        },
        provider,
        embeddings,
        output_path=tmp_path / "semantic.json",
    )

    assert report["reused_chunks"] == 1
    assert report["new_chunks"] >= 1
    assert provider.calls == ["source-b"]
    saved = json.loads((tmp_path / "semantic.json").read_text(encoding="utf-8"))
    assert {row["drive_item_id"] for row in saved["chunks"]} == {
        "source-a",
        "source-b",
    }


def test_p5_never_promotes_derived_material_to_claim_evidence():
    retrieval = {
        "evidence": [
            {
                "claim_eligible": False,
                "grounding_status": "grounded",
                "excerpt": "Notebook generated interpretation",
                "provenance": {
                    "item_id": "item-derived",
                    "drive_item_id": "derived-1",
                    "notebook_id": "nb-1",
                    "notebook_title": "N",
                    "title": "Artifact",
                    "source_role": "derived",
                },
            }
        ]
    }

    report = atlas_evidence_bundle(retrieval, claim="A claim")

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["claim_eligible_count"] == 0
    assert report["policy"]["derived_is_claim_evidence"] is False


def test_notebook_operator_commands_are_registered():
    result = runner.invoke(app, ["notebook", "--help"])
    assert result.exit_code == 0
    for command in ("build", "status", "sync", "evidence", "atlas", "search"):
        assert command in result.stdout
