from __future__ import annotations

from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_corpus_semantic import (
    FROZEN_D4_QUERIES,
    build_semantic_index,
    evaluate_semantic_vs_d4,
    semantic_search,
)


class FakeTextProvider:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def fetch_text(self, drive_item_id, mime_type, *, max_bytes):
        self.calls.append((drive_item_id, mime_type, max_bytes))
        text = self.payloads[drive_item_id]
        encoded = text.encode("utf-8")[:max_bytes]
        return {
            "status": "ok",
            "text": encoded.decode("utf-8", errors="ignore"),
            "bytes_fetched": len(encoded),
        }


class KeywordEmbedding:
    vocab = ["mcp", "agent", "togaf", "guitar", "akkadian", "python"]

    def embed(self, texts):
        vectors = []
        for text in texts:
            lower = text.lower()
            vectors.append([1.0 if term in lower else 0.0 for term in self.vocab])
        return vectors


def _catalog():
    doc = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-29T00:00:00Z",
        "notebooks": [
            {"drive_item_id": "nb-mcp", "title": "General Engineering"},
            {"drive_item_id": "nb-ai", "title": "General AI"},
            {"drive_item_id": "nb-ea", "title": "Architecture"},
            {"drive_item_id": "nb-guitar", "title": "Music"},
        ],
        "items": [
            {
                "drive_item_id": "mcp-source",
                "notebook_drive_item_id": "nb-mcp",
                "parent_drive_item_id": "s1",
                "relative_path": "Sources/doc1.md",
                "title": "document one",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-20T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "a" * 64,
            },
            {
                "drive_item_id": "ai-source",
                "notebook_drive_item_id": "nb-ai",
                "parent_drive_item_id": "s2",
                "relative_path": "Sources/doc2.md",
                "title": "document two",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-20T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "b" * 64,
            },
            {
                "drive_item_id": "ea-source",
                "notebook_drive_item_id": "nb-ea",
                "parent_drive_item_id": "s3",
                "relative_path": "Sources/doc3.md",
                "title": "document three",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-20T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "c" * 64,
            },
            {
                "drive_item_id": "guitar-source",
                "notebook_drive_item_id": "nb-guitar",
                "parent_drive_item_id": "s4",
                "relative_path": "Sources/doc4.md",
                "title": "document four",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-20T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "d" * 64,
            },
        ],
    }
    return build_from_document(doc)[0]


def _texts():
    return FakeTextProvider(
        {
            "mcp-source": "Building an MCP server in Python with tools.",
            "ai-source": "Agentic AI and multi agent design patterns.",
            "ea-source": "TOGAF enterprise architecture concepts.",
            "guitar-source": "Pentatonic guitar technique and rock licks.",
        }
    )


def test_semantic_index_keeps_provenance_and_is_disposable():
    index = build_semantic_index(
        _catalog(),
        _texts(),
        KeywordEmbedding(),
        chunk_chars=64,
        overlap_chars=8,
    )

    assert index["canonical"] is False
    assert index["disposable"] is True
    assert index["trace"]["hosted_egress"] is False
    assert all(row["drive_item_id"] for row in index["chunks"])
    assert all(row["notebook_id"] for row in index["chunks"])
    assert all(row["source_role"] == "source" for row in index["chunks"])
    assert all(row["claim_eligible"] is True for row in index["chunks"])


def test_semantic_search_does_not_change_source_role():
    index = build_semantic_index(_catalog(), _texts(), KeywordEmbedding())

    report = semantic_search(index, "MCP Python", KeywordEmbedding(), top_k=3)

    assert report["results"][0]["drive_item_id"] == "mcp-source"
    assert report["results"][0]["source_role"] == "source"
    assert report["results"][0]["claim_eligible"] is True
    assert report["trace"]["source_role_preserved"] is True


def test_semantic_search_collapses_repeated_chunks_per_file():
    index = build_semantic_index(
        _catalog(),
        _texts(),
        KeywordEmbedding(),
        chunk_chars=32,
        overlap_chars=8,
    )

    report = semantic_search(index, "agent", KeywordEmbedding(), top_k=10)

    ids = [row["drive_item_id"] for row in report["results"]]
    assert len(ids) == len(set(ids))


def test_evaluation_uses_exact_frozen_d4_queries_and_can_measure_improvement():
    catalog = _catalog()
    index = build_semantic_index(catalog, _texts(), KeywordEmbedding())
    expected = {
        FROZEN_D4_QUERIES[0]: ["mcp-source"],
        FROZEN_D4_QUERIES[1]: ["ai-source"],
        FROZEN_D4_QUERIES[2]: ["ea-source"],
        FROZEN_D4_QUERIES[3]: ["guitar-source"],
        FROZEN_D4_QUERIES[4]: [],
        FROZEN_D4_QUERIES[5]: [],
    }

    report = evaluate_semantic_vs_d4(
        catalog,
        index,
        KeywordEmbedding(),
        expected,
        top_k=3,
    )

    assert [row["query"] for row in report["queries"]] == FROZEN_D4_QUERIES
    assert report["metrics"]["semantic_passes"] >= report["metrics"]["lexical_passes"]
    assert report["metrics"]["provenance_coverage"] == 1.0
    assert report["metrics"]["hosted_egress"] is False


def test_negative_control_can_report_semantic_regression():
    catalog = _catalog()
    index = build_semantic_index(catalog, _texts(), KeywordEmbedding())
    expected: dict[str, list[str]] = {query: [] for query in FROZEN_D4_QUERIES}

    report = evaluate_semantic_vs_d4(
        catalog,
        index,
        KeywordEmbedding(),
        expected,
        top_k=3,
    )

    negative = next(
        row for row in report["queries"]
        if "Akkadian" in row["query"]
    )
    assert negative["semantic_pass"] is False
    assert report["decision"] in {
        "SEMANTIC_REGRESSION_OR_MIXED",
        "NO_MEASURED_BENEFIT",
    }
