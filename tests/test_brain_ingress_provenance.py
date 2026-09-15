"""What `signal --brain` tells mq-mcp about who produced the evidence.

`signal` has always established a runtime identity before the run and used it
for the execution record. The brain write, 48 lines later, sent none of it, so
mq-mcp received evidence with no way to say which runtime produced it — or
whether the process taking the write was still the code its checkout holds.

mq-agent owns the comparison and the reason codes, so it sends findings it has
already derived. It does not send `running_matches_checkout`: the intermediate
field would give the receiver a second route to RTP semantics, and one
authoritative signal is the point. The projection is the smallest thing the
receiving policy needs — component, running identity, findings — and nothing
else crosses the boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from mq_agent.core import stack_provenance


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "runtime_identity.schema.json"

RTP010 = "RTP010_RUNNING_CHECKOUT_MISMATCH"


def identity(component: str = "mq-mcp", *, commit: str | None = "aaaaaaa") -> dict[str, Any]:
    return {
        "schema": "mq.runtime-identity.v1",
        "component": component,
        "version": "2.1.0",
        "commit": commit,
        "install_type": "editable",
        "identity_quality": "verified" if commit else "partial",
        "started_at": "2026-09-14T08:00:00Z",
        "executable": "/opt/homebrew/bin/python3",
        "module_path": "/Users/someone/mq-mcp",
        "source_path": "/Users/someone/mq-mcp",
    }


_DEFAULT = object()


def assessed(reasons: list[str], *, running: Any = _DEFAULT) -> dict[str, Any]:
    """An assessed component, as `stack_provenance.assess` would return it."""
    return {
        "name": "mq-mcp",
        "running": identity() if running is _DEFAULT else running,
        "checkout": {"commit": "bbbbbbb"},
        "comparison": {"running_matches_checkout": RTP010 not in reasons},
        "reasons": reasons,
        "status": "WARN",
    }


# ── the projection ───────────────────────────────────────────────────────────

def test_the_projection_keeps_rtp010_when_the_comparison_is_false():
    """The test the whole track turns on: mq-agent derived the finding, and it
    has to survive the trip. If the projection drops it, ingress cannot see a
    stale receiver and nothing downstream will notice."""
    projection = stack_provenance.project_receiver_observation(assessed([RTP010]))
    assert {"component": "mq-mcp", "code": RTP010} in projection["findings"]


def test_the_projection_has_exactly_the_fields_ingress_uses():
    projection = stack_provenance.project_receiver_observation(assessed([RTP010]))
    assert set(projection) == {"component", "running", "findings"}


def test_the_comparison_field_does_not_cross_the_boundary():
    """`running_matches_checkout` is mq-agent's intermediate value. Sending it
    would give the receiver a second route to RTP semantics."""
    projection = stack_provenance.project_receiver_observation(assessed([RTP010]))
    assert "running_matches_checkout" not in json.dumps(projection)


def test_findings_about_other_layers_are_not_sent():
    """Ingress warns on any finding it is given. A checkout that is dirty or a
    remote nobody contacted are true facts about the stack and say nothing
    about the process taking the write — sending them would make the warning
    mean nothing."""
    projection = stack_provenance.project_receiver_observation(
        assessed(["RTP001_DIRTY_WORKTREE", "RTP004_REMOTE_NOT_VERIFIED", RTP010])
    )
    assert projection["findings"] == [{"component": "mq-mcp", "code": RTP010}]


@pytest.mark.parametrize(
    "code",
    [
        "RTP008_RUNNING_IDENTITY_UNKNOWN",
        "RTP009_RUNNING_INSTALLED_MISMATCH",
        RTP010,
        "RTP013_RUNTIME_IDENTITY_INVALID",
    ],
)
def test_every_finding_about_the_running_process_is_sent(code):
    projection = stack_provenance.project_receiver_observation(assessed([code]))
    assert projection["findings"] == [{"component": "mq-mcp", "code": code}]


def test_every_finding_names_the_component_it_is_about():
    """Ingress refuses an observation whose findings name someone else."""
    projection = stack_provenance.project_receiver_observation(assessed([RTP010]))
    assert all(f["component"] == projection["component"] for f in projection["findings"])


def test_the_running_identity_is_passed_through_unchanged():
    running = identity()
    projection = stack_provenance.project_receiver_observation(assessed([], running=running))
    assert projection["running"] == running


def test_a_component_with_nothing_running_says_so():
    """Nothing answered. That is not an identity, and none is invented."""
    projection = stack_provenance.project_receiver_observation(
        assessed(["RTP008_RUNNING_IDENTITY_UNKNOWN"], running=None)
    )
    assert projection["running"] is None


def test_the_running_identity_it_sends_satisfies_the_contract():
    """The receiver validates it against the same schema."""
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    projection = stack_provenance.project_receiver_observation(assessed([RTP010]))
    validator.validate(projection["running"])


# ── the producer identity ────────────────────────────────────────────────────

def test_the_guard_hands_back_the_whole_identity_it_validated(monkeypatch, tmp_path):
    """The brain payload needs a full mq.runtime-identity.v1 record, not the
    four-field execution fingerprint: the receiver validates what it is sent."""
    from mq_agent import main
    from mq_agent.core import runtime_guard

    full = identity("mq-agent", commit="df6014f")
    monkeypatch.setattr(
        runtime_guard,
        "check",
        lambda *a, **k: runtime_guard.Verdict(
            allowed=True, reason="", detail="", remedy="", identity=full
        ),
    )
    monkeypatch.setattr(runtime_guard, "production_stores_at_risk", lambda: ["exec"])
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "real.jsonl"))
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(tmp_path / "real-route.jsonl"))

    result = main._require_recordable_runtime()
    assert result == full

    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    validator.validate(result)


def test_the_execution_record_still_keeps_only_the_fingerprint(tmp_path, monkeypatch):
    """The wider identity travels to the brain, not into execution evidence."""
    from mq_agent import main

    store = tmp_path / "exec.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(store))
    monkeypatch.setenv("MQ_AGENT_TELEMETRY", "on")

    with main._execution_outcome("signal", runtime_fingerprint=identity("mq-agent", commit="df6014f")):
        pass

    written = json.loads(store.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert set(written["runtime_fingerprint"]) == {
        "component", "version", "commit", "identity_quality"
    }


# ── the call ─────────────────────────────────────────────────────────────────

class _Bridge:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        return {"ok": True, "path": "reviews/x.md"}


def test_the_brain_call_carries_both_halves():
    from mq_agent import main

    bridge = _Bridge()
    producer = identity("mq-agent", commit="df6014f")
    observation = stack_provenance.project_receiver_observation(assessed([RTP010]))

    main._brain_record_review(
        bridge, "repo-signal:mq-mcp", {"findings": []},
        producer=producer,
        receiver_observation=observation,
    )

    _, arguments = bridge.calls[0]
    assert arguments["producer"] == producer
    assert arguments["receiver_observation"] == observation


def test_a_caller_with_no_provenance_sends_neither_key():
    """Absence is absence: an empty object would claim an observation nobody
    made, and the receiver treats a malformed one as a refusal."""
    from mq_agent import main

    bridge = _Bridge()
    main._brain_record_review(bridge, "diff", {"findings": []})

    _, arguments = bridge.calls[0]
    assert "producer" not in arguments
    assert "receiver_observation" not in arguments


# ── the entrypoint ───────────────────────────────────────────────────────────

def test_the_receiver_is_observed_at_write_time(monkeypatch):
    """The producer identity is frozen before the run because it describes code
    that already executed. The receiver is whatever process answers now."""
    from mq_agent import main

    monkeypatch.setattr(stack_provenance, "observe_mq_mcp", lambda **k: {"unassessed": True})
    monkeypatch.setattr(stack_provenance, "assess", lambda c: assessed([RTP010]))

    assert main._mq_mcp_receiver_observation() == {
        "component": "mq-mcp",
        "running": identity(),
        "findings": [{"component": "mq-mcp", "code": RTP010}],
    }


def test_nothing_to_observe_sends_no_observation(monkeypatch):
    """No checkout here and nothing answering is not an empty observation."""
    from mq_agent import main

    monkeypatch.setattr(stack_provenance, "observe_mq_mcp", lambda **k: None)
    assert main._mq_mcp_receiver_observation() is None


def test_signal_sends_both_halves(monkeypatch):
    """The wiring itself: the fingerprint established before the run, and the
    receiver observed after it, both reach the brain call.

    Asserted on the source because signal() is a long Typer command and the
    call is the thing under test. The observation argument is checked by shape
    rather than by exact spelling — it gained the live receiver in
    feat/signal-brain-live-receiver, and pinning the literal text made an
    intended change look like a regression.
    """
    import inspect
    import re
    from mq_agent import main

    source = inspect.getsource(main.signal)
    assert "producer=fingerprint" in source
    assert re.search(r"receiver_observation=_mq_mcp_receiver_observation\(", source)
    # the receiver handed in is the live one, not something derived locally
    assert "receiver_launch.ensure_receiver()" in source
    assert "receiver.usable" in source
