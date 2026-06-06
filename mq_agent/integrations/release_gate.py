"""mq-mcp Release Gate v2 integration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mq_agent.tools.mcp_bridge import MultiMCPBridge


def get_release_status(repo: str = ".", target: str = "v1.4.0") -> Any:
    """Ask mq-mcp for Release Gate v2 status.

    mq-agent intentionally does not calculate release gate rules locally.
    """
    return MultiMCPBridge().release_gate_run(repo=str(Path(repo).expanduser().resolve()), target=target)
