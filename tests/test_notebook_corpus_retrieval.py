from __future__ import annotations

import copy
import json

import httpx
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_corpus_retrieval import (
    GoogleDriveSelectiveFetcher,
    retrieve_evidence,
)

runner = CliRunner()


class FakeFetcher:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def fetch_text(self, drive_item_id, mime_type, *, max_bytes):
        self.calls.append((drive_item_id, mime_type, max_bytes))
        value = self.payloads[drive_item_id]
        if isinstance(value, Exception):
            raise value
        return value


def _catalog():
    document = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-29T00:00:00Z",
        "notebooks": [
            {"drive_item_id": "nb-a", "title": "MCP Python Engineering"},
            {"drive_item_id": "nb-b", "title": "Derived Only Notebook"},
        ],
        "items": [
            {
                "drive_item_id": "source-a",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "sources-a",
                "relative_path": "Sources/mcp-python.html",
                "title": "MCP Python source.html",
                "mime_type": "text/html",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:00:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "derived-a",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "artifacts-a",
                "relative_path": "Artifacts/mcp-python.md",
                "title": "MCP Python guide.md",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:01:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "chat-a",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "chat-a-folder",
                "relative_path": "Chat History/mcp-python.html",
                "title": "MCP Python chat.html",
                "mime_type": "text/html",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:02:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "derived-b",
                "notebook_drive_item_id": "nb-b",
                "parent_drive_item_id": "artifacts-b",
                "relative_path": "Artifacts/mcp-python.md",
                "title": "MCP Python derived only.md",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:03:00Z",
                "origin_provider": "google-drive",
            },
        ],
    }
    catalog, _ = build_from_document(document)
    return catalog


def _ok(text, n=10):
    return {
        "status": "ok",
        "reason": None,
        "text": text,
        "bytes_fetched": n,
        "truncated": False,
    }


def test_source_is_fetched_before_derived_and_only_source_is_claim_eligible():
    fetcher = FakeFetcher(
        {
            "source-a": _ok("source evidence"),
            "derived-a": _ok("derived interpretation"),
            "derived-b": _ok("derived without source"),
        }
    )

    report = retrieve_evidence(_catalog(), "MCP Python", fetcher, max_files=3)

    assert [call[0] for call in fetcher.calls][:2] == ["source-a", "derived-a"]
    assert report["evidence"][0]["claim_eligible"] is True
    assert report["evidence"][0]["provenance"]["source_role"] == "source"
    assert all(
        not item["claim_eligible"]
        for item in report["evidence"]
        if item["provenance"]["source_role"] != "source"
    )
    assert report["status"] == "EVIDENCE_READY"


def test_interaction_is_never_fetched_as_claim_evidence():
    fetcher = FakeFetcher(
        {
            "source-a": _ok("source"),
            "derived-a": _ok("derived"),
            "derived-b": _ok("derived only"),
        }
    )

    report = retrieve_evidence(_catalog(), "MCP Python", fetcher, max_files=4)

    assert "chat-a" not in [call[0] for call in fetcher.calls]
    assert report["trace"]["interaction_rejected"] == 1


def test_derived_without_source_is_explicitly_missing_source():
    catalog = _catalog()
    catalog["items"] = [
        item for item in catalog["items"] if item["drive_item_id"] == "derived-b"
    ]
    catalog["notebooks"] = [
        notebook for notebook in catalog["notebooks"]
        if notebook["drive_item_id"] == "nb-b"
    ]
    fetcher = FakeFetcher({"derived-b": _ok("derived only")})

    report = retrieve_evidence(catalog, "MCP Python", fetcher)

    assert report["status"] == "MISSING_SOURCE"
    assert report["evidence"][0]["grounding_status"] == "missing_source"
    assert report["evidence"][0]["claim_eligible"] is False


def test_provider_unavailable_degrades_readably():
    fetcher = FakeFetcher(
        {
            "source-a": {
                "status": "unavailable",
                "reason": "http_403",
                "text": "",
                "bytes_fetched": 0,
            },
            "derived-a": {
                "status": "unavailable",
                "reason": "unsupported_mime",
                "text": "",
                "bytes_fetched": 0,
            },
        }
    )

    report = retrieve_evidence(_catalog(), "MCP Python", fetcher, max_files=2)

    assert report["status"] == "UNAVAILABLE"
    assert report["trace"]["unavailable"] == 2
    assert report["evidence"][0]["fetch_reason"] == "http_403"


