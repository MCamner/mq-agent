"""The bridge must forward an explicit repo path to mq-mcp's review_repo.

Regression: review_repo previously dropped `path`, so `review repo <path>`
silently reviewed mq-mcp itself instead of the requested repo.
"""
from __future__ import annotations

from typing import Any

from mq_agent.tools.mcp_bridge import MCPBridge, _review_repo_args


def test_review_repo_args_forwards_real_path():
    args = _review_repo_args("/Users/mansys/repo-signal", {"mode": "comment"})
    assert args["repo_path"] == "/Users/mansys/repo-signal"
    assert args["mode"] == "comment"


def test_review_repo_args_omits_default_dot():
    for bare in (".", "./", "", None):
        args = _review_repo_args(bare, {"mode": "comment"})
        assert "repo_path" not in args, f"{bare!r} should not forward a path"


def test_review_repo_args_does_not_mutate_flags():
    flags = {"mode": "comment"}
    _review_repo_args("/x/repo", flags)
    assert "repo_path" not in flags


def test_mcpbridge_review_repo_calls_tool_with_repo_path():
    bridge = MCPBridge()
    captured: dict[str, Any] = {}

    def fake_call_tool(tool: str, args: dict[str, Any]) -> Any:
        captured["tool"] = tool
        captured["args"] = args
        return {"ok": True}

    bridge.call_tool = fake_call_tool  # type: ignore[assignment]
    bridge.review_repo("/Users/mansys/mq-hal", {"mode": "comment"})

    assert captured["tool"] == "review_repo"
    assert captured["args"]["repo_path"] == "/Users/mansys/mq-hal"


def test_mcpbridge_review_repo_self_review_when_no_path():
    bridge = MCPBridge()
    captured: dict[str, Any] = {}

    def fake_call_tool(tool: str, args: dict[str, Any]) -> Any:
        captured["args"] = args
        return {"ok": True}

    bridge.call_tool = fake_call_tool  # type: ignore[assignment]
    bridge.review_repo(".", {"mode": "comment"})

    assert "repo_path" not in captured["args"]
