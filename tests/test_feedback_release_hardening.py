from __future__ import annotations

import json
from pathlib import Path

import pytest
from git import Repo

from mq_agent.feedback import (
    append_comparison,
    append_experiment,
    build_feedback_experiment,
    compare_feedback_run,
    feedback_report,
    feedback_status,
    maybe_create_candidate,
    read_comparison_history,
    read_experiment_history,
    run_context_experiment,
)
from mq_agent.feedback.evaluation import build_operational_comparison


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "mq-agent"
    root.mkdir()
    repo = Repo.init(root)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Feedback Release Test")
        config.set_value("user", "email", "feedback-release@example.invalid")
    (root / "README.md").write_text("# release fixture\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("baseline")
    return root


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".mq").mkdir(parents=True)
    (root / ".mq" / "context-selection-vocabulary.json").write_text(
        json.dumps(
            {
                "source_heavy_hints": ["review"],
                "source_heavy_suppress": [],
                "max_codegraph_queries": 4,
            }
        ),
        encoding="utf-8",
    )
    cards = root / "memory" / "context-cards"
    cards.mkdir(parents=True)
    (cards / "mq-agent-card.md").write_text(
        "---\nfreshness: fresh\nscope: public\npublishability: public-safe\n---\n"
        "# mq-agent\n",
        encoding="utf-8",
    )
    return root


def _pack(*, codegraph: str) -> dict:
    relevant = "vault/memory/context-cards/relevant.md"
    noise = "vault/memory/context-cards/noise.md"
    cards = [relevant, noise] if codegraph == "off" else [relevant]
    body = (
        "active context with extra irrelevant material\n"
        if codegraph == "off"
        else "shadow context\n"
    )
    return {
        "content": body,
        "relevant_repos": ["mq-agent"],
        "cards": cards,
        "card_metadata": {
            "mq-agent": {
                "freshness": "fresh",
                "scope": "public",
                "publishability": "public-safe",
            }
        },
    }


def _fixture(path: Path, expected: list[str], **extra) -> Path:
    payload = {
        "id": "f6-release-fixture",
        "expected_sources": expected,
        "negative": False,
        **extra,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _experiment(run_id: str = "fb-f6") -> dict:
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


def _metrics() -> tuple[dict, dict]:
    active = {
        "context_lines": 20,
        "context_bytes": 200,
        "context_tokens": None,
        "retrieval_latency_ms": 10.0,
        "source_count": 2,
        "deduplicated_source_count": 2,
        "provenance_coverage": 1.0,
        "stale_source_rate": 0.0,
        "external_api_calls": 0,
        "cost": 0.0,
    }
    shadow = dict(active)
    shadow["context_lines"] = 10
    shadow["context_bytes"] = 100
    shadow["source_count"] = 1
    shadow["deduplicated_source_count"] = 1
    return active, shadow


def test_f6_end_to_end_fixture_experiment_comparison_candidate_report(
    tmp_path, monkeypatch
) -> None:
    repo = _repo(tmp_path)
    vault = _vault(tmp_path)
    state = tmp_path / "state"
    monkeypatch.setattr(
        "mq_agent.feedback.engine.build_task_pack",
        lambda *args, codegraph, **kwargs: _pack(codegraph=codegraph),
    )

    run = run_context_experiment(
        "review repository release boundary",
        repo,
        vault=vault,
        state_root=state,
    )
    run_id = run["experiment"]["feedback_run_id"]
    relevant = "context-card:relevant.md"
    fixture = _fixture(tmp_path / "fixture.json", [relevant])

    comparison = compare_feedback_run(
        run_id,
        fixture_path=fixture,
        state_root=state,
    )
    candidate, created = maybe_create_candidate(
        comparison,
        state_root=state,
    )
    report = feedback_report(state, task_class="repo-review")

    assert run["status"] == "PASS"
    assert comparison["verdict"] == "CANDIDATE_BETTER"
    assert created is True
    assert candidate is not None
    assert candidate["comparison_ids"] == [comparison["comparison_id"]]
    assert report["matched_records"] == 1
    assert report["comparison"]["status"] == "available"
    assert report["comparison"]["reason"] == "CANDIDATE_BETTER"
    assert feedback_status(state)["candidate_events"] == 1


def test_f6_missing_provenance_blocks_deterministic_verdict(tmp_path) -> None:
    experiment = _experiment()
    active, shadow = _metrics()
    base = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=["context-card:relevant.md"],
        shadow_sources=["context-card:relevant.md"],
    )
    base["evidence_refs"] = []
    append_experiment(experiment, tmp_path)
    append_comparison(base, tmp_path)
    fixture = _fixture(tmp_path / "fixture.json", ["context-card:relevant.md"])

    result = compare_feedback_run(
        experiment["feedback_run_id"],
        fixture_path=fixture,
        state_root=tmp_path,
    )

    assert result["valid"] is False
    assert result["verdict"] == "BLOCKED"
    assert "missing-experiment-provenance" in result["blocked_reasons"]


