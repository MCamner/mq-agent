from __future__ import annotations

import json

import httpx
import pytest

from mq_agent.notebook_drive_inventory import (
    CHECKPOINT_SCHEMA,
    DriveInventoryError,
    FOLDER_MIME,
    GoogleDriveRestClient,
    new_checkpoint,
    refresh_changes,
    run_full_scan,
    scan_full_page,
    to_d3_input,
)


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.change_calls = []
        self.pages = {}
        self.change_pages = {}
        self.start_token = "changes-0"

    def list_children(self, folder_id, page_token=None):
        self.calls.append((folder_id, page_token))
        value = self.pages[(folder_id, page_token)]
        if isinstance(value, Exception):
            raise value
        return value

    def get_start_page_token(self):
        return self.start_token

    def list_changes(self, page_token):
        self.change_calls.append(page_token)
        value = self.change_pages[page_token]
        if isinstance(value, Exception):
            raise value
        return value


def _full_provider():
    provider = FakeProvider()
    provider.pages[("root", None)] = {
        "files": [
            {"id": "nb-a", "name": "Notebook A", "mimeType": FOLDER_MIME, "parents": ["root"]},
            {"id": "manifest", "name": "Private Manifest", "mimeType": FOLDER_MIME, "parents": ["root"]},
        ],
        "nextPageToken": "root-2",
    }
    provider.pages[("root", "root-2")] = {"files": []}
    provider.pages[("nb-a", None)] = {
        "files": [
            {"id": "sources", "name": "Sources", "mimeType": FOLDER_MIME, "parents": ["nb-a"]},
            {
                "id": "meta",
                "name": "Notebook A metadata.json",
                "mimeType": "application/json",
                "size": "10",
                "modifiedTime": "2026-09-27T10:00:00Z",
                "parents": ["nb-a"],
            },
        ]
    }
    provider.pages[("manifest", None)] = {"files": []}
    provider.pages[("sources", None)] = {
        "files": [
            {
                "id": "source-1",
                "name": "MCP Python.pdf",
                "mimeType": "application/pdf",
                "size": "100",
                "modifiedTime": "2026-09-27T10:01:00Z",
                "parents": ["sources"],
            }
        ]
    }
    return provider


def test_full_scan_resumes_from_opaque_page_token():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")

    run_full_scan(provider, checkpoint, max_pages=1)

    assert checkpoint["status"] == "partial"
    assert checkpoint["pending"][0]["folder_id"] == "root"
    assert checkpoint["pending"][0]["page_token"] == "root-2"

    run_full_scan(provider, checkpoint)

    assert checkpoint["status"] == "current"
    assert checkpoint["change_token"] == "changes-0"
    assert checkpoint["items"]["source-1"]["relative_path"] == "Notebook A/Sources/MCP Python.pdf"
    assert provider.calls.count(("root", None)) == 1


def test_failed_page_keeps_cursor_and_partial_state():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")
    provider.pages[("root", None)] = DriveInventoryError("quota")

    with pytest.raises(DriveInventoryError):
        scan_full_page(provider, checkpoint)

    assert checkpoint["status"] == "partial"
    assert checkpoint["pending"][0]["page_token"] is None
    assert checkpoint["last_error"] == "quota"


def test_retries_do_not_duplicate_records():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")

    run_full_scan(provider, checkpoint)
    count = len(checkpoint["items"])

    # A completed full scan is not replayed.
    run_full_scan(provider, checkpoint)

    assert len(checkpoint["items"]) == count
    assert checkpoint["status"] == "current"


def test_incremental_no_change_second_scan_is_one_change_call():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")
    run_full_scan(provider, checkpoint)

    provider.change_pages["changes-0"] = {
        "changes": [],
        "newStartPageToken": "changes-1",
    }
    refresh_changes(provider, checkpoint)

    assert checkpoint["status"] == "current"
    assert checkpoint["change_token"] == "changes-1"
    assert provider.change_calls == ["changes-0"]


