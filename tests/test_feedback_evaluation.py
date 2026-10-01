from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq_agent.feedback import append_comparison, append_experiment, build_feedback_experiment
from mq_agent.feedback.evaluation import (
    build_operational_comparison,
    compare_feedback_run,
)


def _experiment(run_id: str = "fb-eval") -> dict:
    return build_feedback_experiment(
        task_class="repo-review",
        repository="MCamner/mq-agent",
        active_strategy="context-pack-v1",
        shadow_strategy="context-pack-v1+codegraph-guidance",
        snapshot_ref="main",
        snapshot_commit="a" * 40,
        evidence_sources=["repo-context", "mqobsidian-context"],
        state="completed",
        feedback_run_id=run_id,
    )


def _metrics(*, active_latency: float = 10.0, shadow_latency: float = 10.0) -> tuple[dict, dict]:
    base = {
        "context_lines": 10,
        "context_bytes": 100,
        "context_tokens": None,
        "retrieval_latency_ms": active_latency,
        "source_count": 2,
        "deduplicated_source_count": 2,
        "provenance_coverage": 1.0,
        "stale_source_rate": 0.0,
        "external_api_calls": 0,
        "cost": 0.0,
    }
    shadow = dict(base)
    shadow["retrieval_latency_ms"] = shadow_latency
    return base, shadow


def _store_base(
    tmp_path: Path,
    *,
    active_sources: list[str],
    shadow_sources: list[str],
    active_latency: float = 10.0,
    shadow_latency: float = 10.0,
) -> str:
    experiment = _experiment()
    active, shadow = _metrics(
        active_latency=active_latency,
        shadow_latency=shadow_latency,
    )
    comparison = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=active_sources,
        shadow_sources=shadow_sources,
    )
    append_experiment(experiment, tmp_path)
    append_comparison(comparison, tmp_path)
    return experiment["feedback_run_id"]


def _fixture(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_f3_candidate_better_requires_deterministic_relevance_evidence(tmp_path) -> None:
    relevant = "repo-context:repo-card.md"
    run_id = _store_base(
        tmp_path,
        active_sources=[relevant, "file-ref:plausible-but-irrelevant.md"],
        shadow_sources=[relevant],
    )
    fixture = _fixture(
        tmp_path,
        {
            "id": "repo-review-positive",
            "expected_sources": [relevant],
            "negative": False,
            "stale_sources": [],
            "contradicted_sources": [],
        },
    )

    result = compare_feedback_run(run_id, fixture_path=fixture, state_root=tmp_path)

    assert result["verdict"] == "CANDIDATE_BETTER"
    assert result["metrics"]["relevance_precision"]["active"] == 0.5
    assert result["metrics"]["relevance_precision"]["shadow"] == 1.0
    assert result["relevance_fixture"]["id"] == "repo-review-positive"


def test_f3_more_plausible_but_irrelevant_material_is_not_better(tmp_path) -> None:
    relevant = "repo-context:repo-card.md"
    run_id = _store_base(
        tmp_path,
        active_sources=[relevant],
        shadow_sources=[relevant, "file-ref:plausible-but-irrelevant.md"],
    )
    fixture = _fixture(
        tmp_path,
        {
            "id": "irrelevant-regression",
            "expected_sources": [relevant],
            "negative": False,
        },
    )

    result = compare_feedback_run(run_id, fixture_path=fixture, state_root=tmp_path)

    assert result["verdict"] == "CANDIDATE_WORSE"
    assert result["metrics"]["relevance_precision"]["delta"] < 0


def test_f3_negative_query_rewards_returning_no_material(tmp_path) -> None:
    run_id = _store_base(
        tmp_path,
        active_sources=["file-ref:noise.md"],
        shadow_sources=[],
    )
    fixture = _fixture(
        tmp_path,
        {
            "id": "negative-query",
            "expected_sources": [],
            "negative": True,
        },
    )

    result = compare_feedback_run(run_id, fixture_path=fixture, state_root=tmp_path)

    assert result["verdict"] == "CANDIDATE_BETTER"
    metric = result["metrics"]["negative_query_correctness"]
    assert metric["active"] == 0.0
    assert metric["shadow"] == 1.0


def test_f3_stale_and_contradictory_sources_are_visible_per_metric(tmp_path) -> None:
    relevant = "repo-context:repo-card.md"
    stale = "context-card:stale-card.md"
    run_id = _store_base(
        tmp_path,
        active_sources=[relevant, stale],
        shadow_sources=[relevant],
    )
    fixture = _fixture(
        tmp_path,
        {
            "id": "stale-memory",
            "expected_sources": [relevant],
            "negative": False,
            "stale_sources": [stale],
            "contradicted_sources": [stale],
        },
    )

    result = compare_feedback_run(run_id, fixture_path=fixture, state_root=tmp_path)

    assert result["metrics"]["stale_source_rate"]["active"] == 0.5
    assert result["metrics"]["stale_source_rate"]["shadow"] == 0.0
    assert result["metrics"]["contradicted_source_rate"]["active"] == 0.5
    assert result["metrics"]["contradicted_source_rate"]["shadow"] == 0.0


def test_f3_quality_gain_plus_material_latency_regression_is_conflicting(tmp_path) -> None:
    relevant = "repo-context:repo-card.md"
    run_id = _store_base(
        tmp_path,
        active_sources=[relevant, "file-ref:noise.md"],
        shadow_sources=[relevant],
        active_latency=10.0,
        shadow_latency=30.0,
    )
    fixture = _fixture(
        tmp_path,
        {
            "id": "quality-vs-latency",
            "expected_sources": [relevant],
            "negative": False,
        },
    )

    result = compare_feedback_run(run_id, fixture_path=fixture, state_root=tmp_path)

    assert result["verdict"] == "CONFLICTING_EVIDENCE"
    assert result["metrics"]["retrieval_latency_ms"]["material"] is True


def test_f3_atlas_is_advisory_and_must_resolve_to_observed_evidence(tmp_path) -> None:
    relevant = "repo-context:repo-card.md"
    run_id = _store_base(
        tmp_path,
        active_sources=[relevant, "file-ref:noise.md"],
        shadow_sources=[relevant],
    )
    fixture = _fixture(
        tmp_path,
        {
            "id": "atlas-bound",
            "expected_sources": [relevant],
            "negative": False,
        },
    )
    base = json.loads((tmp_path / "comparisons.jsonl").read_text().splitlines()[0])
    observed = base["evidence_refs"][0]
    atlas = tmp_path / "atlas.json"
    atlas.write_text(
        json.dumps(
            {
                "schema": "atlas.feedback-evaluation.v1",
                "assessment": "prefer active",
                "evidence_refs": [observed],
            }
        ),
        encoding="utf-8",
    )

    result = compare_feedback_run(
        run_id,
        fixture_path=fixture,
        atlas_evaluation=atlas,
        state_root=tmp_path,
    )

    assert result["verdict"] == "CANDIDATE_BETTER"
    assert result["advisory_evaluator"]["assessment"] == "prefer active"

    atlas.write_text(
        json.dumps(
            {
                "schema": "atlas.feedback-evaluation.v1",
                "assessment": "prefer shadow",
                "evidence_refs": ["source:never-observed"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unobserved evidence"):
        compare_feedback_run(
            run_id,
            fixture_path=fixture,
            atlas_evaluation=atlas,
            state_root=tmp_path,
        )
