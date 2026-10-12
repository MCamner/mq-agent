from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.feedback.approvals import revoke_approval
from mq_agent.feedback.canary import _sha256, create_canary_plan, run_canary
from mq_agent.feedback.contracts import validate_policy_event
from mq_agent.feedback.control import (
    activate,
    approval_receipt,
    effective_strategy,
    rollback,
)
from mq_agent.feedback.promotion import promotion_approve, promotion_status
from mq_agent.main import app
from tests.test_feedback_canary_v2 import (
    BASELINE,
    CANDIDATE,
    _mock_execution,
    _ready_candidate,
)

runner = CliRunner()


def _canary(root: Path, monkeypatch, verdicts: list[str] | None = None):
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(root, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=root)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        root=root,
    )
    if verdicts is not None:
        _mock_execution(monkeypatch, verdicts)
        result = run_canary(
            plan["canary_id"],
            task="review release boundaries",
            fixture_path=root / "fixture.json",
            root=root,
        )
    else:
        result = None
    return candidate_id, approval, plan, result


def _passed(root: Path, monkeypatch):
    return _canary(root, monkeypatch, ["CANDIDATE_BETTER"] * 3)


def _activate(candidate_id: str, approval: dict, plan: dict, promotion: dict, root: Path):
    return activate(
        candidate_id,
        approval_id=approval["approval_id"],
        promotion_approval_id=promotion["promotion_approval_id"],
        canary_id=plan["canary_id"],
        reason="promotion approved",
        root=root,
    )


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_promotion_requires_canary_result(tmp_path: Path, monkeypatch) -> None:
    candidate_id, _approval, plan, _result = _canary(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="canary has no RESULT"):
        promotion_approve(
            candidate_id, canary_id=plan["canary_id"], reason="x", root=tmp_path
        )
    assert not (tmp_path / "promotion-approvals.jsonl").exists()


def test_promotion_requires_pass_verdict(tmp_path: Path, monkeypatch) -> None:
    candidate_id, _approval, plan, result = _canary(
        tmp_path, monkeypatch, ["CANDIDATE_WORSE"] * 3
    )
    assert result["verdict"] != "PASS"

    with pytest.raises(ValueError, match="verdict is not PASS"):
        promotion_approve(
            candidate_id, canary_id=plan["canary_id"], reason="x", root=tmp_path
        )
    assert not (tmp_path / "promotion-approvals.jsonl").exists()


def test_promotion_approval_binds_exact_canary_result(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_id, approval, plan, result = _passed(tmp_path, monkeypatch)

    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )

    assert promotion["schema"] == "mq.feedback-promotion-approval.v1"
    assert promotion["promotion_approval_id"].startswith("approval-promotion-")
    assert promotion["promotion_approval_id"] != approval["approval_id"]
    assert promotion["canary_approval_id"] == approval["approval_id"]
    assert promotion["candidate_id"] == candidate_id
    assert promotion["candidate_fingerprint"] == plan["candidate_fingerprint"]
    assert promotion["canary_id"] == plan["canary_id"]
    assert promotion["canary_result_fingerprint"] == _sha256(result)
    assert promotion["task_class"] == "repo-review"
    assert promotion["current_strategy"] == BASELINE
    assert promotion["proposed_strategy"] == CANDIDATE
    assert promotion["policy_snapshot"] == plan["policy_snapshot"]
    stored = (tmp_path / "promotion-approvals.jsonl").read_text(encoding="utf-8")
    assert [json.loads(line) for line in stored.splitlines()] == [promotion]


def test_promotion_status_valid_is_read_only(tmp_path: Path, monkeypatch) -> None:
    candidate_id, _approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.jsonl")}

    status = promotion_status(promotion["promotion_approval_id"], tmp_path)

    assert status["status"] == "VALID"
    assert status["checks"] == {
        "resolved": True,
        "revoked": False,
        "expired": False,
        "candidate_match": True,
        "policy_match": True,
        "canary_match": True,
    }
    assert status["read_only"] is True
    assert status["activation_available"] is False
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.jsonl")} == before
    assert effective_strategy("repo-review", tmp_path) == BASELINE


def test_promotion_status_expired_blocks_activation(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id,
        canary_id=plan["canary_id"],
        reason="reviewed",
        expires_hours=1,
        root=tmp_path,
    )
    later = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr("mq_agent.feedback.promotion._now", lambda: later)

    assert promotion_status(promotion["promotion_approval_id"], tmp_path)["status"] == "EXPIRED"
    with pytest.raises(ValueError, match="promotion approval has expired"):
        _activate(candidate_id, approval, plan, promotion, tmp_path)
    assert effective_strategy("repo-review", tmp_path) == BASELINE


def test_revoked_promotion_blocks_activation(tmp_path: Path, monkeypatch) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )
    before = (tmp_path / "promotion-approvals.jsonl").read_bytes()

    revoke_approval(promotion["promotion_approval_id"], reason="withdrawn", root=tmp_path)

    assert (tmp_path / "promotion-approvals.jsonl").read_bytes() == before
    status = promotion_status(promotion["promotion_approval_id"], tmp_path)
    assert status["status"] == "REVOKED"
    with pytest.raises(ValueError, match="revoked"):
        _activate(candidate_id, approval, plan, promotion, tmp_path)
    assert effective_strategy("repo-review", tmp_path) == BASELINE


