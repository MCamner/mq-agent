"""Regression tests for mq-mcp process/port ownership during startup."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from mq_agent.mcp import manager


def _server_dir(tmp_path):
    server_dir = tmp_path / "mq-mcp"
    server_dir.mkdir()
    return server_dir


def _child_env() -> dict[str, str]:
    return {
        "MQ_MCP_HOST": "127.0.0.1",
        "MQ_MCP_PORT": "8765",
        "OPENAI_API_KEY": "test-key",
    }


def test_start_refuses_untracked_listener_before_spawn(tmp_path):
    """A stale server on :8765 must win over a missing/stale PID file."""
    pid_file = tmp_path / "mq-mcp.pid"
    server_dir = _server_dir(tmp_path)

    with patch.object(manager, "PID_FILE", pid_file), \
         patch.object(manager, "is_running", return_value=False), \
         patch.object(manager, "mq_mcp_dir", return_value=server_dir), \
         patch.object(manager, "_child_env", return_value=_child_env()), \
         patch.object(manager, "_port_is_open", return_value=True), \
         patch.object(manager, "_listener_pid", return_value=87314), \
         patch.object(manager.subprocess, "Popen") as popen:
        already, pid, msg = manager.start()

    assert already is False
    assert pid is None
    assert "port 8765 already in use by PID 87314" in msg
    assert "refusing to start" in msg
    assert not pid_file.exists()
    popen.assert_not_called()


def test_start_aborts_when_post_spawn_listener_is_not_ours(tmp_path):
    """Close the bind race: another process cannot become our readiness proof."""
    pid_file = tmp_path / "mq-mcp.pid"
    server_dir = _server_dir(tmp_path)
    proc = MagicMock()
    proc.pid = 98102
    proc.poll.return_value = None

    with patch.object(manager, "PID_FILE", pid_file), \
         patch.object(manager, "is_running", return_value=False), \
         patch.object(manager, "mq_mcp_dir", return_value=server_dir), \
         patch.object(manager, "_child_env", return_value=_child_env()), \
         patch.object(manager, "_port_is_open", side_effect=[False, True]), \
         patch.object(manager, "_listener_pid", return_value=87314), \
         patch.object(manager, "_listener_belongs_to_start", return_value=False), \
         patch.object(manager.subprocess, "Popen", return_value=proc), \
         patch.object(manager.time, "sleep"):
        already, pid, msg = manager.start()

    assert already is False
    assert pid is None
    assert "owned by PID 87314, not started PID 98102" in msg
    assert not pid_file.exists()
    proc.terminate.assert_called_once_with()


def test_start_accepts_listener_owned_by_spawned_process_group(tmp_path):
    pid_file = tmp_path / "mq-mcp.pid"
    server_dir = _server_dir(tmp_path)
    proc = MagicMock()
    proc.pid = 98102
    proc.poll.return_value = None

    with patch.object(manager, "PID_FILE", pid_file), \
         patch.object(manager, "is_running", return_value=False), \
         patch.object(manager, "mq_mcp_dir", return_value=server_dir), \
         patch.object(manager, "_child_env", return_value=_child_env()), \
         patch.object(manager, "_port_is_open", side_effect=[False, True]), \
         patch.object(manager, "_listener_pid", return_value=98103), \
         patch.object(manager, "_listener_belongs_to_start", return_value=True), \
         patch.object(manager.subprocess, "Popen", return_value=proc), \
         patch.object(manager.time, "sleep"):
        already, pid, msg = manager.start()

    assert already is False
    assert pid == 98102
    assert msg == "started (PID 98102)"
    assert pid_file.read_text().strip() == "98102"


def test_start_does_not_publish_pid_for_immediate_failure(tmp_path):
    pid_file = tmp_path / "mq-mcp.pid"
    server_dir = _server_dir(tmp_path)
    proc = MagicMock()
    proc.pid = 98102
    proc.poll.return_value = 1
    proc.returncode = 1

    with patch.object(manager, "PID_FILE", pid_file), \
         patch.object(manager, "is_running", return_value=False), \
         patch.object(manager, "mq_mcp_dir", return_value=server_dir), \
         patch.object(manager, "_child_env", return_value=_child_env()), \
         patch.object(manager, "_port_is_open", return_value=False), \
         patch.object(manager.subprocess, "Popen", return_value=proc), \
         patch.object(manager.time, "sleep"):
        already, pid, msg = manager.start()

    assert already is False
    assert pid is None
    assert "server exited immediately" in msg
    assert not pid_file.exists()


def test_start_rejects_invalid_port_configuration(tmp_path):
    server_dir = _server_dir(tmp_path)
    env = _child_env()
    env["MQ_MCP_PORT"] = "not-a-port"

    with patch.object(manager, "PID_FILE", tmp_path / "mq-mcp.pid"), \
         patch.object(manager, "is_running", return_value=False), \
         patch.object(manager, "mq_mcp_dir", return_value=server_dir), \
         patch.object(manager, "_child_env", return_value=env), \
         patch.object(manager.subprocess, "Popen") as popen:
        already, pid, msg = manager.start()

    assert already is False
    assert pid is None
    assert msg == "invalid MQ_MCP_HOST/MQ_MCP_PORT configuration"
    popen.assert_not_called()
