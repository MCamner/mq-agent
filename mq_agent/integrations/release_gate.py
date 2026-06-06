"""mq-mcp Release Gate v2 integration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mq_agent.tools.mcp_bridge import MultiMCPBridge


def get_release_status(repo: str = ".", target: str = "v1.4.0") -> Any:
    """Ask mq-mcp for Release Gate v2 status.

    mq-agent intentionally does not calculate release gate rules locally.
    """
    result = MultiMCPBridge().release_gate_run(repo=str(Path(repo).expanduser().resolve()), target=target)
    return _extract_release_gate_payload(result)


def _extract_release_gate_payload(result: Any) -> Any:
    if isinstance(result, dict):
        if result.get("type") == "text" and isinstance(result.get("text"), str):
            return _extract_release_gate_payload(result["text"])
        return result
    if isinstance(result, list):
        for item in result:
            extracted = _extract_release_gate_payload(item)
            if isinstance(extracted, dict) and "status" in extracted:
                return extracted
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return result
        return _extract_release_gate_payload(parsed)
    return result