def test_promotion_status_stale_policy(tmp_path: Path, monkeypatch) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )
    drifted = dict(plan["policy_snapshot"], event_count=1, last_event_id="policy-x")
    monkeypatch.setattr(
        "mq_agent.feedback.canary._policy_snapshot",
        lambda *_args, **_kwargs: drifted,
    )

    status = promotion_status(promotion["promotion_approval_id"], tmp_path)

    assert status["status"] == "STALE_POLICY"
    with pytest.raises(ValueError, match="policy snapshot"):
        _activate(candidate_id, approval, plan, promotion, tmp_path)


def test_promotion_status_stale_canary_result(tmp_path: Path, monkeypatch) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )
    path = tmp_path / "canaries.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    result_row = next(row for row in rows if row["record_type"] == "RESULT")
    result_row["metrics"]["latency_delta_ms"] = -50.0
    _rewrite_jsonl(path, rows)

    status = promotion_status(promotion["promotion_approval_id"], tmp_path)

    assert status["status"] == "STALE_CANARY"
    assert "canary RESULT changed" in status["reason"]
    with pytest.raises(ValueError, match="canary RESULT changed"):
        _activate(candidate_id, approval, plan, promotion, tmp_path)


def test_canary_approval_alone_cannot_activate(tmp_path: Path, monkeypatch) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="promotion approval"):
        activate(
            candidate_id,
            approval_id=approval["approval_id"],
            promotion_approval_id=approval["approval_id"],
            canary_id=plan["canary_id"],
            reason="reuse canary approval",
            root=tmp_path,
        )
    assert effective_strategy("repo-review", tmp_path) == BASELINE
    assert not (tmp_path / "policy-events.jsonl").exists()


def test_promotion_bound_to_another_canary_cannot_activate(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )
    other = create_canary_plan(
        candidate_id, approval_id=approval["approval_id"], root=tmp_path
    )

    with pytest.raises(ValueError, match="promotion approval is bound to another canary"):
        activate(
            candidate_id,
            approval_id=approval["approval_id"],
            promotion_approval_id=promotion["promotion_approval_id"],
            canary_id=other["canary_id"],
            reason="wrong canary",
            root=tmp_path,
        )


def test_activation_event_records_both_approvals(tmp_path: Path, monkeypatch) -> None:
    candidate_id, approval, plan, _result = _passed(tmp_path, monkeypatch)
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="reviewed", root=tmp_path
    )

    event = _activate(candidate_id, approval, plan, promotion, tmp_path)

    validate_policy_event(event)
    assert event["schema"] == "mq.feedback-policy-event.v2"
    assert event["canary_approval_id"] == approval["approval_id"]
    assert event["promotion_approval_id"] == promotion["promotion_approval_id"]
    assert "approval_id" not in event
    assert effective_strategy("repo-review", tmp_path) == CANDIDATE

    undone = rollback(event["event_id"], reason="regression", root=tmp_path)
    assert undone["schema"] == "mq.feedback-policy-event.v2"
    assert undone["canary_approval_id"] is None
    assert undone["promotion_approval_id"] is None
    assert effective_strategy("repo-review", tmp_path) == BASELINE


def test_promotion_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "feedback"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(root))
    candidate_id, approval, plan, _result = _passed(root, monkeypatch)

    refused = runner.invoke(
        app,
        [
            "feedback", "promotion-approve", candidate_id,
            "--canary-id", plan["canary_id"], "--reason", "reviewed", "--json",
        ],
    )
    assert refused.exit_code != 0
    assert not (root / "promotion-approvals.jsonl").exists()

    issued = runner.invoke(
        app,
        [
            "feedback", "promotion-approve", candidate_id,
            "--canary-id", plan["canary_id"], "--reason", "reviewed",
            "--approve", "--json",
        ],
    )
    assert issued.exit_code == 0, issued.output
    promotion_id = json.loads(issued.output)["promotion_approval_id"]

    status = runner.invoke(app, ["feedback", "promotion-status", promotion_id, "--json"])
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["status"] == "VALID"

    missing = runner.invoke(
        app,
        [
            "feedback", "activate", candidate_id,
            "--approval-id", approval["approval_id"],
            "--canary-id", plan["canary_id"],
            "--reason", "no promotion", "--approve", "--json",
        ],
    )
    assert missing.exit_code != 0
    assert effective_strategy("repo-review", root) == BASELINE

    activated = runner.invoke(
        app,
        [
            "feedback", "activate", candidate_id,
            "--approval-id", approval["approval_id"],
            "--promotion-approval-id", promotion_id,
            "--canary-id", plan["canary_id"],
            "--reason", "promotion approved", "--approve", "--json",
        ],
    )
    assert activated.exit_code == 0, activated.output
    assert json.loads(activated.output)["promotion_approval_id"] == promotion_id

    unknown = runner.invoke(
        app, ["feedback", "promotion-status", "approval-promotion-unknown", "--json"]
    )
    assert unknown.exit_code == 2
    assert json.loads(unknown.output)["status"] == "INVALID"