def test_f6_mixed_snapshot_blocks_comparison(tmp_path) -> None:
    experiment = _experiment()
    active, shadow = _metrics()
    base = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=["context-card:relevant.md"],
        shadow_sources=["context-card:relevant.md"],
    )
    base["snapshot"] = {"kind": "git", "ref": "main", "commit": "b" * 40}
    append_experiment(experiment, tmp_path)
    append_comparison(base, tmp_path)
    fixture = _fixture(tmp_path / "fixture.json", ["context-card:relevant.md"])

    result = compare_feedback_run(
        experiment["feedback_run_id"],
        fixture_path=fixture,
        state_root=tmp_path,
    )

    assert result["verdict"] == "BLOCKED"
    assert "snapshot-mismatch" in result["blocked_reasons"]


def test_f6_duplicate_run_ids_fail_closed(tmp_path) -> None:
    experiment = _experiment("fb-duplicate")
    append_experiment(experiment, tmp_path)
    append_experiment(experiment, tmp_path)
    fixture = _fixture(tmp_path / "fixture.json", [])

    with pytest.raises(ValueError, match="exactly one experiment"):
        compare_feedback_run(
            "fb-duplicate",
            fixture_path=fixture,
            state_root=tmp_path,
        )


def test_f6_stale_evidence_is_visible_not_silently_dropped(tmp_path) -> None:
    experiment = _experiment()
    active, shadow = _metrics()
    stale = "context-card:stale.md"
    relevant = "context-card:relevant.md"
    base = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=[relevant, stale],
        shadow_sources=[relevant],
    )
    append_experiment(experiment, tmp_path)
    append_comparison(base, tmp_path)
    fixture = _fixture(
        tmp_path / "fixture.json",
        [relevant],
        stale_sources=[stale],
    )

    result = compare_feedback_run(
        experiment["feedback_run_id"],
        fixture_path=fixture,
        state_root=tmp_path,
    )

    metric = result["metrics"]["stale_source_rate"]
    assert metric["active"] == 0.5
    assert metric["shadow"] == 0.0
    assert metric["material"] is True


def test_f6_malformed_history_degrades_but_keeps_valid_evidence(tmp_path) -> None:
    append_experiment(_experiment(), tmp_path)
    path = tmp_path / "experiments.jsonl"
    with path.open("ab") as handle:
        handle.write(b'{"schema":"mq.feedback-experiment.v1"')

    history = read_experiment_history(tmp_path)
    status = feedback_status(tmp_path)

    assert len(history.records) == 1
    assert len(history.issues) == 1
    assert status["health"] == "DEGRADED"


def test_f6_unavailable_metric_is_not_coerced_to_zero(tmp_path) -> None:
    experiment = _experiment()
    active, shadow = _metrics()
    comparison = build_operational_comparison(
        experiment,
        active_metrics=active,
        shadow_metrics=shadow,
        active_sources=["context-card:relevant.md"],
        shadow_sources=["context-card:relevant.md"],
    )
    append_experiment(experiment, tmp_path)
    append_comparison(comparison, tmp_path)

    report = feedback_report(tmp_path)

    assert comparison["metrics"]["context_tokens"]["status"] == "unavailable"
    assert comparison["metrics"]["context_tokens"]["delta"] is None
    assert report["metrics"]["context_tokens"] == {
        "status": "unavailable",
        "value": None,
    }


def test_f6_historical_v1_records_remain_readable_after_optional_extensions(
    tmp_path,
) -> None:
    legacy = _experiment("fb-legacy-v1")
    legacy.pop("network_backends", None)
    legacy.pop("execution_run_id", None)
    path = tmp_path / "experiments.jsonl"
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    history = read_experiment_history(tmp_path)

    assert history.issues == []
    assert len(history.records) == 1
    assert history.records[0].record["feedback_run_id"] == "fb-legacy-v1"
