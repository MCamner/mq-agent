"""Where the receiver identity comes from when signal --brain has to start one.

The rule from docs/RUNTIME_PROVENANCE.md:

    who started the receiver != source of the receiver identity

A receiver may be started by this CLI. The identity must then be read from the
process that is actually running — never from the launch arguments, the
checkout, the configuration, the expected version, or the identity the producer
intended to start. Every step fails closed, because a review recorded under an
unverified receiver is worse than a review not recorded.
"""
from __future__ import annotations

from typing import Any

import pytest

from mq_agent.core import receiver_launch

LIVE = {
    "schema": "mq.runtime-identity.v1",
    "component": "mq-mcp",
    "version": "2.1.0",
    "commit": "d07b042000000000000000000000000000000000",
    "install_type": "editable",
    "identity_quality": "verified",
}

# What a producer could derive without asking the process. Deliberately a
# different commit, so any test that accepts it is visibly wrong.
FROM_CHECKOUT = dict(LIVE, commit="0000000000000000000000000000000000000000")


class _Probe:
    """Records how often the live process was asked, and what it answered."""

    def __init__(self, answers: list[dict[str, Any] | None]):
        self._answers = list(answers)
        self.calls = 0

    def __call__(self, endpoint: str):
        self.calls += 1
        answer = self._answers.pop(0) if self._answers else self._answers[-1:] or [None]
        answer = answer if not isinstance(answer, list) else answer[0]
        return answer, {"attempted": True, "endpoint": endpoint, "reachable": answer is not None}


def _ensure(monkeypatch, *, probe_answers, start=(False, 4242, "started (PID 4242)"), **kw):
    probe = _Probe(probe_answers)
    monkeypatch.setattr(receiver_launch, "probe_running", probe)
    monkeypatch.setattr(receiver_launch, "start_receiver", lambda: start)
    monkeypatch.setattr(receiver_launch, "_sleep", lambda _s: None)
    result = receiver_launch.ensure_receiver(**kw)
    return result, probe


# ── the reuse path ───────────────────────────────────────────────────────────

