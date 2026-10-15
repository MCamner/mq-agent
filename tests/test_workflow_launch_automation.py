"""Regression gates for target binding, bounded selection and truthful receipts."""

import subprocess
from typing import Any

import pytest
from typer.testing import CliRunner

from mq_agent.workflows.cli import workflow_app
from mq_agent.workflows.models import StepStatus, WorkflowStatus
from mq_agent.workflows.state import new_run
from mq_agent.workflows.templates import instantiate


def git_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "initial",
        ],
        check=True,
    )
    return path


def test_target_canonicalizes_subdirectory_and_binds_commit(tmp_path):
    from mq_agent.workflows.target import bind_target, verify_target

    root = git_repo(tmp_path / "target")
    sub = root / "sub"
    sub.mkdir()
    run = new_run(instantiate("review-and-test", str(sub), "target-run"))
    bind_target(run)
    assert run.plan.repo == str(root.resolve())
    assert len((run.repo_identity or {})["commit"]) == 40
    verify_target(run)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "changed",
        ],
        check=True,
    )
    with pytest.raises(ValueError, match="changed"):
        verify_target(run)


def test_selection_is_deterministic_and_unknown_fails():
    from mq_agent.workflows.selection import select_task, SelectionError

    assert select_task("granska ändringarna").template == "review-and-test"
    assert select_task("granska ändringarna") == select_task("GRANSKA ÄNDRINGARNA")
    assert select_task("felsök repot").template == "repo-preflight"
    assert select_task("förbered release").template == "release-ready"
    for task in [
        "deploy everything",
        "review and release",
        "granska ändringarna; rm -rf /",
    ]:
        with pytest.raises(SelectionError):
            select_task(task)


def test_do_plan_uses_bound_target_and_does_not_save(tmp_path, monkeypatch):
    root = git_repo(tmp_path / "target")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    result = CliRunner().invoke(
        workflow_app,
        ["do", "granska ändringarna", "--repo", str(root), "--plan", "--json"],
    )
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert report["plan"]["repo"] == str(root)
    assert report["selection"]["template"] == "review-and-test"
    assert not (tmp_path / "state").exists()


def test_receipt_cannot_pass_skipped_or_partial_work():
    from mq_agent.workflows.receipt import build_receipt

    run = new_run(instantiate("review-and-test", "/tmp/target", "partial-run"))
    run.plan.status = WorkflowStatus.COMPLETED
    for step in run.plan.steps:
        step.status = StepStatus.PASSED
        step.result = {"ok": True, "data": {}}
    run.plan.steps[1].status = StepStatus.SKIPPED
    receipt = build_receipt(run)
    assert receipt["ok"] is False
    assert receipt["completeness"]["status"] == "partial"
    assert receipt["recording"]["execution_outcome"] is None
    run.plan.steps[1].status = StepStatus.PASSED
    run.plan.steps[1].result = {
        "ok": True,
        "data": {"completeness": {"status": "partial", "coverage": 0.2}},
    }
    assert build_receipt(run)["ok"] is False


def test_receipt_preserves_unknown_and_only_observed_execution_links():
    from mq_agent.workflows.receipt import build_receipt

    run = new_run(instantiate("review-and-test", "/tmp/target", "unknown-run"))
    rec = build_receipt(run)
    assert rec["verification"]["status"] == "unknown"
    assert all(s["execution_run_id"] is None for s in rec["steps"])
    run.plan.steps[0].result = {
        "ok": True,
        "data": {"execution_run_id": "actual-id", "execution_outcome_recorded": False},
    }
    rec = build_receipt(run)
    assert rec["steps"][0]["execution_run_id"] == "actual-id"
    assert rec["steps"][0]["execution_outcome_recorded"] is False


def test_unknown_and_partial_tool_results_never_pass():
    from mq_agent.workflows.evaluator import normalize_result

    assert normalize_result({})["ok"] is False
    assert normalize_result(None)["ok"] is False
    assert normalize_result([{"type": "text", "text": ""}])["ok"] is False
    assert (
        normalize_result(
            [
                {
                    "type": "text",
                    "text": '{"status":"LIMITED","coverage":{"complete":false}}',
                }
            ]
        )["ok"]
        is False
    )


