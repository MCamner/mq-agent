"""Tests for MCP registry, bridge, and safety classification — no mq-mcp server required."""
import pytest

from mq_agent.tools.mcp_registry import MCPSafetyClass, MCPToolSpec, classify_tool_name


# ── classify_tool_name ──────────────────────────────────────────────────────

def test_classify_read_only_read_prefix():
    assert classify_tool_name("read_repo_file") == MCPSafetyClass.READ_ONLY

def test_classify_read_only_list_prefix():
    assert classify_tool_name("list_files") == MCPSafetyClass.READ_ONLY

def test_classify_read_only_get_prefix():
    assert classify_tool_name("get_status") == MCPSafetyClass.READ_ONLY

def test_classify_read_only_search_prefix():
    assert classify_tool_name("search_repos") == MCPSafetyClass.READ_ONLY

def test_classify_read_only_find_prefix():
    assert classify_tool_name("find_todos") == MCPSafetyClass.READ_ONLY

def test_classify_read_only_git_prefix():
    assert classify_tool_name("git_status") == MCPSafetyClass.READ_ONLY
    assert classify_tool_name("git_diff") == MCPSafetyClass.READ_ONLY
    assert classify_tool_name("git_log") == MCPSafetyClass.READ_ONLY

def test_classify_write_capable_update():
    assert classify_tool_name("update_repo_file") == MCPSafetyClass.WRITE_CAPABLE

def test_classify_write_capable_write():
    assert classify_tool_name("write_file") == MCPSafetyClass.WRITE_CAPABLE

def test_classify_write_capable_edit():
    assert classify_tool_name("edit_image") == MCPSafetyClass.WRITE_CAPABLE

def test_classify_write_capable_create():
    assert classify_tool_name("create_branch") == MCPSafetyClass.WRITE_CAPABLE

def test_classify_dangerous_delete():
    assert classify_tool_name("delete_data") == MCPSafetyClass.DANGEROUS

def test_classify_dangerous_remove():
    assert classify_tool_name("remove_file") == MCPSafetyClass.DANGEROUS

def test_classify_subprocess_run():
    assert classify_tool_name("run_command") == MCPSafetyClass.SUBPROCESS

def test_classify_subprocess_validate():
    assert classify_tool_name("validate_project") == MCPSafetyClass.SUBPROCESS

def test_classify_subprocess_execute():
    assert classify_tool_name("execute_script") == MCPSafetyClass.SUBPROCESS

def test_classify_subprocess_open():
    assert classify_tool_name("open_repo_terminal") == MCPSafetyClass.SUBPROCESS

def test_classify_unknown():
    assert classify_tool_name("frobnicate_things") == MCPSafetyClass.UNKNOWN
    assert classify_tool_name("hal_repo_report") == MCPSafetyClass.UNKNOWN
    assert classify_tool_name("repo_signal_analyze") == MCPSafetyClass.UNKNOWN


# ── MCPToolSpec.from_name ───────────────────────────────────────────────────

def test_spec_from_name_read_only():
    spec = MCPToolSpec.from_name("read_repo_file", "Read a file")
    assert spec.name == "read_repo_file"
    assert spec.description == "Read a file"
    assert spec.safety_class == MCPSafetyClass.READ_ONLY
    assert spec.read_only is True
    assert spec.write_capable is False
    assert spec.subprocess is False
    assert spec.dangerous is False

def test_spec_from_name_write_capable():
    spec = MCPToolSpec.from_name("update_repo_file")
    assert spec.safety_class == MCPSafetyClass.WRITE_CAPABLE
    assert spec.write_capable is True
    assert spec.read_only is False

def test_spec_from_name_dangerous():
    spec = MCPToolSpec.from_name("remove_device")
    assert spec.safety_class == MCPSafetyClass.DANGEROUS
    assert spec.dangerous is True

