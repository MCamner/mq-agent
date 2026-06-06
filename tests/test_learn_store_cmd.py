"""Tests for mq-agent learn store command."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()

_SUCCESS_TEXT = "Pattern stored successfully.\n\npattern_name: release-gate-contracts\nstored: true"
_MCP_TEXT_RESULT = [[{"type": "text", "text": _SUCCESS_TEXT}], {"result": _SUCCESS_TEXT}]
_ERROR_RESULT = {"ok": False, "error": "mq-mcp tool 'record_learning' is not available.", "tool": "record_learning"}


def test_store_without_approve_exits_nonzero():
    result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py"])
    assert result.exit_code == 1
    assert "--approve" in result.output


def test_store_dry_run_shows_preview():
    result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--dry-run"])
    assert result.exit_code == 0
    assert "Would call" in result.output
    assert "record_learning" in result.output
    assert "mq-mcp/server.py" in result.output


def test_store_dry_run_does_not_call_bridge():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--dry-run"])
    MockBridge.assert_not_called()


def test_store_approve_renders_success():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_record.return_value = _MCP_TEXT_RESULT
        result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--approve"])

    assert result.exit_code == 0
    assert "Pattern stored" in result.output
    assert "stored successfully" in result.output


def test_store_approve_json_output():
    payload = {"stored": True, "pattern_name": "release-gate-contracts"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_record.return_value = payload
        result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--approve", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["stored"] is True


def test_store_tool_unavailable_exits_nonzero():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_record.return_value = _ERROR_RESULT
        result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--approve"])

    assert result.exit_code == 1
    assert "record_learning" in result.output


def test_store_tool_unavailable_json_exits_nonzero():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_record.return_value = _ERROR_RESULT
        result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--approve", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False


def test_store_calls_bridge_with_path():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_record.return_value = _MCP_TEXT_RESULT
        runner.invoke(app, ["learn", "store", "some/path.py", "--approve"])

    MockBridge.return_value.learn_record.assert_called_once_with("some/path.py")
