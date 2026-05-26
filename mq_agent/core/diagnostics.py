"""Environment checks for `mq-agent doctor`.

Returns plain data — no Rich, no console, no CLI imports.
"""
from __future__ import annotations

import subprocess
import sys


def run_checks() -> list[tuple[str, bool, str]]:
    """Run all environment checks.

    Returns a list of (name, ok, fix_action) tuples.  fix_action is empty
    when the check passes.
    """
    import os

    checks: list[tuple[str, bool, str]] = []

    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    checks.append(("OPENAI_API_KEY", has_key, "export OPENAI_API_KEY=sk-..."))

    git_ok = subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    checks.append(("git", git_ok, "Install git"))

    uv_ok = subprocess.run(["uv", "--version"], capture_output=True).returncode == 0
    checks.append(("uv", uv_ok, "curl -LsSf https://astral.sh/uv/install.sh | sh"))

    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python ≥ 3.11", py_ok, f"Upgrade Python (have {sys.version.split()[0]})"))

    from mq_agent.tools.signal_tools import signal_available
    checks.append(("repo-signal", signal_available(), "uv pip install repo-signal"))

    try:
        import httpx
        mcp_ok = httpx.get("http://localhost:8765/health", timeout=1).status_code == 200
    except Exception:
        mcp_ok = False
    checks.append(("mq-mcp (optional)", mcp_ok, "Start mq-mcp on :8765"))

    return checks


def required_checks_pass(checks: list[tuple[str, bool, str]]) -> bool:
    """True when the first 4 (required) checks all pass."""
    return all(ok for _, ok, _ in checks[:4])
