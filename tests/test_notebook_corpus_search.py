from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import app

from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_corpus_search import (
    catalog_summary,
    query_terms,
    search_catalog,
    show_catalog_entry,
)


runner = CliRunner()


FROZEN_QUERIES = [
    "Find sources about building an MCP server in Python.",
    "What design patterns recur across material about agentic AI and multi-agent systems?",
    "Find material explaining TOGAF 10 and enterprise architecture.",
    "Find sources about pentatonic guitar technique and recurring rock licks.",
    "For a matching notebook, return original sources before NotebookLM-generated artifacts.",
    "Find sources about Akkadian cuneiform accounting tablets.",
]


def _catalog() -> dict:
    document = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-28T16:32:50Z",
        "notebooks": [
            {"drive_item_id": "nb-mcp", "title": "MCP Python Engineering"},
            {"drive_item_id": "nb-ai", "title": "Agentic AI Multi Agent Systems"},
            {"drive_item_id": "nb-ea", "title": "TOGAF 10 Enterprise Architecture"},
            {"drive_item_id": "nb-guitar", "title": "Pentatonic Guitar Rock Licks"},
        ],
        "items": [
            {
                "drive_item_id": "mcp-source",
                "notebook_drive_item_id": "nb-mcp",
                "parent_drive_item_id": "mcp-sources",
                "relative_path": "Sources/building-mcp-server-python.html",
                "title": "Building MCP Server in Python.html",
                "mime_type": "text/html",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:00:00Z",
                "origin_provider": "takeout",
                "content_sha256": "a" * 64,
            },
            {
                "drive_item_id": "mcp-derived",
                "notebook_drive_item_id": "nb-mcp",
                "parent_drive_item_id": "mcp-artifacts",
                "relative_path": "Artifacts/building-mcp-server-python.pdf",
                "title": "Building MCP Server in Python.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 200,
                "modified_time": "2026-09-27T10:01:00Z",
                "origin_provider": "notebooklm",
                "content_sha256": "b" * 64,
            },
            {
                "drive_item_id": "ai-source",
                "notebook_drive_item_id": "nb-ai",
                "parent_drive_item_id": "ai-sources",
                "relative_path": "Sources/agentic-design-patterns.pdf",
                "title": "Agentic Design Patterns for Multi Agent Systems.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 300,
                "modified_time": "2026-09-27T10:02:00Z",
                "origin_provider": "takeout",
                "content_sha256": "c" * 64,
            },
            {
                "drive_item_id": "ea-source",
                "notebook_drive_item_id": "nb-ea",
                "parent_drive_item_id": "ea-sources",
                "relative_path": "Sources/togaf-enterprise-architecture.pdf",
                "title": "TOGAF 10 Enterprise Architecture.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 400,
                "modified_time": "2026-09-27T10:03:00Z",
                "origin_provider": "takeout",
                "content_sha256": "d" * 64,
            },
            {
                "drive_item_id": "guitar-source",
                "notebook_drive_item_id": "nb-guitar",
                "parent_drive_item_id": "guitar-sources",
                "relative_path": "Sources/pentatonic-rock-licks.pdf",
                "title": "Pentatonic Guitar Technique and Rock Licks.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 500,
                "modified_time": "2026-09-27T10:04:00Z",
                "origin_provider": "takeout",
                "content_sha256": "e" * 64,
            },
        ],
    }
    catalog, _ = build_from_document(document)
    return catalog


def test_frozen_d4_queries_remain_exact():
    assert FROZEN_QUERIES == [
        "Find sources about building an MCP server in Python.",
        "What design patterns recur across material about agentic AI and multi-agent systems?",
        "Find material explaining TOGAF 10 and enterprise architecture.",
        "Find sources about pentatonic guitar technique and recurring rock licks.",
        "For a matching notebook, return original sources before NotebookLM-generated artifacts.",
        "Find sources about Akkadian cuneiform accounting tablets.",
    ]


@pytest.mark.parametrize(
    ("query", "drive_item_id"),
    [
        (FROZEN_QUERIES[0], "mcp-source"),
        (FROZEN_QUERIES[1], "ai-source"),
        (FROZEN_QUERIES[2], "ea-source"),
        (FROZEN_QUERIES[3], "guitar-source"),
    ],
)
def test_metadata_baseline_recalls_expected_topic(query, drive_item_id):
    report = search_catalog(_catalog(), query, top_k=5)

    assert any(row["drive_item_id"] == drive_item_id for row in report["results"])
    assert report["trace"]["file_bodies_fetched"] == 0
    assert report["trace"]["bytes_fetched"] == 0


def test_source_role_breaks_equal_relevance_tie_before_derived():
    report = search_catalog(_catalog(), FROZEN_QUERIES[0], top_k=5)
    matching = [
        row for row in report["results"]
        if row["drive_item_id"] in {"mcp-source", "mcp-derived"}
    ]

    assert [row["source_role"] for row in matching[:2]] == ["source", "derived"]


