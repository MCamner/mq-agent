"""Quota-aware, read-only Google Drive inventory for the NotebookLM corpus.

Phase 2 owns transport and checkpoint semantics only. It lists metadata, stores
opaque provider cursors unchanged, and updates a disposable local inventory.
It never downloads file bodies and exposes no Drive mutation operation.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any, Protocol

import httpx

FOLDER_MIME = "application/vnd.google-apps.folder"
CHECKPOINT_SCHEMA = "notebook-drive-inventory-checkpoint.v1"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

_RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DriveInventoryError(RuntimeError):
    """A truthful provider/read failure; the caller should keep partial state."""


class DriveMetadataProvider(Protocol):
    """Small provider surface required by the inventory engine."""

    def list_children(
        self, folder_id: str, page_token: str | None = None
    ) -> Mapping[str, Any]: ...

    def get_start_page_token(self) -> str: ...

    def list_changes(self, page_token: str) -> Mapping[str, Any]: ...


class GoogleDriveRestClient:
    """Minimal Drive v3 metadata client with bounded exponential backoff.

    Authentication is injected as an access token and never persisted by this
    class. Only read endpoints are implemented.
    """

    def __init__(
        self,
        access_token: str,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 4,
    ) -> None:
        if not access_token:
            raise ValueError("access_token must be non-empty")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self._token = access_token
        self._client = client or httpx.Client(timeout=30.0)
        self._sleep = sleep
        self._max_retries = max_retries
        self.retry_count = 0
        self.request_count = 0

    @staticmethod
    def _reason(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        errors = payload.get("error", {}).get("errors") or []
        if errors:
            return errors[0].get("reason")
        return None

    @classmethod
    def _retryable(cls, response: httpx.Response) -> bool:
        if response.status_code in _RETRYABLE_STATUS:
            return True
        return (
            response.status_code == 403
            and cls._reason(response) in _RATE_LIMIT_REASONS
        )

    def _get(self, path: str, params: Mapping[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        for attempt in range(self._max_retries + 1):
            self.request_count += 1
            response = self._client.get(
                f"{DRIVE_API_BASE}{path}",
                params=dict(params),
                headers=headers,
            )
            if response.is_success:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise DriveInventoryError("Drive returned non-object JSON")
                return payload

            if not self._retryable(response) or attempt >= self._max_retries:
                reason = self._reason(response)
                suffix = f" reason={reason}" if reason else ""
                raise DriveInventoryError(
                    f"Drive metadata request failed: HTTP {response.status_code}{suffix}"
                )

            self.retry_count += 1
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(0.0, float(retry_after))
                except ValueError:
                    delay = float(2**attempt)
            else:
                delay = float(2**attempt)
            self._sleep(delay)

        raise AssertionError("unreachable")

    def list_children(
        self, folder_id: str, page_token: str | None = None
    ) -> Mapping[str, Any]:
        params: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": (
                "nextPageToken,files("
                "id,name,mimeType,size,modifiedTime,parents,trashed)"
            ),
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token is not None:
            params["pageToken"] = page_token
        return self._get("/files", params)

    def get_start_page_token(self) -> str:
        payload = self._get(
            "/changes/startPageToken",
            {"fields": "startPageToken", "supportsAllDrives": "true"},
        )
        token = payload.get("startPageToken")
        if not token:
            raise DriveInventoryError("Drive did not return startPageToken")
        return str(token)

    def list_changes(self, page_token: str) -> Mapping[str, Any]:
        if not page_token:
            raise ValueError("page_token must be non-empty")
        return self._get(
            "/changes",
            {
                "pageToken": page_token,
                "pageSize": 1000,
                "includeRemoved": "true",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "fields": (
                    "nextPageToken,newStartPageToken,"
                    "changes(fileId,removed,file("
                    "id,name,mimeType,size,modifiedTime,parents,trashed))"
                ),
            },
        )


def new_checkpoint(root_drive_item_id: str) -> dict[str, Any]:
    if not root_drive_item_id:
        raise ValueError("root_drive_item_id must be non-empty")
    return {
        "schema": CHECKPOINT_SCHEMA,
        "root_drive_item_id": root_drive_item_id,
        "status": "partial",
        "mode": "full",
        "pending": [
            {
                "folder_id": root_drive_item_id,
                "relative_path": "",
                "top_level_folder_id": None,
                "page_token": None,
            }
        ],
        "folders": {},
        "items": {},
        "missing": {},
        "change_token": None,
        "pages_read": 0,
        "last_error": None,
    }


def _normalize_file(raw: Mapping[str, Any]) -> dict[str, Any]:
    file_id = str(raw.get("id", ""))
    if not file_id:
        raise DriveInventoryError("Drive item missing id")
    parents = [str(value) for value in (raw.get("parents") or [])]
    return {
        "drive_item_id": file_id,
        "title": str(raw.get("name", "")),
        "mime_type": str(raw.get("mimeType", "")),
        "size_bytes": int(raw.get("size") or 0),
        "modified_time": str(raw.get("modifiedTime", "")),
        "parent_ids": parents,
    }


def _known_folder_ids(checkpoint: Mapping[str, Any]) -> set[str]:
    return {
        str(checkpoint["root_drive_item_id"]),
        *[str(key) for key in checkpoint["folders"]],
    }


def scan_full_page(
    provider: DriveMetadataProvider,
    checkpoint: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Process exactly one full-scan page and advance cursor only on success."""

    pending = checkpoint.get("pending") or []
    if not pending:
        if checkpoint.get("change_token") is None:
            checkpoint["change_token"] = provider.get_start_page_token()
        checkpoint["status"] = "current"
        checkpoint["mode"] = "changes"
        checkpoint["last_error"] = None
        return checkpoint

    task = dict(pending[0])
    folder_id = str(task["folder_id"])
    page_token = task.get("page_token")
    try:
        page = provider.list_children(folder_id, page_token)
    except Exception as exc:
        checkpoint["status"] = "partial"
        checkpoint["last_error"] = str(exc)
        raise

    files = page.get("files") or []
    next_page_token = page.get("nextPageToken")
    queued: list[dict[str, Any]] = []

    for raw in files:
        normalized = _normalize_file(raw)
        drive_id = normalized["drive_item_id"]
        title = normalized["title"]
        relative = (
            f"{task['relative_path']}/{title}".strip("/")
            if task.get("relative_path")
            else title
        )
        top_level = task.get("top_level_folder_id")
        if folder_id == checkpoint["root_drive_item_id"]:
            top_level = drive_id

        normalized["parent_drive_item_id"] = folder_id
        normalized["relative_path"] = relative
        normalized["top_level_folder_id"] = top_level

        if normalized["mime_type"] == FOLDER_MIME:
            checkpoint["folders"][drive_id] = normalized
            queued.append(
                {
                    "folder_id": drive_id,
                    "relative_path": relative,
                    "top_level_folder_id": top_level,
                    "page_token": None,
                }
            )
        else:
            checkpoint["items"][drive_id] = normalized
            checkpoint["missing"].pop(drive_id, None)

    if next_page_token:
        # The current folder still has another provider page, but folders
        # discovered on this successful page are already durable work. Keep
        # them behind the current cursor so pagination can resume without
        # losing descendants.
        pending[0] = {**task, "page_token": str(next_page_token)}
        pending.extend(queued)
    else:
        pending.pop(0)
        pending.extend(queued)

    checkpoint["pending"] = pending
    checkpoint["pages_read"] = int(checkpoint.get("pages_read", 0)) + 1
    checkpoint["status"] = "partial" if pending else "partial"
    checkpoint["last_error"] = None
    return checkpoint


