from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mq_agent.memory.hybrid_evidence import (
    HybridEvidenceStore,
    audit_hybrid_policy_plans,
    collect_hybrid_ablation,
    collect_hybrid_challenge,
    collect_hybrid_evidence,
    discover_hybrid_challenge_candidates,
    evaluate_hybrid_admission,
    plan_hybrid_runtime_policy,
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
        "codegraph_root": ".",
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


def _write_ablation_suite(tmp_path: Path) -> Path:
    path = _write_suite(tmp_path)
    semantic_index = {
        "schema": "notebook-semantic-index-experiment.v1",
        "canonical": False,
        "disposable": True,
        "chunks": [
            {
                "chunk_id": "doc-1:0",
                "item_id": "doc-1",
                "drive_item_id": "doc-1",
                "notebook_id": "nb-1",
                "notebook_title": "MQ research",
                "title": "MCP orchestration tools",
                "source_role": "source",
                "claim_eligible": True,
                "modified_time": "2026-10-01T00:00:00Z",
                "content_sha256": "a" * 64,
                "start_char": 0,
                "end_char": 3,
                "vector": [1.0],
            }
        ],
        "trace": {"chunks": 1, "embedding_dimension": 1},
    }
    (tmp_path / "semantic-index.json").write_text(
        json.dumps(semantic_index),
        encoding="utf-8",
    )
    suite = json.loads(path.read_text(encoding="utf-8"))
    suite["semantic_index"] = "semantic-index.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    return path


def _write_challenge_suite(tmp_path: Path) -> Path:
    path = _write_ablation_suite(tmp_path)
    suite = json.loads(path.read_text(encoding="utf-8"))
    suite["cases"][0]["challenge_target"] = "notebook-keyword"
    suite["cases"][1]["challenge_target"] = "notebook-vector"
    suite["cases"].append(
        {
            "id": "ci-1",
            "task_class": "ci",
            "query": "MCP orchestration",
            "fixture": "fixture.json",
            "challenge_target": "codegraph",
        }
    )
    path.write_text(json.dumps(suite), encoding="utf-8")
    return path


def _write_ceilinged_challenge_suite(tmp_path: Path) -> Path:
    path = _write_challenge_suite(tmp_path)
    fixture = {
        "schema": "mq.hybrid-retrieval-fixture.v1",
        "expected_refs": ["semantic-memory:memory-1"],
        "contradicted_refs": [],
        "stale_refs": [],
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    return path


def _write_active_only_optimal_suite(tmp_path: Path) -> Path:
    path = _write_ablation_suite(tmp_path)
    fixture = {
        "schema": "mq.hybrid-retrieval-fixture.v1",
        "expected_refs": ["semantic-memory:memory-1"],
        "contradicted_refs": [],
        "stale_refs": [],
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
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


def test_collects_and_verifies_fixed_channel_ablation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_ablation_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    result = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert result["schema"] == "mq.hybrid-retrieval-ablation.v1"
    assert result["status"] == "PASS"
    assert result["zero_effect"] is True
    assert result["promotion_eligible"] is False
    assert result["baseline"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["baseline"]["metrics"]["mean_precision"] == 1.0
    assert result["baseline"]["metrics"]["mean_recall"] == 0.333333
    assert [row["variant_id"] for row in result["variants"]] == [
        "keyword",
        "vector",
        "codegraph",
        "keyword+vector",
        "keyword+codegraph",
        "vector+codegraph",
        "all",
    ]

    by_id = {row["variant_id"]: row for row in result["variants"]}
    assert by_id["keyword"]["metrics"]["mean_recall"] == 0.666667
    assert by_id["vector"]["metrics"]["mean_recall"] == 0.666667
    assert by_id["codegraph"]["metrics"]["mean_recall"] == 0.666667
    assert by_id["keyword+vector"]["metrics"]["mean_recall"] == 0.666667
    assert by_id["keyword+codegraph"]["metrics"]["mean_recall"] == 1.0
    assert by_id["vector+codegraph"]["metrics"]["mean_recall"] == 1.0
    assert by_id["all"]["metrics"]["mean_recall"] == 1.0
    assert by_id["all"]["delta_vs_baseline"]["mean_recall"] == 0.666667
    assert by_id["all"]["metrics"]["mean_token_delta_vs_active"] > 0

    serialized = json.dumps(result)
    assert "MCP orchestration" not in serialized
    assert str(tmp_path) not in serialized

    verified = HybridEvidenceStore(root).verify_ablation(result["ablation_id"])
    assert verified["status"] == "VERIFIED"
    assert verified["errors"] == []


def test_discovers_real_challenge_candidates_without_writing_fixtures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_ablation_suite(tmp_path)

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    result = discover_hybrid_challenge_candidates(
        "MCP orchestration",
        catalog_path=tmp_path / "catalog.json",
        semantic_index_path=tmp_path / "semantic-index.json",
        codegraph_root=tmp_path,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert result["schema"] == "mq.hybrid-retrieval-challenge-candidates.v1"
    assert result["status"] == "PASS"
    assert result["zero_effect"] is True
    assert result["persisted"] is False
    assert result["fixture_generation_available"] is False
    assert result["operator_review_required"] is True
    assert result["active"]["refs"] == ["semantic-memory:memory-1"]
    assert result["next_action"] == "select-relevant-refs-for-fixtures"

    by_channel = {row["channel"]: row for row in result["channels"]}
    keyword = by_channel["notebook-keyword"]["candidates"][0]
    vector = by_channel["notebook-vector"]["candidates"][0]
    codegraph = by_channel["codegraph"]["candidates"][0]

    assert keyword["ref"] == "notebook:doc-1"
    assert keyword["also_returned_by"] == ["notebook-vector"]
    assert keyword["exclusive_optional"] is False
    assert keyword["not_in_active_ref_set"] is True
    assert keyword["metadata"] == {
        "title": "MCP orchestration tools",
        "notebook_title": "MQ research",
        "source_role": "source",
    }

    assert vector["ref"] == "notebook:doc-1"
    assert vector["also_returned_by"] == ["notebook-keyword"]
    assert vector["exclusive_optional"] is False

    assert codegraph["ref"] == (
        "codegraph:mq_agent/tools/context_pack.py#build_task_pack"
    )
    assert codegraph["also_returned_by"] == []
    assert codegraph["exclusive_optional"] is True
    assert codegraph["metadata"] is None

    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized


def test_candidate_discovery_marks_unconfigured_notebook_channels() -> None:
    result = discover_hybrid_challenge_candidates(
        "build task pack",
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert result["status"] == "PASS"
    by_channel = {row["channel"]: row for row in result["channels"]}
    assert by_channel["notebook-keyword"]["status"] == "NOT_CONFIGURED"
    assert by_channel["notebook-vector"]["status"] == "NOT_CONFIGURED"
    assert by_channel["codegraph"]["status"] == "AVAILABLE"
    assert by_channel["codegraph"]["review_candidate_count"] == 1


def test_challenge_suite_proves_singleton_discrimination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_challenge_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    challenge = collect_hybrid_challenge(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert challenge["schema"] == "mq.hybrid-retrieval-challenge.v1"
    assert challenge["status"] == "PASS"
    assert challenge["discriminating"] is True
    assert challenge["zero_effect"] is True
    assert challenge["promotion_eligible"] is False
    assert challenge["runtime_consumption_available"] is False
    assert challenge["next_action"] == "review-channel-gains"
    assert challenge["required_channels"] == [
        "codegraph",
        "notebook-keyword",
        "notebook-vector",
    ]
    assert {row["channel"] for row in challenge["channels"]} == {
        "notebook-keyword",
        "notebook-vector",
        "codegraph",
    }
    assert all(row["result"] == "DISCRIMINATING" for row in challenge["channels"])
    assert all(row["supporting_case_count"] == 1 for row in challenge["channels"])
    assert all(row["non_ceiling_case_count"] == 1 for row in challenge["channels"])
    assert all(
        row["cases"][0]["challenge_result"] == "SUPPORTS_TARGET"
        for row in challenge["channels"]
    )

    serialized = json.dumps(challenge)
    assert "MCP orchestration" not in serialized
    assert str(tmp_path) not in serialized

    verified = HybridEvidenceStore(root).verify_challenge(
        challenge["challenge_id"]
    )
    assert verified["status"] == "VERIFIED"
    assert verified["errors"] == []


def test_challenge_suite_reports_ceiling_without_claiming_discrimination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_ceilinged_challenge_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    challenge = collect_hybrid_challenge(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert challenge["status"] == "PASS"
    assert challenge["discriminating"] is False
    assert challenge["next_action"] == "redesign-challenge-cases"
    assert all(row["result"] == "NO_MEASURED_GAIN" for row in challenge["channels"])
    assert all(row["non_ceiling_case_count"] == 0 for row in challenge["channels"])
    assert all(
        row["cases"][0]["challenge_result"] == "CEILINGED"
        for row in challenge["channels"]
    )


def test_challenge_no_write_leaves_no_operator_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_challenge_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    challenge = collect_hybrid_challenge(
        suite,
        state_root=root,
        persist=False,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert challenge["status"] == "PASS"
    assert challenge["discriminating"] is True
    assert not root.exists()


def test_admission_marks_quality_improving_singletons_eligible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_ablation_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(
        ablation["ablation_id"],
        state_root=root,
    )

    assert admission["schema"] == "mq.hybrid-retrieval-admission.v1"
    assert admission["status"] == "PASS"
    assert admission["decision"] == "OPTIONAL_CHANNELS_ELIGIBLE"
    assert admission["zero_effect"] is True
    assert admission["activation_available"] is False
    assert admission["promotion_eligible"] is False
    assert all(
        row["eligible_channels"]
        == ["codegraph", "notebook-keyword", "notebook-vector"]
        for row in admission["task_classes"]
    )
    assert all(
        channel["decision"] == "ELIGIBLE"
        for row in admission["task_classes"]
        for channel in row["channels"]
    )

    verified = HybridEvidenceStore(root).verify_admission(
        admission["admission_id"]
    )
    assert verified["status"] == "VERIFIED"
    assert verified["errors"] == []


def test_admission_keeps_active_only_when_singletons_reduce_precision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_active_only_optimal_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(
        ablation["ablation_id"],
        state_root=root,
    )

    assert admission["decision"] == "ACTIVE_ONLY"
    assert admission["next_action"] == "keep-active-only"
    assert all(
        row["decision"] == "ACTIVE_ONLY"
        and row["eligible_channels"] == []
        for row in admission["task_classes"]
    )
    for row in admission["task_classes"]:
        for channel in row["channels"]:
            assert channel["decision"] == "ACTIVE_ONLY"
            assert channel["mean_delta_vs_active_only"]["precision"] < 0
            assert "precision" in channel["cases"][0]["quality_regressions"]


def test_policy_plan_keeps_verified_active_only_effective(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_active_only_optimal_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(ablation["ablation_id"], state_root=root)
    plan = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "repo-review",
        state_root=root,
    )

    assert plan["schema"] == "mq.hybrid-retrieval-policy-plan.v1"
    assert plan["status"] == "PASS"
    assert plan["decision"] == "ACTIVE_ONLY"
    assert plan["admission_decision"] == "ACTIVE_ONLY"
    assert plan["eligible_channels"] == []
    assert plan["proposed_channel_selection"] == {
        "notebook_keyword": False,
        "notebook_vector": False,
        "codegraph": False,
    }
    assert plan["effective_channel_selection"] == {
        "notebook_keyword": False,
        "notebook_vector": False,
        "codegraph": False,
    }
    assert plan["apply_available"] is False
    assert plan["runtime_consumption_available"] is False
    assert plan["next_action"] == "use-active-only"

    verified = HybridEvidenceStore(root).verify_policy_plan(
        plan["policy_plan_id"]
    )
    assert verified["status"] == "VERIFIED"
    assert verified["errors"] == []


def test_policy_plan_never_effects_eligible_optional_channels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_ablation_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(ablation["ablation_id"], state_root=root)
    plan = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "docs",
        state_root=root,
    )

    assert plan["decision"] == "REVIEW_REQUIRED"
    assert plan["admission_decision"] == "OPTIONAL_CHANNELS_ELIGIBLE"
    assert plan["eligible_channels"] == [
        "codegraph",
        "notebook-keyword",
        "notebook-vector",
    ]
    assert plan["proposed_channel_selection"] == {
        "notebook_keyword": True,
        "notebook_vector": True,
        "codegraph": True,
    }
    assert plan["effective_channel_selection"] == {
        "notebook_keyword": False,
        "notebook_vector": False,
        "codegraph": False,
    }
    assert plan["next_action"] == "human-review"


def test_policy_plan_fails_closed_for_unknown_task_class(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_active_only_optimal_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(ablation["ablation_id"], state_root=root)

    with pytest.raises(ValueError, match="no unique task class decision"):
        plan_hybrid_runtime_policy(
            admission["admission_id"],
            "unknown-task-class",
            state_root=root,
        )


def test_policy_plan_audit_verifies_exact_active_only_set(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_active_only_optimal_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(ablation["ablation_id"], state_root=root)
    docs = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "docs",
        state_root=root,
    )
    repo_review = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "repo-review",
        state_root=root,
    )

    audit = audit_hybrid_policy_plans(
        [docs["policy_plan_id"], repo_review["policy_plan_id"]],
        admission_id=admission["admission_id"],
        expected_task_classes=["docs", "repo-review"],
        state_root=root,
    )

    assert audit["status"] == "VERIFIED"
    assert audit["errors"] == []
    assert audit["verified_task_classes"] == ["docs", "repo-review"]
    assert audit["effective_channel_selection"] == {
        "notebook_keyword": False,
        "notebook_vector": False,
        "codegraph": False,
    }
    assert audit["runtime_consumption_available"] is False
    assert all(row["status"] == "VERIFIED" for row in audit["plans"])


def test_policy_plan_audit_refuses_missing_task_class(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_active_only_optimal_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(ablation["ablation_id"], state_root=root)
    docs = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "docs",
        state_root=root,
    )

    audit = audit_hybrid_policy_plans(
        [docs["policy_plan_id"]],
        admission_id=admission["admission_id"],
        expected_task_classes=["docs", "repo-review"],
        state_root=root,
    )

    assert audit["status"] == "REFUSED"
    assert "missing task classes: repo-review" in audit["errors"]


def test_policy_plan_audit_refuses_duplicate_task_class(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_active_only_optimal_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(ablation["ablation_id"], state_root=root)
    docs_one = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "docs",
        state_root=root,
    )
    docs_two = plan_hybrid_runtime_policy(
        admission["admission_id"],
        "docs",
        state_root=root,
    )

    audit = audit_hybrid_policy_plans(
        [docs_one["policy_plan_id"], docs_two["policy_plan_id"]],
        admission_id=admission["admission_id"],
        expected_task_classes=["docs", "repo-review"],
        state_root=root,
    )

    assert audit["status"] == "REFUSED"
    assert "duplicate task classes: docs" in audit["errors"]
    assert "missing task classes: repo-review" in audit["errors"]


def test_admission_no_write_does_not_create_admission_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_ablation_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    ablation = collect_hybrid_ablation(
        suite,
        state_root=root,
        active_search=_active,
        codegraph_search=_codegraph,
    )
    admission = evaluate_hybrid_admission(
        ablation["ablation_id"],
        state_root=root,
        persist=False,
    )

    assert admission["status"] == "PASS"
    assert not (root / "admissions").exists()


def test_ablation_no_write_leaves_no_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = _write_ablation_suite(tmp_path)
    root = tmp_path / "state"

    class FakeEmbeddingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def embed(self, texts):
            return [[1.0] for _ in texts]

    monkeypatch.setattr(
        "mq_agent.notebook_corpus_semantic.OllamaEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    result = collect_hybrid_ablation(
        suite,
        state_root=root,
        persist=False,
        active_search=_active,
        codegraph_search=_codegraph,
    )

    assert result["status"] == "PASS"
    assert not root.exists()


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
