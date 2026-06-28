"""MCPBridgeExecutor argument injection.

The runner speaks repo paths, but some mq-mcp tools (e.g. run_tests) key off the
registered repo NAME. mq-mcp registers repos by directory basename, so the
executor injects repo_name = basename(repo) alongside repo_path. Caller-supplied
args always win (setdefault).
"""
from __future__ import annotations

from mq_agent.workflows.runner import MCPBridgeExecutor


class _RecordingBridge:
    def __init__(self):
        self.calls = []

    def call_tool(self, tool, payload):
        self.calls.append((tool, payload))
        return {"ok": True}


def _executor():
    ex = MCPBridgeExecutor.__new__(MCPBridgeExecutor)  # skip real bridge construction
    ex._bridge = _RecordingBridge()
    return ex


def test_injects_repo_path_and_repo_name():
    ex = _executor()
    ex("run_tests", {}, "/Users/mansys/macos-scripts")
    _, payload = ex._bridge.calls[0]
    assert payload["repo_path"] == "/Users/mansys/macos-scripts"
    assert payload["repo_name"] == "macos-scripts"  # basename == registry key


def test_caller_args_are_not_overridden():
    ex = _executor()
    ex("run_tests", {"repo_name": "explicit", "repo_path": "/x"}, "/Users/mansys/mq-mcp")
    _, payload = ex._bridge.calls[0]
    assert payload["repo_name"] == "explicit"
    assert payload["repo_path"] == "/x"


def test_repo_name_is_basename_for_nested_path():
    ex = _executor()
    ex("git_status", {}, "/a/b/c/mq-mcp")
    _, payload = ex._bridge.calls[0]
    assert payload["repo_name"] == "mq-mcp"