def run_full_scan(
    provider: DriveMetadataProvider,
    checkpoint: MutableMapping[str, Any],
    *,
    max_pages: int | None = None,
) -> MutableMapping[str, Any]:
    pages = 0
    while checkpoint.get("status") != "current":
        if max_pages is not None and pages >= max_pages:
            break
        scan_full_page(provider, checkpoint)
        pages += 1
    return checkpoint


def _belongs_to_corpus(
    file: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
) -> bool:
    known = _known_folder_ids(checkpoint)
    return any(str(parent) in known for parent in (file.get("parents") or []))


def refresh_changes(
    provider: DriveMetadataProvider,
    checkpoint: MutableMapping[str, Any],
    *,
    max_pages: int | None = None,
) -> MutableMapping[str, Any]:
    """Apply Drive changes while preserving history and opaque cursors."""

    token = checkpoint.get("change_token")
    if not token:
        raise ValueError("checkpoint has no change_token; complete full scan first")

    checkpoint["mode"] = "changes"
    checkpoint["status"] = "partial"
    pages = 0
    cursor = str(token)

    while True:
        if max_pages is not None and pages >= max_pages:
            checkpoint["change_token"] = cursor
            checkpoint["status"] = "partial"
            return checkpoint

        try:
            page = provider.list_changes(cursor)
        except Exception as exc:
            checkpoint["change_token"] = cursor
            checkpoint["status"] = "partial"
            checkpoint["last_error"] = str(exc)
            raise

        for change in page.get("changes") or []:
            file_id = str(change.get("fileId", ""))
            removed = bool(change.get("removed"))
            raw_file = change.get("file") or {}
            trashed = bool(raw_file.get("trashed"))

            if removed or trashed:
                known = checkpoint["items"].get(file_id) or checkpoint["folders"].get(file_id)
                if known is not None:
                    checkpoint["missing"][file_id] = {
                        "drive_item_id": file_id,
                        "last_known": dict(known),
                        "reason": "removed" if removed else "trashed",
                    }
                continue

            if not raw_file or not _belongs_to_corpus(raw_file, checkpoint):
                continue

            normalized = _normalize_file(raw_file)
            parent_id = (
                normalized["parent_ids"][0]
                if normalized["parent_ids"]
                else ""
            )
            normalized["parent_drive_item_id"] = parent_id
            existing = checkpoint["items"].get(file_id) or checkpoint["folders"].get(file_id)
            if existing:
                normalized["relative_path"] = existing.get("relative_path", normalized["title"])
                normalized["top_level_folder_id"] = existing.get("top_level_folder_id")
            else:
                parent = checkpoint["folders"].get(parent_id)
                parent_path = parent.get("relative_path", "") if parent else ""
                normalized["relative_path"] = (
                    f"{parent_path}/{normalized['title']}".strip("/")
                )
                normalized["top_level_folder_id"] = (
                    parent.get("top_level_folder_id") if parent else None
                )

            if normalized["mime_type"] == FOLDER_MIME:
                checkpoint["folders"][file_id] = normalized
                checkpoint["items"].pop(file_id, None)
            else:
                checkpoint["items"][file_id] = normalized
                checkpoint["folders"].pop(file_id, None)
            checkpoint["missing"].pop(file_id, None)

        pages += 1
        checkpoint["pages_read"] = int(checkpoint.get("pages_read", 0)) + 1
        next_page = page.get("nextPageToken")
        if next_page:
            cursor = str(next_page)
            checkpoint["change_token"] = cursor
            continue

        new_start = page.get("newStartPageToken")
        if not new_start:
            raise DriveInventoryError(
                "Drive changes page ended without newStartPageToken"
            )
        checkpoint["change_token"] = str(new_start)
        checkpoint["status"] = "current"
        checkpoint["last_error"] = None
        return checkpoint


