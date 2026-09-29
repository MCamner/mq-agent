from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from mq_agent.main import app

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


runner = CliRunner()


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

    sleeps: list[float] = []
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



def test_cli_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN", raising=False)
    result = runner.invoke(
        app,
        [
            "notebook",
            "inventory",
            "--root-id",
            "root",
            "--checkpoint",
            str(tmp_path / "inventory.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert "access token" in payload["error"]


def test_cli_full_scan_writes_checkpoint_and_d3_projection(tmp_path, monkeypatch):
    import mq_agent.notebook_drive_inventory as inventory

    provider = _full_provider()

    class FakeClient:
        request_count = 4
        retry_count = 0

        def __init__(self, token):
            assert token == "secret"

        def list_children(self, folder_id, page_token=None):
            return provider.list_children(folder_id, page_token)

        def get_start_page_token(self):
            return provider.get_start_page_token()

        def list_changes(self, page_token):
            return provider.list_changes(page_token)

    monkeypatch.setattr(inventory, "GoogleDriveRestClient", FakeClient)
    monkeypatch.setenv("MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN", "secret")

    checkpoint = tmp_path / "inventory.json"
    d3_input = tmp_path / "d3.json"
    result = runner.invoke(
        app,
        [
            "notebook",
            "inventory",
            "--root-id",
            "root",
            "--checkpoint",
            str(checkpoint),
            "--d3-input",
            str(d3_input),
            "--snapshot-at",
            "2026-09-29T00:00:00Z",
            "--exclude-root-folder-id",
            "manifest",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "current"
    assert payload["d3_notebooks"] == 1
    assert payload["d3_items"] == 2
    assert checkpoint.is_file()
    assert d3_input.is_file()


def test_cli_changes_requires_existing_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN", "secret")
    result = runner.invoke(
        app,
        [
            "notebook",
            "inventory",
            "--changes",
            "--checkpoint",
            str(tmp_path / "missing.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert "existing completed checkpoint" in payload["error"]


def test_d3_projection_supports_legacy_and_canonical_notebook_layouts():
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "root_drive_item_id": "root",
        "status": "current",
        "mode": "changes",
        "pending": [],
        "folders": {
            "legacy-nb": {
                "drive_item_id": "legacy-nb",
                "title": "Legacy Notebook",
                "parent_drive_item_id": "root",
                "relative_path": "Legacy Notebook",
                "top_level_folder_id": "legacy-nb",
            },
            "canonical-container": {
                "drive_item_id": "canonical-container",
                "title": "notebooks",
                "parent_drive_item_id": "root",
                "relative_path": "notebooks",
                "top_level_folder_id": "canonical-container",
            },
            "canonical-nb": {
                "drive_item_id": "canonical-nb",
                "title": "New Notebook",
                "parent_drive_item_id": "canonical-container",
                "relative_path": "notebooks/New Notebook",
                "top_level_folder_id": "canonical-container",
            },
            "manifest": {
                "drive_item_id": "manifest",
                "title": "_manifest",
                "parent_drive_item_id": "root",
                "relative_path": "_manifest",
                "top_level_folder_id": "manifest",
            },
        },
        "items": {
            "legacy-source": {
                "drive_item_id": "legacy-source",
                "title": "source.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 10,
                "modified_time": "2026-09-29T00:00:00Z",
                "parent_drive_item_id": "legacy-nb",
                "relative_path": "Legacy Notebook/Sources/source.pdf",
                "top_level_folder_id": "legacy-nb",
            },
            "canonical-source": {
                "drive_item_id": "canonical-source",
                "title": "source.md",
                "mime_type": "text/markdown",
                "size_bytes": 11,
                "modified_time": "2026-09-29T00:00:00Z",
                "parent_drive_item_id": "canonical-nb",
                "relative_path": "notebooks/New Notebook/sources/source.md",
                "top_level_folder_id": "canonical-container",
            },
            "manifest-json": {
                "drive_item_id": "manifest-json",
                "title": "notebooklm-manifest.json",
                "mime_type": "application/json",
                "size_bytes": 12,
                "modified_time": "2026-09-29T00:00:00Z",
                "parent_drive_item_id": "manifest",
                "relative_path": "_manifest/notebooklm-manifest.json",
                "top_level_folder_id": "manifest",
            },
        },
        "missing": {},
        "change_token": "changes-1",
        "pages_read": 1,
        "last_error": None,
    }

    projected = to_d3_input(
        checkpoint,
        snapshot_at="2026-09-29T18:00:00Z",
        excluded_top_level_folder_ids={"manifest"},
    )

    assert {row["drive_item_id"] for row in projected["notebooks"]} == {
        "legacy-nb",
        "canonical-nb",
    }
    by_id = {row["drive_item_id"]: row for row in projected["items"]}
    assert by_id["legacy-source"]["relative_path"] == "Sources/source.pdf"
    assert by_id["canonical-source"]["relative_path"] == "sources/source.md"
    assert by_id["canonical-source"]["archive_relative_path"] == (
        "notebooks/New Notebook/sources/source.md"
    )
    assert "manifest-json" not in by_id
