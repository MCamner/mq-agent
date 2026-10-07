from __future__ import annotations

from pathlib import Path

import pytest

from mq_agent.feedback import append_comparison
from mq_agent.feedback.canary import (
    canary_status,
    create_canary_plan,
    require_passing_canary,
    run_canary,
)
from mq_agent.feedback.candidates import maybe_create_candidate
from mq_agent.feedback.models import build_feedback_experiment
from mq_agent.feedback.store import append_experiment
from mq_agent.feedback.control import activate, approval_receipt, effective_strategy
from mq_agent.feedback.evaluation import metric_pair


BASELINE = "context-pack-v1"
CANDIDATE = "context-pack-v1+codegraph-guidance"


def _comparison(
    comparison_id: str,
    *,
    commit: str,
    recorded_at: str = "2026-10-06T10:00:00Z",
) -> dict:
    return {
        "schema": "mq.feedback-comparison.v1",
        "comparison_id": comparison_id,
        "feedback_run_id": f"fb-{comparison_id}",
        "task_class": "repo-review",
        "repository": "MCamner/mq-agent",
        "active_strategy": BASELINE,
        "shadow_strategy": CANDIDATE,
        "snapshot": {"kind": "git", "ref": "main", "commit": commit},
        "valid": True,
        "blocked_reasons": [],
        "verdict": "CANDIDATE_BETTER",
        "metrics": {
            "relevance_precision": metric_pair("relevance_precision", 0.5, 1.0),
            "retrieval_latency_ms": metric_pair("retrieval_latency_ms", 10.0, 10.0),
        },
        "sources": {
            "active": ["repo-context:repo-card.md", "file-ref:noise.md"],
            "shadow": ["repo-context:repo-card.md"],
        },
        "evidence_refs": [f"seed:{comparison_id}"],
        "relevance_fixture": {
            "id": f"fixture-{comparison_id}",
            "sha256": "b" * 64,
            "negative": False,
            "expected_sources": 1,
        },
        "advisory_evaluator": None,
        "recorded_at": recorded_at,
    }


def _ready_candidate(root: Path) -> str:
    candidate_id = ""
    for comparison in (
        _comparison("cmp-a", commit="a" * 40),
        _comparison("cmp-b", commit="b" * 40),
    ):
        append_comparison(comparison, root)
        candidate, _ = maybe_create_candidate(comparison, state_root=root)
        assert candidate is not None
        candidate_id = candidate["candidate_id"]
    return candidate_id


def _mock_execution(monkeypatch, verdicts: list[str]) -> None:
    counter = {"value": 0}

    def fake_run(*_args, **kwargs):
        counter["value"] += 1
        index = counter["value"]
        feedback_run_id = f"fb-canary-{index}"
        snapshot = {
            "kind": "git",
            "ref": "main",
            "commit": "d" * 40,
        }
        experiment = build_feedback_experiment(
            task_class="repo-review",
            repository="MCamner/mq-agent",
            active_strategy=BASELINE,
            shadow_strategy=CANDIDATE,
            snapshot_ref=snapshot["ref"],
            snapshot_commit=snapshot["commit"],
            evidence_sources=["repo-context"],
            state="completed",
            feedback_run_id=feedback_run_id,
        )
        append_experiment(experiment, kwargs.get("state_root"))
        return {
            "status": "PASS",
            "reason": None,
            "experiment": experiment,
            "comparison": None,
        }

    def fake_compare(feedback_run_id, **_kwargs):
        index = int(feedback_run_id.rsplit("-", 1)[-1])
        verdict = verdicts[index - 1]
        latency = metric_pair("retrieval_latency_ms", 10.0, 8.0)
        grounding = metric_pair("relevance_precision", 0.5, 0.8)
        context = metric_pair("context_bytes", 1000.0, 900.0)
        if verdict == "CANDIDATE_WORSE":
            grounding = metric_pair("relevance_precision", 0.8, 0.5)
        comparison = {
            "schema": "mq.feedback-comparison.v1",
            "comparison_id": f"cmp-canary-{index}",
            "feedback_run_id": feedback_run_id,
            "task_class": "repo-review",
            "repository": "MCamner/mq-agent",
            "active_strategy": BASELINE,
            "shadow_strategy": CANDIDATE,
            "snapshot": {"kind": "git", "ref": "main", "commit": "d" * 40},
            "valid": True,
            "blocked_reasons": [],
            "verdict": verdict,
            "metrics": {
                "retrieval_latency_ms": latency,
                "relevance_precision": grounding,
                "context_bytes": context,
            },
            "sources": {"active": [], "shadow": []},
            "evidence_refs": [f"experiment:{feedback_run_id}"],
            "relevance_fixture": {
                "id": "fixture",
                "sha256": "c" * 64,
                "negative": False,
                "expected_sources": 1,
            },
            "advisory_evaluator": None,
            "recorded_at": "2099-01-01T00:00:00Z",
        }
        append_comparison(comparison, _kwargs.get("state_root"))
        return comparison

    monkeypatch.setattr("mq_agent.feedback.canary.run_context_experiment", fake_run)
    monkeypatch.setattr("mq_agent.feedback.canary.compare_feedback_run", fake_compare)


