from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.workflows.checkpoint import (
    MAX_TTL_HOURS,
    WorkflowCheckpointError,
    WorkflowCheckpointStore,
)
from mq_agent.workflows.models import StepStatus, WorkflowStatus
from mq_agent.workflows.state import new_run, resume
from mq_agent.workflows.storage import WorkflowStore
from mq_agent.workflows.templates import instantiate

runner = CliRunner()


def _failed_run(store: WorkflowStore, run_id: str = "run_20261008_001"):
    plan = instantiate(
        "repo-preflight",
        repo="/Users/example/private/mq-agent",
        run_id=run_id,
    )
    run = new_run(plan)
    run.plan.status = WorkflowStatus.FAILED
    run.plan.current_step = "selftest"
    run.plan.steps[0].status = StepStatus.PASSED
    run.plan.steps[0].attempt = 1
    run.plan.steps[0].result = {
        "summary": "doctor ok",
        "detail": "bounded result body that must not enter checkpoint",
    }
    run.plan.steps[1].status = StepStatus.FAILED
    run.plan.steps[1].attempt = 1
    run.plan.steps[1].error = "selftest failed"
    store.save_run(run)
    return run


def test_checkpoint_is_bounded_content_addressed_and_path_free(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)

    payload = checkpoints.create(
        run.run_id,
        owner="operator-1",
        ttl_hours=24,
        now=datetime(2026, 10, 8, tzinfo=UTC),
    )

    assert payload["schema"] == "mq.workflow-checkpoint.v1"
    assert payload["checkpoint_id"].startswith("sha256:")
    assert payload["run"]["run_fingerprint"].startswith("sha256:")
    assert payload["run"]["template_fingerprint"].startswith("sha256:")
    assert payload["run"]["repo_name"] == "mq-agent"
    assert payload["run"]["passed_steps"] == ["doctor"]
    assert payload["run"]["resumable_steps"] == ["selftest", "release_check"]

    raw = checkpoints._path(payload["checkpoint_id"]).read_text(encoding="utf-8")
    assert "/Users/" not in raw
    assert "Verify repository readiness" not in raw
    assert "doctor ok" not in raw
    assert "bounded result body" not in raw
    assert '"args"' not in raw
    assert '"result"' not in raw


def test_checkpoint_owner_mismatch_refuses_resume(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="owner-a")

    report = checkpoints.verify(payload["checkpoint_id"], owner="owner-b")

    assert report["status"] == "REFUSED"
    assert "owner mismatch" in report["errors"]
    with pytest.raises(WorkflowCheckpointError, match="owner mismatch"):
        checkpoints.prepare_resume(payload["checkpoint_id"], owner="owner-b")


def test_checkpoint_expiry_fails_closed(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    created = datetime(2026, 10, 8, tzinfo=UTC)
    payload = checkpoints.create(
        run.run_id,
        owner="operator",
        ttl_hours=1,
        now=created,
    )

    report = checkpoints.verify(
        payload["checkpoint_id"],
        owner="operator",
        now=created + timedelta(hours=1),
    )

    assert report["status"] == "REFUSED"
    assert "checkpoint expired" in report["errors"]


def test_checkpoint_tamper_is_detected(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="operator")
    path = checkpoints._path(payload["checkpoint_id"])
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["expires_at"] = "2099-01-01T00:00:00Z"
    path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(WorkflowCheckpointError, match="fingerprint mismatch"):
        checkpoints.load(payload["checkpoint_id"])


def test_run_drift_invalidates_checkpoint(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="operator")

    run.summary = {"status": "failed", "note": "state changed"}
    store.save_run(run)
    report = checkpoints.verify(payload["checkpoint_id"], owner="operator")

    assert report["status"] == "REFUSED"
    assert "workflow run changed since checkpoint creation" in report["errors"]


def test_template_drift_invalidates_checkpoint(tmp_path, monkeypatch) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="operator")

    monkeypatch.setattr(
        "mq_agent.workflows.checkpoint.template_fingerprint",
        lambda template: "sha256:" + ("f" * 64),
    )
    report = checkpoints.verify(payload["checkpoint_id"], owner="operator")

    assert report["status"] == "REFUSED"
    assert "workflow template changed since checkpoint creation" in report["errors"]


def test_checkpoint_becomes_stale_before_execution_on_first_resume(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="operator")

    _payload, prepared = checkpoints.prepare_resume(
        payload["checkpoint_id"],
        owner="operator",
    )
    resume(prepared)
    store.save_run(prepared)

    report = checkpoints.verify(payload["checkpoint_id"], owner="operator")
    assert report["status"] == "REFUSED"
    assert "workflow run changed since checkpoint creation" in report["errors"]


def test_checkpoint_creation_requires_resumable_run(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    plan = instantiate("repo-preflight", repo="/tmp/repo", run_id="run_20261008_001")
    run = new_run(plan)
    store.save_run(run)

    with pytest.raises(WorkflowCheckpointError, match="paused or failed"):
        WorkflowCheckpointStore(store).create(run.run_id, owner="operator")


def test_checkpoint_ttl_is_bounded(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)

    with pytest.raises(WorkflowCheckpointError, match="ttl_hours"):
        WorkflowCheckpointStore(store).create(
            run.run_id,
            owner="operator",
            ttl_hours=MAX_TTL_HOURS + 1,
        )


def test_checkpoint_status_ready(tmp_path) -> None:
    store = WorkflowStore(base_dir=tmp_path / "workflows")
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="operator")

    report = checkpoints.verify(payload["checkpoint_id"], owner="operator")

    assert report["status"] == "READY"
    assert report["run_id"] == run.run_id
    assert report["current_step"] == "selftest"


def test_checkpoint_cli_dry_run_does_not_change_run(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    store = WorkflowStore()
    run = _failed_run(store)
    checkpoints = WorkflowCheckpointStore(store)
    payload = checkpoints.create(run.run_id, owner="operator")
    before = store.run_fingerprint(run.run_id)

    result = runner.invoke(
        app,
        [
            "workflow",
            "checkpoint",
            "resume",
            payload["checkpoint_id"],
            "--owner",
            "operator",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["status"] == "READY"
    assert body["action"] == "WOULD_RESUME"
    assert body["would_execute_steps"] == ["selftest", "release_check"]
    assert store.run_fingerprint(run.run_id) == before


def test_checkpoint_cli_execution_requires_explicit_approval(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    store = WorkflowStore()
    run = _failed_run(store)
    payload = WorkflowCheckpointStore(store).create(run.run_id, owner="operator")

    result = runner.invoke(
        app,
        [
            "workflow",
            "checkpoint",
            "resume",
            payload["checkpoint_id"],
            "--owner",
            "operator",
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "approve" in result.output
