"""Tests for task_runner and mq-agent task CLI commands."""
from __future__ import annotations

import textwrap
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mq_agent.core.task_runner import Task, TaskStep, _resolve_templates, find_task_files, load_task, run_task
from mq_agent.main import app

runner = CliRunner()


# ── load_task ───────────────────────────────────────────────────────────────

def test_load_task_parses_steps(tmp_path):
    f = tmp_path / "my-task.yaml"
    f.write_text(textwrap.dedent("""\
        name: my-task
        version: "0.1"
        description: A test task
        steps:
          - name: step-one
            tool: repo_summary
            args:
              path: "."
    """))
    task = load_task(f)
    assert task.name == "my-task"
    assert task.version == "0.1"
    assert task.description == "A test task"
    assert len(task.steps) == 1
    assert task.steps[0].tool == "repo_summary"
    assert task.steps[0].args == {"path": "."}


def test_load_task_defaults_name_to_stem(tmp_path):
    f = tmp_path / "fallback.yaml"
    f.write_text("steps: []\n")
    task = load_task(f)
    assert task.name == "fallback"


def test_load_task_defaults_version(tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text("steps: []\n")
    task = load_task(f)
    assert task.version == "0.1"


def test_load_task_requires_pyyaml(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def block_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_yaml)
    f = tmp_path / "t.yaml"
    f.write_text("steps: []\n")
    with pytest.raises(ImportError, match="PyYAML"):
        load_task(f)


# ── run_task ────────────────────────────────────────────────────────────────

def test_run_task_dry_run_returns_dry_run_status():
    task = Task(
        name="t",
        steps=[TaskStep(name="s", tool="repo_summary", args={"path": "."})],
    )
    results = run_task(task, dry_run=True)
    assert len(results) == 1
    assert results[0].status == "dry-run"
    assert "repo_summary" in results[0].output


def test_run_task_calls_registered_tool():
    task = Task(
        name="t",
        steps=[TaskStep(name="s", tool="repo_summary", args={"path": "."})],
    )
    with patch("mq_agent.tools.TOOL_REGISTRY", {"repo_summary": lambda path: "ok"}):
        results = run_task(task)
    assert results[0].status == "ok"
    assert results[0].output == "ok"


def test_run_task_unknown_tool():
    task = Task(
        name="t",
        steps=[TaskStep(name="s", tool="no_such_tool")],
    )
    results = run_task(task)
    assert results[0].status == "unknown-tool"
    assert "no_such_tool" in results[0].output


def test_run_task_captures_exception():
    def boom(**kwargs):
        raise RuntimeError("exploded")

    task = Task(
        name="t",
        steps=[TaskStep(name="s", tool="boom_tool", args={})],
    )
    with patch("mq_agent.tools.TOOL_REGISTRY", {"boom_tool": boom}):
        results = run_task(task)
    assert results[0].status == "error"
    assert "exploded" in results[0].output


def test_run_task_multiple_steps_all_dry_run():
    task = Task(
        name="t",
        steps=[
            TaskStep(name="a", tool="repo_summary"),
            TaskStep(name="b", tool="git_status"),
        ],
    )
    results = run_task(task, dry_run=True)
    assert len(results) == 2
    assert all(r.status == "dry-run" for r in results)


# ── find_task_files ─────────────────────────────────────────────────────────

def test_find_task_files_returns_yaml_files(tmp_path):
    (tmp_path / "a.yaml").write_text("steps: []\n")
    (tmp_path / "b.yaml").write_text("steps: []\n")
    (tmp_path / "ignore.txt").write_text("")
    files = find_task_files(tmp_path)
    names = {f.name for f in files}
    assert "a.yaml" in names
    assert "b.yaml" in names
    assert "ignore.txt" not in names


def test_find_task_files_deduplicates(tmp_path):
    (tmp_path / "t.yaml").write_text("steps: []\n")
    files = find_task_files(tmp_path, tmp_path)
    assert len(files) == 1


def test_find_task_files_skips_missing_dirs(tmp_path):
    missing = tmp_path / "nonexistent"
    (tmp_path / "t.yaml").write_text("steps: []\n")
    files = find_task_files(missing, tmp_path)
    assert len(files) == 1


# ── _resolve_templates ──────────────────────────────────────────────────────

def test_resolve_templates_substitutes_step_output():
    args = {"content": "{{step:my-step}}"}
    outputs = {"my-step": "hello world"}
    result = _resolve_templates(args, outputs)
    assert result["content"] == "hello world"


def test_resolve_templates_keeps_placeholder_when_step_missing():
    args = {"content": "{{step:missing}}"}
    result = _resolve_templates(args, {})
    assert result["content"] == "{{step:missing}}"


def test_resolve_templates_ignores_non_string_values():
    args = {"path": ".", "limit": 5}
    result = _resolve_templates(args, {"limit": "10"})
    assert result["limit"] == 5


def test_resolve_templates_multiple_refs_in_one_string():
    args = {"content": "{{step:a}} and {{step:b}}"}
    result = _resolve_templates(args, {"a": "foo", "b": "bar"})
    assert result["content"] == "foo and bar"


def test_run_task_passes_step_output_to_next_step():
    call_log: list[dict] = []

    def first(**kwargs):
        return "FIRST_OUTPUT"

    def second(**kwargs):
        call_log.append(kwargs)
        return "done"

    task = Task(
        name="t",
        steps=[
            TaskStep(name="step-one", tool="first_tool", args={"path": "."}),
            TaskStep(name="step-two", tool="second_tool", args={"content": "{{step:step-one}}"}),
        ],
    )
    with patch("mq_agent.tools.TOOL_REGISTRY", {"first_tool": first, "second_tool": second}):
        run_task(task)

    assert call_log[0]["content"] == "FIRST_OUTPUT"


def test_run_task_template_dry_run_does_not_resolve():
    task = Task(
        name="t",
        steps=[
            TaskStep(name="a", tool="tool_a", args={}),
            TaskStep(name="b", tool="tool_b", args={"content": "{{step:a}}"}),
        ],
    )
    results = run_task(task, dry_run=True)
    assert all(r.status == "dry-run" for r in results)
    # original args preserved in dry-run output
    assert "{{step:a}}" in results[1].output


# ── CLI: task list ───────────────────────────────────────────────────────────

def test_task_list_shows_tasks():
    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code == 0
    assert "repo-audit" in result.output


def test_task_list_json():
    result = runner.invoke(app, ["task", "list", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert isinstance(data, list)
    names = [t["name"] for t in data]
    assert "repo-audit" in names


# ── CLI: task run ────────────────────────────────────────────────────────────

def test_task_run_dry_run_by_stem():
    result = runner.invoke(app, ["task", "run", "audit", "--dry-run"])
    assert result.exit_code == 0
    assert "dry-run" in result.output.lower() or "Would call" in result.output


def test_task_run_dry_run_by_internal_name():
    result = runner.invoke(app, ["task", "run", "repo-audit", "--dry-run"])
    assert result.exit_code == 0
    assert "repo-audit" in result.output


def test_task_run_not_found():
    result = runner.invoke(app, ["task", "run", "nonexistent-task-xyz"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_task_run_json_dry_run():
    result = runner.invoke(app, ["task", "run", "repo-audit", "--dry-run", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["task"] == "repo-audit"
    assert data["dry_run"] is True
    steps = data["steps"]
    assert isinstance(steps, list)
    assert all(s["status"] == "dry-run" for s in steps)
