from collections.abc import Callable

from .browser_tools import fetch_url, inspect_url, summarize_url, verify_release_url
from .git_tools import git_branch, git_diff, git_log, git_remote, git_status
from .mcp_bridge import mcp_call
from .repo_tools import find_files, list_files, read_file, repo_summary, run_task_tool, write_file
from .shell_tools import run_command, which
from .signal_tools import (
    repo_analyze,
    repo_publish_checklist,
    repo_readme_score,
    repo_scan,
    repo_signal_json,
    repo_suggest,
)

TOOL_REGISTRY: dict[str, Callable] = {
    # Git
    "git_status": git_status,
    "git_log": git_log,
    "git_diff": git_diff,
    "git_branch": git_branch,
    "git_remote": git_remote,
    # Shell
    "run_command": run_command,
    "which": which,
    # Repo
    "repo_summary": repo_summary,
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "find_files": find_files,
    "run_task": run_task_tool,
    # repo-signal (optional — degrades gracefully if not installed)
    "repo_scan": repo_scan,
    "repo_readme_score": repo_readme_score,
    "repo_publish_checklist": repo_publish_checklist,
    "repo_analyze": repo_analyze,
    "repo_signal_json": repo_signal_json,
    "repo_suggest": repo_suggest,
    # MCP
    "mcp_call": mcp_call,
    # Browser (read-only, safe GET requests only)
    "fetch_url": fetch_url,
    "inspect_url": inspect_url,
    "summarize_url": summarize_url,
    "verify_release_url": verify_release_url,
}


def register_tool(name: str, fn: Callable) -> None:
    TOOL_REGISTRY[name] = fn


def tool_names() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())
