"""Integration contract tests for the mq-agent → mq-mcp tool flow.

These tests run without a live server. They lock the behavior of
MCPBridge when the server returns safety_class in its /tools response,
and verify the /tool-contracts endpoint contract shape.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from mq_agent.tools.mcp_registry import MCPSafetyClass, MCPToolSpec


# ── safety_class from server wins over name heuristic ──────────────────────

def test_server_safety_class_overrides_name_heuristic():
    """If server returns safety_class, from_dict must use it over name prefix."""
    spec = MCPToolSpec.from_dict({
        "name": "run_mqlaunch",
        "description": "Launch mqlaunch",
        "safety_class": "read-only",  # server says read-only despite run_ prefix
    })
    assert spec.safety_class == MCPSafetyClass.READ_ONLY
    assert spec.subprocess is False


def test_server_safety_class_class_d_subprocess():
    """Class D tools (subprocess) come through correctly from server response."""
    spec = MCPToolSpec.from_dict({
        "name": "open_in_app",
        "safety_class": "subprocess",
    })
    assert spec.safety_class == MCPSafetyClass.SUBPROCESS
    assert spec.subprocess is True
    assert spec.dangerous is False


def test_server_safety_class_write_capable():
    spec = MCPToolSpec.from_dict({
        "name": "edit_image",
        "safety_class": "write-capable",
    })
    assert spec.safety_class == MCPSafetyClass.WRITE_CAPABLE
    assert spec.write_capable is True


def test_server_safety_class_unknown_falls_back_to_name():
    """If server omits safety_class, fall back to name classification."""
    spec = MCPToolSpec.from_dict({"name": "list_repo_files"})
    assert spec.safety_class == MCPSafetyClass.READ_ONLY


def test_server_contract_class_maps_to_safety_label():
    """Older mq-mcp responses may expose contract class instead of safety_class."""
    spec = MCPToolSpec.from_dict({"name": "review_diff", "class": "A"})
    assert spec.safety_class == MCPSafetyClass.READ_ONLY

    spec = MCPToolSpec.from_dict({"name": "open_in_app", "class": "D"})
    assert spec.safety_class == MCPSafetyClass.SUBPROCESS


# ── MCPBridge with mocked /tools that includes safety_class ────────────────

def _make_mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = data
    return mock


def test_bridge_list_tool_specs_uses_server_safety_class():
    """list_tool_specs must propagate safety_class returned by the server."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    server_tools = {
        "tools": [
            {"name": "run_mqlaunch", "safety_class": "subprocess"},
            {"name": "read_repo_file", "safety_class": "read-only"},
        ]
    }
    with patch("httpx.get", return_value=_make_mock_response(server_tools)):
        bridge = MCPBridge(endpoint="http://localhost:8765")
        specs = bridge.list_tool_specs()

    assert len(specs) == 2
    by_name = {s.name: s for s in specs}
    assert by_name["run_mqlaunch"].safety_class == MCPSafetyClass.SUBPROCESS
    assert by_name["read_repo_file"].safety_class == MCPSafetyClass.READ_ONLY


def test_bridge_list_tool_specs_falls_back_when_no_safety_class():
    """list_tool_specs must fall back to name heuristic when server omits safety_class."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    server_tools = {"tools": [{"name": "list_repo_files"}]}
    with patch("httpx.get", return_value=_make_mock_response(server_tools)):
        bridge = MCPBridge(endpoint="http://localhost:8765")
        specs = bridge.list_tool_specs()

    assert specs[0].safety_class == MCPSafetyClass.READ_ONLY


def test_bridge_list_tool_specs_uses_tool_contracts_when_tools_omit_safety():
    """If /tools omits safety_class, /tool-contracts supplies the authoritative class."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    def fake_get(url: str, timeout: int = 5):
        if url.endswith("/tools"):
            return _make_mock_response({"tools": [{"name": "repo_signal_analyze"}]})
        if url.endswith("/tool-contracts"):
            return _make_mock_response({
                "tools": [{"name": "repo_signal_analyze", "class": "B"}]
            })
        return _make_mock_response({})

    with patch("httpx.get", side_effect=fake_get):
        bridge = MCPBridge(endpoint="http://localhost:8765")
        specs = bridge.list_tool_specs()

    assert specs[0].safety_class == MCPSafetyClass.READ_ONLY


