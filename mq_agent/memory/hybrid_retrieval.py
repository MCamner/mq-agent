"""Measured zero-effect Hybrid Retrieval v2.

v1 stays available as ``memory hybrid-shadow``. v2 adds deterministic
multi-channel fusion and quality measurement while leaving the active semantic
memory result authoritative. No retrieved bodies, query text, or credentials
are returned or persisted by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Callable

from mq_agent.tools.contract_validation import validate_contract

RetrievalSearch = Callable[[str], Any]

SCHEMA_ID = "mq.hybrid-retrieval.v2"
FIXTURE_SCHEMA_ID = "mq.hybrid-retrieval-fixture.v1"
RRF_K = 60


def _digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json_with_fingerprint(
    path: Path,
    binding: dict[str, str | None],
) -> Any:
    """Read JSON once and bind the exact consumed bytes by SHA-256."""
    raw = path.expanduser().read_bytes()
    binding["sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    return json.loads(raw.decode("utf-8"))


def _payload_tokens(value: Any) -> int:
    """Return a deterministic rough token estimate without retaining payload text."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return math.ceil(len(raw) / 4) if raw else 0


def _ref(namespace: str, reference: Any) -> dict[str, str] | None:
    value = str(reference or "").strip()
    if not value:
        return None
    return {"namespace": namespace, "reference": value}


