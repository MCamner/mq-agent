from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from mq_agent.feedback import append_comparison, append_experiment, build_feedback_experiment
from mq_agent.feedback.evaluation import (
    build_operational_comparison,
    compare_feedback_run,
    metric_pair,
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


def test_f3_comparison_schema_is_packaged_registered_and_rejects_incomplete_records() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "schemas" / "feedback_comparison.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    contract = json.loads(
        (root / ".mq" / "repo-contract.json").read_text(encoding="utf-8")
    )

    assert (
        '"schemas/feedback_comparison.schema.json" = '
        '"mq_agent/schemas/feedback_comparison.schema.json"'
    ) in pyproject
    assert "mq.feedback-comparison.v1" in contract["contracts"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(
            {"schema": "mq.feedback-comparison.v1", "verdict": "CANDIDATE_BETTER"}
        )



def test_f3_measured_codegraph_gain_survives_small_guidance_overhead(tmp_path) -> None:
    experiment = _experiment("fb-codegraph-measured")
    active, shadow = _metrics()
    active["context_lines"] = 44
    shadow["context_lines"] = 50
    active["context_bytes"] = 1253
    shadow["context_bytes"] = 1854
    active["source_count"] = 2
    shadow["source_count"] = 3
    active["deduplicated_source_count"] = 2
    shadow["deduplicated_source_count"] = 3

    base_sources = [
        "repo-context:repo-card.md",
        "context-card:mq-agent-card.md",
    ]
    codegraph_ref = "codegraph:mq_agent/main.py#app"
    comparison = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=base_sources,
        shadow_sources=[*base_sources, codegraph_ref],
    )
    append_experiment(experiment, tmp_path)
    append_comparison(comparison, tmp_path)
    fixture = _fixture(
        tmp_path,
        {
            "id": "measured-codegraph-gain",
            "expected_sources": [*base_sources, codegraph_ref],
            "negative": False,
            "stale_sources": [],
            "contradicted_sources": [],
        },
    )

    result = compare_feedback_run(
        experiment["feedback_run_id"],
        fixture_path=fixture,
        state_root=tmp_path,
    )

    assert result["metrics"]["context_lines"]["material"] is False
    assert result["metrics"]["context_bytes"]["material"] is False
    assert result["metrics"]["relevance_recall"]["active"] == pytest.approx(2 / 3)
    assert result["metrics"]["relevance_recall"]["shadow"] == 1.0
    assert result["verdict"] == "CANDIDATE_BETTER"


def test_f3_large_context_growth_remains_material() -> None:
    assert metric_pair("context_lines", 44, 60)["material"] is True
    assert metric_pair("context_bytes", 1253, 2500)["material"] is True
    assert metric_pair("context_tokens", 500, 800)["material"] is True



def test_f3_retrieval_latency_materiality_uses_real_execution_latency() -> None:
    experiment = _experiment("fb-task-latency")
    active, shadow = _metrics(active_latency=93.161, shadow_latency=591.092)
    active["execution_latency_ms"] = 10000
    shadow["execution_latency_ms"] = 10000

    comparison = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=["repo-context:repo-card.md"],
        shadow_sources=["repo-context:repo-card.md"],
    )

    latency = comparison["metrics"]["retrieval_latency_ms"]
    task_latency = comparison["metrics"]["execution_latency_ms"]
    assert latency["delta"] == pytest.approx(497.931)
    assert latency["material"] is False
    assert task_latency["active"] == 10000.0
    assert task_latency["shadow"] == 10000.0
    assert task_latency["direction"] == "neutral"


def test_f3_retrieval_latency_remains_material_for_short_real_task() -> None:
    experiment = _experiment("fb-short-task-latency")
    active, shadow = _metrics(active_latency=93.161, shadow_latency=591.092)
    active["execution_latency_ms"] = 2000
    shadow["execution_latency_ms"] = 2000

    comparison = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=["repo-context:repo-card.md"],
        shadow_sources=["repo-context:repo-card.md"],
    )

    assert comparison["metrics"]["retrieval_latency_ms"]["material"] is True


def test_f3_latency_falls_back_to_context_baseline_without_real_execution() -> None:
    experiment = _experiment("fb-no-task-latency")
    active, shadow = _metrics(active_latency=93.161, shadow_latency=591.092)

    comparison = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=["repo-context:repo-card.md"],
        shadow_sources=["repo-context:repo-card.md"],
    )

    assert comparison["metrics"]["retrieval_latency_ms"]["material"] is True
