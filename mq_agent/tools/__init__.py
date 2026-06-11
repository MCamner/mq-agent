from collections.abc import Callable

from .b2tui_tools import (
    b2_get_prompt,
    b2_history,
    b2_list_prompts,
    b2_log_run,
    b2_route,
    b2_route_info,
)
from .browser_tools import fetch_url, inspect_url, summarize_url, verify_release_url
from .git_tools import git_branch, git_diff, git_log, git_remote, git_status
from .image_tools import (
    image_analyze,
    image_analyze_ui,
    image_compare,
    image_doctor,
    image_observe_architecture,
    image_status,
    image_version,
)
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
from .stack_release import stack_release
from .stack_tools import stack_export, stack_github_summary, stack_release_check, stack_status
from .stack_truth import stack_truth_export

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
    # mq-stack status & release discipline
    "stack_status": stack_status,
    "stack_export": stack_export,
    "stack_truth_export": stack_truth_export,
    "stack_release_check": stack_release_check,
    "stack_release": stack_release,
    "stack_github_summary": stack_github_summary,
    # B2 prompt OS
    "b2_list_prompts": b2_list_prompts,
    "b2_route": b2_route,
    "b2_route_info": b2_route_info,
    "b2_get_prompt": b2_get_prompt,
    "b2_history": b2_history,
    "b2_log_run": b2_log_run,
    # mq-image-analyze (read-only, Class A — degrades gracefully if not installed)
    "image_version": image_version,
    "image_doctor": image_doctor,
    "image_status": image_status,
    "image_analyze": image_analyze,
    "image_observe_architecture": image_observe_architecture,
    "image_analyze_ui": image_analyze_ui,
    "image_compare": image_compare,
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
