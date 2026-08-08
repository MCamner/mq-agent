"""Tests for MCP registry, bridge, safety classification, and process manager."""
import json
from unittest.mock import MagicMock, patch

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

def test_classify_visual_perception_tools_read_only():
    assert classify_tool_name("observe_architecture") == MCPSafetyClass.READ_ONLY
    assert classify_tool_name("image_ocr") == MCPSafetyClass.READ_ONLY
    assert classify_tool_name("analyze_ui") == MCPSafetyClass.READ_ONLY
    assert classify_tool_name("compare_images") == MCPSafetyClass.READ_ONLY

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
    assert classify_tool_name("review_diff") == MCPSafetyClass.UNKNOWN
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

def test_spec_from_dict_contract_class_maps_to_safety_label():
    assert MCPToolSpec.from_dict({"name": "review_diff", "class": "A"}).read_only is True
    assert MCPToolSpec.from_dict({"name": "repo_signal_analyze", "class": "B"}).read_only is True
    assert MCPToolSpec.from_dict({"name": "update_repo_file", "class": "C"}).write_capable is True
    assert MCPToolSpec.from_dict({"name": "open_in_app", "class": "D"}).subprocess is True


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

def test_bridge_not_reachable_message_suggests_start():
    from mq_agent.tools.mcp_bridge import MCPBridge
    bridge = MCPBridge(endpoint="http://localhost:19998")
    msg = bridge.not_reachable_message()
    assert "mq-agent mcp start" in msg

def test_default_mcp_servers_include_visual_perception_server():
    from mq_agent.core import config

    with patch.object(config, "load_config", return_value={"mcp_servers": {}}):
        servers = config.get_mcp_servers()

    assert servers["mq-mcp"] == "http://localhost:8765"
    assert servers["mq-image-analyze"] == "http://localhost:8766"

def test_default_mcp_servers_preserve_configured_visual_endpoint():
    from mq_agent.core import config

    configured = {
        "mcp_servers": {
            "mq-image-analyze": "http://localhost:9999",
        }
    }
    with patch.object(config, "load_config", return_value=configured):
        servers = config.get_mcp_servers()

    assert servers["mq-image-analyze"] == "http://localhost:9999"

def test_multi_bridge_routes_visual_tool_to_mq_image_analyze():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    image_bridge = MagicMock()
    image_bridge.list_tools.return_value = ["observe_architecture", "image_ocr"]
    image_bridge.call_tool.return_value = {"schema": "visual_architecture_observation.v1"}
    mcp_bridge = MagicMock()
    mcp_bridge.list_tools.return_value = ["review_file"]
    bridge.bridges = {"mq-mcp": mcp_bridge, "mq-image-analyze": image_bridge}

    result = bridge.call_tool("observe_architecture", {"image_path": "docs/arch.png"})

    assert result == {"schema": "visual_architecture_observation.v1"}
    image_bridge.call_tool.assert_called_once_with("observe_architecture", {"image_path": "docs/arch.png"})
    mcp_bridge.call_tool.assert_not_called()

def test_multi_bridge_describe_visual_tool_uses_image_source_hint():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    mcp_bridge = MagicMock()
    mcp_bridge.list_tools.return_value = []
    mcp_bridge.describe_tool.return_value = MCPToolSpec.from_name("observe_architecture")
    image_bridge = MagicMock()
    image_bridge.list_tools.return_value = []
    image_bridge.describe_tool.return_value = MCPToolSpec.from_name("observe_architecture")
    bridge.bridges = {"mq-mcp": mcp_bridge, "mq-image-analyze": image_bridge}

    spec = bridge.describe_tool("observe_architecture")

    assert spec.safety_class == MCPSafetyClass.READ_ONLY
    assert spec.source == "mq-image-analyze"


# ── server down vs tool missing ─────────────────────────────────────────────
#
# A down server and a server without the tool both leave list_tools() empty, so
# the required-tool error has to ask is_available() to tell them apart. The
# operator fix differs: start mq-mcp, or upgrade it.