def _dedupe_refs(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, str]] = []
    for item in refs:
        key = (item["namespace"], item["reference"])
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _active_refs(result: Any) -> list[dict[str, str]]:
    if isinstance(result, dict):
        items = result.get("items") or result.get("results")
        if isinstance(items, list):
            refs: list[dict[str, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                value = item.get("id") or item.get("key") or item.get("reference")
                normalized = _ref("semantic-memory", value)
                if normalized:
                    refs.append(normalized)
            if refs:
                return _dedupe_refs(refs)
    return [{"namespace": "semantic-memory", "reference": "sha256:" + _digest(result)}]


def _notebook_refs(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for row in rows:
        normalized = _ref(
            "notebook",
            row.get("drive_item_id") or row.get("item_id"),
        )
        if normalized:
            refs.append(normalized)
    return _dedupe_refs(refs)


_CODEGRAPH_FILE_HEADER = re.compile(r"^\*\*`([^`]+)`\*\*(?: — (.+))?$")


def _codegraph_text_values(value: Any) -> list[str]:
    """Collect bounded text leaves from MCP wrappers or CLI output."""
    found: list[str] = []
    stack = [value]
    while stack and len(found) < 100:
        item = stack.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return found


def _codegraph_text_refs(value: Any) -> list[dict[str, str]]:
    """Extract stable path/symbol refs from CodeGraph explore file headers."""
    refs: list[dict[str, str]] = []
    for text in _codegraph_text_values(value):
        for line in text.splitlines():
            match = _CODEGRAPH_FILE_HEADER.match(line.strip())
            if not match:
                continue
            path, suffix = match.groups()
            if not suffix:
                normalized = _ref("codegraph", path)
                if normalized:
                    refs.append(normalized)
                continue

            # Explore headers are `path — sym(kind), other · tag` or
            # `path — sym, other`. The marker is unique in CodeGraph output;
            # source bodies do not use it as a section header.
            names = suffix.split(" · ", 1)[0]
            emitted = False
            for raw_name in names.split(","):
                name = raw_name.strip()
                if not name or re.fullmatch(r"\\+\\d+ more", name):
                    continue
                name = re.sub(r"\\([A-Za-z_-]+\\)$", "", name).strip()
                if not name:
                    continue
                normalized = _ref("codegraph", f"{path}#{name}")
                if normalized:
                    refs.append(normalized)
                    emitted = True
            if not emitted:
                normalized = _ref("codegraph", path)
                if normalized:
                    refs.append(normalized)
    return _dedupe_refs(refs)


def _codegraph_refs(result: Any) -> list[dict[str, str]]:
    """Normalize structured or textual CodeGraph explore results."""
    candidates: list[Any]
    if isinstance(result, dict):
        value = (
            result.get("results")
            or result.get("items")
            or result.get("nodes")
            or result.get("matches")
        )
        candidates = value if isinstance(value, list) else [result]
    elif isinstance(result, list):
        candidates = result
    else:
        candidates = []

    refs: list[dict[str, str]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("file") or item.get("file_path")
        symbol = item.get("symbol") or item.get("name")
        value = (
            item.get("reference")
            or item.get("node_id")
            or item.get("id")
            or (f"{path}#{symbol}" if path and symbol else path or symbol)
        )
        normalized = _ref("codegraph", value)
        if normalized:
            refs.append(normalized)

    if refs:
        return _dedupe_refs(refs)
    text_refs = _codegraph_text_refs(result)
    if text_refs:
        return text_refs
    if result not in (None, "", [], {}):
        return [{"namespace": "codegraph", "reference": "sha256:" + _digest(result)}]
    return []


def _failure_reason(result: Any) -> str | None:
    if isinstance(result, dict) and result.get("ok") is False:
        return str(result.get("error") or result.get("reason") or "tool reported failure")[:240]
    if isinstance(result, str):
        lowered = result.lower()
        if "not found on any connected mcp server" in lowered or "mcp bridge error" in lowered:
            return result[:240]
    return None


def _default_active_search(query: str) -> Any:
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    return MultiMCPBridge().search_semantic_memory(query)


def _default_codegraph_search(query: str, root: Path | None = None) -> Any:
    """Use the connected CodeGraph MCP tool or its local read-only CLI equivalent."""
    from mq_agent.memory.codegraph_runtime import search_codegraph

    return search_codegraph(query, root)


def _run_channel(
    name: str,
    kind: str,
    search: Callable[[], Any],
    normalize: Callable[[Any], list[dict[str, str]]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    started = time.perf_counter()
    try:
        raw = search()
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        failure = _failure_reason(raw)
        if failure:
            return (
                {
                    "name": name,
                    "kind": kind,
                    "status": "UNAVAILABLE",
                    "latency_ms": elapsed,
                    "returned": 0,
                    "payload_token_estimate": None,
                    "reason": failure,
                    "refs": [],
                },
                [],
            )
        refs = normalize(raw)
        return (
            {
                "name": name,
                "kind": kind,
                "status": "AVAILABLE",
                "latency_ms": elapsed,
                "returned": len(refs),
                "payload_token_estimate": _payload_tokens(raw),
                "reason": None,
                "refs": refs,
            },
            refs,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        return (
            {
                "name": name,
                "kind": kind,
                "status": "UNAVAILABLE",
                "latency_ms": elapsed,
                "returned": 0,
                "payload_token_estimate": None,
                "reason": str(exc)[:240],
                "refs": [],
            },
            [],
        )


def _rrf(
    channel_refs: list[tuple[str, list[dict[str, str]]]],
    top_k: int,
) -> list[dict[str, Any]]:
    scores: dict[tuple[str, str], float] = {}
    channels: dict[tuple[str, str], list[str]] = {}
    ranks: dict[tuple[str, str], dict[str, int]] = {}

    for channel, refs in channel_refs:
        for rank, item in enumerate(_dedupe_refs(refs), start=1):
            key = (item["namespace"], item["reference"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            channels.setdefault(key, []).append(channel)
            ranks.setdefault(key, {})[channel] = rank

    merged: list[dict[str, Any]] = [
        {
            "namespace": namespace,
            "reference": reference,
            "score": round(scores[(namespace, reference)], 9),
            "channels": sorted(set(channels[(namespace, reference)])),
            "ranks": dict(sorted(ranks[(namespace, reference)].items())),
        }
        for namespace, reference in scores
    ]
    merged.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["namespace"]),
            str(item["reference"]),
        )
    )
    return merged[:top_k]


def _ref_key(item: dict[str, Any]) -> str:
    return f"{item['namespace']}:{item['reference']}"


def _load_fixture(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    raw = path.expanduser().read_bytes()
    fixture = json.loads(raw.decode("utf-8"))
    if not isinstance(fixture, dict) or fixture.get("schema") != FIXTURE_SCHEMA_ID:
        raise ValueError(f"fixture schema must be {FIXTURE_SCHEMA_ID}")
    for field in ("expected_refs", "contradicted_refs", "stale_refs"):
        value = fixture.get(field, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) and ":" in item for item in value
        ):
            raise ValueError(f"fixture {field} must contain namespace:reference strings")
        if len(value) != len(set(value)):
            raise ValueError(f"fixture {field} must not contain duplicates")
    return fixture, hashlib.sha256(raw).hexdigest()


def _quality_metrics(
    refs: list[dict[str, Any]],
    fixture: dict[str, Any] | None,
) -> dict[str, float | None]:
    if fixture is None:
        return {
            "precision": None,
            "recall": None,
            "contradiction_rate": None,
            "stale_rate": None,
        }
    retrieved = {_ref_key(item) for item in refs}
    expected = set(fixture.get("expected_refs", []))
    contradicted = set(fixture.get("contradicted_refs", []))
    stale = set(fixture.get("stale_refs", []))
    hits = len(retrieved & expected)
    precision = hits / len(retrieved) if retrieved else (1.0 if not expected else 0.0)
    recall = hits / len(expected) if expected else None
    contradiction_rate = len(retrieved & contradicted) / len(retrieved) if retrieved else 0.0
    stale_rate = len(retrieved & stale) / len(retrieved) if retrieved else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6) if recall is not None else None,
        "contradiction_rate": round(contradiction_rate, 6),
        "stale_rate": round(stale_rate, 6),
    }


def hybrid_retrieval_v2(
    query: str,
    *,
    catalog_path: Path | None = None,
    semantic_index_path: Path | None = None,
    semantic_model: str = "nomic-embed-text",
    fixture_path: Path | None = None,
    codegraph_root: Path | None = None,
    top_k: int = 10,
    active_search: RetrievalSearch | None = None,
    codegraph_search: RetrievalSearch | None = None,
    enable_codegraph: bool = True,
) -> dict[str, Any]:
    """Measure a deterministic hybrid shadow without changing active retrieval."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    fixture, fixture_sha = _load_fixture(fixture_path)
    active_search = active_search or _default_active_search
    if codegraph_search is None:
        codegraph_search = lambda value: _default_codegraph_search(value, codegraph_root)

    channels: list[dict[str, Any]] = []
    ranked: list[tuple[str, list[dict[str, str]]]] = []
    catalog_binding: dict[str, str | None] = {"sha256": None}
    semantic_index_binding: dict[str, str | None] = {"sha256": None}

    active_channel, active_refs = _run_channel(
        "mq-mcp-semantic",
        "vector",
        lambda: active_search(query),
        _active_refs,
    )
    channels.append(active_channel)
    if active_channel["status"] == "AVAILABLE":
        ranked.append((active_channel["name"], active_refs))

    if catalog_path is not None:
        from mq_agent.notebook_corpus_search import search_catalog

        lexical_channel, lexical_refs = _run_channel(
            "notebook-keyword",
            "keyword",
            lambda: search_catalog(
                _read_json_with_fingerprint(catalog_path, catalog_binding),
                query,
                top_k=top_k,
            ),
            lambda raw: _notebook_refs(raw["results"]),
        )
        channels.append(lexical_channel)
        if lexical_channel["status"] == "AVAILABLE":
            ranked.append((lexical_channel["name"], lexical_refs))

    if semantic_index_path is not None:
        from mq_agent.notebook_corpus_semantic import (
            OllamaEmbeddingProvider,
            semantic_search,
        )

        semantic_channel, semantic_refs = _run_channel(
            "notebook-vector",
            "notebook",
            lambda: semantic_search(
                _read_json_with_fingerprint(
                    semantic_index_path,
                    semantic_index_binding,
                ),
                query,
                OllamaEmbeddingProvider(model=semantic_model),
                top_k=top_k,
            ),
            lambda raw: _notebook_refs(raw["results"]),
        )
        channels.append(semantic_channel)
        if semantic_channel["status"] == "AVAILABLE":
            ranked.append((semantic_channel["name"], semantic_refs))

    if enable_codegraph:
        codegraph_channel, codegraph_refs = _run_channel(
            "codegraph",
            "codegraph",
            lambda: codegraph_search(query),
            _codegraph_refs,
        )
        channels.append(codegraph_channel)
        if codegraph_channel["status"] == "AVAILABLE":
            ranked.append((codegraph_channel["name"], codegraph_refs))
    else:
        channels.append(
            {
                "name": "codegraph",
                "kind": "codegraph",
                "status": "SKIPPED",
                "latency_ms": 0.0,
                "returned": 0,
                "payload_token_estimate": None,
                "reason": "disabled by operator",
                "refs": [],
            }
        )

    merged = _rrf(ranked, top_k)
    available = [row for row in channels if row["status"] == "AVAILABLE"]
    active_available = active_channel["status"] == "AVAILABLE"
    status = (
        "PASS"
        if active_available and len(available) >= 2
        else "INSUFFICIENT_EVIDENCE"
    )

    payload_token_estimate = sum(
        int(row["payload_token_estimate"])
        for row in available
        if row["payload_token_estimate"] is not None
    )
    active_tokens = active_channel["payload_token_estimate"]
    metrics = {
        **_quality_metrics(merged, fixture),
        "payload_token_estimate": payload_token_estimate,
        "active_payload_token_estimate": active_tokens,
        "token_delta_vs_active": (
            payload_token_estimate - int(active_tokens)
            if active_tokens is not None
            else None
        ),
        "token_measurement": "approx-json-chars-div-4",
    }

    payload = {
        "schema": SCHEMA_ID,
        "status": status,
        "query_sha256": _digest(query),
        "active_authoritative": True,
        "shadow_effect_on_active_result": False,
        "promotion_eligible": False,
        "top_k": top_k,
        "input_fingerprints": {
            "notebook_catalog_sha256": catalog_binding["sha256"],
            "notebook_semantic_index_sha256": semantic_index_binding["sha256"],
        },
        "channels": channels,
        "merge": {
            "algorithm": "reciprocal-rank-fusion",
            "rrf_k": RRF_K,
            "result_count": len(merged),
            "refs": merged,
        },
        "metrics": metrics,
        "quality_evidence": {
            "status": "MEASURED" if fixture is not None else "UNAVAILABLE",
            "fixture_sha256": fixture_sha,
            "expected_count": (
                len(fixture.get("expected_refs", [])) if fixture is not None else None
            ),
            "contradicted_count": (
                len(fixture.get("contradicted_refs", []))
                if fixture is not None
                else None
            ),
            "stale_count": (
                len(fixture.get("stale_refs", [])) if fixture is not None else None
            ),
        },
        "limitations": [
            "Hybrid Retrieval v2 is zero-effect shadow evidence; active semantic memory remains authoritative.",
            "Precision, recall, stale rate and contradiction rate are unavailable without an explicit relevance fixture.",
            "Token counts are deterministic JSON character estimates, not provider tokenizer counts.",
            "Notebook input fingerprints bind the exact local JSON bytes consumed by measured channels.",
            "A PASS run is measurement success, never approval or activation evidence by itself.",
        ],
    }
    validate_contract("hybrid_retrieval_v2.schema.json", payload)
    return payload
