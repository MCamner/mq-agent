"""Process lifecycle management for mq-mcp background server."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

PID_FILE = Path.home() / ".mq-agent" / "mq-mcp.pid"
_DEFAULT_MQ_MCP_DIR = Path.home() / "mq-mcp" / "mq-mcp"


def mq_mcp_dir() -> Path:
    raw = os.environ.get("MQ_MCP_DIR", "")
    return Path(raw).expanduser().resolve() if raw else _DEFAULT_MQ_MCP_DIR


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def is_running() -> bool:
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return False
    except PermissionError:
        return True


def start() -> tuple[bool, int | None, str]:
    """Start mq-mcp in background.

    Returns (already_running, pid, message).
    """
    if is_running():
        pid = read_pid()
        return True, pid, f"already running (PID {pid})"

    server_dir = mq_mcp_dir()
    if not server_dir.exists():
        return False, None, f"mq-mcp directory not found: {server_dir}"

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        ["uv", "run", "mcp", "run", "server.py", "--transport", "sse"],
        cwd=server_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    PID_FILE.write_text(str(proc.pid))

    # brief wait to catch immediate crash
    time.sleep(0.4)
    if proc.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        return False, None, f"server exited immediately (rc={proc.returncode})"

    return False, proc.pid, f"started (PID {proc.pid})"


def stop() -> tuple[bool, int | None, str]:
    """Stop mq-mcp.

    Returns (was_running, pid, message).
    """
    pid = read_pid()

    if pid is None:
        if not is_running():
            return False, None, "not running"

    if not is_running():
        return False, pid, "not running (stale PID file removed)"

    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return True, pid, f"stopped (PID {pid})"
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return False, pid, f"process {pid} not found (PID file removed)"
    except PermissionError:
        return False, pid, f"permission denied killing PID {pid}"
