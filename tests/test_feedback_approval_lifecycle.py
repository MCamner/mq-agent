from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.feedback import append_comparison
from mq_agent.feedback.approvals import (
    approval_status,
    require_valid_approval,
    revoke_approval,
)
from mq_agent.feedback.canary import create_canary_plan, run_canary
from mq_agent.feedback.candidates import maybe_create_candidate
from mq_agent.feedback.contracts import validate_approval_revocation
from mq_agent.feedback.control import (
    activate,
    approval_receipt,
    effective_strategy,
    validate_canary,
)
from mq_agent.feedback.promotion import promotion_approve
from mq_agent.feedback.readiness import activation_readiness
from mq_agent.main import app
from tests.test_feedback_canary_v2 import (
    BASELINE,
    CANARY_EXECUTION_IDS,
    CANDIDATE,
    _comparison,
    _mock_execution,
    _ready_candidate,
    _seed_real_run,
)

runner = CliRunner()


def _approvals(root: Path) -> list[dict]:
    path = root / "approvals.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _rewrite_approvals(root: Path, rows: list[dict]) -> None:
    (root / "approvals.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _legacy_v1(record: dict, approval_id: str) -> dict:
    legacy = dict(record)
    legacy["schema"] = "mq.feedback-approval.v1"
    legacy["approval_id"] = approval_id
    legacy.pop("evidence_snapshots")
    return legacy


def test_approval_status_valid(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    before = (tmp_path / "approvals.jsonl").read_bytes()

    status = approval_status(approval["approval_id"], tmp_path)

    assert status["status"] == "VALID"
    assert status["reason"] is None
    assert status["checks"] == {
        "resolved": True,
        "revoked": False,
        "expired": False,
        "candidate_match": True,
        "readiness_match": True,
        "commit_match": True,
        "policy_match": True,
    }
    assert status["read_only"] is True
    assert status["activation_available"] is False
    assert (tmp_path / "approvals.jsonl").read_bytes() == before
    assert not (tmp_path / "approval-revocations.jsonl").exists()


def test_approval_status_expired(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    later = datetime.now(UTC) + timedelta(hours=25)
    monkeypatch.setattr("mq_agent.feedback.approvals._now", lambda: later)

    status = approval_status(approval["approval_id"], tmp_path)

    assert status["status"] == "EXPIRED"
    assert status["checks"]["expired"] is True
    with pytest.raises(ValueError, match="approval receipt has expired"):
        require_valid_approval(candidate_id, approval["approval_id"], tmp_path)


def test_approval_status_stale_readiness(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    _seed_real_run(
        tmp_path,
        tmp_path / "execution-outcomes.jsonl",
        feedback_run_id="fb-new-population",
        execution_run_id="exec-new-population",
        recorded_at="2026-10-05T10:00:00Z",
        commit="f" * 40,
    )

    status = approval_status(approval["approval_id"], tmp_path)

    assert status["status"] == "STALE_READINESS"
    assert "readiness evidence changed" in status["reason"]


def test_approval_status_stale_policy(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    monkeypatch.setattr(
        "mq_agent.feedback.control.effective_strategy",
        lambda *_args, **_kwargs: CANDIDATE,
    )

    status = approval_status(approval["approval_id"], tmp_path)

    assert status["status"] == "STALE_POLICY"
    assert status["checks"]["policy_match"] is False
    with pytest.raises(ValueError, match="effective policy no longer matches"):
        create_canary_plan(
            candidate_id,
            approval_id=approval["approval_id"],
            root=tmp_path,
        )


def test_approval_v2_binds_repo_commit(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    readiness = activation_readiness(candidate_id, tmp_path)

    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)

    assert approval["schema"] == "mq.feedback-approval.v2"
    assert approval["evidence_snapshots"] == readiness["evidence"]["snapshots"]
    assert approval["evidence_snapshots"] == [
        "MCamner/mq-agent@" + "a" * 40,
        "MCamner/mq-agent@" + "b" * 40,
        "MCamner/mq-agent@" + "c" * 40,
    ]
    assert _approvals(tmp_path) == [approval]


def test_approval_commit_mismatch_is_invalid(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    rows = _approvals(tmp_path)
    rows[0]["evidence_snapshots"][0] = "MCamner/mq-agent@" + "9" * 40
    _rewrite_approvals(tmp_path, rows)

    status = approval_status(approval["approval_id"], tmp_path)

    assert status["status"] == "COMMIT_MISMATCH"
    assert status["checks"]["commit_match"] is False
    with pytest.raises(ValueError, match="repo/commit binding"):
        create_canary_plan(
            candidate_id,
            approval_id=approval["approval_id"],
            root=tmp_path,
        )


def test_approval_revoke_is_append_only(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    before = (tmp_path / "approvals.jsonl").read_bytes()

    revocation = revoke_approval(
        approval["approval_id"],
        reason="operator withdrew approval",
        root=tmp_path,
    )

    assert (tmp_path / "approvals.jsonl").read_bytes() == before
    validate_approval_revocation(revocation)
    assert revocation["schema"] == "mq.feedback-approval-revocation.v1"
    assert revocation["approval_id"] == approval["approval_id"]
    assert revocation["reason"] == "operator withdrew approval"
    stored = (tmp_path / "approval-revocations.jsonl").read_text(encoding="utf-8")
    assert [json.loads(line) for line in stored.splitlines()] == [revocation]


def test_duplicate_revoke_fails_closed(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    revoke_approval(approval["approval_id"], reason="first", root=tmp_path)
    before = (tmp_path / "approval-revocations.jsonl").read_bytes()

    with pytest.raises(ValueError, match="already revoked"):
        revoke_approval(approval["approval_id"], reason="second", root=tmp_path)
    with pytest.raises(ValueError, match="exactly one receipt"):
        revoke_approval("approval-unknown-12345678", reason="x", root=tmp_path)

    assert (tmp_path / "approval-revocations.jsonl").read_bytes() == before


def test_revoked_approval_status_is_revoked(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    revoke_approval(approval["approval_id"], reason="withdrawn", root=tmp_path)

    status = approval_status(approval["approval_id"], tmp_path)

    assert status["status"] == "REVOKED"
    assert status["checks"]["revoked"] is True
    assert status["revocation"]["reason"] == "withdrawn"


def test_revoked_approval_cannot_create_canary_plan(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    revoke_approval(approval["approval_id"], reason="withdrawn", root=tmp_path)

    with pytest.raises(ValueError, match="revoked"):
        create_canary_plan(
            candidate_id,
            approval_id=approval["approval_id"],
            root=tmp_path,
        )
    assert not (tmp_path / "canaries.jsonl").exists()


def test_revoked_approval_cannot_check_legacy_canary(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    comparison = _comparison(
        "cmp-after-approval",
        commit="d" * 40,
        recorded_at="2099-01-01T00:00:00Z",
    )
    append_comparison(comparison, tmp_path)
    revoke_approval(approval["approval_id"], reason="withdrawn", root=tmp_path)

    with pytest.raises(ValueError, match="revoked"):
        validate_canary(
            candidate_id,
            approval["approval_id"],
            "cmp-after-approval",
            root=tmp_path,
        )


def test_revoked_approval_cannot_activate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MQ_FEEDBACK_ACTIVATION", "on")
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        root=tmp_path,
    )
    _mock_execution(monkeypatch, ["CANDIDATE_BETTER"] * 3)
    result = run_canary(
        plan["canary_id"],
        task="review release boundaries",
        fixture_path=tmp_path / "fixture.json",
        execution_run_ids=CANARY_EXECUTION_IDS,
        root=tmp_path,
    )
    assert result["verdict"] == "PASS"
    promotion = promotion_approve(
        candidate_id, canary_id=plan["canary_id"], reason="promoted", root=tmp_path
    )
    revoke_approval(approval["approval_id"], reason="withdrawn", root=tmp_path)

    with pytest.raises(ValueError, match="revoked"):
        activate(
            candidate_id,
            approval_id=approval["approval_id"],
            promotion_approval_id=promotion["promotion_approval_id"],
            canary_id=plan["canary_id"],
            reason="canary passed",
            root=tmp_path,
        )
    assert effective_strategy("repo-review", tmp_path) == BASELINE


def test_old_approval_record_is_not_rewritten(tmp_path: Path, monkeypatch) -> None:
    candidate_id = _ready_candidate(tmp_path, monkeypatch)
    current = approval_receipt(candidate_id, reason="approved", root=tmp_path)
    legacy = _legacy_v1(current, "approval-legacy-v1-0001")
    _rewrite_approvals(tmp_path, [legacy])
    legacy_bytes = (tmp_path / "approvals.jsonl").read_bytes()

    fresh = approval_receipt(candidate_id, reason="re-approved", root=tmp_path)
    revoke_approval(fresh["approval_id"], reason="withdrawn", root=tmp_path)

    assert (tmp_path / "approvals.jsonl").read_bytes().startswith(legacy_bytes)
    assert _approvals(tmp_path)[0] == legacy
    status = approval_status(legacy["approval_id"], tmp_path)
    assert status["status"] == "INVALID"
    assert "predates repo/commit binding" in status["reason"]
    with pytest.raises(ValueError, match="predates repo/commit binding"):
        create_canary_plan(
            candidate_id,
            approval_id=legacy["approval_id"],
            root=tmp_path,
        )


def test_unknown_approval_status_is_invalid(tmp_path: Path) -> None:
    status = approval_status("approval-unknown-12345678", tmp_path)

    assert status["status"] == "INVALID"
    assert status["checks"]["resolved"] is False


def test_approve_still_requires_ready_for_human_approval(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "execution-outcomes.jsonl")
    )
    comparison = _comparison("cmp-only", commit="a" * 40)
    append_comparison(comparison, tmp_path)
    candidate, _ = maybe_create_candidate(comparison, state_root=tmp_path)
    assert candidate is not None
    readiness = activation_readiness(candidate["candidate_id"], tmp_path)
    assert readiness["status"] != "READY_FOR_HUMAN_APPROVAL"

    with pytest.raises(ValueError, match="not ready for approval"):
        approval_receipt(candidate["candidate_id"], reason="approved", root=tmp_path)
    assert not (tmp_path / "approvals.jsonl").exists()


def test_approval_status_and_revoke_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "feedback"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(root))
    candidate_id = _ready_candidate(root, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=root)

    valid = runner.invoke(
        app, ["feedback", "approval-status", approval["approval_id"], "--json"]
    )
    assert valid.exit_code == 0, valid.output
    assert json.loads(valid.output)["status"] == "VALID"

    revoked = runner.invoke(
        app,
        [
            "feedback",
            "approval-revoke",
            approval["approval_id"],
            "--reason",
            "withdrawn",
            "--json",
        ],
    )
    assert revoked.exit_code == 0, revoked.output
    assert json.loads(revoked.output)["approval_id"] == approval["approval_id"]

    after = runner.invoke(
        app, ["feedback", "approval-status", approval["approval_id"], "--json"]
    )
    assert after.exit_code == 1
    assert json.loads(after.output)["status"] == "REVOKED"

    unknown = runner.invoke(
        app, ["feedback", "approval-status", "approval-unknown-12345678", "--json"]
    )
    assert unknown.exit_code == 2
    assert json.loads(unknown.output)["status"] == "INVALID"
