"""Tests for mq_agent tools layer."""
import inspect
import textwrap

import pytest

from mq_agent.tools import TOOL_REGISTRY
from mq_agent.tools.git_tools import git_log, git_status
from mq_agent.tools.repo_tools import (
    find_files,
    list_files,
    read_file,
    repo_summary,
    run_task_tool,
    write_file,
)
from mq_agent.tools.shell_tools import run_command
from mq_agent.tools.signal_tools import _version_tuple


def test_git_status_in_current_repo():
    result = git_status(".")
    assert isinstance(result, str)
    # Either clean or shows file list — both are valid strings
    assert len(result) > 0

def test_git_log_returns_commits():
    result = git_log(".", limit=3)
    assert isinstance(result, str)

def test_repo_summary_contains_fields():
    result = repo_summary(".")
    assert "Repo:" in result
    assert "Branch:" in result
    assert "Files:" in result

def test_list_files_returns_string():
    result = list_files(".", pattern="*.toml")
    assert isinstance(result, str)

def test_read_file_existing():
    result = read_file("pyproject.toml")
    assert "[project]" in result

def test_read_file_missing():
    result = read_file("/tmp/definitely_does_not_exist_xyz.txt")
    assert "not found" in result

def test_run_command_echo():
    result = run_command("echo hello")
    assert "hello" in result

def test_run_command_blocks_dangerous():
    with pytest.raises(ValueError, match="Blocked"):
        run_command("rm -rf /")

def test_run_command_default_timeout_is_120():
    sig = inspect.signature(run_command)
    assert sig.parameters["timeout"].default == 120

def test_read_file_accepts_path_and_file_path():
    sig = inspect.signature(read_file)
    params = list(sig.parameters.keys())
    assert "path" in params
    assert "file_path" in params

def test_read_file_file_path_kwarg(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    from mq_agent.tools.repo_tools import read_file as rf
    assert rf(file_path=str(f)) == "hello"

def test_find_files_excludes_venv(tmp_path):
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "site.py").write_text("x")
    (tmp_path / "main.py").write_text("x")
    result = find_files(str(tmp_path), "*.py")
    assert "main.py" in result
    assert ".venv" not in result

def test_repo_summary_excludes_venv(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    for i in range(10):
        (venv / f"pkg{i}.py").write_text("x")
    (tmp_path / "main.py").write_text("x")
    result = repo_summary(str(tmp_path))
    assert "Files:  1 total, 1 Python" in result

def test_write_file_creates_file(tmp_path):
    target = str(tmp_path / "out.txt")
    result = write_file(target, "hello")
    assert "Written:" in result
    assert (tmp_path / "out.txt").read_text() == "hello"

def test_write_file_creates_parent_dirs(tmp_path):
    target = str(tmp_path / "sub" / "dir" / "file.md")
    write_file(target, "content")
    assert (tmp_path / "sub" / "dir" / "file.md").exists()

def test_write_file_in_registry():
    assert "write_file" in TOOL_REGISTRY

def test_repo_signal_json_in_registry():
    assert "repo_signal_json" in TOOL_REGISTRY


# ── run_task_tool ────────────────────────────────────────────────────────────

def test_run_task_tool_in_registry():
    assert "run_task" in TOOL_REGISTRY


def test_run_task_tool_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_task_tool("nonexistent-task-xyz")
    assert "not found" in result.lower()


def test_run_task_tool_runs_task_by_stem(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "echo-task.yaml").write_text(textwrap.dedent("""\
        name: echo-task
        steps:
          - name: greet
            tool: echo_tool
            args:
              msg: hello
    """))
    from unittest.mock import patch
    with patch("mq_agent.tools.TOOL_REGISTRY", {"echo_tool": lambda msg: f"got: {msg}"}):
        result = run_task_tool("echo-task")
    assert "echo-task" in result
    assert "got: hello" in result


def test_run_task_tool_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t.yaml").write_text(textwrap.dedent("""\
        name: t
        steps:
          - name: s
            tool: any_tool
            args: {}
    """))
    result = run_task_tool("t", dry_run=True)
    assert "t" in result


# ── version guard ─────────────────────────────────────────────────────────────

def test_version_tuple_parses_correctly():
    assert _version_tuple("0.7.0") == (0, 7, 0)
    assert _version_tuple("1.2.3") == (1, 2, 3)
    assert _version_tuple("0.6.0") == (0, 6, 0)


def test_version_tuple_handles_bad_input():
    assert _version_tuple("not-a-version") == (0,)
    assert _version_tuple("") == (0,)


def test_version_guard_min_version_is_0_7_0():
    from mq_agent.tools.signal_tools import _MIN_VERSION
    assert _MIN_VERSION >= (0, 7, 0)


def test_version_guard_old_version_triggers_error_message(monkeypatch):
    from mq_agent.tools import signal_tools

    stale = "/tmp/mq-agent/.venv/bin/repo-signal"
    monkeypatch.setattr(signal_tools, "_candidate_bins", lambda: [stale])
    monkeypatch.setattr(signal_tools, "_probe_version", lambda _executable: (1, 0, 0))

    msg = signal_tools._not_available_msg()
    assert "too old" in msg
    assert "1.4.2" in msg
    assert stale in msg
    assert "uv tool install" in msg