def test_change_cursor_advances_page_by_page_and_resumes():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")
    run_full_scan(provider, checkpoint)

    provider.change_pages["changes-0"] = {
        "changes": [],
        "nextPageToken": "changes-page-2",
    }
    provider.change_pages["changes-page-2"] = {
        "changes": [],
        "newStartPageToken": "changes-2",
    }

    refresh_changes(provider, checkpoint, max_pages=1)
    assert checkpoint["status"] == "partial"
    assert checkpoint["change_token"] == "changes-page-2"

    refresh_changes(provider, checkpoint)
    assert checkpoint["status"] == "current"
    assert checkpoint["change_token"] == "changes-2"


def test_removed_item_is_retained_as_missing_history():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")
    run_full_scan(provider, checkpoint)
    provider.change_pages["changes-0"] = {
        "changes": [{"fileId": "source-1", "removed": True}],
        "newStartPageToken": "changes-1",
    }

    refresh_changes(provider, checkpoint)

    assert checkpoint["missing"]["source-1"]["reason"] == "removed"
    assert checkpoint["missing"]["source-1"]["last_known"]["title"] == "MCP Python.pdf"


def test_change_outside_known_corpus_is_ignored():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")
    run_full_scan(provider, checkpoint)
    provider.change_pages["changes-0"] = {
        "changes": [
            {
                "fileId": "elsewhere",
                "file": {
                    "id": "elsewhere",
                    "name": "Other.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["outside-folder"],
                },
            }
        ],
        "newStartPageToken": "changes-1",
    }

    refresh_changes(provider, checkpoint)

    assert "elsewhere" not in checkpoint["items"]


def test_d3_projection_excludes_local_manifest_folder():
    provider = _full_provider()
    checkpoint = new_checkpoint("root")
    run_full_scan(provider, checkpoint)

    projected = to_d3_input(
        checkpoint,
        snapshot_at="2026-09-29T00:00:00Z",
        excluded_top_level_folder_ids={"manifest"},
    )

    assert projected["notebooks"] == [
        {"drive_item_id": "nb-a", "title": "Notebook A"}
    ]
    assert {item["drive_item_id"] for item in projected["items"]} == {"meta", "source-1"}
    source = next(item for item in projected["items"] if item["drive_item_id"] == "source-1")
    assert source["relative_path"] == "Sources/MCP Python.pdf"


def test_d3_projection_refuses_partial_inventory():
    checkpoint = new_checkpoint("root")

    with pytest.raises(ValueError, match="current"):
        to_d3_input(checkpoint, snapshot_at="2026-09-29T00:00:00Z")


def test_checkpoint_schema_is_explicit():
    checkpoint = new_checkpoint("root")

    assert checkpoint["schema"] == CHECKPOINT_SCHEMA
    assert checkpoint["status"] == "partial"


def test_rest_client_retries_403_rate_limit_and_429():
    responses = iter(
        [
            httpx.Response(
                403,
                json={"error": {"errors": [{"reason": "rateLimitExceeded"}]}},
            ),
            httpx.Response(
                429,
                json={"error": {"errors": [{"reason": "rateLimitExceeded"}]}},
                headers={"Retry-After": "0"},
            ),
            httpx.Response(200, json={"files": []}),
        ]
    )

    def handler(request):
        return next(responses)

    sleeps = []
    client = GoogleDriveRestClient(
        "token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
        max_retries=3,
    )

    result = client.list_children("root")

    assert result == {"files": []}
    assert client.retry_count == 2
    assert client.request_count == 3
    assert sleeps == [1.0, 0.0]


def test_rest_client_does_not_retry_permission_403():
    def handler(request):
        return httpx.Response(
            403,
            json={"error": {"errors": [{"reason": "insufficientFilePermissions"}]}},
        )

    client = GoogleDriveRestClient(
        "token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    with pytest.raises(DriveInventoryError, match="403"):
        client.list_children("root")

    assert client.retry_count == 0
