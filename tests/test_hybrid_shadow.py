from __future__ import annotations

import json
from pathlib import Path

from mq_agent.memory.hybrid_shadow import hybrid_shadow
from mq_agent.notebook_corpus import build_from_document


def _catalog() -> dict:
    document = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-10-01T00:00:00Z",
        "notebooks": [{"drive_item_id": "nb-1", "title": "MQ research"}],
        "items": [
            {
                "drive_item_id": "doc-1",
                "notebook_drive_item_id": "nb-1",
                "parent_drive_item_id": "sources",
                "relative_path": "Sources/mcp.md",
                "title": "MCP orchestration tools",
                "mime_type": "text/markdown",
                "size_bytes": 42,
                "modified_time": "2026-10-01T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "a" * 64,
            }
        ],
    }
    return build_from_document(document)[0]


def test_hybrid_shadow_adds_provenance_without_changing_active_result(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog()))

    result = hybrid_shadow(
        "MCP orchestration",
        catalog_path=catalog_path,
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
    )

    assert result["status"] == "PASS"
    assert result["active_authoritative"] is True
    assert result["shadow_effect_on_active_result"] is False
    assert result["active"]["refs"] == [
        {"source": "mq-mcp-semantic", "reference": "memory-1"}
    ]
    assert result["shadow"]["added_count"] == 1
    assert result["shadow"]["added_refs"][0]["reference"] == "doc-1"
    assert result["shadow"]["provenance_coverage"] == 1.0
    assert "query" not in result
    assert result["query_sha256"]


def test_one_available_channel_is_insufficient_evidence() -> None:
    result = hybrid_shadow(
        "only active",
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
    )

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["shadow_effect_on_active_result"] is False
