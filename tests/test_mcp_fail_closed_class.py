"""A declared MQ producer's tool is never classified by its name.

mq-mcp and mq-image-analyze declare an ADR-003 class for every tool they
register. When that class is missing — an older server, a 404 on
``/tools/<name>``, a server that is down — the name prefix used to stand in for
it. ``extract_coding_conventions`` is declared C (it writes
architecture_memory/) but its ``extract_`` prefix reads as read-only, so
``run-tool`` would have run a write tool without ``--approve``.

For those producers the class is now ``unknown`` and run-tool blocks. Name
guessing remains only for third-party servers, which declare nothing.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.mcp_bridge import MCPBridge, MultiMCPBridge
from mq_agent.tools.mcp_registry import MCPSafetyClass

runner = CliRunner()
TOOL = "extract_coding_conventions"


class _Response:
    def __init__(self, status: int, payload: object):
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        return self._payload


def _server(tools: list[dict | str], *, describe: dict | None = None, contracts: list[dict] | None = None):
    """Fake one MCP HTTP server: /tools, /tools/<name>, /tool-contracts."""

    def get(url: str, **_kwargs):
        if url.endswith("/tool-contracts"):
            return _Response(200, {"tools": contracts}) if contracts is not None else _Response(404, {})
        if url.endswith("/tools"):
            return _Response(200, {"tools": tools})
        if describe is not None:
            return _Response(200, describe)
        return _Response(404, {})

    return patch.object(httpx, "get", side_effect=get)


def _down():
    return patch.object(httpx, "get", side_effect=httpx.ConnectError("refused"))


# --- MCPBridge ---------------------------------------------------------------


def test_declared_producer_without_class_is_unknown():
    with _server([{"name": TOOL}]):
        spec = MCPBridge("http://mq-mcp.test", source="mq-mcp").describe_tool(TOOL)
    assert spec.safety_class == MCPSafetyClass.UNKNOWN


def test_declared_producer_down_is_unknown():
    with _down():
        spec = MCPBridge("http://mq-mcp.test", source="mq-mcp").describe_tool(TOOL)
    assert spec.safety_class == MCPSafetyClass.UNKNOWN


def test_declared_listing_without_class_is_unknown():
    with _server([{"name": TOOL}, "get_status"]):
        specs = MCPBridge("http://mq-mcp.test", source="mq-mcp").list_tool_specs(source="mq-mcp")
    assert {s.name: s.safety_class for s in specs} == {
        TOOL: MCPSafetyClass.UNKNOWN,
        "get_status": MCPSafetyClass.UNKNOWN,
    }


def test_declared_class_still_wins():
    with _server([{"name": TOOL, "class": "C"}], describe={"name": TOOL, "class": "C"}):
        spec = MCPBridge("http://mq-mcp.test", source="mq-mcp").describe_tool(TOOL)
    assert spec.safety_class == MCPSafetyClass.WRITE_CAPABLE


def test_class_from_listing_when_server_has_no_per_tool_endpoint():
    # mq-image-analyze answers /tools/<name> with 405 and declares classes in
    # /tools only; the listing is server metadata, not a name to read.
    with _server([{"name": "observe_architecture", "class": "A"}]):
        spec = MCPBridge("http://image.test", source="mq-image-analyze").describe_tool("observe_architecture")
    assert spec.safety_class == MCPSafetyClass.READ_ONLY


def test_image_analyze_is_a_declared_producer():
    with _server([{"name": "observe_architecture"}]):
        spec = MCPBridge("http://image.test", source="mq-image-analyze").describe_tool("observe_architecture")
    assert spec.safety_class == MCPSafetyClass.UNKNOWN


def test_third_party_server_keeps_name_guessing():
    with _server([{"name": "read_notes"}]):
        spec = MCPBridge("http://other.test", source="notes-server").describe_tool("read_notes")
    assert spec.safety_class == MCPSafetyClass.READ_ONLY


# --- MultiMCPBridge ----------------------------------------------------------


def test_multi_bridge_tool_listed_nowhere_is_unknown():
    with patch("mq_agent.core.config.get_mcp_servers", return_value={"mq-mcp": "http://a", "mq-image-analyze": "http://b"}), \
         _down():
        spec = MultiMCPBridge().describe_tool(TOOL)
    assert spec.safety_class == MCPSafetyClass.UNKNOWN


# --- run-tool: the write tool is blocked, not run without --approve ----------


def test_run_tool_blocks_declared_tool_without_class():
    with patch("mq_agent.core.config.get_mcp_servers", return_value={"mq-mcp": "http://a"}), \
         _server([{"name": TOOL}]), \
         patch.object(MCPBridge, "call_tool") as call:
        result = runner.invoke(app, ["run-tool", TOOL])
    assert result.exit_code == 1
    assert "unknown safety class" in result.output
    call.assert_not_called()
