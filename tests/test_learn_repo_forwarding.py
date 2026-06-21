"""repo_path forwarding for the learn/review-file bridge + CLI.

Ensures `--repo` flows through to mq-mcp's repo_path so cross-repo review and
lesson extraction target and attribute the right repo.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.mcp_bridge import MCPBridge, MultiMCPBridge, _add_repo_path

runner = CliRunner()


def test_add_repo_path_resolves_real_path(tmp_path):
    target = tmp_path / "repo-signal"
    target.mkdir()
    out = _add_repo_path({"relative_path": "a.py"}, str(target))
    assert out["repo_path"] == str(target.resolve())
    assert out["relative_path"] == "a.py"


def test_add_repo_path_omits_default():
    for bare in (".", "./", "", None):
        assert "repo_path" not in _add_repo_path({"relative_path": "a.py"}, bare)


def test_mcpbridge_review_file_forwards_repo_path(tmp_path):
    target = tmp_path / "mq-hal"
    target.mkdir()
    bridge = MCPBridge()
    captured: dict[str, Any] = {}
    bridge.call_tool = lambda tool, args: captured.update(tool=tool, args=args) or {"ok": True}  # type: ignore
    bridge.review_file("tools/x.py", {"security": False}, repo_path=str(target))
    assert captured["tool"] == "review_file"
    assert captured["args"]["relative_path"] == "tools/x.py"
    assert captured["args"]["repo_path"] == str(target.resolve())


def _capture_required_tool(bridge: MultiMCPBridge, captured: dict[str, Any]):
    def _fake(tool: str, args: dict[str, Any]) -> Any:
        captured["tool"] = tool
        captured["args"] = args
        return {"ok": True}
    bridge._call_required_tool = _fake  # type: ignore


def test_multibridge_learn_from_review_forwards_repo_path(tmp_path):
    target = tmp_path / "repo-signal"
    target.mkdir()
    bridge = MultiMCPBridge()
    captured: dict[str, Any] = {}
    _capture_required_tool(bridge, captured)
    bridge.learn_from_review("tools/x.py", task="t", risk="low", repo_path=str(target))
    assert captured["tool"] == "learn_from_review"
    assert captured["args"]["repo_path"] == str(target.resolve())
    assert captured["args"]["relative_path"] == "tools/x.py"


def test_multibridge_learn_extract_forwards_repo_path(tmp_path):
    target = tmp_path / "mq-hal"
    target.mkdir()
    bridge = MultiMCPBridge()
    captured: dict[str, Any] = {}
    _capture_required_tool(bridge, captured)
    bridge.learn_extract_from_last_review("tools/x.py", repo_path=str(target))
    assert captured["tool"] == "learn_extract_from_last_review"
    assert captured["args"]["repo_path"] == str(target.resolve())


def test_multibridge_learn_from_review_no_repo_omits_path():
    bridge = MultiMCPBridge()
    captured: dict[str, Any] = {}
    _capture_required_tool(bridge, captured)
    bridge.learn_from_review("tools/x.py")
    assert "repo_path" not in captured["args"]


# CLI dry-runs surface the target repo path.
def test_cli_review_file_dry_run_shows_repo():
    r = runner.invoke(app, ["review", "file", "tools/x.py", "--repo", "/tmp/repo-signal", "--dry-run"])
    assert r.exit_code == 0
    assert "repo_path=/tmp/repo-signal" in r.output


def test_cli_learn_from_review_dry_run_shows_repo():
    r = runner.invoke(app, ["learn", "from-review", "tools/x.py", "--repo", "/tmp/repo-signal", "--dry-run"])
    assert r.exit_code == 0
    assert "repo_path=/tmp/repo-signal" in r.output


def test_cli_learn_extract_dry_run_shows_repo():
    r = runner.invoke(app, ["learn", "extract-review", "tools/x.py", "--repo", "/tmp/mq-hal", "--dry-run"])
    assert r.exit_code == 0
    assert "repo_path=/tmp/mq-hal" in r.output
