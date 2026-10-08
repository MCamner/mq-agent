"""Read-only CodeGraph runtime adapter for Hybrid Retrieval evidence.

Prefer an already-connected MCP tool. When mq-agent is running outside an MCP
client, fall back to CodeGraph's documented local CLI equivalent so the same
repository index can still be measured without inventing an HTTP transport.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

CODEGRAPH_TOOL = "codegraph_explore"
CODEGRAPH_TIMEOUT_SECONDS = 30


def _resolved_root(root: Path | None) -> Path:
    return (root or Path.cwd()).expanduser().resolve()


def _cli_search(query: str, root: Path | None) -> Any:
    project = _resolved_root(root)
    if not project.is_dir():
        return {
            "ok": False,
            "reason": "CodeGraph project root is not a directory",
        }
    if not (project / ".codegraph").is_dir():
        return {
            "ok": False,
            "reason": "CodeGraph index is unavailable for the selected project root",
        }

    executable = shutil.which("codegraph")
    if executable is None:
        return {
            "ok": False,
            "reason": "CodeGraph CLI is not installed or not on PATH",
        }

    try:
        completed = subprocess.run(
            [executable, "explore", query],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=CODEGRAPH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "reason": f"CodeGraph explore timed out after {CODEGRAPH_TIMEOUT_SECONDS}s",
        }
    except OSError as exc:
        return {
            "ok": False,
            "reason": f"CodeGraph CLI could not start: {exc}",
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        detail = stderr or stdout or f"exit {completed.returncode}"
        return {
            "ok": False,
            "reason": f"CodeGraph explore failed: {detail}"[:240],
        }
    if not stdout:
        return {
            "ok": False,
            "reason": "CodeGraph explore returned no output",
        }
    return stdout


def search_codegraph(query: str, root: Path | None = None) -> Any:
    """Search CodeGraph read-only, preferring MCP and falling back to local CLI."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    names = {spec.name for spec in bridge.list_tool_specs()}
    if CODEGRAPH_TOOL in names:
        args: dict[str, Any] = {"query": query}
        if root is not None:
            args["projectPath"] = str(_resolved_root(root))
        return bridge.call_tool(CODEGRAPH_TOOL, args)

    return _cli_search(query, root)
