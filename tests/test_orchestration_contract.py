"""Contract tests for the current mq-agent orchestration surface.

These tests intentionally lock existing behavior before larger orchestration
changes. They avoid OpenAI calls and external services.
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import TOOL_REGISTRY, tool_names
from mq_agent.tui.app import COMMANDS

runner = CliRunner()


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