def test_storage_failure_prevents_receipt_pass():
    from mq_agent.workflows.receipt import build_receipt

    run = new_run(instantiate("review-and-test", "/tmp/target", "storage-run"))
    run.plan.status = WorkflowStatus.COMPLETED
    for step in run.plan.steps:
        step.status = StepStatus.PASSED
        step.result = {"ok": True, "data": {}}
    run.recording["workflow_state"] = False
    assert build_receipt(run)["ok"] is False


def test_unknown_review_verification_is_separate_from_complete_coverage():
    from mq_agent.workflows.receipt import build_receipt

    run = new_run(instantiate("review-and-test", "/tmp/target", "verification-run"))
    run.plan.status = WorkflowStatus.COMPLETED
    for step in run.plan.steps:
        step.status = StepStatus.PASSED
        step.result = {"ok": True, "data": {}}
    run.plan.steps[1].result = {
        "ok": True,
        "data": {"coverage": {"complete": True}, "verification": "unknown"},
    }
    receipt = build_receipt(run)
    assert receipt["completeness"]["status"] == "complete"
    assert receipt["verification"]["status"] == "unknown"
    assert receipt["ok"] is False


def test_observation_does_not_claim_policy_denied_tool_executed():
    from mq_agent.workflows.observation import build_observation

    run = new_run(instantiate("review-and-test", "/tmp/target", "denied-run"))
    run.plan.status = WorkflowStatus.FAILED
    run.plan.steps[0].status = StepStatus.FAILED
    rec = build_observation(run)
    assert rec["tool_sequence"] == []
    assert rec["outcome"] == "failed"


def test_bound_runner_rejects_other_repo_and_does_not_continue(tmp_path):
    from mq_agent.workflows.runner import Runner
    from mq_agent.workflows.policy import PolicyProvider
    from mq_agent.workflows.storage import WorkflowStore
    from mq_agent.workflows.target import bind_target

    root = git_repo(tmp_path / "target")
    run = new_run(instantiate("review-and-test", str(root), "wrong-target"))
    bind_target(run)
    calls = []

    def execute(tool, args, repo):
        calls.append(tool)
        return {
            "status": "PASS",
            "repo_path": "/server/b",
            "git_commit": (run.repo_identity or {})["commit"],
        }

    policy = PolicyProvider(
        fetcher=lambda: [
            {
                "name": s.tool,
                "workflow_allowed": True,
                "approval": "none",
                "retry_safe": True,
            }
            for s in run.plan.steps
        ]
    )
    Runner(WorkflowStore(tmp_path / "state"), execute, policy_provider=policy).run(run)
    assert calls == ["git_diff"]
    assert (run.summary or {})["ok"] is False
    assert run.plan.steps[0].error == "tool did not confirm the bound root and commit"


def test_advisory_review_failure_still_runs_tests(tmp_path):
    from mq_agent.workflows.runner import Runner
    from mq_agent.workflows.policy import PolicyProvider
    from mq_agent.workflows.storage import WorkflowStore

    run = new_run(instantiate("review-and-test", "/tmp/fixture-target", "advisory-run"))
    calls = []

    def execute(tool, args, repo):
        calls.append(tool)
        return {"ok": tool != "review_diff"}

    policy = PolicyProvider(
        fetcher=lambda: [
            {
                "name": s.tool,
                "workflow_allowed": True,
                "approval": "none",
                "retry_safe": True,
            }
            for s in run.plan.steps
        ]
    )
    Runner(WorkflowStore(tmp_path / "state"), execute, policy_provider=policy).run(run)
    assert calls == ["git_diff", "review_diff", "run_tests"]
    assert (run.summary or {})["ok"] is False
    assert run.plan.steps[-1].status is StepStatus.PASSED