def test_canary_v2_plan_run_status_and_activation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(
        candidate_id,
        reason="operator reviewed exact evidence",
        root=tmp_path,
    )
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        execution_budget=3,
        min_executions=3,
        max_duration_seconds=60,
        max_failure_rate=0.0,
        root=tmp_path,
    )

    _mock_execution(monkeypatch, ["CANDIDATE_BETTER"] * 3)
    result = run_canary(
        plan["canary_id"],
        task="review release boundaries",
        fixture_path=tmp_path / "fixture.json",
        root=tmp_path,
    )

    assert result["verdict"] == "PASS"
    assert result["executions_completed"] == 3
    assert result["successes"] == 3
    assert result["failures"] == 0
    assert result["inconclusive"] == 0
    assert result["failure_rate"] == 0.0
    assert result["metrics"]["latency_delta_ms"] == -2.0
    assert result["metrics"]["grounding_delta"] == 0.3
    assert result["metrics"]["context_delta_bytes"] == -100.0
    assert result["metrics"]["fallback_delta"] is None

    status = canary_status(plan["canary_id"], tmp_path)
    assert status["state"] == "COMPLETED"
    assert status["result"]["plan_sha256"] == plan["plan_sha256"]

    event = activate(
        candidate_id,
        approval_id=approval["approval_id"],
        canary_id=plan["canary_id"],
        reason="bounded Canary v2 passed",
        root=tmp_path,
    )
    assert event["event_type"] == "ACTIVATION"
    assert event["canary_id"] == plan["canary_id"]
    assert effective_strategy("repo-review", tmp_path) == CANDIDATE


def test_canary_v2_fail_blocks_activation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        execution_budget=3,
        min_executions=2,
        max_failure_rate=0.0,
        root=tmp_path,
    )

    _mock_execution(
        monkeypatch,
        ["CANDIDATE_BETTER", "CANDIDATE_WORSE", "CANDIDATE_BETTER"],
    )
    result = run_canary(
        plan["canary_id"],
        task="review release boundaries",
        fixture_path=tmp_path / "fixture.json",
        root=tmp_path,
    )

    assert result["verdict"] == "FAIL"
    assert result["failures"] == 1
    assert result["failure_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert result["regressions"]

    with pytest.raises(ValueError, match="canary verdict is not PASS"):
        activate(
            candidate_id,
            approval_id=approval["approval_id"],
            canary_id=plan["canary_id"],
            reason="must fail closed",
            root=tmp_path,
        )


def test_canary_v2_inconclusive_is_not_activation_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        execution_budget=2,
        min_executions=2,
        root=tmp_path,
    )

    _mock_execution(monkeypatch, ["NO_MATERIAL_DIFFERENCE", "INSUFFICIENT_EVIDENCE"])
    result = run_canary(
        plan["canary_id"],
        task="review release boundaries",
        fixture_path=tmp_path / "fixture.json",
        root=tmp_path,
    )

    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["successes"] == 0
    assert result["inconclusive"] == 2

    with pytest.raises(ValueError, match="canary verdict is not PASS"):
        require_passing_canary(
            plan["canary_id"],
            candidate_id=candidate_id,
            approval_id=approval["approval_id"],
            root=tmp_path,
        )


def test_canary_v2_refuses_duplicate_result(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        execution_budget=1,
        min_executions=1,
        root=tmp_path,
    )
    _mock_execution(monkeypatch, ["CANDIDATE_BETTER"])

    run_canary(
        plan["canary_id"],
        task="review release boundaries",
        fixture_path=tmp_path / "fixture.json",
        root=tmp_path,
    )

    with pytest.raises(ValueError, match="already has a RESULT"):
        run_canary(
            plan["canary_id"],
            task="review release boundaries",
            fixture_path=tmp_path / "fixture.json",
            root=tmp_path,
        )


def test_canary_v2_refuses_stale_policy_snapshot(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        root=tmp_path,
    )

    monkeypatch.setattr(
        "mq_agent.feedback.canary._policy_snapshot",
        lambda *_args, **_kwargs: {
            "effective_strategy": CANDIDATE,
            "event_count": 1,
            "last_event_id": "policy-drifted",
        },
    )

    with pytest.raises(ValueError, match="policy snapshot is stale"):
        run_canary(
            plan["canary_id"],
            task="review release boundaries",
            fixture_path=tmp_path / "fixture.json",
            root=tmp_path,
        )
