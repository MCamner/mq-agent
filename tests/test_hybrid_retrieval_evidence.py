from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mq_agent.memory.hybrid_evidence import (
    HybridEvidenceStore,
    collect_hybrid_evidence,
)
from mq_agent.notebook_corpus import build_from_document


def _catalog() -> dict:
    document = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-10-01T00:00:00Z",
        "notebooks": [{"drive_item_id": "nb-1", "title": "MQ research"}],
        "items": [
            {
                "drive_item_id": "doc-1",
                "notebook_drive_item_id": "nb-1",
                "parent_drive_item_id": "sources",
                "relative_path": "Sources/mcp.md",
                "title": "MCP orchestration tools",
                "mime_type": "text/markdown",
                "size_bytes": 42,
                "modified_time": "2026-10-01T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "a" * 64,
            }
        ],
    }
    return build_from_document(document)[0]


def _write_suite(tmp_path: Path) -> Path:
    (tmp_path / "catalog.json").write_text(json.dumps(_catalog()), encoding="utf-8")
    fixture = {
        "schema": "mq.hybrid-retrieval-fixture.v1",
        "expected_refs": [
            "semantic-memory:memory-1",
            "notebook:doc-1",
            "codegraph:mq_agent/tools/context_pack.py#build_task_pack",
        ],
        "contradicted_refs": [],
        "stale_refs": [],
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    suite = {
        "schema": "mq.hybrid-retrieval-suite.v1",
        "catalog": "catalog.json",
        "cases": [
            {
                "id": "repo-review-1",
                "task_class": "repo-review",
                "query": "MCP orchestration",
                "fixture": "fixture.json",
            },
            {
                "id": "docs-1",
                "task_class": "docs",
                "query": "MCP orchestration",
                "fixture": "fixture.json",
            },
        ],
    }
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    return path


def _active(_query: str):
    return {"results": [{"id": "memory-1"}]}


def _codegraph(_query: str):
    return {
        "results": [
            {
                "path": "mq_agent/tools/context_pack.py",
                "symbol": "build_task_pack",
            }
        ]
    }


def test_collects_content_addressed_bounded_evidence(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path)
    root = tmp_path / "state"

    result = collect_hybrid_evidence(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert result["schema"] == "mq.hybrid-retrieval-evidence-set.v1"
    assert result["status"] == "PASS"
    assert result["zero_effect"] is True
    assert result["promotion_eligible"] is False
    assert result["aggregate"]["case_count"] == 2
    assert result["aggregate"]["task_class_count"] == 2
    assert result["aggregate"]["pass_count"] == 2
    assert result["aggregate"]["quality_measured_count"] == 2
    assert result["aggregate"]["mean_precision"] == 1.0
    assert result["aggregate"]["mean_recall"] == 1.0
    expected_catalog_sha = (
        "sha256:" + hashlib.sha256((tmp_path / "catalog.json").read_bytes()).hexdigest()
    )
    assert all(
        case["input_fingerprints"]["notebook_catalog_sha256"] == expected_catalog_sha
        for case in result["cases"]
    )
    assert all(
        case["input_fingerprints"]["notebook_semantic_index_sha256"] is None
        for case in result["cases"]
    )

    serialized = json.dumps(result)
    assert "MCP orchestration" not in serialized
    assert str(tmp_path) not in serialized

    verified = HybridEvidenceStore(root).verify_set(result["evidence_id"])
    assert verified["status"] == "VERIFIED"
    assert verified["errors"] == []


def test_no_write_mode_leaves_no_state(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path)
    root = tmp_path / "state"

    result = collect_hybrid_evidence(
        suite,
        state_root=root,
        persist=False,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert result["status"] == "PASS"
    assert not root.exists()


def test_missing_fixture_fails_before_retrieval(tmp_path: Path) -> None:
    suite = {
        "schema": "mq.hybrid-retrieval-suite.v1",
        "cases": [
            {
                "id": "missing",
                "task_class": "docs",
                "query": "query",
                "fixture": "missing.json",
            }
        ],
    }
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture file does not exist"):
        collect_hybrid_evidence(
            path,
            state_root=tmp_path / "state",
            active_search=_active,
            codegraph_search=_codegraph,
        )


def test_duplicate_case_ids_fail_closed(tmp_path: Path) -> None:
    fixture = {
        "schema": "mq.hybrid-retrieval-fixture.v1",
        "expected_refs": [],
        "contradicted_refs": [],
        "stale_refs": [],
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    suite = {
        "schema": "mq.hybrid-retrieval-suite.v1",
        "cases": [
            {"id": "same", "task_class": "docs", "query": "a", "fixture": "fixture.json"},
            {"id": "same", "task_class": "ci", "query": "b", "fixture": "fixture.json"},
        ],
    }
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")

    with pytest.raises(ValueError, match="case ids must be unique"):
        collect_hybrid_evidence(path, state_root=tmp_path / "state")


def test_tampered_run_refuses_verification(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path)
    root = tmp_path / "state"
    result = collect_hybrid_evidence(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    run_id = result["cases"][0]["run_fingerprint"]
    digest = run_id.split(":", 1)[1]
    run_path = root / "runs" / f"{digest}.json"
    data = json.loads(run_path.read_text(encoding="utf-8"))
    data["top_k"] = data["top_k"] + 1
    run_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    verified = HybridEvidenceStore(root).verify_set(result["evidence_id"])
    assert verified["status"] == "REFUSED"
    assert any("fingerprint mismatch" in error for error in verified["errors"])


def test_run_input_fingerprint_mismatch_refuses_verification(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path)
    root = tmp_path / "state"
    result = collect_hybrid_evidence(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    run_id = result["cases"][0]["run_fingerprint"]
    digest = run_id.split(":", 1)[1]
    run_path = root / "runs" / f"{digest}.json"
    data = json.loads(run_path.read_text(encoding="utf-8"))
    data["input_fingerprints"]["notebook_catalog_sha256"] = "sha256:" + ("0" * 64)
    run_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    verified = HybridEvidenceStore(root).verify_set(result["evidence_id"])
    assert verified["status"] == "REFUSED"
    assert "repo-review-1: input fingerprint mismatch" in verified["errors"]


def test_tampered_evidence_id_refuses_verification(tmp_path: Path) -> None:
    suite = _write_suite(tmp_path)
    root = tmp_path / "state"
    result = collect_hybrid_evidence(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    digest = result["evidence_id"].split(":", 1)[1]
    set_path = root / "sets" / f"{digest}.json"
    data = json.loads(set_path.read_text(encoding="utf-8"))
    data["evidence_id"] = "sha256:" + ("0" * 64)
    set_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    verified = HybridEvidenceStore(root).verify_set(result["evidence_id"])
    assert verified["status"] == "REFUSED"
    assert "evidence set id/path mismatch" in verified["errors"]