def test_changed_head_during_tool_is_rejected(tmp_path):
    from mq_agent.workflows.runner import Runner
    from mq_agent.workflows.policy import PolicyProvider
    from mq_agent.workflows.storage import WorkflowStore
    from mq_agent.workflows.target import bind_target

    root = git_repo(tmp_path / "target")
    run = new_run(instantiate("review-and-test", str(root), "drift-run"))
    bind_target(run)

    def execute(tool, args, repo):
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                "concurrent",
            ],
            check=True,
        )
        return {
            "status": "PASS",
            "repo_path": str(root),
            "git_commit": (run.repo_identity or {})["commit"],
        }

    policy = PolicyProvider(
        fetcher=lambda: [
            {
                "name": s.tool,
                "workflow_allowed": True,
                "approval": "none",
                "retry_safe": True,
            }
            for s in run.plan.steps
        ]
    )
    Runner(WorkflowStore(tmp_path / "state"), execute, policy_provider=policy).run(run)
    assert (run.summary or {})["ok"] is False
    assert run.plan.steps[0].status is StepStatus.FAILED


def test_observer_exposes_failed_recording_with_direct_execution_id(monkeypatch):
    from mq_agent.workflows.cli import _default_observer
    from mq_agent.workflows import cli

    monkeypatch.delenv("MQ_WORKFLOW_OBSERVE", raising=False)
    observed = []

    def not_recorded(**fields):
        observed.append(fields)
        return None

    monkeypatch.setattr(
        "mq_agent.tools.execution_outcome.emit_execution_outcome", not_recorded
    )
    monkeypatch.setattr(cli, "emit_observation", lambda *args, **kwargs: None)
    run = new_run(
        instantiate("review-and-test", "/tmp/fixture-target", "recording-fixture")
    )
    run.plan.status = WorkflowStatus.FAILED
    run.plan.steps[0].status = StepStatus.FAILED
    run.plan.steps[0].attempt = 1
    _default_observer()(run, {"duration_ms": 1, "approval_count": 1})
    assert observed[0]["run_id"] == run.execution_run_id
    assert observed[0]["result"] == "FAIL"
    assert run.recording["execution_outcome"] is False
    assert run.recording["observation"] is False


def test_partial_observation_and_receipt_agree():
    from mq_agent.workflows.observation import build_observation
    from mq_agent.workflows.receipt import build_receipt

    run = new_run(
        instantiate("review-and-test", "/tmp/fixture-target", "partial-fixture")
    )
    run.plan.status = WorkflowStatus.COMPLETED
    run.plan.steps[0].status = StepStatus.PASSED
    run.plan.steps[0].attempt = 1
    run.plan.steps[1].status = StepStatus.SKIPPED
    run.plan.steps[2].status = StepStatus.SKIPPED
    assert build_receipt(run)["ok"] is False
    record = build_observation(run)
    assert record["outcome"] == "failed"
    assert "completeness:partial" in record["tags"]
    assert record["tool_sequence"] == ["git_diff"]


def test_exact_completed_mcp_shape_preserves_unknown_verification():
    from mq_agent.workflows.evaluator import normalize_result
    from mq_agent.workflows.receipt import build_receipt

    raw = {
        "status": "COMPLETED",
        "repo_path": "/tmp/fixture-target",
        "git_commit": "a" * 40,
        "verification": "unknown",
        "coverage": {
            "changed_files": 1,
            "eligible_files": 1,
            "reviewed_files": 1,
            "complete": True,
        },
        "results": [],
    }
    normalized = normalize_result(raw)
    assert normalized["ok"] is True
    run = new_run(
        instantiate("review-and-test", "/tmp/fixture-target", "producer-shape")
    )
    run.plan.status = WorkflowStatus.COMPLETED
    for step in run.plan.steps:
        step.status = StepStatus.PASSED
        step.result = {"ok": True, "data": {}}
    run.plan.steps[1].result = normalized
    receipt = build_receipt(run)
    assert receipt["verification"]["status"] == "unknown"
    assert receipt["ok"] is False


def test_unknown_result_is_failed_execution_but_unknown_verification():
    from mq_agent.workflows.evaluator import normalize_result
    from mq_agent.workflows.receipt import build_receipt

    run = new_run(
        instantiate("review-and-test", "/tmp/fixture-target", "unknown-shape")
    )
    raw: Any
    for raw in ({}, None, [{"type": "text", "text": "Unrecognized result"}]):
        result = normalize_result(raw)
        assert result["ok"] is False
        run.plan.steps[0].status = StepStatus.FAILED
        run.plan.steps[0].result = result
        assert build_receipt(run)["verification"]["status"] == "unknown"