def test_an_existing_receiver_is_reused_and_never_started(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(receiver_launch, "probe_running", _Probe([LIVE]))
    def _start():
        started.append(True)
        return (False, 1, "started")

    monkeypatch.setattr(receiver_launch, "start_receiver", _start)

    result = receiver_launch.ensure_receiver()

    assert result.identity == LIVE
    assert result.origin == "existing"
    assert started == [], "a live receiver must not be restarted"


# ── the start path ───────────────────────────────────────────────────────────

def test_a_started_receiver_is_identified_from_the_live_process(monkeypatch):
    """Nothing answers, one is started, and the identity comes from the probe."""
    result, probe = _ensure(monkeypatch, probe_answers=[None, LIVE])

    assert result.identity == LIVE
    assert result.origin == "started_by_cli"
    assert probe.calls == 2, "the identity must be re-read after the start"


def test_the_identity_is_not_taken_from_what_was_launched(monkeypatch):
    """The start reports one identity; the live process reports another.

    Only the live one may reach the record. This is the invariant, stated as a
    test: a producer that answered with what it meant to launch would be
    attesting to its own intent.
    """
    result, _ = _ensure(
        monkeypatch,
        probe_answers=[None, LIVE],
        start=(False, 4242, f"started with {FROM_CHECKOUT['commit']}"),
    )

    assert result.identity["commit"] == LIVE["commit"]
    assert result.identity["commit"] != FROM_CHECKOUT["commit"]


def test_readiness_is_waited_for_rather_than_assumed(monkeypatch):
    """start() returns before the port is bound. Probing once would miss it."""
    result, probe = _ensure(monkeypatch, probe_answers=[None, None, None, LIVE])

    assert result.identity == LIVE
    assert probe.calls == 4


# ── fail closed ──────────────────────────────────────────────────────────────

def test_a_failed_start_yields_no_identity(monkeypatch):
    result, _ = _ensure(monkeypatch, probe_answers=[None],
                        start=(False, None, "server exited immediately (rc=1)"))

    assert result.identity is None
    assert result.origin == "started_by_cli"
    assert "exited immediately" in (result.reason or "")


def test_a_receiver_that_never_becomes_ready_yields_no_identity(monkeypatch):
    result, probe = _ensure(monkeypatch, probe_answers=[None], attempts=3)

    assert result.identity is None
    assert result.reason == "receiver-never-ready"
    assert probe.calls == 1 + 3


def test_a_malformed_live_identity_is_not_passed_on(monkeypatch):
    """Something answered and could not identify itself. That is not evidence."""
    result, _ = _ensure(monkeypatch, probe_answers=[None, {"schema": "something-else"}])

    assert result.identity is None
    assert result.reason == "receiver-identity-malformed"


def test_an_answer_that_is_not_an_object_is_not_passed_on(monkeypatch):
    result, _ = _ensure(monkeypatch, probe_answers=[None, "mq-mcp 2.1.0"])

    assert result.identity is None
    assert result.reason == "receiver-identity-malformed"


@pytest.mark.parametrize(
    "broken",
    [
        dict(LIVE, identity_quality="verified", commit=None),
        dict(LIVE, schema="mq.runtime-identity.v2"),
        {k: v for k, v in LIVE.items() if k != "component"},
    ],
    ids=["verified-without-commit", "wrong-schema", "no-component"],
)
def test_an_identity_failing_its_own_contract_is_refused(monkeypatch, broken):
    result, _ = _ensure(monkeypatch, probe_answers=[None, broken])

    assert result.identity is None
    assert result.reason == "receiver-identity-malformed"


def test_an_identity_for_another_component_is_refused(monkeypatch):
    """A process answered, but it is not the receiver."""
    result, _ = _ensure(monkeypatch, probe_answers=[None, dict(LIVE, component="mq-agent")])

    assert result.identity is None
    assert result.reason == "receiver-wrong-component"


# ── what the caller may do with it ───────────────────────────────────────────

def test_the_result_says_whether_a_write_may_proceed(monkeypatch):
    ok, _ = _ensure(monkeypatch, probe_answers=[None, LIVE])
    bad, _ = _ensure(monkeypatch, probe_answers=[None, {"schema": "nope"}])

    assert ok.usable is True
    assert bad.usable is False


def test_origin_is_recorded_for_both_paths(monkeypatch):
    monkeypatch.setattr(receiver_launch, "probe_running", _Probe([LIVE]))
    monkeypatch.setattr(receiver_launch, "start_receiver", lambda: (True, 1, "already running"))
    assert receiver_launch.ensure_receiver().origin == "existing"

    started, _ = _ensure(monkeypatch, probe_answers=[None, LIVE])
    assert started.origin == "started_by_cli"


# ── the live identity has to reach the payload ───────────────────────────────

def test_the_live_identity_replaces_the_observed_running_layer(monkeypatch):
    """Starting a receiver is pointless if what gets sent is still null.

    This is the bug the whole change exists to close: observe_mq_mcp saw no
    process, so the observation carried running: null, which mq-mcp refuses as
    malformed rather than absent. The live identity must land in the payload.
    """
    from mq_agent import main
    from mq_agent.core import stack_provenance

    # what this machine saw on its own: a checkout, and nothing answering
    monkeypatch.setattr(
        stack_provenance, "observe_mq_mcp",
        lambda **k: {"name": "mq-mcp", "checkout": None, "integration": None,
                     "remote": None, "installed": None, "running": None,
                     "running_probe": {"attempted": True, "reachable": False},
                     "release": None},
    )

    without = main._mq_mcp_receiver_observation()
    with_live = main._mq_mcp_receiver_observation(
        receiver_launch.ReceiverResult(LIVE, receiver_launch.STARTED_BY_CLI)
    )

    assert without is not None and without["running"] is None
    assert with_live is not None
    assert with_live["running"] == LIVE
    assert with_live["running"]["commit"] == LIVE["commit"]


def test_an_unusable_receiver_does_not_fabricate_a_running_layer(monkeypatch):
    """No identity means the observation stays as this machine saw it."""
    from mq_agent import main
    from mq_agent.core import stack_provenance

    monkeypatch.setattr(
        stack_provenance, "observe_mq_mcp",
        lambda **k: {"name": "mq-mcp", "checkout": None, "integration": None,
                     "remote": None, "installed": None, "running": None,
                     "running_probe": {"attempted": True, "reachable": False},
                     "release": None},
    )

    obs = main._mq_mcp_receiver_observation(
        receiver_launch.ReceiverResult(None, receiver_launch.STARTED_BY_CLI,
                                       "receiver-never-ready")
    )

    assert obs is not None
    assert obs["running"] is None


def test_the_origin_never_crosses_to_the_receiver(monkeypatch):
    """Admission must not depend on who started the process."""
    from mq_agent import main
    from mq_agent.core import stack_provenance

    monkeypatch.setattr(
        stack_provenance, "observe_mq_mcp",
        lambda **k: {"name": "mq-mcp", "checkout": None, "integration": None,
                     "remote": None, "installed": None, "running": None,
                     "running_probe": {"attempted": True, "reachable": False},
                     "release": None},
    )

    obs = main._mq_mcp_receiver_observation(
        receiver_launch.ReceiverResult(LIVE, receiver_launch.STARTED_BY_CLI)
    )

    assert obs is not None
    assert set(obs) == {"component", "running", "findings"}
    assert "started_by_cli" not in str(obs)


# ── the server directory MQ_MCP_DIR points at ────────────────────────────────

def _layout(tmp_path, *, package_child: bool):
    """MQ_MCP_DIR has existed in both shapes. Build one of them."""
    root = tmp_path / "mq-mcp"
    server_dir = (root / "mq-mcp") if package_child else root
    server_dir.mkdir(parents=True)
    (server_dir / "server.py").write_text("x = 1\n", encoding="utf-8")
    return root, server_dir


@pytest.mark.parametrize("package_child", [True, False], ids=["repo-root", "package-dir"])
def test_the_server_directory_is_found_in_either_layout(tmp_path, monkeypatch, package_child):
    """MQ_MCP_DIR may name the repo root or the package directory.

    Resolving it as the repo root without probing meant `uv run mcp run
    server.py` started in a directory with no server.py, and the child exited
    rc=1 — so ensure_receiver could never produce a receiver on a machine
    configured the other way. Probe for server.py, the way mq_mcp_root probes
    for .git.
    """
    from mq_agent.mcp import manager

    root, server_dir = _layout(tmp_path, package_child=package_child)
    monkeypatch.setenv("MQ_MCP_DIR", str(root))

    assert manager.mq_mcp_dir() == server_dir
    assert (manager.mq_mcp_dir() / "server.py").exists()


def test_an_unresolvable_layout_still_returns_a_path(tmp_path, monkeypatch):
    """start() reports 'directory not found' on it, rather than raising here."""
    from mq_agent.mcp import manager

    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv("MQ_MCP_DIR", str(empty))

    assert manager.mq_mcp_dir() == empty
