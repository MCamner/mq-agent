"""MQ ecosystem stack-health summary for terminal operators."""
from __future__ import annotations

import shutil
from typing import Any


def get_stack_health() -> dict[str, Any]:
    """Return lightweight status for the MQ operator stack."""
    from mq_agent.mcp.manager import is_running as mq_mcp_process_running
    from mq_agent.mcp.manager import read_pid
    from mq_agent.tools.mcp_bridge import MultiMCPBridge
    from mq_agent.tools.signal_tools import signal_available

    bridge = MultiMCPBridge()
    server_statuses = bridge.get_server_statuses()
    components: list[dict[str, Any]] = [
        {
            "name": "mq-agent",
            "status": "pass",
            "detail": "CLI available",
            "required": True,
        },
        {
            "name": "mq-mcp",
            "status": "pass" if server_statuses.get("mq-mcp", {}).get("available") else "warning",
            "detail": _mcp_detail(server_statuses.get("mq-mcp", {}), read_pid(), mq_mcp_process_running()),
            "required": False,
        },
        {
            "name": "repo-signal",
            "status": "pass" if signal_available() else "warning",
            "detail": "available" if signal_available() else "not installed",
            "required": False,
            "next_action": "" if signal_available() else "uv pip install repo-signal",
        },
        {
            "name": "mq-image-analyze",
            "status": "pass" if server_statuses.get("mq-image-analyze", {}).get("available") else "warning",
            "detail": _mcp_detail(server_statuses.get("mq-image-analyze", {}), None, False),
            "required": False,
            "next_action": "Start mq-image-analyze on :8766"
            if not server_statuses.get("mq-image-analyze", {}).get("available")
            else "",
        },
        {
            "name": "mq-hal",
            "status": "pass" if shutil.which("mq-hal") or shutil.which("mqlaunch") else "warning",
            "detail": "available" if shutil.which("mq-hal") or shutil.which("mqlaunch") else "not found",
            "required": False,
            "next_action": "Install or expose mq-hal/mqlaunch on PATH"
            if not (shutil.which("mq-hal") or shutil.which("mqlaunch"))
            else "",
        },
    ]

    status = "pass" if all(item["status"] == "pass" for item in components) else "warning"
    return {"status": status, "components": components}


def render_stack_health(report: dict[str, Any]) -> str:
    lines = ["MQ STACK HEALTH", "", f"Overall: {str(report.get('status', 'unknown')).upper()}", "", "Components:"]
    for item in report.get("components", []):
        status = str(item.get("status", "unknown")).upper()
        name = item.get("name", "unknown")
        detail = item.get("detail", "")
        lines.append(f"- {status}: {name} — {detail}")
        next_action = str(item.get("next_action", "")).strip()
        if next_action:
            lines.append(f"  next: {next_action}")
    return "\n".join(lines)


def _mcp_detail(status: dict[str, Any], pid: int | None, process_running: bool) -> str:
    if not status:
        return "not configured"
    endpoint = status.get("endpoint", "unknown")
    if not status.get("available"):
        return f"unreachable at {endpoint}"
    tools = status.get("tools", 0)
    if pid:
        process = f", PID {pid}" if process_running else f", stale PID {pid}"
    else:
        process = ""
    return f"reachable at {endpoint}, tools={tools}{process}"
