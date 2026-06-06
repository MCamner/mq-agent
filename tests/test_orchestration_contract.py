"""Contract tests for the current mq-agent orchestration surface.

These tests intentionally lock existing behavior before larger orchestration
changes. They avoid OpenAI calls and external services.

Two parallel step models co-exist in the codebase:
  PlanStep (core/state.py)     — used by the Executor loop (planner-driven runs)
  StepResult (core/task_runner.py) — used by the declarative task runner (YAML tasks)
SwarmRunner (core/swarm.py) is a separate runtime mode: it coordinates multiple
specialist agents, not steps within a single Executor plan.
"""
from __future__ import annotations

import inspect
import json
from dataclasses import fields
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.core.state import AgentState, PlanStep, StepStatus
from mq_agent.core.swarm import AgentManifest
from mq_agent.core.task_runner import StepResult
from mq_agent.main import app
from mq_agent.tools import TOOL_REGISTRY, tool_names
from mq_agent.tui.app import COMMANDS

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_tool_registry_keeps_core_orchestration_tools():
    expected = {
        "git_status",
        "repo_summary",
        "read_file",
        "write_file",
        "run_command",
        "run_task",
        "mcp_call",
        "inspect_url",
        "summarize_url",
        "verify_release_url",
        "repo_signal_json",
        "repo_suggest",
    }
    assert expected.issubset(set(TOOL_REGISTRY))


def test_tool_names_are_sorted_for_planner_stability():
    names = tool_names()
    assert names == sorted(names)
    assert "run_task" in names


def test_task_list_includes_suggest_workflow_json():
    result = runner.invoke(app, ["task", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    names = {item["name"] for item in data}
    assert "suggest-patches" in names


def test_task_run_suggest_dry_run_json_does_not_execute():
    result = runner.invoke(app, ["task", "run", "suggest-patches", "--dry-run", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["task"] == "suggest-patches"
    assert data["dry_run"] is True
    assert data["passed"] is True
    assert {step["status"] for step in data["steps"]} == {"dry-run"}
    assert "write-report" in {step["step"] for step in data["steps"]}


def test_swarm_plan_is_available_without_api_key():
    result = runner.invoke(app, ["swarm", "plan", "audit", "--json"], env={})
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["config"] == "audit"
    assert [agent["agent"] for agent in data["agents"]] == ["audit", "signal", "docs"]


def test_run_command_without_approve_stays_suggest_only():
    result = runner.invoke(app, ["run", "echo hello"], env={})
    assert result.exit_code == 0
    assert "Would run" in result.output
    assert "--approve" in result.output


def test_tui_command_list_keeps_core_commands():
    commands = {command for _, command in COMMANDS}
    expected = {
        "audit .",
        "score .",
        "release-check",
        "doctor",
        "tools",
        "mcp status",
        "mcp tools",
    }
    assert expected.issubset(commands)


def test_cross_repo_routing_matrix_covers_core_owners():
    matrix = (ROOT / "docs" / "CROSS_REPO_ROUTING_MATRIX.md").read_text(encoding="utf-8")

    for owner in ("mq-agent", "mq-mcp", "repo-signal", "mq-image-analyze", "macos-scripts", "mq-hal"):
        assert owner in matrix
    for phrase in ("Overlap Rules", "Escalation Rules", "mq-agent must not auto-run"):
        assert phrase in matrix


def test_skill_quality_review_is_release_checked():
    review = (ROOT / "docs" / "SKILL_QUALITY_REVIEW.md").read_text(encoding="utf-8")
    release_check = (ROOT / "release-check.sh").read_text(encoding="utf-8")

    for criterion in ("Trigger clarity", "Responsibility boundary", "Output format", "Verification", "Overlap risk"):
        assert criterion in review
    assert "scripts/check-skill-quality.sh" in review
    assert "check-skill-quality.sh" in release_check


def test_perception_scope_docs_lock_owner_boundaries():
    scope = (ROOT / "docs" / "V1_4_0_SCOPE.md").read_text(encoding="utf-8")
    perception = (ROOT / "docs" / "PERCEPTION_INTEGRATION.md").read_text(encoding="utf-8")

    for doc in (scope, perception):
        assert "mq-agent" in doc
        assert "mq-image-analyze" in doc
        assert "mq-mcp" in doc
        assert "must not implement OCR" in doc or "No OCR" in doc

    assert "mq-agent review perception" in perception
    assert "source_type" in perception
    assert "confidence" in perception


# --- Shape contracts (locked before v0.9.0 consolidation) ---

def test_plan_step_fields_are_stable():
    """Lock PlanStep field set — Executor loop step model."""
    field_names = {f.name for f in fields(PlanStep)}
    assert field_names == {
        "index", "description", "tool", "args",
        "status", "result", "error", "verified", "verification_note",
    }


def test_step_result_fields_are_stable():
    """Lock StepResult field set — task runner step model."""
    field_names = {f.name for f in fields(StepResult)}
    assert field_names == {"step", "tool", "status", "output"}


def test_agent_manifest_fields_are_stable():
    """Lock AgentManifest field set — swarm declarative agent metadata."""
    field_names = {f.name for f in fields(AgentManifest)}
    assert field_names == {
        "name", "purpose", "safety_class", "allowed_tools",
        "requires_approve", "output_contract", "failure_behavior",
    }


def test_agent_state_to_dict_shape_is_stable():
    """Lock AgentState.to_dict() top-level keys and step sub-keys."""
    state = AgentState(goal="test")
    state.plan = [
        PlanStep(index=0, description="step", tool="git_status",
                 status=StepStatus.SUCCESS, result="ok")
    ]
    d = state.to_dict()
    assert set(d.keys()) == {
        "goal", "safety_mode", "dry_run", "working_dir",
        "steps", "is_complete", "has_failures",
    }
    step_d = d["steps"][0]
    assert set(step_d.keys()) == {
        "index", "description", "tool", "status",
        "result", "error", "verified", "verification_note",
    }


def test_agent_manifest_allowed_tools_must_be_subset_of_registry():
    """AgentManifest.allowed_tools entries must all exist in TOOL_REGISTRY."""
    manifest = AgentManifest(
        name="test-agent",
        purpose="verify contract",
        safety_class="read-only",
        allowed_tools=["git_status", "read_file", "repo_summary", "mcp_call"],
    )
    unknown = [t for t in manifest.allowed_tools if t not in TOOL_REGISTRY]
    assert not unknown, f"Tools not in TOOL_REGISTRY: {unknown}"


def test_run_task_tool_delegates_to_task_runner(tmp_path, mocker):
    """run_task_tool must delegate execution to task_runner.run_task."""
    from mq_agent.tools.repo_tools import run_task_tool

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "smoke.yaml").write_text(
        "name: smoke\nsteps:\n  - name: s1\n    tool: git_status\n    args:\n      path: .\n"
    )

    mock_run = mocker.patch(
        "mq_agent.core.task_runner.run_task",
        return_value=[StepResult(step="s1", tool="git_status", status="ok", output="clean")],
    )

    import os
    prev = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = run_task_tool("smoke")
    finally:
        os.chdir(prev)

    mock_run.assert_called_once()
    assert "smoke" in result


def test_tool_registry_has_no_positional_only_params():
    """All registered tools must be callable with keyword args — no positional-only params."""
    violations = []
    for name, fn in TOOL_REGISTRY.items():
        sig = inspect.signature(fn)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                violations.append(f"{name}.{param.name}")
    assert not violations, f"Positional-only params found: {violations}"
