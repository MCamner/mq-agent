from __future__ import annotations

from pathlib import Path

import json

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from mq_agent.feedback import append_candidate, append_comparison
from mq_agent.feedback.candidates import (
    candidate_detail,
    list_candidates,
    maybe_create_candidate,
    memory_handoff,
    set_candidate_state,
)
from mq_agent.feedback.contracts import validate_candidate
from mq_agent.feedback.evaluation import metric_pair


def _comparison(
    comparison_id: str,
    *,
    proposed: str = "hybrid-context-v1",
    recorded_at: str = "2026-10-01T08:00:00Z",
) -> dict:
    return {
        "schema": "mq.feedback-comparison.v1",
        "comparison_id": comparison_id,
        "feedback_run_id": f"fb-{comparison_id}",
        "task_class": "repo-review",
        "repository": "MCamner/mq-agent",
        "active_strategy": "context-pack-v1",
        "shadow_strategy": proposed,
        "snapshot": {"kind": "git", "ref": "main", "commit": "a" * 40},
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
        "evidence_refs": [f"comparison-seed:{comparison_id}"],
        "relevance_fixture": {
            "id": "fixture",
            "sha256": "b" * 64,
            "negative": False,
            "expected_sources": 1,
        },
        "advisory_evaluator": None,
        "recorded_at": recorded_at,
    }


def test_f4_creates_reviewable_candidate_and_reconstructs_comparison(tmp_path) -> None:
    comparison = _comparison("cmp-1")
    append_comparison(comparison, tmp_path)

    candidate, created = maybe_create_candidate(comparison, state_root=tmp_path)
    assert created is True
    assert candidate is not None
    assert candidate["state"] == "proposed"
    assert candidate["rollback_target"] == "context-pack-v1"
    assert candidate["comparison_ids"] == ["cmp-1"]

    detail = candidate_detail(candidate["candidate_id"], tmp_path)
    assert detail["candidate"]["candidate_id"] == candidate["candidate_id"]
    assert [item["comparison_id"] for item in detail["comparisons"]] == ["cmp-1"]


def test_f4_materially_identical_candidate_is_deduplicated_and_evidence_extended(
    tmp_path,
) -> None:
    first = _comparison("cmp-1", recorded_at="2026-10-01T08:00:00Z")
    second = _comparison("cmp-2", recorded_at="2026-10-01T08:05:00Z")
    append_comparison(first, tmp_path)
    append_comparison(second, tmp_path)

    candidate1, _ = maybe_create_candidate(first, state_root=tmp_path)
    candidate2, created = maybe_create_candidate(second, state_root=tmp_path)

    assert candidate1 is not None and candidate2 is not None
    assert candidate1["candidate_id"] == candidate2["candidate_id"]
    assert created is True
    assert candidate2["comparison_ids"] == ["cmp-1", "cmp-2"]
    assert list_candidates(tmp_path)["count"] == 1


def test_f4_new_proposal_supersedes_old_without_rewriting_history(tmp_path) -> None:
    first = _comparison("cmp-1", proposed="hybrid-context-v1")
    second = _comparison("cmp-2", proposed="hybrid-context-v2")
    append_comparison(first, tmp_path)
    append_comparison(second, tmp_path)

    old, _ = maybe_create_candidate(first, state_root=tmp_path)
    new, _ = maybe_create_candidate(second, state_root=tmp_path)

    assert old is not None and new is not None
    effective = {item["candidate_id"]: item for item in list_candidates(tmp_path)["candidates"]}
    assert effective[old["candidate_id"]]["state"] == "superseded"
    assert old["candidate_id"] in new["supersedes"]


def test_f4_human_review_state_is_append_only_and_never_activation(tmp_path) -> None:
    comparison = _comparison("cmp-1")
    append_comparison(comparison, tmp_path)
    candidate, _ = maybe_create_candidate(comparison, state_root=tmp_path)
    assert candidate is not None

    reviewed = set_candidate_state(
        candidate["candidate_id"],
        "deferred",
        reason="Need more repo-review evidence",
        state_root=tmp_path,
    )

    assert reviewed["state"] == "deferred"
    detail = candidate_detail(candidate["candidate_id"], tmp_path)
    assert [event["state"] for event in detail["history"]] == ["proposed", "deferred"]
    assert "activation" not in reviewed


def test_f4_memory_handoff_uses_existing_mqobsidian_review_path(
    tmp_path, monkeypatch
) -> None:
    comparison = _comparison("cmp-memory")
    append_comparison(comparison, tmp_path)
    candidate = {
        "schema": "mq.feedback-candidate.v1",
        "candidate_id": "cand-memory",
        "fingerprint": "c" * 64,
        "kind": "memory",
        "task_class": "repo-review",
        "current_strategy": "memory-v1",
        "proposed_strategy": "memory-v2",
        "comparison_ids": ["cmp-memory"],
        "evidence_window": {
            "from": "2026-10-01T08:00:00Z",
            "to": "2026-10-01T08:00:00Z",
        },
        "rationale": "Reviewed reusable learning.",
        "gains": ["relevance improved"],
        "regressions": [],
        "limitations": ["review required"],
        "rollback_target": "memory-v1",
        "state": "approved-for-handoff",
        "state_reason": "operator approved review handoff",
        "supersedes": [],
        "recorded_at": "2026-10-01T08:10:00Z",
    }
    validate_candidate(candidate)
    append_candidate(candidate, tmp_path)

    captured = {}

    def fake_emit(record, *, vault=None):
        captured.update(record)
        return Path("/tmp/mqobsidian-observations.jsonl")

    monkeypatch.setattr("mq_agent.feedback.candidates.emit_observation", fake_emit)

    result = memory_handoff(
        "cand-memory",
        confidence=0.7,
        state_root=tmp_path,
    )

    assert result["status"] == "submitted-for-review"
    assert captured["schema"] == "memory-observation.v1"
    assert captured["evidence"][0]["source"] == "mq.feedback-comparison.v1"
    assert "durable" not in result


def test_f4_candidate_schema_is_packaged_registered_and_rejects_activation_state() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "schemas" / "feedback_candidate.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    contract = json.loads(
        (root / ".mq" / "repo-contract.json").read_text(encoding="utf-8")
    )

    assert (
        '"schemas/feedback_candidate.schema.json" = '
        '"mq_agent/schemas/feedback_candidate.schema.json"'
    ) in pyproject
    assert "mq.feedback-candidate.v1" in contract["contracts"]

    candidate = {
        "schema": "mq.feedback-candidate.v1",
        "candidate_id": "cand-no-activation",
        "fingerprint": "d" * 64,
        "kind": "context-strategy",
        "task_class": "repo-review",
        "current_strategy": "context-pack-v1",
        "proposed_strategy": "context-pack-v2",
        "comparison_ids": ["cmp-1"],
        "evidence_window": {
            "from": "2026-10-01T08:00:00Z",
            "to": "2026-10-01T08:01:00Z",
        },
        "rationale": "proposal only",
        "gains": [],
        "regressions": [],
        "limitations": ["human review required"],
        "rollback_target": "context-pack-v1",
        "state": "activated",
        "state_reason": None,
        "supersedes": [],
        "recorded_at": "2026-10-01T08:02:00Z",
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(candidate)
