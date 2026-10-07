"""Read-only hybrid retrieval shadow orchestration.

The active mq-mcp semantic-memory result stays authoritative. Shadow mode adds
existing local Notebook corpus retrieval channels, merges only result identities
and provenance, and reports divergence/latency. It never changes context,
answers, routing, memory promotion, or a remote vector store.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from mq_agent.tools.contract_validation import validate_contract

ActiveSearch = Callable[[str], Any]


def _digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _active_refs(result: Any) -> list[dict[str, str]]:
    """Project active retrieval to identities without persisting its content."""
    if isinstance(result, dict):
        items = result.get("items") or result.get("results")
        if isinstance(items, list):
            refs: list[dict[str, str]] = []
            for item in items:
                if isinstance(item, dict):
                    value = item.get("id") or item.get("key")
                    if value:
                        refs.append(
                            {
                                "source": "mq-mcp-semantic",
                                "reference": str(value),
                            }
                        )
            if refs:
                return refs
    return [
        {
            "source": "mq-mcp-semantic",
            "reference": "sha256:" + _digest(result),
        }
    ]


def _notebook_refs(rows: list[dict[str, Any]], channel: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for row in rows:
        value = row.get("drive_item_id") or row.get("item_id")
        if value:
            refs.append(
                {
                    "source": channel,
                    "reference": str(value),
                }
            )
    return refs


def _dedupe(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, str]] = []
    for ref in refs:
        key = (ref["source"], ref["reference"])
        if key in seen:
            continue
        seen.add(key)
        output.append(ref)
    return output


def hybrid_shadow(
    query: str,
    *,
    catalog_path: Path | None = None,
    semantic_index_path: Path | None = None,
    semantic_model: str = "nomic-embed-text",
    top_k: int = 10,
    active_search: ActiveSearch | None = None,
) -> dict[str, Any]:
    """Compare the active semantic-memory surface with a hybrid shadow union."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    if active_search is None:
        from mq_agent.tools.mcp_bridge import MultiMCPBridge

        active_search = MultiMCPBridge().search_semantic_memory

    from mq_agent.tools.mcp_bridge import tool_failure

    channels: list[dict[str, Any]] = []

    started = time.perf_counter()
    active_raw = active_search(query)
    active_ms = round((time.perf_counter() - started) * 1000, 3)
    active_failure = tool_failure("search_semantic_memory", active_raw)
    if active_failure:
        active_refs: list[dict[str, str]] = []
        channels.append(
            {
                "name": "mq-mcp-semantic",
                "status": "UNAVAILABLE",
                "latency_ms": active_ms,
                "returned": 0,
                "reason": active_failure[:240],
            }
        )
    else:
        active_refs = _active_refs(active_raw)
        channels.append(
            {
                "name": "mq-mcp-semantic",
                "status": "AVAILABLE",
                "latency_ms": active_ms,
                "returned": len(active_refs),
                "reason": None,
            }
        )

    shadow_refs = list(active_refs)

    if catalog_path is not None:
        from mq_agent.notebook_corpus_search import load_json, search_catalog

        started = time.perf_counter()
        catalog = load_json(catalog_path.expanduser())
        lexical = search_catalog(catalog, query, top_k=top_k)
        lexical_ms = round((time.perf_counter() - started) * 1000, 3)
        refs = _notebook_refs(lexical["results"], "notebook-lexical")
        shadow_refs.extend(refs)
        channels.append(
            {
                "name": "notebook-lexical",
                "status": "AVAILABLE",
                "latency_ms": lexical_ms,
                "returned": len(refs),
                "reason": None,
            }
        )
    else:
        catalog = None

    if semantic_index_path is not None:
        from mq_agent.notebook_corpus_search import load_json
        from mq_agent.notebook_corpus_semantic import (
            OllamaEmbeddingProvider,
            semantic_search,
        )

        started = time.perf_counter()
        index = load_json(semantic_index_path.expanduser())
        semantic = semantic_search(
            index,
            query,
            OllamaEmbeddingProvider(model=semantic_model),
            top_k=top_k,
        )
        semantic_ms = round((time.perf_counter() - started) * 1000, 3)
        refs = _notebook_refs(semantic["results"], "notebook-semantic")
        shadow_refs.extend(refs)
        channels.append(
            {
                "name": "notebook-semantic",
                "status": "AVAILABLE",
                "latency_ms": semantic_ms,
                "returned": len(refs),
                "reason": None,
            }
        )

    active_refs = _dedupe(active_refs)
    shadow_refs = _dedupe(shadow_refs)
    active_keys = {(row["source"], row["reference"]) for row in active_refs}
    shadow_keys = {(row["source"], row["reference"]) for row in shadow_refs}
    added = [
        row
        for row in shadow_refs
        if (row["source"], row["reference"]) not in active_keys
    ]
    available = sum(1 for row in channels if row["status"] == "AVAILABLE")

    payload = {
        "schema": "mq.hybrid-retrieval-shadow.v1",
        "status": "PASS" if available >= 2 else "INSUFFICIENT_EVIDENCE",
        "query_sha256": _digest(query),
        "active_authoritative": True,
        "shadow_effect_on_active_result": False,
        "top_k": top_k,
        "channels": channels,
        "active": {
            "result_count": len(active_refs),
            "refs": active_refs,
        },
        "shadow": {
            "result_count": len(shadow_refs),
            "refs": shadow_refs,
            "added_count": len(added),
            "added_refs": added,
            "overlap_count": len(active_keys & shadow_keys),
            "provenance_coverage": (
                1.0
                if shadow_refs
                and all(row.get("source") and row.get("reference") for row in shadow_refs)
                else 0.0
                if shadow_refs
                else None
            ),
        },
        "limitations": [
            "Shadow retrieval does not alter the active answer or context.",
            "Result identities compare retrieval surfaces; they do not prove relevance.",
            "Quality activation still requires explicit relevance evidence and feedback gates.",
        ],
    }
    validate_contract("hybrid_retrieval_shadow.schema.json", payload)
    return payload
