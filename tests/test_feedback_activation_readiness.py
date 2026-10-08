from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.feedback import append_comparison
from mq_agent.feedback.candidates import maybe_create_candidate, set_candidate_state
from mq_agent.feedback.evaluation import metric_pair
from mq_agent.feedback.models import build_feedback_experiment
from mq_agent.feedback.readiness import activation_readiness
from mq_agent.feedback.store import append_experiment
from mq_agent.main import app
from mq_agent.tools.execution_outcome import (
    build_execution_outcome,
    record_execution_outcome,
)

runner = CliRunner()


def _comparison(
    comparison_id: str,
    *,
    commit: str = "a" * 40,
    latency_shadow: float = 10.0,
    recorded_at: str = "2026-10-01T10:00:00Z",
) -> dict:
    return {
        "schema": "mq.feedback-comparison.v1",
        "comparison_id": comparison_id,
        "feedback_run_id": f"fb-{comparison_id}",
        "task_class": "repo-review",
        "repository": "MCamner/mq-agent",
        "active_strategy": "context-pack-v1",
        "shadow_strategy": "context-pack-v1+codegraph-guidance",
        "snapshot": {"kind": "git", "ref": "main", "commit": commit},
        "valid": True,
        "blocked_reasons": [],
        "verdict": "CANDIDATE_BETTER",
        "metrics": {
            "relevance_precision": metric_pair("relevance_precision", 0.5, 1.0),
            "retrieval_latency_ms": metric_pair(
                "retrieval_latency_ms", 10.0, latency_shadow
            ),
        },
        "sources": {
            "active": ["repo-context:repo-card.md", "file-ref:noise.md"],
            "shadow": ["repo-context:repo-card.md"],
        },
        "evidence_refs": [f"comparison-seed:{comparison_id}"],
        "relevance_fixture": {
            "id": f"fixture-{comparison_id}",
            "sha256": "b" * 64,
            "negative": False,
            "expected_sources": 1,
        },
        "advisory_evaluator": None,
        "recorded_at": recorded_at,
    }


def _real_run(
    root: Path,
    outcome_path: Path,
    *,
    feedback_run_id: str,
    execution_run_id: str,
    recorded_at: str,
    result: str = "PASS",
    exit_status: str = "ok",
    commit: str = "a" * 40,
) -> None:
    experiment = build_feedback_experiment(
        task_class="repo-review",
        repository="MCamner/mq-agent",
        active_strategy="context-pack-v1",
        shadow_strategy="context-pack-v1+codegraph-guidance",
        snapshot_ref="main",
        snapshot_commit=commit,
        evidence_sources=["repo-context"],
        state="completed",
        execution_run_id=execution_run_id,
        feedback_run_id=feedback_run_id,
    )
    append_experiment(experiment, root)
    outcome = build_execution_outcome(
        runtime="agent",
        # Deliberately a different vocabulary from feedback task_class. Readiness
        # correlates by execution_run_id and never invents repo-review -> audit.
        task_class="audit",
        result=result,
        exit_status=exit_status,
        latency_ms=10,
        run_id=execution_run_id,
    )
    outcome["recorded_at"] = recorded_at
    record_execution_outcome(outcome, outcome_path)


def _candidate_with(
    root: Path,
    outcome_path: Path,
    comparisons: list[dict],
    *,
    extra_population: int = 0,
) -> str:
    candidate_id = ""
    dates = [
        "2026-10-01T10:00:00Z",
        "2026-10-02T10:00:00Z",
        "2026-10-03T10:00:00Z",
        "2026-10-04T10:00:00Z",
        "2026-10-05T10:00:00Z",
        "2026-10-06T10:00:00Z",
    ]
    for index, comparison in enumerate(comparisons):
        _real_run(
            root,
            outcome_path,
            feedback_run_id=comparison["feedback_run_id"],
            execution_run_id=f"exec-{comparison['comparison_id']}",
            recorded_at=dates[index],
            commit=comparison["snapshot"]["commit"],
        )
        append_comparison(comparison, root)
        candidate, _created = maybe_create_candidate(comparison, state_root=root)
        assert candidate is not None
        candidate_id = candidate["candidate_id"]

    for offset in range(extra_population):
        index = len(comparisons) + offset
        _real_run(
            root,
            outcome_path,
            feedback_run_id=f"fb-pop-{index}",
            execution_run_id=f"exec-pop-{index}",
            recorded_at=dates[index],
            commit=chr(ord("d") + offset) * 40,
        )
    return candidate_id


