from __future__ import annotations

import json
from pathlib import Path

from mq_agent.memory.hybrid_retrieval import _rrf, hybrid_retrieval_v2
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


def test_v2_merges_channels_and_measures_explicit_fixture(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema": "mq.hybrid-retrieval-fixture.v1",
                "expected_refs": [
                    "semantic-memory:memory-1",
                    "notebook:doc-1",
                    "codegraph:mq_agent/tools/context_pack.py#build_task_pack",
                ],
                "contradicted_refs": ["codegraph:legacy.py#stale_symbol"],
                "stale_refs": ["codegraph:legacy.py#stale_symbol"],
            }
        ),
        encoding="utf-8",
    )

    result = hybrid_retrieval_v2(
        "MCP orchestration",
        catalog_path=catalog_path,
        fixture_path=fixture_path,
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
        codegraph_search=lambda _query: {
            "results": [
                {
                    "path": "mq_agent/tools/context_pack.py",
                    "symbol": "build_task_pack",
                },
                {"path": "legacy.py", "symbol": "stale_symbol"},
            ]
        },
    )

    assert result["schema"] == "mq.hybrid-retrieval.v2"
    assert result["status"] == "PASS"
    assert result["active_authoritative"] is True
    assert result["shadow_effect_on_active_result"] is False
    assert result["promotion_eligible"] is False
    assert result["merge"]["algorithm"] == "reciprocal-rank-fusion"
    assert result["quality_evidence"]["status"] == "MEASURED"
    assert result["metrics"]["precision"] == 0.75
    assert result["metrics"]["recall"] == 1.0
    assert result["metrics"]["contradiction_rate"] == 0.25
    assert result["metrics"]["stale_rate"] == 0.25
    assert result["metrics"]["payload_token_estimate"] > 0
    assert result["metrics"]["token_delta_vs_active"] is not None
    serialized = json.dumps(result)
    assert "MCP orchestration" not in serialized


def test_quality_metrics_are_unavailable_without_fixture(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")

    result = hybrid_retrieval_v2(
        "MCP orchestration",
        catalog_path=catalog_path,
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
        codegraph_search=lambda _query: {"results": []},
    )

    assert result["status"] == "PASS"
    assert result["quality_evidence"]["status"] == "UNAVAILABLE"
    assert result["metrics"]["precision"] is None
    assert result["metrics"]["recall"] is None
    assert result["metrics"]["contradiction_rate"] is None


def test_active_baseline_is_required_for_pass() -> None:
    result = hybrid_retrieval_v2(
        "retrieval",
        active_search=lambda _query: {"ok": False, "error": "mq-mcp down"},
        codegraph_search=lambda _query: {
            "results": [{"path": "mq_agent/main.py", "symbol": "app"}]
        },
    )

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["channels"][0]["status"] == "UNAVAILABLE"
    assert result["shadow_effect_on_active_result"] is False


def test_codegraph_can_be_explicitly_skipped() -> None:
    result = hybrid_retrieval_v2(
        "retrieval",
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
        enable_codegraph=False,
    )

    codegraph = next(row for row in result["channels"] if row["name"] == "codegraph")
    assert codegraph["status"] == "SKIPPED"
    assert result["status"] == "INSUFFICIENT_EVIDENCE"


def test_rrf_dedupes_same_notebook_identity_across_channels() -> None:
    merged = _rrf(
        [
            ("notebook-keyword", [{"namespace": "notebook", "reference": "doc-1"}]),
            ("notebook-vector", [{"namespace": "notebook", "reference": "doc-1"}]),
        ],
        top_k=10,
    )

    assert len(merged) == 1
    assert merged[0]["channels"] == ["notebook-keyword", "notebook-vector"]
    assert merged[0]["ranks"] == {"notebook-keyword": 1, "notebook-vector": 1}