def test_live_runtime_scope_delegates_without_fetching():
    fetcher = FakeFetcher({})

    report = retrieve_evidence(
        _catalog(),
        "what does mq-agent main do now",
        fetcher,
        scope="live-runtime",
    )

    assert report["status"] == "DELEGATE_RUNTIME"
    assert fetcher.calls == []


def test_total_byte_budget_bounds_fetches():
    fetcher = FakeFetcher(
        {
            "source-a": _ok("source", n=7),
            "derived-a": _ok("derived", n=3),
            "derived-b": _ok("derived", n=3),
        }
    )

    report = retrieve_evidence(
        _catalog(),
        "MCP Python",
        fetcher,
        max_files=3,
        max_bytes_per_file=8,
        max_total_bytes=10,
    )

    assert report["trace"]["bytes_fetched"] == 10
    assert [call[2] for call in fetcher.calls] == [8, 3]


def test_provenance_is_present_for_every_evidence_item():
    fetcher = FakeFetcher(
        {
            "source-a": _ok("source"),
            "derived-a": _ok("derived"),
        }
    )

    report = retrieve_evidence(_catalog(), "MCP Python", fetcher, max_files=2)

    for item in report["evidence"]:
        assert item["provenance"]["notebook_id"]
        assert item["provenance"]["drive_item_id"]
        assert item["provenance"]["source_role"]
        assert item["provenance"]["modified_time"]


def test_no_result_fetches_nothing():
    fetcher = FakeFetcher({})

    report = retrieve_evidence(_catalog(), "Akkadian cuneiform tablets", fetcher)

    assert report["status"] == "NO_RESULT"
    assert fetcher.calls == []


def test_conflicting_sources_stay_separate():
    catalog = _catalog()
    source = next(
        item for item in catalog["items"] if item["drive_item_id"] == "source-a"
    )
    second = copy.deepcopy(source)
    second["drive_item_id"] = "source-a-2"
    second["item_id"] = "item-source-a-2"
    second["title"] = "MCP Python contradictory source.html"
    catalog["items"].append(second)

    fetcher = FakeFetcher(
        {
            "source-a": _ok("claim A"),
            "source-a-2": _ok("claim not A"),
        }
    )

    report = retrieve_evidence(catalog, "MCP Python", fetcher, max_files=2)

    assert len(report["evidence"]) == 2
    assert {item["excerpt"] for item in report["evidence"]} == {"claim A", "claim not A"}


def test_drive_fetcher_strips_html_and_bounds_bytes():
    def handler(request):
        assert request.headers["Range"] == "bytes=0-31"
        return httpx.Response(
            206,
            content=b"<html><style>x</style><body>Hello <b>world</b></body></html>",
        )

    fetcher = GoogleDriveSelectiveFetcher(
        "token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = fetcher.fetch_text("item", "text/html", max_bytes=32)

    assert result["status"] == "ok"
    assert "style" not in result["text"]
    assert result["bytes_fetched"] == 32
    assert result["truncated"] is True


def test_drive_fetcher_refuses_binary_mime_without_request():
    def handler(request):
        raise AssertionError("network should not be used")

    fetcher = GoogleDriveSelectiveFetcher(
        "token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = fetcher.fetch_text("pdf", "application/pdf", max_bytes=100)

    assert result["status"] == "unavailable"
    assert result["reason"] == "unsupported_mime"
    assert fetcher.request_count == 0



def test_provider_exception_becomes_unavailable_record():
    fetcher = FakeFetcher(
        {
            "source-a": RuntimeError("boom"),
            "derived-a": _ok("derived"),
        }
    )

    report = retrieve_evidence(_catalog(), "MCP Python", fetcher, max_files=2)

    assert report["status"] == "MISSING_SOURCE"
    assert report["evidence"][0]["fetch_status"] == "unavailable"
    assert report["evidence"][0]["fetch_reason"] == "provider_error:RuntimeError"
    assert report["evidence"][1]["fetch_status"] == "ok"



def test_cli_live_runtime_delegates_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN", raising=False)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "notebook",
            "retrieve",
            "what does mq-agent do now",
            "--catalog",
            str(path),
            "--scope",
            "live-runtime",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "DELEGATE_RUNTIME"
    assert payload["trace"]["fetched"] == 0


def test_cli_archive_requires_drive_token(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN", raising=False)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "notebook",
            "retrieve",
            "MCP Python",
            "--catalog",
            str(path),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert "access token" in payload["error"]
