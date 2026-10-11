from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.feedback.approvals import revoke_approval
from mq_agent.feedback.canary import (
    _plan_basis,
    _sha256,
    canary_preflight,
    canary_status,
    create_canary_plan,
    run_canary,
)
from mq_agent.feedback.control import approval_receipt
from mq_agent.main import app
from tests.test_feedback_canary_v2 import CANDIDATE, _mock_execution, _ready_candidate

runner = CliRunner()


def _planned(root: Path, monkeypatch) -> tuple[str, dict, dict]:
    candidate_id = _ready_candidate(root, monkeypatch)
    approval = approval_receipt(candidate_id, reason="approved", root=root)
    plan = create_canary_plan(
        candidate_id,
        approval_id=approval["approval_id"],
        root=root,
    )
    return candidate_id, approval, plan


def _store_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(root.iterdir())
        if path.is_file() and path.suffix == ".jsonl"
    }


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_preflight_ready_is_read_only_and_not_started(
    tmp_path: Path, monkeypatch
) -> None:
    _candidate_id, approval, plan = _planned(tmp_path, monkeypatch)
    before = _store_bytes(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("preflight must not execute an experiment")

    monkeypatch.setattr("mq_agent.feedback.canary.run_context_experiment", forbidden)
    monkeypatch.setattr("mq_agent.feedback.canary.compare_feedback_run", forbidden)

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "CANARY_READY"
    assert result["reason"] is None
    assert result["approval_id"] == approval["approval_id"]
    assert result["approval_status"] == "VALID"
    assert result["plan_sha256"] == plan["plan_sha256"]
    assert all(result["checks"].values())
    assert result["runtime_effect"] is False
    assert result["canary_started"] is False
    assert result["read_only"] is True
    assert _store_bytes(tmp_path) == before
    assert canary_status(plan["canary_id"], tmp_path)["state"] == "PLANNED"


def test_preflight_blocks_completed_canary(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    _mock_execution(monkeypatch, ["CANDIDATE_BETTER"] * 3)
    run_canary(
        plan["canary_id"],
        task="review release boundaries",
        fixture_path=tmp_path / "fixture.json",
        root=tmp_path,
    )

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_CANARY_ALREADY_COMPLETED"
    assert result["checks"]["no_result"] is False


def test_preflight_blocks_revoked_approval(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, approval, plan = _planned(tmp_path, monkeypatch)
    revoke_approval(approval["approval_id"], reason="withdrawn", root=tmp_path)

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_APPROVAL"
    assert result["approval_status"] == "REVOKED"
    assert "revoked" in result["reason"]


def test_preflight_blocks_stale_policy(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "mq_agent.feedback.control.effective_strategy",
        lambda *_args, **_kwargs: CANDIDATE,
    )

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_STALE_POLICY"
    assert result["approval_status"] == "STALE_POLICY"


def test_preflight_blocks_stale_policy_snapshot(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    drifted = dict(plan["policy_snapshot"], event_count=1, last_event_id="policy-x")
    monkeypatch.setattr(
        "mq_agent.feedback.canary._policy_snapshot",
        lambda *_args, **_kwargs: drifted,
    )

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_STALE_POLICY"
    assert result["approval_status"] == "VALID"
    assert "policy snapshot is stale" in result["reason"]


def test_preflight_blocks_commit_mismatch(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    path = tmp_path / "approvals.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["evidence_snapshots"][0] = "MCamner/mq-agent@" + "9" * 40
    _rewrite_jsonl(path, rows)

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_COMMIT_MISMATCH"
    assert result["approval_status"] == "COMMIT_MISMATCH"


def test_preflight_blocks_tampered_plan(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    path = tmp_path / "canaries.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["plan"]["execution_budget"] = 20
    _rewrite_jsonl(path, rows)

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_PLAN_MISMATCH"
    assert "hash mismatch" in result["reason"]
    assert result["runtime_effect"] is False


def test_preflight_blocks_unknown_canary(tmp_path: Path) -> None:
    result = canary_preflight("canary-unknown", tmp_path)

    assert result["status"] == "BLOCKED_PLAN_MISMATCH"
    assert result["checks"]["plan_resolved"] is False


def test_preflight_blocks_unbounded_budget(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    path = tmp_path / "canaries.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["plan"]["min_executions"] = rows[0]["plan"]["execution_budget"] + 1
    rows[0]["plan_sha256"] = _sha256(_plan_basis(rows[0]))
    _rewrite_jsonl(path, rows)

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_BUDGET"


def test_preflight_blocks_missing_rollback(tmp_path: Path, monkeypatch) -> None:
    _candidate_id, _approval, plan = _planned(tmp_path, monkeypatch)
    monkeypatch.setattr("mq_agent.feedback.control.STRATEGY_CODEGRAPH", {})

    result = canary_preflight(plan["canary_id"], tmp_path)

    assert result["status"] == "BLOCKED_NO_ROLLBACK"
    assert result["checks"]["rollback_available"] is False


def test_canary_preflight_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "feedback"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(root))
    _candidate_id, approval, plan = _planned(root, monkeypatch)

    ready = runner.invoke(
        app, ["feedback", "canary-preflight", plan["canary_id"], "--json"]
    )
    assert ready.exit_code == 0, ready.output
    assert json.loads(ready.output)["status"] == "CANARY_READY"

    revoke_approval(approval["approval_id"], reason="withdrawn", root=root)
    blocked = runner.invoke(
        app, ["feedback", "canary-preflight", plan["canary_id"], "--json"]
    )
    assert blocked.exit_code == 1
    assert json.loads(blocked.output)["status"] == "BLOCKED_APPROVAL"
