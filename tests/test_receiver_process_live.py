"""Starting a real mq-mcp and reading its identity from the process.

Everything else about the receiver is tested against monkeypatched seams:
`probe_running`, `start_receiver` and `_sleep` are all replaced in
`tests/test_signal_brain_receiver.py`, and nothing in that suite spawns a
process or binds a port. That is the right shape for the decision logic — it is
fast, hermetic, and states the invariant — but it means the parts that can only
fail on a real machine were never exercised: `uv run mcp run server.py` finding
its project, the child surviving the start window, the port actually binding,
and an HTTP answer coming back from something that is not a fixture.

Those are precisely the parts that broke twice. `manager.mq_mcp_dir()` resolved
a directory with no `server.py`, so the child exited rc=1 and `ensure_receiver`
could never produce a receiver; the whole feature would have shipped inert with
a green suite. Later, the endpoint the probe used and the endpoint the child
bound came from two resolvers that never read each other's input.

So this file starts one, for real, and asserts what only a real one can show.

It needs an mq-mcp checkout, and skips without one rather than pretending. The
fixture owns the process: it is killed in teardown whether the test passed,
failed, or raised, and the port is confirmed free afterwards. A test that leaks
a listener on port 8765 would break every later run on the same machine, and a
red run would then mean "the previous test leaked" rather than "the platform is
broken" — which is the only reason to have this file at all.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from unittest import mock
from pathlib import Path

import pytest

from mq_agent.core import receiver_launch
from mq_agent.core.mq_mcp_endpoint import resolve_mq_mcp_endpoint
from mq_agent.core.mq_mcp_layout import mq_mcp_layout
from mq_agent.mcp import manager

#: How long to wait for a killed child to release the port before saying so.
RELEASE_ATTEMPTS = 20
RELEASE_INTERVAL = 0.25


def _port_is_bound(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _git_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _serves_runtime_identity(target) -> bool:
    """Whether the listener answers the route the receiver identity comes from."""
    try:
        import httpx

        return httpx.get(f"{target.base_url}/runtime-identity", timeout=3.0).status_code == 200
    except Exception:
        return False


def _stop(pid: int | None, target) -> None:
    """Kill the child and wait for the port, used by teardown and by the skip."""
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    manager.PID_FILE.unlink(missing_ok=True)
    for _ in range(RELEASE_ATTEMPTS):
        if not _port_is_bound(target.host, target.port):
            break
        time.sleep(RELEASE_INTERVAL)


@pytest.fixture(scope="module")
def _credential_boundary_stubbed():
    """`_child_env` resolves OPENAI_API_KEY through /usr/bin/security on macOS.

    conftest refuses that for every test — "Stub the credential boundary in the
    test instead" — and this is a test that really does build a child
    environment. Stubbed here rather than left to fixture ordering: a
    module-scoped fixture is set up before the function-scoped guard, so
    running this file alone happened to work while running it after any other
    file did not. A live-process test whose result depends on what ran before
    it is worth less than no test at all.

    The child then starts without a key, which is what this file is about: it
    asserts the process starts, binds and identifies itself, none of which
    needs a credential.
    """
    with mock.patch.object(manager, "install_openai_api_key", lambda env: None):
        yield


@pytest.fixture(scope="module")
def live_receiver(_credential_boundary_stubbed):
    """A real mq-mcp, started here and stopped whatever happens.

    Module-scoped because starting one is the expensive part and every test
    below asks the same process a different question. The teardown runs even
    when a test fails, which is the point: the next run on this machine must
    not inherit a listener.
    """
    # An explicit MQ_MCP_DIR, not the home fallback. `_child_env` copies
    # os.environ, so the child sees the variable only when the caller set it —
    # and a server started without it answered 404 on /runtime-identity while
    # the same checkout started with it answered normally. Until that is
    # understood and fixed on the mq-mcp side, this file refuses to guess which
    # of the two it is measuring.
    if not os.environ.get("MQ_MCP_DIR"):
        pytest.skip("MQ_MCP_DIR is not set; refusing the home-directory fallback")

    layout = mq_mcp_layout()
    if layout.project is None:
        pytest.skip("no mq-mcp project resolves from MQ_MCP_DIR")

    target = resolve_mq_mcp_endpoint()
    if not target.usable or target.host is None or target.port is None:
        pytest.skip(f"mq-mcp endpoint unusable: {target.reason}")

    if _port_is_bound(target.host, target.port):
        pytest.skip(f"port {target.port} already in use; refusing to fight for it")

    # A wider window than the production default of 20 x 0.5s. Measured:
    # started alone the child binds in ~1.5s, but with the rest of the suite
    # running first it has taken longer than the 10s default allows — the port
    # was bound when the fixture looked, after ensure_receiver had already
    # given up with `receiver-never-ready`. A test that fails because a
    # machine is busy reports nothing about the platform, which is the only
    # thing this file exists to report.
    #
    # That the production default can be too tight under load is a real
    # observation, and it belongs in its own change rather than being fixed by
    # a test quietly asking for more time.
    result = receiver_launch.ensure_receiver(attempts=40, interval=0.5)
    pid = manager.read_pid()

    # An mq-mcp old enough to predate the /runtime-identity route binds the
    # port and answers 404, and ensure_receiver then reports
    # `receiver-never-ready` — a timing word for a version problem. An operator
    # reading that would wait and retry forever. Skipping here says which it
    # was; the mislabelled reason is mq-agent's to fix, in its own change.
    if not result.usable and pid is not None and _port_is_bound(target.host, target.port):
        if not _serves_runtime_identity(target):
            _stop(pid, target)
            pytest.skip(
                f"mq-mcp at {layout.project} binds the port but has no "
                f"/runtime-identity route; too old to identify itself"
            )
    try:
        yield result, layout, target, pid
    finally:
        _stop(pid, target)


def test_a_receiver_really_starts_and_binds_the_port(live_receiver):
    """`uv run mcp run server.py` found its project and the child survived."""
    result, _layout, target, pid = live_receiver

    assert result.usable, f"no receiver: {result.reason}"
    assert result.origin == receiver_launch.STARTED_BY_CLI
    assert pid is not None, "a started receiver must leave a pid"
    assert _port_is_bound(target.host, target.port), (
        f"nothing is listening on {target.host}:{target.port}"
    )


def test_the_identity_comes_from_the_process_not_the_checkout(live_receiver):
    """The invariant, against something that can actually disagree.

    The commit is compared with the checkout's HEAD because that is the only
    value available without asking — so a runtime that answered from the
    filesystem would still pass a weaker check. This asserts they agree *and*
    that the answer arrived over HTTP from a process, which the probe below
    re-establishes independently.
    """
    result, layout, target, _pid = live_receiver
    assert result.identity is not None

    head = _git_head(layout.root) if layout.root else None
    if head is None:
        pytest.skip("mq-mcp checkout has no readable HEAD")

    assert result.identity["commit"] == head
    assert result.identity["component"] == "mq-mcp"
    assert result.identity["schema"] == "mq.runtime-identity.v1"


def test_the_live_process_answers_the_endpoint_that_was_probed(live_receiver):
    """probe target == the thing that is actually listening.

    Asked again directly rather than reusing the fixture's answer, so this
    fails if the identity came from anywhere but the port in front of us.
    """
    from mq_agent.core.runtime_identity import mq_mcp_endpoint, probe_running

    result, _layout, _target, _pid = live_receiver
    endpoint = mq_mcp_endpoint()
    assert endpoint is not None

    running, probe = probe_running(endpoint)

    assert probe["reachable"] is True
    assert running is not None
    assert result.identity is not None
    assert running["commit"] == result.identity["commit"]


def test_a_second_call_reuses_the_process_rather_than_starting_another(live_receiver):
    """Two receivers on one port is the failure this prevents."""
    _result, _layout, target, pid = live_receiver

    again = receiver_launch.ensure_receiver()

    assert again.origin == receiver_launch.EXISTING
    assert again.usable
    assert manager.read_pid() == pid, "a second call started a different process"
