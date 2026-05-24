"""Tests for mq_agent tools layer."""
import inspect

import pytest

from mq_agent.tools import TOOL_REGISTRY
from mq_agent.tools.git_tools import git_log, git_status
from mq_agent.tools.repo_tools import find_files, list_files, read_file, repo_summary, write_file
from mq_agent.tools.shell_tools import run_command


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

def test_read_file_single_path_param():
    sig = inspect.signature(read_file)
    assert list(sig.parameters.keys()) == ["path"]

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