def _bridge_with(tools: list[str], available: bool) -> MagicMock:
    fake = MagicMock()
    fake.list_tools.return_value = tools
    fake.is_available.return_value = available
    fake.endpoint = "http://localhost:8765"
    return fake

def test_required_tool_reports_unreachable_server_not_missing_tool():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    bridge.bridges = {"mq-mcp": _bridge_with([], available=False)}

    result = bridge._call_required_tool("review_diff", {})

    assert result["ok"] is False
    assert "No MCP server is reachable" in result["error"]
    assert "is not available" not in result["error"]
    assert "mq-agent mcp start" in result["hint"]

def test_required_tool_still_reports_missing_tool_when_server_is_up():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    bridge.bridges = {"mq-mcp": _bridge_with(["review_file"], available=True)}

    result = bridge._call_required_tool("review_diff", {})

    assert result["ok"] is False
    assert "mq-mcp tool 'review_diff' is not available." == result["error"]
    assert "upgrade" in result["hint"].lower()

def test_review_diff_reports_unreachable_server():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    bridge.bridges = {"mq-mcp": _bridge_with([], available=False)}

    result = bridge.review_diff({})

    assert "No MCP server is reachable" in result["error"]

def test_risk_review_reports_unreachable_server_before_upgrade_hint():
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    bridge.bridges = {"mq-mcp": _bridge_with([], available=False)}

    result = bridge.review_diff({"risk": True})

    assert "No MCP server is reachable" in result["error"]
    assert "--risk requires" not in result["error"]


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


# ── mq_agent.mcp.manager ───────────────────────────────────────────────────

def test_manager_read_pid_no_file(tmp_path):
    from mq_agent.mcp import manager
    with patch.object(manager, "PID_FILE", tmp_path / "mq-mcp.pid"):
        assert manager.read_pid() is None

def test_manager_is_running_no_pid_file(tmp_path):
    from mq_agent.mcp import manager
    with patch.object(manager, "PID_FILE", tmp_path / "mq-mcp.pid"):
        assert manager.is_running() is False

def test_manager_stop_not_running(tmp_path):
    from mq_agent.mcp import manager
    with patch.object(manager, "PID_FILE", tmp_path / "mq-mcp.pid"):
        was_running, pid, msg = manager.stop()
    assert was_running is False
    assert pid is None
    assert "not running" in msg

def test_manager_start_missing_dir(tmp_path):
    from mq_agent.mcp import manager
    pid_file = tmp_path / "mq-mcp.pid"
    missing_dir = tmp_path / "nonexistent"
    with patch.object(manager, "PID_FILE", pid_file):
        with patch.object(manager, "mq_mcp_dir", return_value=missing_dir):
            already, pid, msg = manager.start()
    assert already is False
    assert pid is None
    assert "not found" in msg

def test_manager_start_success(tmp_path):
    from mq_agent.mcp import manager
    pid_file = tmp_path / "mq-mcp.pid"
    fake_dir = tmp_path / "mq-mcp"
    fake_dir.mkdir()

    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_proc.poll.return_value = None

    with patch.object(manager, "PID_FILE", pid_file):
        with patch.object(manager, "mq_mcp_dir", return_value=fake_dir):
            with patch("mq_agent.mcp.manager.subprocess.Popen", return_value=mock_proc):
                with patch("mq_agent.mcp.manager.time.sleep"):
                    already, pid, msg = manager.start()

    assert already is False
    assert pid == 99999
    assert "started" in msg
    assert pid_file.read_text().strip() == "99999"

def test_manager_start_already_running(tmp_path):
    from mq_agent.mcp import manager
    pid_file = tmp_path / "mq-mcp.pid"
    pid_file.write_text("12345")

    with patch.object(manager, "PID_FILE", pid_file):
        with patch("mq_agent.mcp.manager.os.kill", return_value=None):
            already, pid, msg = manager.start()

    assert already is True
    assert pid == 12345
    assert "already running" in msg

