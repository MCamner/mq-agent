"""Tests for mq-agent memory search and memory store commands."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


# ── memory search ─────────────────────────────────────────────────────────

def test_memory_search_renders_results():
    fake_result = {
        "items": [
            {"key": "arch-decision-1", "value": "Use MCPBridge for all tool routing."},
            {"key": "arch-decision-2", "value": "Safety gates enforce read-only mode."},
        ]
    }
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_semantic_memory.return_value = fake_result
        result = runner.invoke(app, ["memory", "search", "architecture"])

    assert result.exit_code == 0
    assert "arch-decision-1" in result.output
    assert "arch-decision-2" in result.output


def test_memory_search_list_result():
    fake_result = [{"key": "k1", "content": "some content"}]
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_semantic_memory.return_value = fake_result
        result = runner.invoke(app, ["memory", "search", "query"])

    assert result.exit_code == 0
    assert "k1" in result.output


def test_memory_search_empty_results():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_semantic_memory.return_value = {"items": []}
        result = runner.invoke(app, ["memory", "search", "noresult"])

    assert result.exit_code == 0
    assert "No results" in result.output


def test_memory_search_json_output():
    fake_result = {"items": [{"key": "k1", "value": "v1"}]}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_semantic_memory.return_value = fake_result
        result = runner.invoke(app, ["memory", "search", "q", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["items"][0]["key"] == "k1"


def test_memory_search_unavailable_tool_exits_nonzero():
    error = {"ok": False, "error": "mq-mcp tool 'search_semantic_memory' is not available.", "tool": "search_semantic_memory"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_semantic_memory.return_value = error
        result = runner.invoke(app, ["memory", "search", "q"])

    assert result.exit_code == 1
    assert "search_semantic_memory" in result.output


def test_memory_search_unavailable_tool_json_exits_nonzero():
    error = {"ok": False, "error": "mq-mcp tool 'search_semantic_memory' is not available.", "tool": "search_semantic_memory"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_semantic_memory.return_value = error
        result = runner.invoke(app, ["memory", "search", "q", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False


# ── memory store ──────────────────────────────────────────────────────────

def test_memory_store_requires_approve():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        result = runner.invoke(app, ["memory", "store", "mykey", "myvalue"])

    assert result.exit_code == 1
    assert "--approve" in result.output
    MockBridge.return_value.store_semantic_memory.assert_not_called()


def test_memory_store_dry_run_does_not_call_bridge():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        result = runner.invoke(app, ["memory", "store", "mykey", "myvalue", "--dry-run"])

    assert result.exit_code == 0
    assert "Would call" in result.output
    assert "store_semantic_memory" in result.output
    MockBridge.return_value.store_semantic_memory.assert_not_called()


def test_memory_store_with_approve():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.store_semantic_memory.return_value = {"ok": True}
        result = runner.invoke(app, ["memory", "store", "mykey", "myvalue", "--approve"])

    assert result.exit_code == 0
    MockBridge.return_value.store_semantic_memory.assert_called_once_with("mykey", "myvalue")
    assert "mykey" in result.output


def test_memory_store_unavailable_tool_exits_nonzero():
    error = {"ok": False, "error": "mq-mcp tool 'store_semantic_memory' is not available.", "tool": "store_semantic_memory"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.store_semantic_memory.return_value = error
        result = runner.invoke(app, ["memory", "store", "k", "v", "--approve"])

    assert result.exit_code == 1
    assert "store_semantic_memory" in result.output


def test_memory_store_json_output():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.store_semantic_memory.return_value = {"ok": True, "stored": True}
        result = runner.invoke(app, ["memory", "store", "k", "v", "--approve", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True


# ── MCPBridge semantic memory methods ─────────────────────────────────────

def test_mcp_bridge_search_calls_required_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"items": []}) as call:
        bridge.search_semantic_memory("query text")

    call.assert_called_once_with("search_semantic_memory", {"query": "query text"})


def test_mcp_bridge_store_calls_required_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"ok": True}) as call:
        bridge.store_semantic_memory("mykey", "myvalue")

    call.assert_called_once_with("store_semantic_memory", {"key": "mykey", "value": "myvalue"})


def test_mcp_bridge_search_returns_error_when_tool_missing():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "bridges", {}):
        result = bridge.search_semantic_memory("query")

    assert result["ok"] is False
    assert "search_semantic_memory" in result["error"]
