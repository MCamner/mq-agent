"""Tests for v1.3.0: arch-memory context, --fast flag, learn commands."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


# ── --fast flag on review commands ────────────────────────────────────────

def test_review_file_fast_flag_passed_to_bridge():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    with patch.object(MultiMCPBridge, "review_file", return_value={"ok": True, "findings": []}) as mock:
        with patch.object(MultiMCPBridge, "list_architecture_decisions", return_value=None):
            result = runner.invoke(app, ["review", "file", "README.md", "--fast"])

    assert result.exit_code == 0
    flags = mock.call_args[0][1]
    assert flags["fast"] is True


def test_review_diff_fast_flag_passed_to_bridge():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    with patch.object(MultiMCPBridge, "review_diff", return_value={"ok": True, "findings": []}) as mock:
        with patch.object(MultiMCPBridge, "list_architecture_decisions", return_value=None):
            result = runner.invoke(app, ["review", "diff", "--fast"])

    assert result.exit_code == 0
    flags = mock.call_args[0][0]
    assert flags["fast"] is True


def test_review_repo_fast_flag_passed_to_bridge():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    with patch.object(MultiMCPBridge, "review_repo", return_value={"ok": True, "findings": []}) as mock:
        with patch.object(MultiMCPBridge, "list_architecture_decisions", return_value=None):
            result = runner.invoke(app, ["review", "repo", ".", "--fast"])

    assert result.exit_code == 0
    flags = mock.call_args[0][1]
    assert flags["fast"] is True


def test_review_fast_dry_run_shows_flag():
    result = runner.invoke(app, ["review", "file", "src/main.py", "--fast", "--dry-run"])
    assert result.exit_code == 0
    assert "--fast" in result.output


# ── architecture-memory context in review ─────────────────────────────────

def test_review_shows_arch_context_when_available():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    decisions = [
        {"id": "adr-001", "title": "Use MCPBridge for all tool routing"},
        {"id": "adr-002", "title": "Safety gates enforce read-only mode"},
    ]
    with patch.object(MultiMCPBridge, "review_file", return_value={"ok": True, "findings": []}):
        with patch.object(MultiMCPBridge, "list_architecture_decisions", return_value=decisions):
            result = runner.invoke(app, ["review", "file", "README.md"])

    assert result.exit_code == 0
    assert "adr-001" in result.output or "MCPBridge" in result.output
    assert "Architecture context" in result.output


def test_review_silent_when_arch_context_unavailable():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    with patch.object(MultiMCPBridge, "review_file", return_value={"ok": True, "findings": []}):
        with patch.object(MultiMCPBridge, "list_architecture_decisions", return_value=None):
            result = runner.invoke(app, ["review", "file", "README.md"])

    assert result.exit_code == 0
    assert "Architecture context" not in result.output


def test_review_json_does_not_include_arch_context():
    """--json output must stay clean: no arch-context panel injected."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    decisions = [{"id": "adr-001", "title": "Some decision"}]
    with patch.object(MultiMCPBridge, "review_file", return_value={"ok": True, "findings": []}):
        with patch.object(MultiMCPBridge, "list_architecture_decisions", return_value=decisions):
            result = runner.invoke(app, ["review", "file", "README.md", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "ok" in data


# ── MultiMCPBridge arch-memory methods ───────────────────────────────────

def test_list_architecture_decisions_uses_optional_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_optional_tool", return_value=[{"id": "adr-1"}]) as call:
        result = bridge.list_architecture_decisions()

    call.assert_called_once_with("list_architecture_decisions", {})
    assert result[0]["id"] == "adr-1"


def test_list_architecture_decisions_returns_none_when_tool_missing():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "bridges", {}):
        result = bridge.list_architecture_decisions()

    assert result is None


def test_get_architecture_decision_uses_required_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"id": "adr-1", "title": "x"}) as call:
        result = bridge.get_architecture_decision("adr-1")

    call.assert_called_once_with("get_architecture_decision", {"id": "adr-1"})
    assert result["id"] == "adr-1"


def test_call_optional_tool_returns_none_when_not_available():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "bridges", {}):
        result = bridge._call_optional_tool("nonexistent_tool", {})

    assert result is None


# ── learn status ──────────────────────────────────────────────────────────

def test_learn_status_renders_result():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_status.return_value = {"ok": True, "patterns": 42}
        result = runner.invoke(app, ["learn", "status"])

    assert result.exit_code == 0
    assert "42" in result.output


def test_learn_status_json():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_status.return_value = {"ok": True, "patterns": 5}
        result = runner.invoke(app, ["learn", "status", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True


def test_learn_status_unavailable_exits_nonzero():
    error = {"ok": False, "error": "mq-mcp tool 'learn_status' is not available.", "tool": "learn_status"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_status.return_value = error
        result = runner.invoke(app, ["learn", "status"])

    assert result.exit_code == 1
    assert "learn_status" in result.output


# ── learn search ──────────────────────────────────────────────────────────

def test_learn_search_renders_patterns():
    patterns = [
        {"id": "p-1", "title": "Avoid direct state mutation"},
        {"id": "p-2", "summary": "Use guard clauses for early returns"},
    ]
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_learned_patterns.return_value = {"patterns": patterns}
        result = runner.invoke(app, ["learn", "search", "mutation"])

    assert result.exit_code == 0
    assert "p-1" in result.output
    assert "p-2" in result.output


def test_learn_search_empty_results():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_learned_patterns.return_value = {"patterns": []}
        result = runner.invoke(app, ["learn", "search", "nothing"])

    assert result.exit_code == 0
    assert "No patterns" in result.output


def test_learn_search_json():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_learned_patterns.return_value = {"patterns": [{"id": "p-1"}]}
        result = runner.invoke(app, ["learn", "search", "q", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["patterns"][0]["id"] == "p-1"


def test_learn_search_unavailable_exits_nonzero():
    error = {"ok": False, "error": "mq-mcp tool 'search_learned_patterns' is not available."}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.search_learned_patterns.return_value = error
        result = runner.invoke(app, ["learn", "search", "q"])

    assert result.exit_code == 1


# ── learn explain ─────────────────────────────────────────────────────────

def test_learn_explain_renders_pattern():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.explain_learned_pattern.return_value = {
            "id": "p-1",
            "explanation": "Avoid mutating state directly.",
        }
        result = runner.invoke(app, ["learn", "explain", "p-1"])

    assert result.exit_code == 0
    assert "p-1" in result.output


def test_learn_explain_json():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.explain_learned_pattern.return_value = {"id": "p-1", "explanation": "x"}
        result = runner.invoke(app, ["learn", "explain", "p-1", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "p-1"


def test_learn_explain_not_found_exits_nonzero():
    error = {"ok": False, "error": "mq-mcp tool 'explain_learned_pattern' is not available."}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.explain_learned_pattern.return_value = error
        result = runner.invoke(app, ["learn", "explain", "p-99"])

    assert result.exit_code == 1


# ── bridge learn methods ───────────────────────────────────────────────────

def test_bridge_learn_status_calls_required_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"ok": True}) as call:
        bridge.learn_status()

    call.assert_called_once_with("learn_status", {})


def test_bridge_search_learned_patterns_calls_required_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"patterns": []}) as call:
        bridge.search_learned_patterns("query text")

    call.assert_called_once_with("search_learned_patterns", {"query": "query text"})


def test_bridge_explain_learned_pattern_calls_required_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"id": "p-1"}) as call:
        bridge.explain_learned_pattern("p-1")

    call.assert_called_once_with("explain_learned_pattern", {"id": "p-1"})