def to_d3_input(
    checkpoint: Mapping[str, Any],
    *,
    snapshot_at: str,
    excluded_top_level_folder_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Project a complete inventory into D3 normalized metadata.

    Top-level folders are notebook candidates except locally configured excluded
    folder IDs (for example a private manifest folder).
    """

    if checkpoint.get("status") != "current":
        raise ValueError("inventory must be current before D3 projection")
    excluded = excluded_top_level_folder_ids or set()
    root_id = str(checkpoint["root_drive_item_id"])

    notebooks: list[dict[str, Any]] = []
    notebook_ids: set[str] = set()
    for folder_id, folder in checkpoint["folders"].items():
        if folder.get("parent_drive_item_id") != root_id:
            continue
        if folder_id in excluded:
            continue
        notebook_ids.add(str(folder_id))
        notebooks.append(
            {
                "drive_item_id": str(folder_id),
                "title": str(folder.get("title", "")),
            }
        )

    items: list[dict[str, Any]] = []
    for row in checkpoint["items"].values():
        top_level = row.get("top_level_folder_id")
        if not top_level or str(top_level) not in notebook_ids:
            continue
        relative = str(row.get("relative_path", ""))
        notebook_title = checkpoint["folders"][str(top_level)]["title"]
        prefix = f"{notebook_title}/"
        notebook_relative = (
            relative[len(prefix):] if relative.startswith(prefix) else relative
        )
        items.append(
            {
                "drive_item_id": row["drive_item_id"],
                "notebook_drive_item_id": str(top_level),
                "parent_drive_item_id": row["parent_drive_item_id"],
                "relative_path": notebook_relative,
                "title": row["title"],
                "mime_type": row["mime_type"],
                "size_bytes": row["size_bytes"],
                "modified_time": row["modified_time"],
                "origin_provider": "google-drive",
            }
        )

    return {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": snapshot_at,
        "notebooks": sorted(notebooks, key=lambda value: value["drive_item_id"]),
        "items": sorted(items, key=lambda value: value["drive_item_id"]),
    }


def atomic_write_checkpoint(path: Path, checkpoint: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def load_checkpoint(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
