"""The bridge must forward an explicit repo path to mq-mcp's review_repo.

Regression: review_repo previously dropped `path`, so `review repo <path>`
silently reviewed mq-mcp itself instead of the requested repo.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import _is_error_result, app
from mq_agent.tools.mcp_bridge import MCPBridge, _review_repo_args

runner = CliRunner()


def test_review_repo_args_forwards_absolute_path(tmp_path):
    target = tmp_path / "repo-signal"
    target.mkdir()
    args = _review_repo_args(str(target), {"mode": "comment"})
    assert args["repo_path"] == str(target.resolve())
    assert args["mode"] == "comment"


def test_review_repo_args_resolves_relative_path_to_absolute(tmp_path, monkeypatch):
    (tmp_path / "repo-x").mkdir()
    monkeypatch.chdir(tmp_path)
    args = _review_repo_args("repo-x", {})
    assert os.path.isabs(args["repo_path"])
    assert args["repo_path"] == str((tmp_path / "repo-x").resolve())


def test_review_repo_args_omits_default_dot():
    for bare in (".", "./", "", None):
        args = _review_repo_args(bare, {"mode": "comment"})
        assert "repo_path" not in args, f"{bare!r} should not forward a path"


def test_review_repo_args_does_not_mutate_flags(tmp_path):
    flags = {"mode": "comment"}
    _review_repo_args(str(tmp_path), flags)
    assert "repo_path" not in flags


def test_mcpbridge_review_repo_calls_tool_with_repo_path(tmp_path):
    target = tmp_path / "mq-hal"
    target.mkdir()
    bridge = MCPBridge()
    captured: dict[str, Any] = {}

    def fake_call_tool(tool: str, args: dict[str, Any]) -> Any:
        captured["tool"] = tool
        captured["args"] = args
        return {"ok": True}

    bridge.call_tool = fake_call_tool  # type: ignore[assignment]
    bridge.review_repo(str(target), {"mode": "comment"})

    assert captured["tool"] == "review_repo"
    assert captured["args"]["repo_path"] == str(target.resolve())


def test_mcpbridge_review_repo_self_review_when_no_path():
    bridge = MCPBridge()
    captured: dict[str, Any] = {}

    def fake_call_tool(tool: str, args: dict[str, Any]) -> Any:
        captured["args"] = args
        return {"ok": True}

    bridge.call_tool = fake_call_tool  # type: ignore[assignment]
    bridge.review_repo(".", {"mode": "comment"})

    assert "repo_path" not in captured["args"]


# C. Dry-run shows the target repo path.
def test_review_repo_dry_run_shows_target_path():
    result = runner.invoke(app, ["review", "repo", "/Users/mansys/repo-signal", "--dry-run"])
    assert result.exit_code == 0
    assert "review_repo" in result.output
    assert "/Users/mansys/repo-signal" in result.output


# D. mq-mcp path-validation error is surfaced, not masked, and not recorded.
def test_review_repo_surfaces_failed_error_and_skips_brain():
    err = "review_repo failed: repo_path outside MQ_MCP_ALLOWED_PATHS: /tmp/foo"
    # _is_error_result must recognize the mq-mcp failure string.
    assert _is_error_result(err) is True

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_repo.return_value = err
        result = runner.invoke(app, ["review", "repo", "/tmp/foo", "--brain", "--json"])

    assert result.exit_code == 1
    assert "review_repo failed" in result.output
    # A failed review is never recorded to the brain.
    MockBridge.return_value.call_tool.assert_not_called()
