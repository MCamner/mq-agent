"""Where mq-mcp answers: one target, probed, bound, and written to.

Two resolvers decided this, and neither read the other's input:

    runtime_identity.mq_mcp_endpoint   MQ_MCP_HOST / MQ_MCP_PORT, else :8765
    MultiMCPBridge via get_mcp_servers config, else http://localhost:8765

`MQ_MCP_PORT=9001` therefore moved the probe and left the write on 8765, and a
configured entry moved the write and left the probe on 8765 — the divergence
runs both ways. The receiver gate refused the mismatch rather than writing
under an unverified identity, so this was a contract defect rather than an
incident; but a system should never verify one process and write to another.

The precedence, decided once:

    explicit mq-mcp config  →  MQ_MCP_HOST / MQ_MCP_PORT  →  127.0.0.1:8765

"Explicit" is what the operator put in `~/.mq-agent/config.json`.
`get_mcp_servers()` injects a synthetic mq-mcp entry when none is set, so
reading precedence from it would make the environment layer unreachable — a
default nobody wrote would outrank a variable the operator set.

Absence is not malformation. A missing config falls through to the next layer.
A config that is present and wrong fails closed, because silently falling back
would send evidence somewhere the operator did not ask for, and the operator
would have no way to see that their setting was ignored.

The target also governs the child process. When mq-agent starts mq-mcp, the
child's `MQ_MCP_HOST` and `MQ_MCP_PORT` are set from the resolved target, so a
configured endpoint cannot be probed at one port while the process binds
another. Only the child's environment is written; the parent's is left alone,
or the decision would leak into everything else this CLI starts.

Remote targets are refused rather than attempted. mq-mcp's bridge is
loopback-only and its Host gate accepts 127.0.0.1, localhost and ::1, so
accepting a remote URL would offer a contract mq-mcp does not implement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

#: Hosts mq-mcp's own Host gate accepts. Anything else is not reachable there.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

CONFIG = "config"
ENV = "env"
DEFAULT = "default"

HOST_VAR = "MQ_MCP_HOST"
PORT_VAR = "MQ_MCP_PORT"


@dataclass(frozen=True)
class MqMcpEndpoint:
    """The resolved target, or the reason there is none.

    `source` records which layer decided, so an operator can see why their
    setting did or did not apply. `reason` is set only when nothing resolved.
    """

    base_url: str | None
    host: str | None
    port: int | None
    source: str
    reason: str | None = None

    @property
    def usable(self) -> bool:
        """Whether anything may be probed, started, or written at this target."""
        return self.base_url is not None


def _refused(reason: str) -> MqMcpEndpoint:
    return MqMcpEndpoint(base_url=None, host=None, port=None, source=reason.split("-")[0],
                         reason=reason)


def _resolved(host: str, port: int, source: str) -> MqMcpEndpoint:
    rendered = f"[{host}]" if ":" in host else host
    return MqMcpEndpoint(
        base_url=f"http://{rendered}:{port}", host=host, port=port, source=source
    )


def _valid_port(raw: object) -> int | None:
    """A port is an integer in range. "80.5" and "0" are not ports."""
    try:
        port = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _from_config() -> MqMcpEndpoint | None:
    """The explicit entry, or None when the operator set no mq-mcp target.

    Returns a refusal — not None — when the config is present and wrong, so the
    caller can tell "nothing was set" from "what was set cannot be used".
    """
    from mq_agent.core.config import load_config

    servers = load_config().get("mcp_servers")
    if servers is None:
        return None
    if not isinstance(servers, dict):
        return _refused("config-malformed")
    if "mq-mcp" not in servers:
        return None

    raw = servers["mq-mcp"]
    if not isinstance(raw, str) or not raw.strip():
        return _refused("config-malformed")

    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return _refused("config-malformed")
    if parsed.hostname not in LOOPBACK_HOSTS or parsed.scheme != "http":
        # mq-mcp serves plain HTTP on loopback only. Anything else names a
        # service this contract cannot describe.
        return _refused("config-not-loopback")

    port = _valid_port(parsed.port) if parsed.port is not None else DEFAULT_PORT
    if port is None:
        return _refused("config-malformed")
    return _resolved(parsed.hostname, port, CONFIG)


def _from_env() -> MqMcpEndpoint | None:
    """The variables, or None when neither is set.

    Either one alone is enough to decide; the other keeps its default. A
    variable that is set and unusable fails closed rather than falling through,
    for the same reason a broken config does.
    """
    raw_host = os.environ.get(HOST_VAR)
    raw_port = os.environ.get(PORT_VAR)
    if not (raw_host or raw_port):
        return None

    host = (raw_host or DEFAULT_HOST).strip()
    if not host:
        return _refused("env-malformed")
    if host not in LOOPBACK_HOSTS:
        return _refused("env-not-loopback")

    port = _valid_port(raw_port) if raw_port else DEFAULT_PORT
    if port is None:
        return _refused("env-malformed")
    return _resolved(host, port, ENV)


def resolve_mq_mcp_endpoint() -> MqMcpEndpoint:
    """The one mq-mcp target: probe it, bind it, write to it.

    Never raises. A target that cannot be used comes back unusable with a
    reason, and every consumer refuses rather than reaching for a fallback.
    """
    for layer in (_from_config, _from_env):
        resolved = layer()
        if resolved is not None:
            return resolved
    return _resolved(DEFAULT_HOST, DEFAULT_PORT, DEFAULT)
