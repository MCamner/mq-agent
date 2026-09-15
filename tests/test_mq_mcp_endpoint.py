"""One target for mq-mcp: probed, bound, and written to.

Two resolvers decided where mq-mcp was, and neither read the other's input:

    runtime_identity.mq_mcp_endpoint   MQ_MCP_HOST / MQ_MCP_PORT, else :8765
    MultiMCPBridge via get_mcp_servers config, else http://localhost:8765

So `MQ_MCP_PORT=9001` moved the probe and left the write on 8765, and a
configured entry moved the write and left the probe on 8765. The receiver gate
refused the mismatch rather than writing under an unverified identity, which is
why this was a contract defect and not an incident — but a system should never
verify one process and write to another.

The precedence, decided once:

    explicit mq-mcp config  →  MQ_MCP_HOST / MQ_MCP_PORT  →  127.0.0.1:8765

"Explicit" means what the operator actually put in the config file.
`get_mcp_servers()` injects a synthetic default for mq-mcp when none is set, so
reading precedence from it would make the environment layer unreachable.

Absence is not malformation. A missing config falls through to the next layer;
a config that is present and wrong fails closed, because silently falling back
would send evidence somewhere the operator did not ask for.

mq-mcp's own bridge is loopback-only and its Host gate accepts 127.0.0.1,
localhost and ::1. Accepting a remote URL here would offer a contract mq-mcp
does not implement, so it is refused rather than attempted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq_agent.core import mq_mcp_endpoint as endpoint_mod
from mq_agent.core.mq_mcp_endpoint import resolve_mq_mcp_endpoint

CONFIG, ENV, DEFAULT = "config", "env", "default"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """No config file and no environment unless a test asks for one."""
    from mq_agent.core import config as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.delenv("MQ_MCP_HOST", raising=False)
    monkeypatch.delenv("MQ_MCP_PORT", raising=False)
    return tmp_path


def _config(tmp_path: Path, payload: object) -> None:
    (tmp_path / "config.json").write_text(json.dumps(payload), encoding="utf-8")


# ── precedence ──────────────────────────────────────────────────────────────

def test_explicit_config_wins_over_the_environment(_isolated, monkeypatch):
    """The conflict case this slice exists for."""
    _config(_isolated, {"mcp_servers": {"mq-mcp": "http://localhost:8765"}})
    monkeypatch.setenv("MQ_MCP_PORT", "9001")

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.source == CONFIG
    assert resolved.port == 8765
    assert resolved.host == "localhost"
    assert resolved.base_url is not None and "9001" not in resolved.base_url


def test_the_environment_is_used_when_no_config_names_mq_mcp(_isolated, monkeypatch):
    monkeypatch.setenv("MQ_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MQ_MCP_PORT", "9001")

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.source == ENV
    assert (resolved.host, resolved.port) == ("127.0.0.1", 9001)
    assert resolved.base_url == "http://127.0.0.1:9001"


def test_a_config_without_an_mq_mcp_entry_is_not_a_config(_isolated, monkeypatch):
    """Absence falls through. Only a present-and-wrong value fails closed."""
    _config(_isolated, {"mcp_servers": {"mq-image-analyze": "http://localhost:8766"}})
    monkeypatch.setenv("MQ_MCP_PORT", "9001")

    assert resolve_mq_mcp_endpoint().source == ENV


def test_nothing_configured_is_the_loopback_default(_isolated):
    resolved = resolve_mq_mcp_endpoint()

    assert resolved.source == DEFAULT
    assert resolved.base_url == "http://127.0.0.1:8765"


def test_the_synthetic_default_never_counts_as_explicit_config(_isolated, monkeypatch):
    """`get_mcp_servers()` always returns an mq-mcp entry.

    Reading precedence from it would make the environment layer unreachable —
    a default nobody wrote would outrank a variable the operator set.
    """
    from mq_agent.core.config import get_mcp_servers

    monkeypatch.setenv("MQ_MCP_PORT", "9001")
    assert get_mcp_servers()["mq-mcp"], "the synthetic entry is still there"

    assert resolve_mq_mcp_endpoint().source == ENV


# ── fail closed ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "payload",
    [
        {"mcp_servers": []},
        {"mcp_servers": "http://localhost:8765"},
        {"mcp_servers": 3},
    ],
    ids=["list", "string", "number"],
)
def test_a_malformed_mcp_servers_block_fails_closed(_isolated, monkeypatch, payload):
    _config(_isolated, payload)
    monkeypatch.setenv("MQ_MCP_PORT", "9001")

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is False
    assert resolved.reason == "config-malformed"
    assert resolved.base_url is None, "no fallback to env or default"


@pytest.mark.parametrize(
    "value",
    ["", "   ", None, 8765, [], "not a url", "http://", "localhost:8765"],
    ids=["empty", "blank", "null", "number", "list", "prose", "no-host", "no-scheme"],
)
def test_a_malformed_mq_mcp_entry_fails_closed(_isolated, monkeypatch, value):
    _config(_isolated, {"mcp_servers": {"mq-mcp": value}})
    monkeypatch.setenv("MQ_MCP_PORT", "9001")

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is False
    assert resolved.base_url is None


@pytest.mark.parametrize(
    "value",
    ["https://remote-host:8765", "http://192.168.1.20:8765", "http://example.com:8765"],
    ids=["https-remote", "lan-address", "public-host"],
)
def test_a_non_loopback_target_is_refused_rather_than_attempted(_isolated, value):
    """mq-mcp's bridge is loopback-only and its Host gate says so.

    Accepting these would offer a contract mq-mcp does not implement, and
    `ensure_receiver` would then either fail obscurely or start a local process
    that is not the endpoint the operator named.
    """
    _config(_isolated, {"mcp_servers": {"mq-mcp": value}})

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is False
    assert resolved.reason == "config-not-loopback"


@pytest.mark.parametrize(
    "url,host,port",
    [
        ("http://127.0.0.1:8765", "127.0.0.1", 8765),
        ("http://localhost:8765", "localhost", 8765),
        ("http://[::1]:8765", "::1", 8765),
        ("http://127.0.0.1:9001/", "127.0.0.1", 9001),
    ],
    ids=["ipv4", "localhost", "ipv6", "trailing-slash"],
)
def test_every_loopback_form_mq_mcp_accepts_is_accepted_here(_isolated, url, host, port):
    _config(_isolated, {"mcp_servers": {"mq-mcp": url}})

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is True
    assert (resolved.host, resolved.port) == (host, port)


@pytest.mark.parametrize("raw", ["nine-thousand", "0", "65536", "-1", "80.5"])
def test_a_malformed_port_in_the_environment_fails_closed(_isolated, monkeypatch, raw):
    """No config and a broken variable is not a reason to use the default."""
    monkeypatch.setenv("MQ_MCP_PORT", raw)

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is False
    assert resolved.reason == "env-malformed"
    assert resolved.base_url is None


def test_a_non_loopback_host_in_the_environment_fails_closed(_isolated, monkeypatch):
    monkeypatch.setenv("MQ_MCP_HOST", "192.168.1.20")

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is False
    assert resolved.reason == "env-not-loopback"


def test_a_host_without_a_port_still_resolves(_isolated, monkeypatch):
    """Half the pair set is not malformed; the other half keeps its default."""
    monkeypatch.setenv("MQ_MCP_HOST", "localhost")

    resolved = resolve_mq_mcp_endpoint()

    assert resolved.usable is True
    assert (resolved.host, resolved.port, resolved.source) == ("localhost", 8765, ENV)


# ── the invariant ───────────────────────────────────────────────────────────

def test_probe_bind_and_write_all_name_the_same_target(_isolated, monkeypatch):
    """The whole point, asserted across the three consumers.

    Config says 8765 and the environment says 9001. Every consumer must land on
    8765, including the child process mq-agent starts — otherwise the divergence
    has only moved into the process launch.
    """
    from mq_agent.core import runtime_identity
    from mq_agent.mcp import manager
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    _config(_isolated, {"mcp_servers": {"mq-mcp": "http://localhost:8765"}})
    monkeypatch.setenv("MQ_MCP_PORT", "9001")
    monkeypatch.setattr(manager, "install_openai_api_key", lambda env: None)

    probe = runtime_identity.mq_mcp_endpoint()
    child = manager._child_env(_isolated)
    write = MultiMCPBridge().servers["mq-mcp"]

    assert probe is not None and probe.startswith("http://localhost:8765")
    assert child["MQ_MCP_PORT"] == "8765", "the child must bind what config named"
    assert child["MQ_MCP_HOST"] == "localhost"
    assert write == "http://localhost:8765"
    assert "9001" not in f"{probe} {child['MQ_MCP_PORT']} {write}"


def test_the_environment_target_reaches_the_child_when_it_wins(_isolated, monkeypatch):
    """The control case: with no config, the variables still decide."""
    from mq_agent.core import runtime_identity
    from mq_agent.mcp import manager
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    monkeypatch.setenv("MQ_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MQ_MCP_PORT", "9001")
    monkeypatch.setattr(manager, "install_openai_api_key", lambda env: None)

    probe = runtime_identity.mq_mcp_endpoint()
    child = manager._child_env(_isolated)
    write = MultiMCPBridge().servers["mq-mcp"]

    assert probe is not None and probe.startswith("http://127.0.0.1:9001")
    assert (child["MQ_MCP_HOST"], child["MQ_MCP_PORT"]) == ("127.0.0.1", "9001")
    assert write == "http://127.0.0.1:9001"


def test_the_parent_environment_is_never_rewritten(_isolated, monkeypatch):
    """Config outranks the variables for the child. It does not edit them here.

    Overwriting os.environ would leak this decision into every other process
    this CLI starts, and into anything else reading the variable.
    """
    import os

    from mq_agent.mcp import manager

    _config(_isolated, {"mcp_servers": {"mq-mcp": "http://localhost:8765"}})
    monkeypatch.setenv("MQ_MCP_PORT", "9001")
    monkeypatch.setattr(manager, "install_openai_api_key", lambda env: None)

    manager._child_env(_isolated)

    assert os.environ["MQ_MCP_PORT"] == "9001"


def test_a_refused_target_stops_the_receiver_rather_than_starting_one(
    _isolated, monkeypatch
):
    """Fail closed reaches the caller: no probe, no launch, a named reason."""
    from mq_agent.core import receiver_launch

    _config(_isolated, {"mcp_servers": {"mq-mcp": "https://remote-host:8765"}})
    started: list[bool] = []

    def _start() -> tuple[bool, int | None, str]:
        started.append(True)
        return False, 1, "started"

    monkeypatch.setattr(receiver_launch, "start_receiver", _start)
    monkeypatch.setattr(receiver_launch, "probe_running",
                        lambda e: pytest.fail("a refused target must not be probed"))

    result = receiver_launch.ensure_receiver()

    assert result.usable is False
    assert result.reason == "config-not-loopback"
    assert started == [], "and no local process stands in for a remote target"


# ── the guard against a fourth resolver ─────────────────────────────────────

def test_only_one_module_resolves_the_target():
    """The defect was two resolvers, so the guard is that there is one.

    Matches an environment lookup naming either variable outside the canonical
    module; explaining them in prose stays allowed.
    """
    package = Path(endpoint_mod.__file__).resolve().parents[1]
    canonical = Path(endpoint_mod.__file__).resolve()

    readers = []
    for source in sorted(package.rglob("*.py")):
        if source.resolve() == canonical:
            continue
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            names_var = "MQ_MCP_HOST" in line or "MQ_MCP_PORT" in line
            if names_var and ("environ" in line or "getenv" in line):
                readers.append(f"{source.relative_to(package.parent).as_posix()}:{number}")

    assert readers == [], (
        "the mq-mcp target must be resolved only by mq_agent/core/mq_mcp_endpoint.py; "
        f"also read at: {readers}"
    )
