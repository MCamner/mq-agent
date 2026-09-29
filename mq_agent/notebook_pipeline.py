"""Operational P0-P5 pipeline for the Drive-backed NotebookLM corpus.

The lower-level corpus modules remain the authority for inventory, catalog
validation, lexical retrieval, selective evidence retrieval and semantic
indexing.  This module only composes those primitives into operator-facing
stages and keeps sync state deterministic and local.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mq_agent.notebook_corpus import materialize, validate_catalog
from mq_agent.notebook_corpus_retrieval import retrieve_evidence
from mq_agent.notebook_corpus_search import catalog_summary, search_catalog
from mq_agent.notebook_corpus_semantic import (
    build_semantic_index,
    write_semantic_index,
)

PIPELINE_SCHEMA = "notebook-knowledge-pipeline.v1"
SYNC_SCHEMA = "notebook-knowledge-sync-state.v1"
ATLAS_SCHEMA = "atlas-notebook-evidence.v1"

DEFAULT_ROOT = Path(".mq/notebook-corpus")
DEFAULT_D3_INPUT = DEFAULT_ROOT / "d3-input.json"
DEFAULT_CATALOG = DEFAULT_ROOT / "catalog.json"
DEFAULT_CATALOG_CHECKPOINT = DEFAULT_ROOT / "catalog.checkpoint.json"
DEFAULT_SEMANTIC_INDEX = DEFAULT_ROOT / "semantic-index.json"
DEFAULT_SYNC_STATE = DEFAULT_ROOT / "sync-state.json"


def load_json(path: Path) -> Any:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_catalog_stage(
    *,
    d3_input: Path = DEFAULT_D3_INPUT,
    catalog: Path = DEFAULT_CATALOG,
    checkpoint: Path = DEFAULT_CATALOG_CHECKPOINT,
    manifest: Path | None = None,
) -> dict[str, Any]:
    """P0: materialize the canonical inbound corpus contract.

    When a reconciled manifest is supplied it is an integrity gate, not merely
    extra metadata: notebook/item/role accounting must match before hashes are
    overlaid into the catalog input.
    """
    document = load_json(d3_input)
    manifest_report = None
    if manifest is not None:
        from mq_agent.notebook_manifest import apply_reconciled_manifest

        document, manifest_report = apply_reconciled_manifest(
            document,
            load_json(manifest),
        )

    result, state = materialize(
        document,
        catalog_path=catalog.expanduser(),
        checkpoint_path=checkpoint.expanduser(),
    )
    return {
        "stage": "P0",
        "status": "PASS",
        "catalog": str(catalog.expanduser()),
        "checkpoint": str(checkpoint.expanduser()),
        "notebooks": len(result["notebooks"]),
        "items": len(result["items"]),
        "catalog_sha256": state["catalog_sha256"],
        "excluded_items": state["excluded_items"],
        "manifest": manifest_report,
    }


def build_semantic_stage(
    catalog: Mapping[str, Any],
    text_provider: Any,
    embedding_provider: Any,
    *,
    output_path: Path = DEFAULT_SEMANTIC_INDEX,
    max_files: int = 500,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 16_777_216,
    chunk_chars: int = 2_000,
    overlap_chars: int = 200,
) -> dict[str, Any]:
    """P1: build the disposable local semantic index with provenance."""
    index = build_semantic_index(
        catalog,
        text_provider,
        embedding_provider,
        max_files=max_files,
        max_bytes_per_file=max_bytes_per_file,
        max_total_bytes=max_total_bytes,
        chunk_chars=chunk_chars,
        overlap_chars=overlap_chars,
    )
    write_semantic_index(index, output_path)
    return {
        "stage": "P1",
        "status": "PASS",
        "semantic_index": str(output_path.expanduser()),
        "chunks": len(index["chunks"]),
        "files_fetched": index["trace"]["files_fetched"],
        "bytes_fetched": index["trace"]["bytes_fetched"],
        "embedding_dimension": index["trace"]["embedding_dimension"],
    }


def search_stage(
    catalog: Mapping[str, Any],
    query: str,
    *,
    top_k: int = 10,
    text_hits: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """P2: searchable corpus facade over the frozen lexical baseline."""
    report = search_catalog(
        catalog,
        query,
        top_k=top_k,
        text_hits=text_hits,
    )
    report["stage"] = "P2"
    return report


def _item_signature(item: Mapping[str, Any]) -> str:
    content_hash = item.get("content_sha256")
    if content_hash:
        return f"sha256:{content_hash}"
    # Drive inventory metadata does not always expose a SHA-256.  Fall back to
    # provider identity + change-relevant metadata without pretending it is a
    # content hash.
    fallback = {
        "drive_item_id": item.get("drive_item_id"),
        "modified_time": item.get("modified_time"),
        "size_bytes": item.get("size_bytes"),
        "mime_type": item.get("mime_type"),
        "role": (item.get("classification") or {}).get("role"),
    }
    return "metadata:" + _canonical_sha(fallback)


def build_sync_state(catalog: Mapping[str, Any]) -> dict[str, Any]:
    validate_catalog(catalog)
    signatures = {
        str(item["drive_item_id"]): _item_signature(item)
        for item in catalog["items"]
    }
    return {
        "schema": SYNC_SCHEMA,
        "snapshot_at": catalog["snapshot_at"],
        "catalog_sha256": _canonical_sha(catalog),
        "items": dict(sorted(signatures.items())),
    }


def diff_sync_state(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    old = dict((previous or {}).get("items") or {})
    new = dict(current.get("items") or {})
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(key for key in set(new) & set(old) if new[key] != old[key])
    unchanged = sorted(
        key for key in set(new) & set(old) if new[key] == old[key]
    )
    return {
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": unchanged,
        "delta_count": len(added) + len(changed) + len(removed),
    }


def sync_catalog(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    state_path: Path = DEFAULT_SYNC_STATE,
    write: bool = True,
) -> dict[str, Any]:
    """P3: calculate incremental NEW/CHANGED/REMOVED state."""
    catalog = load_json(catalog_path)
    validate_catalog(catalog)
    current = build_sync_state(catalog)
    previous = load_json(state_path) if state_path.expanduser().is_file() else None
    diff = diff_sync_state(previous, current)
    if write:
        write_json(state_path, current)

    hash_backed = sum(
        1 for item in catalog["items"] if item.get("content_sha256")
    )
    return {
        "stage": "P3",
        "status": "PASS",
        "state": str(state_path.expanduser()),
        "write": write,
        "items": len(catalog["items"]),
        "hash_backed_items": hash_backed,
        "metadata_signature_items": len(catalog["items"]) - hash_backed,
        **diff,
    }


def incremental_semantic_sync(
    catalog: Mapping[str, Any],
    previous_index: Mapping[str, Any] | None,
    diff: Mapping[str, Any],
    text_provider: Any,
    embedding_provider: Any,
    *,
    output_path: Path = DEFAULT_SEMANTIC_INDEX,
    max_files: int = 500,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 16_777_216,
    chunk_chars: int = 2_000,
    overlap_chars: int = 200,
) -> dict[str, Any]:
    """P3 semantic delta: reuse unchanged vectors and embed only changed files."""
    validate_catalog(catalog)
    delta_ids = {
        str(value)
        for value in (diff.get("added") or [])
    } | {
        str(value)
        for value in (diff.get("changed") or [])
    }
    unchanged_ids = {
        str(value) for value in (diff.get("unchanged") or [])
    }
    previous_ids = {
        str(row.get("drive_item_id"))
        for row in (previous_index or {}).get("chunks", [])
        if row.get("drive_item_id")
    }
    # A P3 baseline may exist before P1 has ever been built. In that case the
    # catalog correctly says "unchanged", but there is no vector to reuse.
    # Missing index coverage is therefore work to do, not evidence of stasis.
    missing_from_index = unchanged_ids - previous_ids
    delta_ids |= missing_from_index
    reusable_ids = unchanged_ids & previous_ids
    kept = [
        dict(row)
        for row in (previous_index or {}).get("chunks", [])
        if str(row.get("drive_item_id")) in reusable_ids
    ]

    delta_items = [
        dict(row)
        for row in catalog["items"]
        if str(row["drive_item_id"]) in delta_ids
    ]
    if delta_items:
        delta_catalog = {
            "schema": catalog["schema"],
            "corpus": dict(catalog["corpus"]),
            "snapshot_at": catalog["snapshot_at"],
            "notebooks": [dict(row) for row in catalog["notebooks"]],
            "items": delta_items,
        }
        delta_index = build_semantic_index(
            delta_catalog,
            text_provider,
            embedding_provider,
            max_files=max_files,
            max_bytes_per_file=max_bytes_per_file,
            max_total_bytes=max_total_bytes,
            chunk_chars=chunk_chars,
            overlap_chars=overlap_chars,
        )
        new_chunks = list(delta_index["chunks"])
        delta_trace = dict(delta_index["trace"])
    else:
        new_chunks = []
        delta_trace = {
            "files_available": 0,
            "files_selected": 0,
            "files_fetched": 0,
            "files_unavailable": 0,
            "bytes_fetched": 0,
            "embedding_dimension": (
                len(kept[0].get("vector") or []) if kept else 0
            ),
            "hosted_egress": False,
        }

    chunks = kept + new_chunks
    chunks.sort(key=lambda row: str(row.get("chunk_id", "")))
    dimensions = {
        len(row.get("vector") or [])
        for row in chunks
        if row.get("vector")
    }
    if len(dimensions) > 1:
        raise ValueError(
            "incremental semantic index contains mixed embedding dimensions"
        )

    index = {
        "schema": "notebook-semantic-index-experiment.v1",
        "canonical": False,
        "disposable": True,
        "snapshot_at": catalog["snapshot_at"],
        "corpus": dict(catalog["corpus"]),
        "chunks": chunks,
        "trace": {
            **delta_trace,
            "chunks": len(chunks),
            "incremental": True,
            "reused_chunks": len(kept),
            "new_chunks": len(new_chunks),
            "removed_items": len(diff.get("removed") or []),
            "changed_items": len(diff.get("changed") or []),
            "added_items": len(diff.get("added") or []),
        },
    }
    write_semantic_index(index, output_path)
    return {
        "stage": "P3",
        "status": "PASS",
        "semantic_index": str(output_path.expanduser()),
        "reused_chunks": len(kept),
        "new_chunks": len(new_chunks),
        "chunks": len(chunks),
    }


def evidence_stage(
    catalog: Mapping[str, Any],
    query: str,
    provider: Any,
    *,
    max_files: int = 4,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 262_144,
    excerpt_chars: int = 4_000,
    text_hits: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """P4: bounded evidence retrieval; only source-role rows can prove claims."""
    report = retrieve_evidence(
        catalog,
        query,
        provider,
        max_files=max_files,
        max_bytes_per_file=max_bytes_per_file,
        max_total_bytes=max_total_bytes,
        excerpt_chars=excerpt_chars,
        text_hits=text_hits,
        scope="archive",
    )
    report["stage"] = "P4"
    return report


def atlas_evidence_bundle(
    retrieval: Mapping[str, Any],
    *,
    claim: str,
) -> dict[str, Any]:
    """P5: adapt retrieval output to an Atlas claim/evidence envelope."""
    evidence = []
    for row in retrieval.get("evidence", []):
        provenance = dict(row.get("provenance") or {})
        source_role = provenance.get("source_role")
        evidence.append(
            {
                "item_id": provenance.get("item_id"),
                "drive_item_id": provenance.get("drive_item_id"),
                "notebook_id": provenance.get("notebook_id"),
                "notebook_title": provenance.get("notebook_title"),
                "title": provenance.get("title"),
                "source_role": source_role,
                "claim_eligible": (
                    source_role == "source" and bool(row.get("claim_eligible"))
                ),
                "grounding_status": row.get("grounding_status"),
                "excerpt": row.get("excerpt", ""),
                "content_sha256": provenance.get("content_sha256"),
            }
        )

    eligible = [
        row
        for row in evidence
        if row["claim_eligible"] and row["source_role"] == "source"
    ]
    return {
        "schema": ATLAS_SCHEMA,
        "claim": claim,
        "status": "SUPPORTED" if eligible else "INSUFFICIENT_EVIDENCE",
        "evidence": evidence,
        "claim_eligible_count": len(eligible),
        "source": "notebooklm-corpus",
        "policy": {
            "interaction_is_evidence": False,
            "derived_is_claim_evidence": False,
        },
    }


def pipeline_status(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    semantic_path: Path = DEFAULT_SEMANTIC_INDEX,
    state_path: Path = DEFAULT_SYNC_STATE,
) -> dict[str, Any]:
    if not catalog_path.expanduser().is_file():
        return {
            "schema": PIPELINE_SCHEMA,
            "status": "NOT_BUILT",
            "catalog": str(catalog_path.expanduser()),
        }

    catalog = load_json(catalog_path)
    summary = catalog_summary(catalog)
    semantic = (
        load_json(semantic_path)
        if semantic_path.expanduser().is_file()
        else None
    )
    sync = load_json(state_path) if state_path.expanduser().is_file() else None
    chunks = len((semantic or {}).get("chunks") or [])
    indexed_ids = {
        str(row.get("drive_item_id"))
        for row in (semantic or {}).get("chunks", [])
        if row.get("drive_item_id")
    }
    indexable = sum(
        1
        for row in catalog["items"]
        if str(row["classification"]["role"])
        in {"source", "derived", "derived-note"}
    )
    return {
        "schema": PIPELINE_SCHEMA,
        "status": "READY" if sync else "CATALOG_READY",
        "snapshot_at": summary["snapshot_at"],
        "notebooks": summary["notebooks"],
        "items": summary["items"],
        "roles": summary["roles"],
        "indexable_items": indexable,
        "semantic_index_present": semantic is not None,
        "semantic_chunks": chunks,
        "semantic_items": len(indexed_ids),
        "sync_state_present": sync is not None,
        "unknown": int(summary["roles"].get("unknown", 0)),
    }
