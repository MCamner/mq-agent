"""Process lifecycle management for mq-mcp background server."""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

from mq_agent.core.credentials import install_openai_api_key
from mq_agent.core.mq_mcp_endpoint import _valid_port, resolve_mq_mcp_endpoint
from mq_agent.core.mq_mcp_layout import mq_mcp_run_dir

try:
    from dotenv import dotenv_values
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False

PID_FILE = Path.home() / ".mq-agent" / "mq-mcp.pid"
_DEFAULT_HOST = "127.0.0.1"


def _child_env(server_dir: Path) -> dict:
    """Build mq-mcp's child environment without accepting secrets from .env."""
    base = os.environ.copy()
    env_file = server_dir / ".env"
    if _HAS_DOTENV and env_file.exists():
        base.update({
            k: v
            for k, v in dotenv_values(env_file).items()
            if v is not None and k != "OPENAI_API_KEY"
        })

    # OPENAI_API_KEY has one process-scoped precedence rule across mq-agent and
    # mq-mcp: an explicitly inherited value wins; otherwise macOS Keychain is
    # consulted. A stale .env secret can therefore never override a rotated key.
    install_openai_api_key(base)

    # The child binds the canonical target, not whatever it inherited. An
    # explicitly configured endpoint outranks MQ_MCP_HOST/MQ_MCP_PORT, so
    # passing the inherited variables through would let mq-agent probe one port
    # and the process bind another. Only the child's copy is written; the
    # parent's environment is left alone.
    target = resolve_mq_mcp_endpoint()
    if target.usable and target.host and target.port:
        base["MQ_MCP_HOST"] = target.host
        base["MQ_MCP_PORT"] = str(target.port)
    else:
        base.pop("MQ_MCP_HOST", None)
        base.pop("MQ_MCP_PORT", None)
    return base


def _endpoint(env: dict) -> tuple[str, int] | None:
    """Return the mq-mcp bind endpoint declared for the child process.

    Read back from the child environment `_child_env` already stamped, so the
    preflight port check and the process cannot disagree about the target.
    """
    host = str(env.get("MQ_MCP_HOST") or "").strip()
    port = _valid_port(env.get("MQ_MCP_PORT"))
    if not host or port is None:
        return None
    return host, port


def _probe_host(host: str) -> str:
    """Map wildcard bind addresses to a connectable loopback probe address."""
    if host in {"0.0.0.0", "::", "[::]"}:
        return _DEFAULT_HOST
    return host


def _port_is_open(host: str, port: int) -> bool:
    """Return True when something is already accepting TCP connections."""
    try:
        with socket.create_connection((_probe_host(host), port), timeout=0.15):
            return True
    except OSError:
        return False


def _listener_pid(port: int) -> int | None:
    """Best-effort PID lookup for a TCP listener, used only for diagnostics."""
    lsof = shutil.which("lsof")
    if lsof is None:
        return None
    try:
        result = subprocess.run(
            [lsof, "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        try:
            return int(line.strip())
        except ValueError:
            continue
    return None


def _listener_belongs_to_start(listener_pid: int, started_pid: int) -> bool | None:
    """Check whether a listener belongs to the process group we just spawned.

    start_new_session=True makes the spawned PID the process-group leader. uv may
    exec the server itself or keep a child process alive; both cases remain in
    that group unless the child explicitly creates another session. None means
    the platform cannot answer and ownership should not be guessed.
    """
    if not hasattr(os, "getpgid"):
        return None
    try:
        return os.getpgid(listener_pid) == started_pid
    except (OSError, ProcessLookupError):
        return None


def mq_mcp_dir() -> Path:
    """The directory holding server.py, which is where the child must run.

    Resolved through `mq_mcp_layout`, which reads MQ_MCP_DIR once for every
    consumer. Returns the configured path unchanged when neither shape holds;
    start() reports that as a missing directory rather than this raising.
    """
    return mq_mcp_run_dir()


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

    child_env = _child_env(server_dir)
    endpoint = _endpoint(child_env)
    if endpoint is None:
        return False, None, "invalid MQ_MCP_HOST/MQ_MCP_PORT configuration"
    host, port = endpoint

    # A PID file only proves what mq-agent previously wrote. The port is the
    # actual service boundary. Refuse to start if another process already owns
    # it, otherwise a short-lived child can fail to bind while mq-agent reports
    # STARTED and later reviews silently talk to the stale server.
    if _port_is_open(host, port):
        owner = _listener_pid(port)
        owner_note = f" by PID {owner}" if owner is not None else ""
        return (
            False,
            None,
            f"port {port} already in use{owner_note}; refusing to start mq-mcp",
        )

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        ["uv", "run", "mcp", "run", "server.py", "--transport", "sse"],
        cwd=server_dir,
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Brief wait catches immediate failures. Do not publish a PID file until the
    # process has survived this boundary; a dead PID must never become evidence
    # that a service started successfully.
    time.sleep(0.4)
    if proc.poll() is not None:
        return False, None, f"server exited immediately (rc={proc.returncode})"

    # If the listener is already ready, verify that it belongs to the process
    # group we just created. This closes the race where another process claims
    # the port between the preflight probe and mq-mcp's bind.
    if _port_is_open(host, port):
        owner = _listener_pid(port)
        if owner is not None:
            belongs = _listener_belongs_to_start(owner, proc.pid)
            if belongs is False:
                try:
                    proc.terminate()
                except OSError:
                    pass
                return (
                    False,
                    None,
                    f"port {port} is owned by PID {owner}, not started PID {proc.pid}; "
                    "mq-mcp start aborted",
                )

    PID_FILE.write_text(str(proc.pid))
    return False, proc.pid, f"started (PID {proc.pid})"


def stop() -> tuple[bool, int | None, str]:
    """Stop mq-mcp.

    Returns (was_running, pid, message).
    """
    pid = read_pid()

    if pid is None:
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
