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
    policy_status,
    rollback,
    validate_canary,
)
from mq_agent.feedback.evaluation import metric_pair
from mq_agent.tools.execution_outcome import (
    build_execution_outcome,
    record_execution_outcome,
)


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


def _seed_real_run(
    root: Path,
    outcome_path: Path,
    *,
    feedback_run_id: str,
    execution_run_id: str,
    recorded_at: str,
    commit: str,
) -> None:
    experiment = build_feedback_experiment(
        task_class="repo-review",
        repository="MCamner/mq-agent",
        active_strategy=BASELINE,
        shadow_strategy=CANDIDATE,
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
        task_class="audit",
        result="PASS",
        exit_status="ok",
        latency_ms=10,
        run_id=execution_run_id,
    )
    outcome["recorded_at"] = recorded_at
    record_execution_outcome(outcome, outcome_path)


def _ready_candidate(root: Path, monkeypatch) -> str:
    outcome_path = root / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcome_path))
    candidate_id = ""
    rows = (
        (_comparison("cmp-a", commit="a" * 40), "2026-10-01T10:00:00Z"),
        (_comparison("cmp-b", commit="b" * 40), "2026-10-02T10:00:00Z"),
        (_comparison("cmp-c", commit="c" * 40), "2026-10-03T10:00:00Z"),
    )
    for comparison, recorded_at in rows:
        _seed_real_run(
            root,
            outcome_path,
            feedback_run_id=comparison["feedback_run_id"],
            execution_run_id=f"exec-{comparison['comparison_id']}",
            recorded_at=recorded_at,
            commit=comparison["snapshot"]["commit"],
        )
        append_comparison(comparison, root)
        candidate, _ = maybe_create_candidate(comparison, state_root=root)
        assert candidate is not None
        candidate_id = candidate["candidate_id"]

    _seed_real_run(
        root,
        outcome_path,
        feedback_run_id="fb-calibration-extra",
        execution_run_id="exec-calibration-extra",
        recorded_at="2026-10-04T10:00:00Z",
        commit="e" * 40,
    )
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
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
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
    assert event["before_snapshot_id"].startswith("snapshot-")
    assert event["after_snapshot_id"].startswith("snapshot-")
    assert event["rollback_target_snapshot_id"] == event["before_snapshot_id"]
    assert effective_strategy("repo-review", tmp_path) == CANDIDATE

    rolled_back = rollback(
        event["event_id"],
        reason="post-activation regression",
        root=tmp_path,
    )

    assert rolled_back["event_type"] == "ROLLBACK"
    assert rolled_back["from_strategy"] == CANDIDATE
    assert rolled_back["to_strategy"] == BASELINE
    assert rolled_back["rollback_of_event_id"] == event["event_id"]
    assert rolled_back["rollback_target_snapshot_id"] == event["before_snapshot_id"]
    assert rolled_back["before_snapshot_id"] == event["after_snapshot_id"]
    assert rolled_back["after_snapshot_id"].startswith("snapshot-")
    assert effective_strategy("repo-review", tmp_path) == BASELINE
    events = (tmp_path / "policy-events.jsonl").read_text().splitlines()
    assert len(events) == 2

    with pytest.raises(ValueError, match="no longer the active latest"):
        rollback(
            event["event_id"],
            reason="must not toggle back to candidate",
            root=tmp_path,
        )


def test_policy_registry_snapshot_status_is_content_verified(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    canary_id = _passing_canary(
        tmp_path,
        candidate_id=candidate_id,
        approval_id=approval["approval_id"],
    )
    event = activate(
        candidate_id,
        approval_id=approval["approval_id"],
        canary_id=canary_id,
        reason="registry snapshot test",
        root=tmp_path,
    )

    status = policy_status("repo-review", tmp_path)
    assert status["events"] == 1
    assert status["snapshots"] == 2
    assert status["current_snapshot"]["snapshot_id"] == event["after_snapshot_id"]
    assert status["current_snapshot"]["effective_strategy"] == CANDIDATE
    assert status["current_snapshot"]["last_event_id"] == event["event_id"]


def test_rollback_refuses_non_activation_and_legacy_unbound_activation(
    tmp_path: Path,
) -> None:
    from mq_agent.feedback.store import append_policy_event

    legacy_event_id = "policy-legacy-12345678"
    legacy = {
        "schema": "mq.feedback-policy-event.v1",
        "event_id": legacy_event_id,
        "event_type": "ACTIVATION",
        "task_class": "repo-review",
        "from_strategy": BASELINE,
        "to_strategy": CANDIDATE,
        "candidate_id": "candidate-legacy",
        "approval_id": "approval-legacy-12345678",
        "canary_id": None,
        "canary_comparison_id": None,
        "recorded_at": "2026-10-07T00:00:00Z",
        "reason": "legacy v1.32 event",
    }
    append_policy_event(legacy, tmp_path)

    with pytest.raises(ValueError, match="predates Policy Registry v2"):
        rollback(
            legacy_event_id,
            reason="must not invent a target snapshot",
            root=tmp_path,
        )


def test_policy_registry_refuses_unknown_activation_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="resolve to exactly one"):
        rollback(
            "policy-does-not-exist-12345678",
            reason="must fail closed",
            root=tmp_path,
        )


def test_policy_registry_detects_snapshot_tamper(
    tmp_path: Path, monkeypatch
) -> None:
    import json

    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    canary_id = _passing_canary(
        tmp_path,
        candidate_id=candidate_id,
        approval_id=approval["approval_id"],
    )
    event = activate(
        candidate_id,
        approval_id=approval["approval_id"],
        canary_id=canary_id,
        reason="snapshot tamper test",
        root=tmp_path,
    )

    path = tmp_path / "policy-snapshots.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row["snapshot_id"] == event["before_snapshot_id"]:
            row["effective_strategy"] = "tampered-strategy"
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="snapshot store contains invalid|fingerprint mismatch"):
        rollback(
            event["event_id"],
            reason="tampered snapshot must fail",
            root=tmp_path,
        )


def test_kill_switch_restores_baseline_without_deleting_activation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
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
