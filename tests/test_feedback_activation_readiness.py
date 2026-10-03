from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.feedback import append_comparison
from mq_agent.feedback.candidates import maybe_create_candidate, set_candidate_state
from mq_agent.feedback.evaluation import metric_pair
from mq_agent.feedback.readiness import activation_readiness
from mq_agent.main import app

runner = CliRunner()


def _comparison(
    comparison_id: str,
    *,
    commit: str,
    latency_shadow: float = 10.0,
) -> dict:
    return {
        "schema": "mq.feedback-comparison.v1",
        "comparison_id": comparison_id,
        "feedback_run_id": f"fb-{comparison_id}",
        "task_class": "repo-review",
        "repository": "MCamner/mq-agent",
        "active_strategy": "context-pack-v1",
        "shadow_strategy": "hybrid-context-v1",
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
        "recorded_at": "2026-10-03T00:00:00Z",
    }


def _candidate_with(
    root: Path,
    comparisons: list[dict],
) -> str:
    candidate_id = ""
    for comparison in comparisons:
        append_comparison(comparison, root)
        candidate, _created = maybe_create_candidate(comparison, state_root=root)
        assert candidate is not None
        candidate_id = candidate["candidate_id"]
    return candidate_id


def test_one_comparison_is_insufficient_not_ready(tmp_path: Path) -> None:
    candidate_id = _candidate_with(
        tmp_path,
        [_comparison("cmp-1", commit="a" * 40)],
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["activation_available"] is False
    assert result["human_approval_required"] is True
    assert result["canary_required"] is True
    assert result["next_action"] == "collect-more-evidence"


def test_two_distinct_snapshots_are_ready_for_human_approval(tmp_path: Path) -> None:
    candidate_id = _candidate_with(
        tmp_path,
        [
            _comparison("cmp-1", commit="a" * 40),
            _comparison("cmp-2", commit="c" * 40),
        ],
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "READY_FOR_HUMAN_APPROVAL"
    assert result["evidence"]["comparison_count"] == 2
    assert result["evidence"]["distinct_snapshot_count"] == 2
    assert result["scope"]["task_class"] == "repo-review"
    assert result["scope"]["cross_task_activation"] is False
    assert result["rollback_target"] == result["current_strategy"]
    assert result["next_action"] == "request-human-approval"


def test_repeated_same_snapshot_is_still_insufficient(tmp_path: Path) -> None:
    candidate_id = _candidate_with(
        tmp_path,
        [
            _comparison("cmp-1", commit="a" * 40),
            _comparison("cmp-2", commit="a" * 40),
        ],
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    requirement = next(
        item for item in result["requirements"] if item["id"] == "distinct-snapshots"
    )
    assert requirement["status"] == "FAIL"


def test_material_regression_blocks_readiness(tmp_path: Path) -> None:
    candidate_id = _candidate_with(
        tmp_path,
        [
            _comparison("cmp-1", commit="a" * 40),
            _comparison("cmp-2", commit="c" * 40, latency_shadow=20.0),
        ],
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "BLOCKED"
    assert "cmp-2:retrieval_latency_ms" in result["evidence"]["material_regressions"]
    assert result["next_action"] == "resolve-blockers"


def test_rejected_candidate_is_blocked(tmp_path: Path) -> None:
    candidate_id = _candidate_with(
        tmp_path,
        [
            _comparison("cmp-1", commit="a" * 40),
            _comparison("cmp-2", commit="c" * 40),
        ],
    )
    set_candidate_state(
        candidate_id,
        "rejected",
        reason="operator rejected activation direction",
        state_root=tmp_path,
    )

    result = activation_readiness(candidate_id, tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["candidate_state"] == "rejected"


def test_readiness_matches_packaged_schema(tmp_path: Path) -> None:
    candidate_id = _candidate_with(
        tmp_path,
        [
            _comparison("cmp-1", commit="a" * 40),
            _comparison("cmp-2", commit="c" * 40),
        ],
    )
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
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(tmp_path))

    one = _candidate_with(
        tmp_path,
        [_comparison("cmp-one", commit="1" * 40)],
    )
    insufficient = runner.invoke(
        app, ["feedback", "activation-readiness", one, "--json"]
    )
    assert insufficient.exit_code == 1
    assert json.loads(insufficient.output)["status"] == "INSUFFICIENT_EVIDENCE"

    two = _comparison("cmp-two", commit="2" * 40)
    append_comparison(two, tmp_path)
    candidate, _ = maybe_create_candidate(two, state_root=tmp_path)
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
