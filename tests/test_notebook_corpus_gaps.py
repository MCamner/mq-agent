from __future__ import annotations

from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_corpus_gaps import (
    analyze_gaps,
    collect_questions,
    extract_questions,
    normalize_question,
)


class FakeFetcher:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def fetch_text(self, drive_item_id, mime_type, *, max_bytes):
        self.calls.append((drive_item_id, mime_type, max_bytes))
        text = self.payloads[drive_item_id]
        encoded = text.encode("utf-8")[:max_bytes]
        return {
            "status": "ok",
            "reason": None,
            "text": encoded.decode("utf-8", errors="ignore"),
            "bytes_fetched": len(encoded),
            "truncated": len(encoded) < len(text.encode("utf-8")),
        }


def _catalog():
    document = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-29T00:00:00Z",
        "notebooks": [
            {"drive_item_id": "nb-a", "title": "MCP Research A"},
            {"drive_item_id": "nb-b", "title": "MCP Research B"},
            {"drive_item_id": "nb-c", "title": "Legacy Python"},
        ],
        "items": [
            {
                "drive_item_id": "chat-a",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "chat-folder-a",
                "relative_path": "Chat History/session-a.md",
                "title": "Session A",
                "mime_type": "text/markdown",
                "size_bytes": 200,
                "modified_time": "2026-09-25T10:00:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "chat-b",
                "notebook_drive_item_id": "nb-b",
                "parent_drive_item_id": "chat-folder-b",
                "relative_path": "Chat History/session-b.md",
                "title": "Session B",
                "mime_type": "text/markdown",
                "size_bytes": 200,
                "modified_time": "2026-09-26T10:00:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "source-mcp",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "sources-a",
                "relative_path": "Sources/mcp transport.md",
                "title": "MCP transport guidance",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-20T10:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "a" * 64,
            },
            {
                "drive_item_id": "derived-auth",
                "notebook_drive_item_id": "nb-b",
                "parent_drive_item_id": "artifacts-b",
                "relative_path": "Artifacts/oauth tokens.md",
                "title": "OAuth token rotation guidance",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-21T10:00:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "source-python",
                "notebook_drive_item_id": "nb-c",
                "parent_drive_item_id": "sources-c",
                "relative_path": "Sources/python packaging.md",
                "title": "Python packaging migration",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2024-01-01T10:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "b" * 64,
            },
        ],
    }
    return build_from_document(document)[0]


def _fetcher():
    return FakeFetcher(
        {
            "chat-a": (
                "User: What transport should MCP use?\n"
                "How do we rotate OAuth tokens?\n"
                "What evidence do we have for the missing topic?"
            ),
            "chat-b": (
                "what transport should mcp use?\n"
                "What changed in Python packaging?\n"
                "This statement has no question."
            ),
        }
    )


def test_extract_questions_is_deterministic_and_ignores_non_questions():
    rows = extract_questions(
        "User: What transport should MCP use?\n"
        "This is an answer.\n"
        "Hur fungerar OAuth tokens?"
    )

    assert [row["question_key"] for row in rows] == [
        "what transport should mcp use",
        "hur fungerar oauth tokens",
    ]
    assert rows[0]["question_id"] == rows[0]["question_id"]


def test_normalize_question_deduplicates_case_prefix_and_punctuation():
    assert normalize_question("User: What transport should MCP use?") == (
        normalize_question("what transport should MCP use???")
    )


def test_collect_questions_deduplicates_across_notebooks_and_marks_history_only():
    report = collect_questions(_catalog(), _fetcher())

    transport = next(
        row for row in report["questions"]
        if row["question_key"] == "what transport should mcp use"
    )
    assert transport["occurrence_count"] == 2
    assert transport["notebook_count"] == 2
    assert transport["recurring"] is True
    assert transport["cross_notebook"] is True
    assert transport["claim_eligible"] is False
    assert transport["evidence_role"] == "inquiry-history-only"
    assert all(
        trace["source_role"] == "interaction"
        and trace["claim_eligible"] is False
        for trace in transport["interaction_trace"]
    )


def test_collect_questions_reads_only_interaction_role_files():
    fetcher = _fetcher()
    collect_questions(_catalog(), fetcher)

    assert {call[0] for call in fetcher.calls} == {"chat-a", "chat-b"}


def test_gap_analysis_marks_source_derived_missing_and_stale_states():
    catalog = _catalog()
    questions = collect_questions(catalog, _fetcher())
    report = analyze_gaps(catalog, questions, stale_after_days=365)

    by_key = {
        row["question"]: row
        for row in report["gaps"]
    }

    transport = next(
        row for row in report["gaps"]
        if "transport should MCP use" in row["question"]
    )
    oauth = next(
        row for row in report["gaps"]
        if "rotate OAuth tokens" in row["question"]
    )
    missing = next(
        row for row in report["gaps"]
        if "missing topic" in row["question"]
    )
    python = next(
        row for row in report["gaps"]
        if "Python packaging" in row["question"]
    )

    assert transport["gap_state"] == "SOURCE_MATCHES_PRESENT"
    assert oauth["gap_state"] == "DERIVED_ONLY"
    assert missing["gap_state"] == "NO_SOURCE_EVIDENCE"
    assert python["gap_state"] == "STALE_SOURCE_THEME"
    assert all(row["interaction_is_evidence"] is False for row in by_key.values())
    assert report["trace"]["semantic_embeddings_used"] is False
    assert report["trace"]["interaction_promoted_to_evidence"] is False


def test_gap_output_contains_no_answer_claim_from_chat_history():
    catalog = _catalog()
    questions = collect_questions(catalog, _fetcher())
    report = analyze_gaps(catalog, questions)

    assert "answer" not in report
    for row in report["gaps"]:
        assert "answer" not in row
        assert row["claim_eligible"] is False


def test_question_order_is_deterministic():
    first = collect_questions(_catalog(), _fetcher())
    second = collect_questions(_catalog(), _fetcher())

    assert first["questions"] == second["questions"]
