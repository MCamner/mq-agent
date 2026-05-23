"""Tests for mq_agent tools layer."""
import pytest

from mq_agent.tools.git_tools import git_log, git_status
from mq_agent.tools.repo_tools import list_files, read_file, repo_summary
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