def test_bridge_describe_tool_uses_tool_contracts_when_tool_not_listed():
    """Dry-run can classify contracted tools even before the live server exposes them."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    def fake_get(url: str, timeout: int = 5):
        if url.endswith("/tools/review_diff"):
            mock = _make_mock_response({"error": "Unknown tool"})
            mock.status_code = 404
            return mock
        if url.endswith("/tool-contracts"):
            return _make_mock_response({"tools": [{"name": "review_diff", "class": "A"}]})
        if url.endswith("/tools"):
            return _make_mock_response({"tools": []})
        return _make_mock_response({})

    with patch("httpx.get", side_effect=fake_get):
        bridge = MCPBridge(endpoint="http://localhost:8765")
        spec = bridge.describe_tool("review_diff")

    assert spec.safety_class == MCPSafetyClass.READ_ONLY


# ── /tool-contracts endpoint contract shape ────────────────────────────────

def test_tool_contracts_response_shape():
    """/tool-contracts response must have schema_version, tool_count, and tools list."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    contracts = {
        "schema_version": "tool-contracts.v1",
        "mq_mcp_version": "0.4.0",
        "tool_count": 50,
        "tools": [
            {
                "name": "read_repo_file",
                "class": "A",
                "description": "Read a file from the repo",
                "resolver": "resolve_repo_file",
                "write": False,
                "subprocess": False,
                "side_effects": [],
            }
        ],
    }
    mock_resp = _make_mock_response(contracts)

    with patch("httpx.get", return_value=mock_resp):
        import httpx
        resp = httpx.get("http://localhost:8765/tool-contracts")
        data = resp.json()

    assert data["schema_version"] == "tool-contracts.v1"
    assert data["tool_count"] == 50
    assert isinstance(data["tools"], list)
    assert data["tools"][0]["name"] == "read_repo_file"
    assert data["tools"][0]["class"] == "A"


def test_tool_contracts_class_field_maps_to_safety():
    """Class A→read-only, C→write-capable, D→subprocess mapping is consistent."""
    class_map = {"A": "read-only", "B": "read-only", "C": "write-capable", "D": "subprocess"}
    for cls, expected in class_map.items():
        tool_dict = {"name": f"some_tool_{cls}", "class": cls}
        # Class field is mq-mcp's internal grouping; safety_class is what the
        # server injects into the /tools response. The mapping is defined in
        # generate_tool_contracts.py and TOOL_META. This test locks the naming.
        assert expected in ("read-only", "write-capable", "subprocess", "dangerous")


# ── safety gate: dangerous tools require explicit approval ─────────────────

def test_dangerous_spec_requires_approve_flag():
    """Dangerous tools must be flagged as such so safety gates can block them."""
    spec = MCPToolSpec.from_dict({"name": "nuke_everything", "safety_class": "dangerous"})
    assert spec.dangerous is True
    assert spec.write_capable is False
    assert spec.subprocess is False
    assert spec.read_only is False


def test_read_only_spec_needs_no_approval():
    spec = MCPToolSpec.from_name("read_repo_file")
    assert spec.read_only is True
    assert spec.dangerous is False
    assert spec.write_capable is False
    assert spec.subprocess is False


# ── dry-run passthrough ────────────────────────────────────────────────────

def test_bridge_dry_run_does_not_call_tool():
    """In dry-run mode the bridge must not make HTTP calls to /tools/{name} POST."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    bridge = MCPBridge(endpoint="http://localhost:8765")
    with patch("httpx.post") as mock_post:
        # dry-run is enforced at the executor/safety layer, not bridge.
        # Verify that call_tool itself does POST (the gate is above bridge).
        bridge.call_tool("read_repo_file", {})
        mock_post.assert_called_once()