def test_negative_control_stays_no_result_without_broadening():
    report = search_catalog(_catalog(), FROZEN_QUERIES[5], top_k=10)

    assert report["results"] == []
    assert report["trace"]["no_result"] is True
    assert report["trace"]["candidates_before_top_k"] == 0


def test_provider_text_hits_can_add_recall_without_copying_body():
    catalog = _catalog()
    extra = copy.deepcopy(catalog)
    # Rename away local metadata so the only useful signal is the supplied
    # provider-text match metadata.
    item = next(row for row in extra["items"] if row["drive_item_id"] == "ai-source")
    item["title"] = "document.pdf"
    notebook = next(row for row in extra["notebooks"] if row["notebook_id"] == item["notebook_id"])
    notebook["title"] = "Research"

    report = search_catalog(
        extra,
        FROZEN_QUERIES[1],
        text_hits=[
            {
                "drive_item_id": "ai-source",
                "matched_terms": ["agentic", "design", "patterns", "multi", "agent", "systems"],
            }
        ],
        connector_calls=1,
    )

    assert report["results"][0]["drive_item_id"] == "ai-source"
    assert report["results"][0]["match_channels"] == ["provider-text"]
    assert report["trace"]["connector_calls"] == 1
    assert report["trace"]["file_bodies_fetched"] == 0


def test_unrecognized_provider_text_item_does_not_create_candidate():
    report = search_catalog(
        _catalog(),
        "rareword",
        text_hits=[{"drive_item_id": "not-in-catalog", "matched_terms": ["rareword"]}],
    )

    assert report["results"] == []


def test_trace_explains_selection_and_role_mix():
    report = search_catalog(_catalog(), FROZEN_QUERIES[0], top_k=2)

    assert report["terms"] == ["building", "mcp", "server", "python"]
    assert report["trace"]["metadata_items_considered"] == 5
    assert report["trace"]["returned"] == 2
    assert report["trace"]["returned_role_mix"] == {"derived": 1, "source": 1}
    assert all(row["matched_terms"] for row in report["results"])
    assert all(row["match_channels"] for row in report["results"])


def test_catalog_summary_counts_roles_and_duplicates():
    catalog = _catalog()
    catalog["items"][1]["content_sha256"] = catalog["items"][0]["content_sha256"]

    summary = catalog_summary(catalog)

    assert summary["notebooks"] == 4
    assert summary["items"] == 5
    assert summary["roles"] == {"derived": 1, "source": 4}
    assert summary["duplicate_hash_groups"] == 1


def test_show_resolves_item_and_notebook():
    catalog = _catalog()
    item = catalog["items"][0]
    item_result = show_catalog_entry(catalog, item["item_id"])
    notebook_result = show_catalog_entry(catalog, item["notebook_id"])

    assert item_result["kind"] == "item"
    assert notebook_result["kind"] == "notebook"
    assert any(row["item_id"] == item["item_id"] for row in notebook_result["items"])


def test_show_unknown_identifier_fails_closed():
    with pytest.raises(KeyError):
        show_catalog_entry(_catalog(), "missing")


def test_query_terms_does_not_semantically_expand():
    assert query_terms("Find sources about MCP in Python") == ["mcp", "python"]



def _write_catalog(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8")
    return path


def test_cli_catalog_json(tmp_path):
    path = _write_catalog(tmp_path)
    result = runner.invoke(app, ["notebook", "catalog", "--catalog", str(path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["notebooks"] == 4
    assert payload["items"] == 5


def test_cli_search_json_is_machine_readable(tmp_path):
    path = _write_catalog(tmp_path)
    result = runner.invoke(
        app,
        [
            "notebook",
            "search",
            FROZEN_QUERIES[0],
            "--catalog",
            str(path),
            "--top-k",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["results"][0]["source_role"] == "source"
    assert payload["trace"]["file_bodies_fetched"] == 0


def test_cli_negative_control_returns_successful_empty_result(tmp_path):
    path = _write_catalog(tmp_path)
    result = runner.invoke(
        app,
        ["notebook", "search", FROZEN_QUERIES[5], "--catalog", str(path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["results"] == []
    assert payload["trace"]["no_result"] is True


def test_cli_show_json(tmp_path):
    catalog = _catalog()
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    identifier = catalog["items"][0]["item_id"]

    result = runner.invoke(
        app,
        ["notebook", "show", identifier, "--catalog", str(path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "item"


def test_cli_show_missing_is_nonzero(tmp_path):
    path = _write_catalog(tmp_path)
    result = runner.invoke(
        app,
        ["notebook", "show", "missing", "--catalog", str(path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "NOT_FOUND"
