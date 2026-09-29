"""D8 disposable local semantic retrieval experiment for NotebookLM corpus.

This module is deliberately opt-in and non-canonical. It builds a bounded local
index from text-capable source/derived items, retains full provenance, searches
by cosine similarity, and compares semantic results with the frozen D4 lexical
baseline. Semantic similarity never changes source role or claim eligibility.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from mq_agent.notebook_corpus import validate_catalog
from mq_agent.notebook_corpus_search import search_catalog

FROZEN_D4_QUERIES = [
    "Find sources about building an MCP server in Python.",
    "What design patterns recur across material about agentic AI and multi-agent systems?",
    "Find material explaining TOGAF 10 and enterprise architecture.",
    "Find sources about pentatonic guitar technique and recurring rock licks.",
    "For a matching notebook, return original sources before NotebookLM-generated artifacts.",
    "Find sources about Akkadian cuneiform accounting tablets.",
]

_TEXT_ROLES = {"source", "derived", "derived-note"}
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


class TextProvider(Protocol):
    def fetch_text(self, drive_item_id: str, mime_type: str, *, max_bytes: int) -> Mapping[str, Any]: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass
class OllamaEmbeddingProvider:
    model: str = DEFAULT_EMBED_MODEL
    host: str = DEFAULT_OLLAMA_HOST
    timeout: int = 60

    def __post_init__(self) -> None:
        configured = (os.environ.get("OLLAMA_HOST") or self.host).strip()
        if "://" not in configured:
            configured = "http://" + configured
        self.host = configured.rstrip("/")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        body = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"embedding unavailable: {type(exc).__name__}") from exc
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError("embedding provider returned unexpected shape")
        out: list[list[float]] = []
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise ValueError("embedding vector missing")
            out.append([float(value) for value in vector])
        return out


def _chunk_text(text: str, *, chunk_chars: int, overlap_chars: int) -> list[tuple[int, int, str]]:
    if chunk_chars < 32:
        raise ValueError("chunk_chars must be at least 32")
    if overlap_chars < 0 or overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be >= 0 and < chunk_chars")
    chunks: list[tuple[int, int, str]] = []
    start = 0
    step = chunk_chars - overlap_chars
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        value = text[start:end].strip()
        if value:
            chunks.append((start, end, value))
        if end >= len(text):
            break
        start += step
    return chunks


def build_semantic_index(
    catalog: Mapping[str, Any],
    text_provider: TextProvider,
    embedding_provider: EmbeddingProvider,
    *,
    max_files: int = 50,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 1_048_576,
    chunk_chars: int = 2_000,
    overlap_chars: int = 200,
) -> dict[str, Any]:
    validate_catalog(catalog)
    titles = {str(n["notebook_id"]): str(n["title"]) for n in catalog["notebooks"]}
    items = [
        row for row in catalog["items"]
        if str(row["classification"]["role"]) in _TEXT_ROLES
    ]
    items.sort(key=lambda row: (str(row["notebook_id"]), str(row["item_id"])))

    total_bytes = 0
    fetched = 0
    unavailable = 0
    chunks: list[dict[str, Any]] = []
    chunk_texts: list[str] = []

    for item in items[:max_files]:
        remaining = max_total_bytes - total_bytes
        if remaining <= 0:
            break
        result = text_provider.fetch_text(
            str(item["drive_item_id"]),
            str(item["mime_type"]),
            max_bytes=min(max_bytes_per_file, remaining),
        )
        if str(result.get("status")) != "ok":
            unavailable += 1
            continue
        text = str(result.get("text", ""))
        consumed = int(result.get("bytes_fetched", len(text.encode("utf-8"))))
        total_bytes += max(0, consumed)
        fetched += 1
        role = str(item["classification"]["role"])

        for index, (start, end, chunk) in enumerate(
            _chunk_text(text, chunk_chars=chunk_chars, overlap_chars=overlap_chars)
        ):
            chunks.append(
                {
                    "chunk_id": f"{item['item_id']}:{index}",
                    "item_id": item["item_id"],
                    "drive_item_id": item["drive_item_id"],
                    "notebook_id": item["notebook_id"],
                    "notebook_title": titles[str(item["notebook_id"])],
                    "title": item["title"],
                    "source_role": role,
                    "claim_eligible": role == "source",
                    "modified_time": item["modified_time"],
                    "content_sha256": item.get("content_sha256"),
                    "start_char": start,
                    "end_char": end,
                }
            )
            chunk_texts.append(chunk)

    vectors = embedding_provider.embed(chunk_texts)
    for row, vector in zip(chunks, vectors):
        row["vector"] = vector

    dimension = len(vectors[0]) if vectors else 0
    if any(len(v) != dimension for v in vectors):
        raise ValueError("embedding dimensions are inconsistent")

    return {
        "schema": "notebook-semantic-index-experiment.v1",
        "canonical": False,
        "disposable": True,
        "snapshot_at": catalog["snapshot_at"],
        "corpus": dict(catalog["corpus"]),
        "chunks": chunks,
        "trace": {
            "files_available": len(items),
            "files_selected": min(len(items), max_files),
            "files_fetched": fetched,
            "files_unavailable": unavailable,
            "bytes_fetched": total_bytes,
            "chunks": len(chunks),
            "embedding_dimension": dimension,
            "hosted_egress": False,
        },
    }


def write_semantic_index(index: Mapping[str, Any], path: Path) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    aa = math.sqrt(sum(x * x for x in a))
    bb = math.sqrt(sum(y * y for y in b))
    if aa == 0 or bb == 0:
        return -1.0
    return dot / (aa * bb)


def semantic_search(
    index: Mapping[str, Any],
    query: str,
    embedding_provider: EmbeddingProvider,
    *,
    top_k: int = 10,
) -> dict[str, Any]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    query_vector = embedding_provider.embed([query])[0]
    scored: list[dict[str, Any]] = []
    for chunk in index.get("chunks", []):
        score = _cosine(query_vector, chunk["vector"])
        row = {key: value for key, value in chunk.items() if key != "vector"}
        row["score"] = score
        scored.append(row)

    role_priority = {"source": 0, "derived": 1, "derived-note": 2}
    scored.sort(
        key=lambda row: (
            -float(row["score"]),
            role_priority.get(str(row["source_role"]), 99),
            str(row["notebook_id"]),
            str(row["chunk_id"]),
        )
    )

    # Collapse multiple chunks from the same file after semantic scoring so
    # top-k measures distinct corpus items rather than repeated chunks.
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in scored:
        drive_id = str(row["drive_item_id"])
        if drive_id in seen:
            continue
        seen.add(drive_id)
        results.append(row)
        if len(results) >= top_k:
            break

    return {
        "query": query,
        "results": results,
        "trace": {
            "semantic": True,
            "index_chunks_considered": len(scored),
            "returned": len(results),
            "hosted_egress": False,
            "source_role_preserved": True,
        },
    }


def evaluate_semantic_vs_d4(
    catalog: Mapping[str, Any],
    index: Mapping[str, Any],
    embedding_provider: EmbeddingProvider,
    expected: Mapping[str, Sequence[str]],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for query in FROZEN_D4_QUERIES:
        lexical = search_catalog(catalog, query, top_k=top_k)
        semantic = semantic_search(index, query, embedding_provider, top_k=top_k)
        expected_ids = set(str(x) for x in expected.get(query, []))
        lexical_ids = [str(row["drive_item_id"]) for row in lexical["results"]]
        semantic_ids = [str(row["drive_item_id"]) for row in semantic["results"]]

        if expected_ids:
            lexical_hit = bool(expected_ids.intersection(lexical_ids))
            semantic_hit = bool(expected_ids.intersection(semantic_ids))
        else:
            lexical_hit = not lexical_ids
            semantic_hit = not semantic_ids

        rows.append(
            {
                "query": query,
                "expected_drive_item_ids": sorted(expected_ids),
                "lexical_ids": lexical_ids,
                "semantic_ids": semantic_ids,
                "lexical_pass": lexical_hit,
                "semantic_pass": semantic_hit,
                "semantic_improved": semantic_hit and not lexical_hit,
                "semantic_regressed": lexical_hit and not semantic_hit,
            }
        )

    lexical_passes = sum(1 for row in rows if row["lexical_pass"])
    semantic_passes = sum(1 for row in rows if row["semantic_pass"])
    improvements = sum(1 for row in rows if row["semantic_improved"])
    regressions = sum(1 for row in rows if row["semantic_regressed"])

    if semantic_passes > lexical_passes and regressions == 0:
        decision = "SEMANTIC_BENEFIT_MEASURED"
    elif semantic_passes == lexical_passes and regressions == 0:
        decision = "NO_MEASURED_BENEFIT"
    else:
        decision = "SEMANTIC_REGRESSION_OR_MIXED"

    return {
        "status": "EVALUATED",
        "decision": decision,
        "queries": rows,
        "metrics": {
            "query_count": len(rows),
            "lexical_passes": lexical_passes,
            "semantic_passes": semantic_passes,
            "improvements": improvements,
            "regressions": regressions,
            "provenance_coverage": 1.0 if all(
                row.get("drive_item_id") and row.get("notebook_id") and row.get("source_role")
                for row in index.get("chunks", [])
            ) else 0.0,
            "hosted_egress": False,
        },
    }
