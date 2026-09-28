"""Metadata/text retrieval baseline for the Drive-backed NotebookLM corpus.

D4 searches the disposable D3 catalog and can merge provider-neutral text-match
metadata supplied by a future Drive adapter. It never opens file bodies itself.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from mq_agent.notebook_corpus import validate_catalog

_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "about",
    "across",
    "before",
    "find",
    "for",
    "from",
    "in",
    "material",
    "materials",
    "of",
    "on",
    "or",
    "original",
    "return",
    "source",
    "sources",
    "the",
    "to",
    "what",
    "with",
}
_ROLE_PRIORITY = {
    "source": 0,
    "derived": 1,
    "derived-note": 2,
    "metadata-or-other": 3,
    "unknown": 4,
    "interaction": 5,
}


def query_terms(query: str) -> list[str]:
    """Normalize a query without semantic expansion."""

    terms: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(query.lower()):
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _matched_terms(text: str, terms: Sequence[str]) -> list[str]:
    haystack = set(_TOKEN_RE.findall(text.lower()))
    return [term for term in terms if term in haystack]


def _text_hit_map(
    text_hits: Sequence[Mapping[str, Any]] | None,
    terms: Sequence[str],
) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for hit in text_hits or []:
        drive_item_id = str(hit.get("drive_item_id", ""))
        if not drive_item_id:
            continue
        supplied = {
            str(value).lower()
            for value in (hit.get("matched_terms") or [])
            if str(value).lower() in terms
        }
        if supplied:
            merged.setdefault(drive_item_id, set()).update(supplied)
    return {
        key: sorted(values, key=lambda value: terms.index(value))
        for key, values in merged.items()
    }


def catalog_summary(catalog: Mapping[str, Any]) -> dict[str, Any]:
    validate_catalog(catalog)
    roles = Counter(
        str(item["classification"]["role"]) for item in catalog["items"]
    )
    duplicate_hashes = Counter(
        str(item["content_sha256"])
        for item in catalog["items"]
        if item.get("content_sha256")
    )
    duplicate_groups = sum(1 for count in duplicate_hashes.values() if count > 1)
    return {
        "schema": catalog["schema"],
        "corpus": dict(catalog["corpus"]),
        "snapshot_at": catalog["snapshot_at"],
        "notebooks": len(catalog["notebooks"]),
        "items": len(catalog["items"]),
        "roles": dict(sorted(roles.items())),
        "duplicate_hash_groups": duplicate_groups,
    }


def search_catalog(
    catalog: Mapping[str, Any],
    query: str,
    *,
    top_k: int = 10,
    text_hits: Sequence[Mapping[str, Any]] | None = None,
    connector_calls: int = 0,
) -> dict[str, Any]:
    """Search catalog metadata plus supplied text-match metadata.

    Ranking is intentionally simple and inspectable:
    metadata/text term coverage first, source role as the first tie-breaker,
    then stable notebook/item identity.
    """

    validate_catalog(catalog)
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if connector_calls < 0:
        raise ValueError("connector_calls cannot be negative")

    terms = query_terms(query)
    notebook_titles = {
        str(row["notebook_id"]): str(row["title"]) for row in catalog["notebooks"]
    }
    text_by_drive_id = _text_hit_map(text_hits, terms)
    candidates: list[dict[str, Any]] = []

    if terms:
        for item in catalog["items"]:
            notebook_title = notebook_titles[str(item["notebook_id"])]
            item_terms = _matched_terms(str(item["title"]), terms)
            notebook_terms = _matched_terms(notebook_title, terms)
            external_terms = text_by_drive_id.get(str(item["drive_item_id"]), [])

            # Item-title matches are the strongest local metadata signal;
            # notebook-title matches widen recall without pretending to inspect
            # the file. Provider text terms add another explicit channel.
            score = len(item_terms) * 4 + len(notebook_terms) * 2 + len(external_terms) * 3
            if score == 0:
                continue

            channels: list[str] = []
            if item_terms:
                channels.append("item-title")
            if notebook_terms:
                channels.append("notebook-title")
            if external_terms:
                channels.append("provider-text")

            matched = [
                term
                for term in terms
                if term in set(item_terms) | set(notebook_terms) | set(external_terms)
            ]
            role = str(item["classification"]["role"])
            candidates.append(
                {
                    "item_id": item["item_id"],
                    "drive_item_id": item["drive_item_id"],
                    "notebook_id": item["notebook_id"],
                    "notebook_title": notebook_title,
                    "title": item["title"],
                    "mime_type": item["mime_type"],
                    "size_bytes": item["size_bytes"],
                    "modified_time": item["modified_time"],
                    "origin_provider": item["origin_provider"],
                    "source_role": role,
                    "classification_method": item["classification"]["method"],
                    "content_sha256": item.get("content_sha256"),
                    "score": score,
                    "matched_terms": matched,
                    "match_channels": channels,
                }
            )

    candidates.sort(
        key=lambda row: (
            -int(row["score"]),
            _ROLE_PRIORITY.get(str(row["source_role"]), 99),
            str(row["notebook_id"]),
            str(row["item_id"]),
        )
    )
    results = candidates[:top_k]
    role_mix = Counter(str(row["source_role"]) for row in results)

    return {
        "query": query,
        "terms": terms,
        "top_k": top_k,
        "results": results,
        "trace": {
            "catalog_notebooks": len(catalog["notebooks"]),
            "catalog_items": len(catalog["items"]),
            "metadata_items_considered": len(catalog["items"]),
            "provider_text_hits_supplied": len(text_hits or []),
            "provider_text_items_matched": len(text_by_drive_id),
            "candidates_before_top_k": len(candidates),
            "returned": len(results),
            "returned_role_mix": dict(sorted(role_mix.items())),
            "file_bodies_fetched": 0,
            "bytes_fetched": 0,
            "connector_calls": connector_calls,
            "no_result": not results,
            "ranking": "score-desc, source-role-priority, notebook-id, item-id",
        },
    }


def show_catalog_entry(catalog: Mapping[str, Any], identifier: str) -> dict[str, Any]:
    validate_catalog(catalog)
    for notebook in catalog["notebooks"]:
        if identifier in {notebook["notebook_id"], notebook["drive_item_id"]}:
            items = [
                item for item in catalog["items"]
                if item["notebook_id"] == notebook["notebook_id"]
            ]
            return {"kind": "notebook", "notebook": dict(notebook), "items": items}

    for item in catalog["items"]:
        if identifier in {item["item_id"], item["drive_item_id"]}:
            notebook = next(
                row for row in catalog["notebooks"]
                if row["notebook_id"] == item["notebook_id"]
            )
            return {"kind": "item", "item": dict(item), "notebook": dict(notebook)}

    raise KeyError(identifier)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