def test_spec_from_name_subprocess():
    spec = MCPToolSpec.from_name("validate_project")
    assert spec.safety_class == MCPSafetyClass.SUBPROCESS
    assert spec.subprocess is True

def test_spec_from_name_unknown():
    spec = MCPToolSpec.from_name("some_mystery_tool")
    assert spec.safety_class == MCPSafetyClass.UNKNOWN
    assert spec.read_only is False
    assert spec.write_capable is False
    assert spec.subprocess is False
    assert spec.dangerous is False


# ── MCPToolSpec.from_dict ───────────────────────────────────────────────────

def test_spec_from_dict_with_safety_class():
    spec = MCPToolSpec.from_dict({
        "name": "custom_tool",
        "description": "A custom tool",
        "safety_class": MCPSafetyClass.READ_ONLY,
        "input_schema": {"path": "string"},
        "examples": ["custom_tool path=README.md"],
    })
    assert spec.name == "custom_tool"
    assert spec.safety_class == MCPSafetyClass.READ_ONLY
    assert spec.read_only is True
    assert spec.input_schema == {"path": "string"}
    assert spec.examples == ["custom_tool path=README.md"]

def test_spec_from_dict_falls_back_to_name_classification():
    spec = MCPToolSpec.from_dict({"name": "update_config"})
    assert spec.safety_class == MCPSafetyClass.WRITE_CAPABLE
    assert spec.write_capable is True

def test_spec_from_dict_explicit_class_wins_over_name():
    spec = MCPToolSpec.from_dict({"name": "update_config", "safety_class": "read-only"})
    assert spec.safety_class == MCPSafetyClass.READ_ONLY
    assert spec.read_only is True


# ── MCPToolSpec.to_dict ─────────────────────────────────────────────────────

def test_spec_to_dict_round_trip():
    spec = MCPToolSpec.from_name("read_repo_file", "Read a file")
    d = spec.to_dict()
    assert d["name"] == "read_repo_file"
    assert d["safety_class"] == MCPSafetyClass.READ_ONLY
    assert d["read_only"] is True
    assert d["source"] == "mq-mcp"


# ── MCPBridge (no server needed) ────────────────────────────────────────────

def test_bridge_unavailable_is_available_false():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    assert bridge.is_available() is False

def test_bridge_unavailable_list_tools_empty():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    assert bridge.list_tools() == []

def test_bridge_unavailable_list_tool_specs_empty():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    assert bridge.list_tool_specs() == []

def test_bridge_call_tool_returns_error_string_when_unavailable():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    result = bridge.call_tool("git_status", {})
    assert isinstance(result, str)
    assert "not reachable" in result

def test_bridge_describe_tool_falls_back_to_classification_when_unavailable():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    spec = bridge.describe_tool("read_repo_file")
    assert spec is not None
    assert spec.name == "read_repo_file"
    assert spec.safety_class == MCPSafetyClass.READ_ONLY

def test_bridge_not_reachable_message():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    msg = bridge.not_reachable_message()
    assert "not reachable" in msg
    assert "mq-mcp" in msg


# ── safety counts ───────────────────────────────────────────────────────────

def test_safety_class_counts():
    specs = [
        MCPToolSpec.from_name("read_file"),
        MCPToolSpec.from_name("list_files"),
        MCPToolSpec.from_name("update_file"),
        MCPToolSpec.from_name("remove_file"),
        MCPToolSpec.from_name("validate_project"),
        MCPToolSpec.from_name("mystery_tool"),
    ]
    counts: dict[str, int] = {}
    for s in specs:
        counts[s.safety_class] = counts.get(s.safety_class, 0) + 1
    assert counts[MCPSafetyClass.READ_ONLY] == 2
    assert counts[MCPSafetyClass.WRITE_CAPABLE] == 1
    assert counts[MCPSafetyClass.DANGEROUS] == 1
    assert counts[MCPSafetyClass.SUBPROCESS] == 1
    assert counts[MCPSafetyClass.UNKNOWN] == 1