def _ready_candidate(root: Path, outcome_path: Path) -> str:
    return _candidate_with(
        root,
        outcome_path,
        [
            _comparison("cmp-1", recorded_at="2026-10-01T10:00:00Z"),
            _comparison("cmp-2", recorded_at="2026-10-02T10:00:00Z"),
            _comparison("cmp-3", recorded_at="2026-10-03T10:00:00Z"),
        ],
        extra_population=1,
    )


def test_two_comparisons_no_longer_clear_a_global_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    candidate_id = _candidate_with(
        tmp_path,
        outcomes,
        [
            _comparison("cmp-1"),
            _comparison("cmp-2"),
        ],
        extra_population=2,
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    requirement = next(
        item for item in result["requirements"] if item["id"] == "derived-sample-size"
    )
    assert requirement["status"] == "FAIL"
    assert result["promotion_criteria"]["required_linked_outcomes"] == 3


def test_outcome_derived_criteria_are_ready_without_snapshot_count_gate(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    # Same Git snapshot on purpose: snapshot diversity is no longer the generic
    # promotion threshold. Real-run sample, temporal coverage and class baseline
    # are the evidence gates.
    candidate_id = _candidate_with(
        tmp_path,
        outcomes,
        [
            _comparison("cmp-1", commit="a" * 40),
            _comparison("cmp-2", commit="a" * 40),
            _comparison("cmp-3", commit="a" * 40),
        ],
        extra_population=1,
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "READY_FOR_HUMAN_APPROVAL"
    assert result["evidence"]["distinct_snapshot_count"] == 1
    assert result["evidence"]["real_outcomes"]["linked_outcome_count"] == 3
    assert result["promotion_criteria"]["calibration_outcomes"] == 4
    assert result["promotion_criteria"]["required_linked_outcomes"] == 3
    assert result["promotion_criteria"]["required_success_rate"] == 1.0
    assert len(result["evidence_fingerprint"]) == 64
    assert result["next_action"] == "request-human-approval"


def test_missing_execution_correlation_is_insufficient_not_fabricated(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    comparisons = [
        _comparison("cmp-1"),
        _comparison("cmp-2"),
        _comparison("cmp-3"),
    ]
    candidate_id = ""
    for comparison in comparisons:
        append_comparison(comparison, tmp_path)
        candidate, _ = maybe_create_candidate(comparison, state_root=tmp_path)
        assert candidate is not None
        candidate_id = candidate["candidate_id"]

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["promotion_criteria"]["calibration_outcomes"] == 0
    assert sorted(
        result["evidence"]["real_outcomes"]["unresolved_feedback_run_ids"]
    ) == ["fb-cmp-1", "fb-cmp-2", "fb-cmp-3"]


def test_task_class_success_baseline_is_derived_from_real_outcomes(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    comparisons = [
        _comparison("cmp-1"),
        _comparison("cmp-2"),
        _comparison("cmp-3"),
    ]
    candidate_id = ""
    result_specs = [
        ("PASS", "ok"),
        ("FAIL", "error"),
        ("FAIL", "error"),
    ]
    dates = [
        "2026-10-01T10:00:00Z",
        "2026-10-02T10:00:00Z",
        "2026-10-03T10:00:00Z",
    ]
    for comparison, (run_result, exit_status), recorded_at in zip(
        comparisons, result_specs, dates
    ):
        _real_run(
            tmp_path,
            outcomes,
            feedback_run_id=comparison["feedback_run_id"],
            execution_run_id=f"exec-{comparison['comparison_id']}",
            recorded_at=recorded_at,
            result=run_result,
            exit_status=exit_status,
        )
        append_comparison(comparison, tmp_path)
        candidate, _ = maybe_create_candidate(comparison, state_root=tmp_path)
        assert candidate is not None
        candidate_id = candidate["candidate_id"]

    # Extra successful population run makes the task-class baseline 0.5 while
    # the linked candidate evidence remains 1/3.
    _real_run(
        tmp_path,
        outcomes,
        feedback_run_id="fb-pop-4",
        execution_run_id="exec-pop-4",
        recorded_at="2026-10-04T10:00:00Z",
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["promotion_criteria"]["required_success_rate"] == 0.5
    assert result["evidence"]["real_outcomes"]["linked_success_rate"] == round(1 / 3, 6)
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    gate = next(
        item
        for item in result["requirements"]
        if item["id"] == "task-class-success-baseline"
    )
    assert gate["status"] == "FAIL"


def test_material_regression_still_blocks_readiness(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    candidate_id = _candidate_with(
        tmp_path,
        outcomes,
        [
            _comparison("cmp-1"),
            _comparison("cmp-2"),
            _comparison("cmp-3", latency_shadow=20.0),
        ],
        extra_population=1,
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "BLOCKED"
    assert "cmp-3:retrieval_latency_ms" in result["evidence"]["material_regressions"]
    assert result["next_action"] == "resolve-blockers"


def test_invalid_execution_history_blocks_policy_decision(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    candidate_id = _ready_candidate(tmp_path, outcomes)
    with outcomes.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "BLOCKED"
    gate = next(item for item in result["requirements"] if item["id"] == "store-integrity")
    assert gate["status"] == "FAIL"


def test_rejected_candidate_remains_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    candidate_id = _ready_candidate(tmp_path, outcomes)
    set_candidate_state(
        candidate_id,
        "rejected",
        reason="operator rejected activation direction",
        state_root=tmp_path,
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["candidate_state"] == "rejected"


def test_readiness_fingerprint_changes_when_task_class_population_changes(
    tmp_path: Path, monkeypatch
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    candidate_id = _ready_candidate(tmp_path, outcomes)
    first = activation_readiness(candidate_id, tmp_path)

    _real_run(
        tmp_path,
        outcomes,
        feedback_run_id="fb-pop-new",
        execution_run_id="exec-pop-new",
        recorded_at="2026-10-05T10:00:00Z",
    )
    second = activation_readiness(candidate_id, tmp_path)

    assert first["status"] == "READY_FOR_HUMAN_APPROVAL"
    assert second["status"] == "READY_FOR_HUMAN_APPROVAL"
    assert first["evidence_fingerprint"] != second["evidence_fingerprint"]
    assert (
        first["promotion_criteria"]["calibration_fingerprint"]
        != second["promotion_criteria"]["calibration_fingerprint"]
    )


def test_readiness_matches_packaged_schema(tmp_path: Path, monkeypatch) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    candidate_id = _ready_candidate(tmp_path, outcomes)
    result = activation_readiness(candidate_id, tmp_path)
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "schemas" / "feedback_activation_readiness.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(result)


def test_cli_exit_codes_distinguish_ready_insufficient_and_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outcomes = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))

    one = _candidate_with(
        tmp_path,
        outcomes,
        [_comparison("cmp-one")],
        extra_population=3,
    )
    insufficient = runner.invoke(
        app, ["feedback", "activation-readiness", one, "--json"]
    )
    assert insufficient.exit_code == 1
    assert json.loads(insufficient.output)["status"] == "INSUFFICIENT_EVIDENCE"

    for index, day in ((2, "2026-10-02T10:00:00Z"), (3, "2026-10-03T10:00:00Z")):
        comparison = _comparison(f"cmp-{index}", recorded_at=day)
        _real_run(
            tmp_path,
            outcomes,
            feedback_run_id=comparison["feedback_run_id"],
            execution_run_id=f"exec-{comparison['comparison_id']}",
            recorded_at=day,
        )
        append_comparison(comparison, tmp_path)
        candidate, _ = maybe_create_candidate(comparison, state_root=tmp_path)
        assert candidate is not None and candidate["candidate_id"] == one

    ready = runner.invoke(
        app, ["feedback", "activation-readiness", one, "--json"]
    )
    assert ready.exit_code == 0
    assert json.loads(ready.output)["status"] == "READY_FOR_HUMAN_APPROVAL"

    set_candidate_state(
        one,
        "rejected",
        reason="do not activate",
        state_root=tmp_path,
    )
    blocked = runner.invoke(
        app, ["feedback", "activation-readiness", one, "--json"]
    )
    assert blocked.exit_code == 2
    assert json.loads(blocked.output)["status"] == "BLOCKED"
