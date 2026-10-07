from __future__ import annotations

from pathlib import Path

import pytest

from mq_agent.feedback import append_comparison
from mq_agent.feedback.canary import create_canary_plan
from mq_agent.feedback.models import build_feedback_experiment
from mq_agent.feedback.store import append_canary, append_experiment
from mq_agent.feedback.candidates import maybe_create_candidate
from mq_agent.feedback.control import (
    activate,
    approval_receipt,
    effective_strategy,
    rollback,
    validate_canary,
)
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

def _passing_canary(
    root: Path,
    *,
    candidate_id: str,
    approval_id: str,
) -> str:
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval_id,
        execution_budget=1,
        min_executions=1,
        root=root,
    )
    feedback_run_id = f"fb-{plan['canary_id']}"
    snapshot = {"kind": "git", "ref": "main", "commit": "d" * 40}
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
    append_experiment(experiment, root)

    comparison = _comparison(
        f"cmp-{plan['canary_id']}",
        commit="d" * 40,
        recorded_at="2099-01-01T00:00:00Z",
    )
    comparison["feedback_run_id"] = feedback_run_id
    append_comparison(comparison, root)

    result = {
        **plan,
        "record_type": "RESULT",
        "started_at": "2099-01-01T00:00:00Z",
        "completed_at": "2099-01-01T00:00:01Z",
        "duration_ms": 1,
        "verdict": "PASS",
        "executions_requested": 1,
        "executions_completed": 1,
        "successes": 1,
        "failures": 0,
        "inconclusive": 0,
        "failure_rate": 0.0,
        "feedback_run_ids": [feedback_run_id],
        "comparison_ids": [comparison["comparison_id"]],
        "snapshots": [snapshot],
        "metrics": {
            "latency_delta_ms": 0.0,
            "grounding_delta": 0.5,
            "context_delta_bytes": None,
            "fallback_delta": None,
        },
        "regressions": [],
        "blocked_reasons": [],
    }
    append_canary(result, root)
    return plan["canary_id"]



def test_activation_requires_post_approval_canary_and_rolls_back_append_only(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(
        candidate_id,
        reason="operator reviewed exact evidence",
        root=tmp_path,
    )

    old_canary = _comparison(
        "cmp-old-canary",
        commit="c" * 40,
        recorded_at="2026-10-01T00:00:00Z",
    )
    append_comparison(old_canary, tmp_path)
    with pytest.raises(ValueError, match="recorded after approval"):
        validate_canary(
            candidate_id,
            approval["approval_id"],
            old_canary["comparison_id"],
            root=tmp_path,
        )

    canary_id = _passing_canary(
        tmp_path,
        candidate_id=candidate_id,
        approval_id=approval["approval_id"],
    )

    event = activate(
        candidate_id,
        approval_id=approval["approval_id"],
        canary_id=canary_id,
        reason="bounded canary passed",
        root=tmp_path,
    )

    assert event["event_type"] == "ACTIVATION"
    assert event["from_strategy"] == BASELINE
    assert event["to_strategy"] == CANDIDATE
    assert effective_strategy("repo-review", tmp_path) == CANDIDATE

    rolled_back = rollback(
        "repo-review",
        reason="post-activation regression",
        root=tmp_path,
    )

    assert rolled_back["event_type"] == "ROLLBACK"
    assert rolled_back["from_strategy"] == CANDIDATE
    assert rolled_back["to_strategy"] == BASELINE
    assert effective_strategy("repo-review", tmp_path) == BASELINE
    events = (tmp_path / "policy-events.jsonl").read_text().splitlines()
    assert len(events) == 2

    with pytest.raises(ValueError, match="no active activation"):
        rollback(
            "repo-review",
            reason="must not toggle back to candidate",
            root=tmp_path,
        )


def test_kill_switch_restores_baseline_without_deleting_activation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    canary_id = _passing_canary(
        tmp_path,
        candidate_id=candidate_id,
        approval_id=approval["approval_id"],
    )
    activate(
        candidate_id,
        approval_id=approval["approval_id"],
        canary_id=canary_id,
        reason="canary pass",
        root=tmp_path,
    )
    assert effective_strategy("repo-review", tmp_path) == CANDIDATE

    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "off")

    assert effective_strategy("repo-review", tmp_path) == BASELINE
    assert (tmp_path / "policy-events.jsonl").is_file()