def test_manager_stop_kills_process(tmp_path):
    from mq_agent.mcp import manager
    pid_file = tmp_path / "mq-mcp.pid"
    pid_file.write_text("12345")

    with patch.object(manager, "PID_FILE", pid_file):
        with patch("mq_agent.mcp.manager.os.kill"):
            was_running, pid, msg = manager.stop()

    assert was_running is True
    assert pid == 12345
    assert "stopped" in msg
    assert not pid_file.exists()


# ── mcp start/stop CLI ──────────────────────────────────────────────────────

def test_cli_mcp_start_json_success(tmp_path):
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager

    runner = CliRunner()
    with patch.object(manager, "start", return_value=(False, 42000, "started (PID 42000)")):
        result = runner.invoke(app, ["mcp", "start", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["pid"] == 42000
    assert data["already_running"] is False

def test_cli_mcp_start_json_already_running(tmp_path):
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager

    runner = CliRunner()
    with patch.object(manager, "start", return_value=(True, 42000, "already running (PID 42000)")):
        result = runner.invoke(app, ["mcp", "start", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["already_running"] is True
    assert data["ok"] is True

def test_cli_mcp_start_json_failure(tmp_path):
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager

    runner = CliRunner()
    with patch.object(manager, "start", return_value=(False, None, "mq-mcp directory not found: /missing")):
        result = runner.invoke(app, ["mcp", "start", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["pid"] is None

def test_cli_mcp_stop_json_was_running():
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager

    runner = CliRunner()
    with patch.object(manager, "stop", return_value=(True, 42000, "stopped (PID 42000)")):
        result = runner.invoke(app, ["mcp", "stop", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["was_running"] is True
    assert data["pid"] == 42000

def test_cli_mcp_stop_json_not_running():
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager

    runner = CliRunner()
    with patch.object(manager, "stop", return_value=(False, None, "not running")):
        result = runner.invoke(app, ["mcp", "stop", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["was_running"] is False

def test_cli_mcp_status_json_process_running():
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager

    runner = CliRunner()
    with patch.object(manager, "is_running", return_value=True):
        with patch.object(manager, "read_pid", return_value=42000):
            result = runner.invoke(app, ["mcp", "status", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["mq_mcp_process"]["running"] is True
    assert data["mq_mcp_process"]["pid"] == 42000


def test_mcp_status_enrichment_shown_when_available():
    """mcp status renders semantic memory count and contract status when present."""
    from typer.testing import CliRunner

    from mq_agent.main import app
    from mq_agent.mcp import manager
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    enriched_statuses = {
        "mq-mcp": {
            "available": True,
            "endpoint": "http://localhost:8765",
            "tools": 3,
            "specs": [],
            "semantic_memory_count": 7,
            "contract": {"ok": True, "version": "1.4.0"},
        }
    }
    runner = CliRunner()
    with patch.object(manager, "is_running", return_value=False):
        with patch.object(manager, "read_pid", return_value=None):
            with patch.object(MultiMCPBridge, "get_server_statuses", return_value=enriched_statuses):
                result = runner.invoke(app, ["mcp", "status"])

    assert result.exit_code == 0
    assert "7 item" in result.output
    assert "valid" in result.output


def test_get_server_statuses_enriches_when_tools_available():
    """get_server_statuses adds contract and semantic_memory_count when tools present."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    fake_tools = ["validate_orchestration_contract", "list_semantic_memory"]
    fake_contract = {"ok": True}
    fake_memory = [{"key": "k1"}, {"key": "k2"}]

    with patch.object(bridge, "bridges") as mock_bridges:
        fake_bridge = MagicMock()
        fake_bridge.is_available.return_value = True
        fake_bridge.list_tool_specs.return_value = []
        fake_bridge.list_tools.return_value = fake_tools
        fake_bridge.call_tool.side_effect = lambda name, _: (
            fake_contract if name == "validate_orchestration_contract" else fake_memory
        )
        fake_bridge.endpoint = "http://localhost:8765"
        mock_bridges.items.return_value = [("mq-mcp", fake_bridge)]

        statuses = bridge.get_server_statuses()

    assert statuses["mq-mcp"]["contract"] == {"ok": True}
    assert statuses["mq-mcp"]["semantic_memory_count"] == 2
