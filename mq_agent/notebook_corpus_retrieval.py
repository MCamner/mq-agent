"""Evidence-aware selective retrieval over the NotebookLM corpus.

D5 consumes D4-ranked candidates, fetches only a bounded set of text-capable
items, and returns excerpts with explicit provenance. It does not synthesize an
answer and never upgrades derived or interaction material into source evidence.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import quote

import httpx

from mq_agent.notebook_corpus import validate_catalog
from mq_agent.notebook_corpus_search import search_catalog

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "text/html",
    "application/xhtml+xml",
}
_CLAIM_ROLE = "source"


class SelectiveFetchError(RuntimeError):
    """One selected provider item could not be read safely."""


class SelectiveTextProvider(Protocol):
    def fetch_text(
        self,
        drive_item_id: str,
        mime_type: str,
        *,
        max_bytes: int,
    ) -> Mapping[str, Any]: ...


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._suppressed = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._suppressed += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._suppressed:
            self._suppressed -= 1

    def handle_data(self, data: str) -> None:
        if not self._suppressed:
            self.parts.append(data)


def _html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    joined = " ".join(part.strip() for part in parser.parts if part.strip())
    return re.sub(r"\s+", " ", html.unescape(joined)).strip()


def _decode_text(payload: bytes, mime_type: str) -> str:
    text = payload.decode("utf-8", errors="replace")
    if mime_type in {"text/html", "application/xhtml+xml"}:
        return _html_to_text(text)
    return text.strip()


class GoogleDriveSelectiveFetcher:
    """Bounded Drive body reader for text-capable evidence only."""

    def __init__(
        self,
        access_token: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not access_token:
            raise ValueError("access_token must be non-empty")
        self._token = access_token
        self._client = client or httpx.Client(timeout=30.0)
        self.request_count = 0
        self.bytes_fetched = 0

    def fetch_text(
        self,
        drive_item_id: str,
        mime_type: str,
        *,
        max_bytes: int,
    ) -> Mapping[str, Any]:
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "*/*",
            "Range": f"bytes=0-{max_bytes - 1}",
        }
        if mime_type == GOOGLE_DOC_MIME:
            url = f"{DRIVE_API_BASE}/files/{quote(drive_item_id, safe='')}/export"
            params = {"mimeType": "text/plain"}
            effective_mime = "text/plain"
        elif mime_type in _TEXT_MIMES:
            url = f"{DRIVE_API_BASE}/files/{quote(drive_item_id, safe='')}"
            params = {"alt": "media"}
            effective_mime = mime_type
        else:
            return {
                "status": "unavailable",
                "reason": "unsupported_mime",
                "text": "",
                "bytes_fetched": 0,
            }

        self.request_count += 1
        response = self._client.get(url, params=params, headers=headers)
        if not response.is_success:
            return {
                "status": "unavailable",
                "reason": f"http_{response.status_code}",
                "text": "",
                "bytes_fetched": 0,
            }

        payload = response.content[:max_bytes]
        self.bytes_fetched += len(payload)
        return {
            "status": "ok",
            "reason": None,
            "text": _decode_text(payload, effective_mime),
            "bytes_fetched": len(payload),
            "truncated": len(response.content) > max_bytes
            or response.status_code == 206,
        }


def _excerpt(text: str, *, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max(0, max_chars - 1)].rstrip() + "…"


def _provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "notebook_id": row["notebook_id"],
        "notebook_title": row["notebook_title"],
        "drive_item_id": row["drive_item_id"],
        "item_id": row["item_id"],
        "title": row["title"],
        "mime_type": row["mime_type"],
        "modified_time": row["modified_time"],
        "origin_provider": row["origin_provider"],
        "source_role": row["source_role"],
        "classification_method": row["classification_method"],
        "content_sha256": row.get("content_sha256"),
    }


def retrieve_evidence(
    catalog: Mapping[str, Any],
    query: str,
    provider: SelectiveTextProvider,
    *,
    top_k: int = 10,
    max_files: int = 4,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 262_144,
    excerpt_chars: int = 4_000,
    text_hits: Sequence[Mapping[str, Any]] | None = None,
    scope: str = "archive",
) -> dict[str, Any]:
    """Build a bounded evidence bundle without answer synthesis."""

    validate_catalog(catalog)
    if scope not in {"archive", "live-runtime"}:
        raise ValueError("scope must be archive or live-runtime")
    if max_files < 1:
        raise ValueError("max_files must be at least 1")
    if max_bytes_per_file < 1 or max_total_bytes < 1:
        raise ValueError("byte budgets must be positive")
    if excerpt_chars < 1:
        raise ValueError("excerpt_chars must be positive")

    if scope == "live-runtime":
        return {
            "query": query,
            "status": "DELEGATE_RUNTIME",
            "reason": "live runtime/code truth must use current source/runtime tools",
            "evidence": [],
            "trace": {
                "selected": 0,
                "fetched": 0,
                "unavailable": 0,
                "bytes_fetched": 0,
                "interaction_rejected": 0,
                "derived_without_source": 0,
            },
        }

    ranked = search_catalog(
        catalog,
        query,
        top_k=top_k,
        text_hits=text_hits,
    )
    if not ranked["results"]:
        return {
            "query": query,
            "status": "NO_RESULT",
            "reason": "D4 returned no candidate",
            "evidence": [],
            "trace": {
                "selected": 0,
                "fetched": 0,
                "unavailable": 0,
                "bytes_fetched": 0,
                "interaction_rejected": 0,
                "derived_without_source": 0,
            },
        }

    source_by_notebook = {
        str(row["notebook_id"])
        for row in ranked["results"]
        if row["source_role"] == _CLAIM_ROLE
    }

    selected: list[Mapping[str, Any]] = []
    interaction_rejected = 0

    # D4 already sorted candidates. Preserve relevance ordering within each
    # authority class while ensuring source evidence is attempted before derived.
    for role in ("source", "derived", "derived-note", "metadata-or-other", "unknown"):
        role_rows = [
            row
            for row in ranked["results"]
            if row["source_role"] == role and row["source_role"] != "interaction"
        ]
        if role != "source":
            role_rows.sort(
                key=lambda row: (
                    str(row["notebook_id"]) not in source_by_notebook,
                    ranked["results"].index(row),
                )
            )
        for row in role_rows:
            selected.append(row)
            if len(selected) >= max_files:
                break
        if len(selected) >= max_files:
            break

    interaction_rejected = sum(
        1 for row in ranked["results"] if row["source_role"] == "interaction"
    )

    evidence: list[dict[str, Any]] = []
    total_bytes = 0
    unavailable = 0
    derived_without_source = 0

    for row in selected:
        remaining = max_total_bytes - total_bytes
        if remaining <= 0:
            break
        budget = min(max_bytes_per_file, remaining)

        try:
            fetched = provider.fetch_text(
                str(row["drive_item_id"]),
                str(row["mime_type"]),
                max_bytes=budget,
            )
        except Exception as exc:
            fetched = {
                "status": "unavailable",
                "reason": f"provider_error:{type(exc).__name__}",
                "text": "",
                "bytes_fetched": 0,
                "truncated": False,
            }
        status = str(fetched.get("status", "unavailable"))
        role = str(row["source_role"])
        has_ranked_source = str(row["notebook_id"]) in source_by_notebook
        claim_eligible = role == _CLAIM_ROLE and status == "ok"

        grounding_status = "source"
        if role != _CLAIM_ROLE:
            if has_ranked_source:
                grounding_status = "derived_with_source_candidate"
            else:
                grounding_status = "missing_source"
                derived_without_source += 1

        if status != "ok":
            unavailable += 1

        bytes_fetched = int(fetched.get("bytes_fetched") or 0)
        total_bytes += bytes_fetched

        evidence.append(
            {
                "fetch_status": status,
                "fetch_reason": fetched.get("reason"),
                "claim_eligible": claim_eligible,
                "grounding_status": grounding_status,
                "excerpt": (
                    _excerpt(str(fetched.get("text", "")), max_chars=excerpt_chars)
                    if status == "ok"
                    else ""
                ),
                "bytes_fetched": bytes_fetched,
                "truncated": bool(fetched.get("truncated", False)),
                "provenance": _provenance(row),
            }
        )

    source_ok = any(item["claim_eligible"] for item in evidence)
    fetched_ok = sum(1 for item in evidence if item["fetch_status"] == "ok")

    if source_ok:
        bundle_status = "EVIDENCE_READY"
        reason = None
    elif fetched_ok:
        bundle_status = "MISSING_SOURCE"
        reason = "retrieved material is not claim-eligible source evidence"
    elif evidence:
        bundle_status = "UNAVAILABLE"
        reason = "selected provider material could not be read"
    else:
        bundle_status = "NO_RESULT"
        reason = "no bounded evidence item was selected"

    return {
        "query": query,
        "status": bundle_status,
        "reason": reason,
        "evidence": evidence,
        "trace": {
            "d4_candidates": len(ranked["results"]),
            "selected": len(selected),
            "fetched": fetched_ok,
            "unavailable": unavailable,
            "bytes_fetched": total_bytes,
            "interaction_rejected": interaction_rejected,
            "derived_without_source": derived_without_source,
            "max_files": max_files,
            "max_bytes_per_file": max_bytes_per_file,
            "max_total_bytes": max_total_bytes,
        },
    }
