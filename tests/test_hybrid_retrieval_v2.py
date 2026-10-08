from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mq_agent.memory.hybrid_retrieval import _rrf, hybrid_retrieval_v2
from mq_agent.tools.contract_validation import validate_contract
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
    assert result["input_fingerprints"]["notebook_catalog_sha256"] == (
        "sha256:" + hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    )
    assert result["input_fingerprints"]["notebook_semantic_index_sha256"] is None
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


def test_v2_schema_keeps_historical_runs_without_input_fingerprints_readable(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")

    result = hybrid_retrieval_v2(
        "MCP orchestration",
        catalog_path=catalog_path,
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
        codegraph_search=lambda _query: {"results": []},
    )
    historical = dict(result)
    historical.pop("input_fingerprints")

    validate_contract("hybrid_retrieval_v2.schema.json", historical)


def test_semantic_index_fingerprint_binds_exact_consumed_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    semantic_index_path = tmp_path / "semantic-index.json"
    semantic_index_path.write_text(
        json.dumps(
            {
                "schema": "notebook-semantic-index-experiment.v1",
                "canonical": False,
                "disposable": True,
                "chunks": [
                    {
                        "chunk_id": "doc-1:0",
                        "item_id": "item-1",
                        "drive_item_id": "doc-1",
                        "notebook_id": "nb-1",
                        "notebook_title": "MQ research",
                        "title": "MCP orchestration tools",
                        "source_role": "source",
                        "claim_eligible": True,
                        "modified_time": "2026-10-01T00:00:00Z",
                        "content_sha256": "a" * 64,
                        "start_char": 0,
                        "end_char": 3,
                        "vector": [1.0],
                    }
                ],
                "trace": {"chunks": 1, "embedding_dimension": 1},
            }
        ),
        encoding="utf-8",
    )

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    result = hybrid_retrieval_v2(
        "MCP orchestration",
        semantic_index_path=semantic_index_path,
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
        enable_codegraph=False,
    )

    expected = "sha256:" + hashlib.sha256(semantic_index_path.read_bytes()).hexdigest()
    assert result["input_fingerprints"]["notebook_catalog_sha256"] is None
    assert result["input_fingerprints"]["notebook_semantic_index_sha256"] == expected
    assert result["status"] == "PASS"


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


def test_empty_notebook_vector_index_is_unavailable(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")
    semantic_index_path = tmp_path / "semantic-index.json"
    semantic_index_path.write_text(
        json.dumps(
            {
                "schema": "notebook-semantic-index-experiment.v1",
                "canonical": False,
                "disposable": True,
                "chunks": [],
                "trace": {"chunks": 0, "embedding_dimension": 0},
            }
        ),
        encoding="utf-8",
    )

    result = hybrid_retrieval_v2(
        "MCP orchestration",
        catalog_path=catalog_path,
        semantic_index_path=semantic_index_path,
        active_search=lambda _query: {"results": [{"id": "memory-1"}]},
        enable_codegraph=False,
    )

    vector = next(row for row in result["channels"] if row["name"] == "notebook-vector")
    assert vector["status"] == "UNAVAILABLE"
    assert vector["returned"] == 0
    assert "no usable chunks" in vector["reason"]
    assert result["status"] == "PASS"


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
