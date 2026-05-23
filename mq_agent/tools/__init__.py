from collections.abc import Callable

from .git_tools import git_branch, git_diff, git_log, git_remote, git_status
from .mcp_bridge import mcp_call
from .repo_tools import find_files, list_files, read_file, repo_summary
from .shell_tools import run_command, which
from .signal_tools import (
    repo_analyze,
    repo_publish_checklist,
    repo_readme_score,
    repo_scan,
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
    "find_files": find_files,
    # repo-signal (optional — degrades gracefully if not installed)
    "repo_scan": repo_scan,
    "repo_readme_score": repo_readme_score,
    "repo_publish_checklist": repo_publish_checklist,
    "repo_analyze": repo_analyze,
    # MCP
    "mcp_call": mcp_call,
}


def register_tool(name: str, fn: Callable) -> None:
    TOOL_REGISTRY[name] = fn


def tool_names() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())
