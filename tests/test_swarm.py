"""Tests for swarm coordinator, registry, and CLI commands."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mq_agent.agents.swarm_registry import (
    SWARM_AUDIT,
    SWARM_CI,
    SWARM_RELEASE_CHECK,
    get_swarm,
    list_swarms,
)
from mq_agent.core.swarm import AgentManifest, AgentResult, SwarmConfig, SwarmResult, SwarmRunner
from mq_agent.main import app

runner = CliRunner()


# ── AgentManifest ──────────────────────────────────────────────────────────

def test_agent_manifest_to_dict():
    m = AgentManifest(
        name="audit",
        purpose="Read-only audit",
        safety_class="read-only",
        allowed_tools=["git_status", "read_file"],
        requires_approve=False,
        output_contract=["summary", "passed"],
        failure_behavior="warn",
    )
    d = m.to_dict()
    assert d["name"] == "audit"
    assert d["safety_class"] == "read-only"
    assert d["requires_approve"] is False
    assert "git_status" in d["allowed_tools"]


def test_agent_manifest_defaults():
    m = AgentManifest(name="x", purpose="p", safety_class="read-only", allowed_tools=[])
    assert m.requires_approve is False
    assert m.failure_behavior == "warn"
    assert m.output_contract == []


# ── SwarmConfig ────────────────────────────────────────────────────────────

def test_swarm_config_agent_names():
    assert SWARM_AUDIT.agent_names == ["audit", "signal", "docs"]


def test_swarm_config_requires_approve_false_for_audit():
    assert SWARM_AUDIT.requires_approve is False


def test_swarm_config_requires_approve_true_for_release():
    assert SWARM_RELEASE_CHECK.requires_approve is True


def test_swarm_config_to_dict():
    d = SWARM_AUDIT.to_dict()
    assert d["name"] == "audit"
    assert len(d["agents"]) == 3
    assert d["agents"][0]["name"] == "audit"


def test_swarm_config_safety_classes_audit():
    assert "read-only" in SWARM_AUDIT.safety_classes


# ── SwarmRegistry ──────────────────────────────────────────────────────────

def test_get_swarm_returns_correct_config():
    cfg = get_swarm("audit")
    assert cfg.name == "audit"


def test_get_swarm_raises_for_unknown():
    with pytest.raises(KeyError, match="Unknown swarm config"):
        get_swarm("nonexistent")


def test_list_swarms_returns_all():
    items = list_swarms()
    names = [i["name"] for i in items]
    assert "audit" in names
    assert "release-check" in names
    assert "ci" in names


def test_list_swarms_includes_agents():
    items = list_swarms()
    audit = next(i for i in items if i["name"] == "audit")
    assert "audit" in audit["agents"]
    assert "signal" in audit["agents"]


# ── SwarmRunner.plan ───────────────────────────────────────────────────────

def test_swarm_runner_plan_no_api_needed():
    plan = SwarmRunner(None).plan(SWARM_AUDIT)
    assert len(plan) == 3
    assert plan[0]["agent"] == "audit"
    assert plan[0]["safety_class"] == "read-only"
    assert "purpose" in plan[0]


def test_swarm_runner_plan_includes_tools():
    plan = SwarmRunner(None).plan(SWARM_AUDIT)
    assert "git_status" in plan[0]["tools"]


# ── SwarmRunner.run ────────────────────────────────────────────────────────

def _make_runner():
    client = MagicMock()
    return SwarmRunner(client)


def test_swarm_runner_dry_run_skips_execution():
    runner_obj = _make_runner()
    with patch.object(runner_obj, "_run_agent", return_value={"passed": True}) as mock_run:
        result = runner_obj.run(SWARM_AUDIT, path=".", dry_run=True)
    mock_run.assert_not_called()
    assert result.dry_run is True
    assert all(r.status == "dry-run" for r in result.results)


def test_swarm_runner_skips_approve_agents_without_flag():
    runner_obj = _make_runner()
    with patch.object(runner_obj, "_run_agent", return_value={"passed": True}):
        result = runner_obj.run(SWARM_RELEASE_CHECK, path=".", dry_run=False, approve=False)
    release_result = next(r for r in result.results if r.agent == "release")
    assert release_result.status == "skipped"
    assert "approve" in release_result.error


def test_swarm_runner_runs_agents_with_approve():
    runner_obj = _make_runner()
    with patch.object(runner_obj, "_run_agent", return_value={"passed": True, "ready": True}):
        result = runner_obj.run(SWARM_RELEASE_CHECK, path=".", dry_run=False, approve=True)
    assert all(r.status == "ok" for r in result.results)


def test_swarm_runner_handles_agent_error_warn():
    runner_obj = _make_runner()

    def fail_audit(manifest, path, dry_run, approve):
        if manifest.name == "audit":
            raise RuntimeError("audit exploded")
        return {"passed": True}

    with patch.object(runner_obj, "_run_agent", side_effect=fail_audit):
        result = runner_obj.run(SWARM_AUDIT, path=".", dry_run=False)

    audit_result = next(r for r in result.results if r.agent == "audit")
    assert audit_result.status == "error"
    assert "audit exploded" in audit_result.error
    # warn — does NOT abort, remaining agents still run
    assert len(result.results) == 3


def test_swarm_result_passed_when_all_ok():
    result = SwarmResult(
        config="audit", path=".", dry_run=False,
        results=[
            AgentResult(agent="audit", status="ok"),
            AgentResult(agent="signal", status="ok"),
        ],
    )
    assert result.passed is True


def test_swarm_result_fails_on_error():
    result = SwarmResult(
        config="audit", path=".", dry_run=False,
        results=[
            AgentResult(agent="audit", status="ok"),
            AgentResult(agent="signal", status="error", error="boom"),
        ],
    )
    assert result.passed is False
    assert "signal" in result.failed_agents


def test_swarm_result_to_dict():
    r = SwarmResult(
        config="audit", path=".", dry_run=False,
        results=[AgentResult(agent="audit", status="ok")],
        elapsed_s=1.23,
    )
    d = r.to_dict()
    assert d["config"] == "audit"
    assert d["passed"] is True
    assert d["elapsed_s"] == 1.23
    assert len(d["results"]) == 1


# ── CLI: swarm list ────────────────────────────────────────────────────────

def test_cli_swarm_list():
    result = runner.invoke(app, ["swarm", "list"])
    assert result.exit_code == 0
    assert "audit" in result.output
    assert "release-check" in result.output


def test_cli_swarm_list_json():
    result = runner.invoke(app, ["swarm", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    names = [d["name"] for d in data]
    assert "audit" in names


# ── CLI: swarm plan ────────────────────────────────────────────────────────

def test_cli_swarm_plan_audit():
    result = runner.invoke(app, ["swarm", "plan", "audit"])
    assert result.exit_code == 0
    assert "audit" in result.output
    assert "signal" in result.output
    assert "docs" in result.output


def test_cli_swarm_plan_json():
    result = runner.invoke(app, ["swarm", "plan", "audit", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["config"] == "audit"
    assert len(data["agents"]) == 3


def test_cli_swarm_plan_unknown_config():
    result = runner.invoke(app, ["swarm", "plan", "does-not-exist"])
    assert result.exit_code == 1


# ── CLI: swarm run ─────────────────────────────────────────────────────────

def test_cli_swarm_run_dry_run_json():
    result = runner.invoke(app, ["swarm", "run", "audit", ".", "--dry-run", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert all(r["status"] == "dry-run" for r in data["results"])


def test_cli_swarm_run_unknown_config_exits_1():
    result = runner.invoke(app, ["swarm", "run", "bogus"])
    assert result.exit_code == 1


# ── CLI: swarm audit ──────────────────────────────────────────────────────

def test_cli_swarm_audit_dry_run():
    result = runner.invoke(app, ["swarm", "audit", ".", "--dry-run"])
    assert result.exit_code == 0
    assert "Swarm" in result.output or "audit" in result.output


# ── CLI: swarm release-check ──────────────────────────────────────────────

def test_cli_swarm_release_check_dry_run_json():
    result = runner.invoke(app, ["swarm", "release-check", ".", "--dry-run", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["config"] == "release-check"
    assert data["dry_run"] is True
