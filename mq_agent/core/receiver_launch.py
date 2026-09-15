"""Getting a live mq-mcp receiver, and reading its identity from the process.

`signal --brain` sends mq-mcp an observation of the receiver that is about to
take the write. Observing whatever already ran meant that on a machine with a
checkout and no long-lived process — the ordinary case — the observation
carried `running: null`, which mq-mcp refuses as malformed rather than absent,
and the review was never written.

A receiver may be started to fix that. The rule that has to hold while doing so
(docs/RUNTIME_PROVENANCE.md):

    who started the receiver != source of the receiver identity

The identity is read, after start, from the process that is actually running.
It is never derived from the launch arguments, the checkout, the configuration,
the expected version, or the identity this CLI intended to start — a producer
reporting what it meant to launch would be attesting to its own intent, not to
the code that took the write.

Every step fails closed. A review recorded under an unverified receiver is
worse than a review not recorded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from mq_agent.core.mq_mcp_endpoint import resolve_mq_mcp_endpoint
from mq_agent.core.runtime_identity import MQ_MCP, mq_mcp_endpoint, probe_running

#: How many times to re-ask after a start before giving up. `manager.start()`
#: waits only long enough to catch a process that dies immediately, so the port
#: is usually not bound when it returns.
READY_ATTEMPTS = 20

#: Between attempts. Twenty of these is ten seconds, which is far longer than a
#: local server needs and still bounded.
READY_INTERVAL_SECONDS = 0.5

EXISTING = "existing"
STARTED_BY_CLI = "started_by_cli"

_REQUIRED = ("schema", "component", "version", "commit", "install_type", "identity_quality")
_SCHEMA = "mq.runtime-identity.v1"


def _sleep(seconds: float) -> None:
    """Indirection so tests do not wait. Never call time.sleep directly."""
    time.sleep(seconds)


def start_receiver() -> tuple[bool, int | None, str]:
    """Start mq-mcp. Returns (already_running, pid, message)."""
    from mq_agent.mcp.manager import start

    return start()


@dataclass(frozen=True)
class ReceiverResult:
    """A live receiver identity, or the reason there is none.

    `origin` records whether this CLI started the process. It is lifecycle
    provenance, kept for tests and debugging, and deliberately not sent to
    mq-mcp: the receiver's admission decision must not depend on who started it.
    """

    identity: dict[str, Any] | None
    origin: str
    reason: str | None = None

    @property
    def usable(self) -> bool:
        """Whether a brain write may proceed on this receiver."""
        return self.identity is not None


def _identity_is_sound(record: Any) -> str | None:
    """Return a refusal reason, or None when the record identifies a receiver.

    Structural only. Whether the identity is *admissible* is mq-mcp's decision,
    made by its own ingress gate against its own vendored contract; this checks
    that something coherent came back from the process at all.
    """
    if not isinstance(record, dict):
        return "receiver-identity-malformed"
    if record.get("schema") != _SCHEMA:
        return "receiver-identity-malformed"
    if any(field not in record for field in _REQUIRED):
        return "receiver-identity-malformed"
    if record.get("identity_quality") == "verified" and not record.get("commit"):
        return "receiver-identity-malformed"
    if record.get("component") != MQ_MCP:
        return "receiver-wrong-component"
    return None


def ensure_receiver(
    *,
    attempts: int = READY_ATTEMPTS,
    interval: float = READY_INTERVAL_SECONDS,
) -> ReceiverResult:
    """Return the live identity of an mq-mcp receiver, starting one if needed.

    Asks first. A process that is already running is reused and never
    restarted. When nothing answers, one is started and then asked again until
    it answers or the attempts run out — readiness is waited for, not assumed.

    The identity always comes from the answering process.
    """
    target = resolve_mq_mcp_endpoint()
    if not target.usable:
        # A target the operator configured and this runtime cannot use. Probing
        # elsewhere, or starting a local process to stand in for it, would put
        # the write somewhere nobody asked for.
        return ReceiverResult(None, EXISTING, target.reason)

    endpoint = mq_mcp_endpoint()
    if endpoint is None:
        return ReceiverResult(None, EXISTING, "endpoint-unresolved")

    running, _probe = probe_running(endpoint)
    if running is not None:
        reason = _identity_is_sound(running)
        return ReceiverResult(None if reason else running, EXISTING, reason)

    already_running, pid, message = start_receiver()
    if pid is None:
        return ReceiverResult(None, STARTED_BY_CLI, message)

    for _ in range(attempts):
        _sleep(interval)
        running, _probe = probe_running(endpoint)
        if running is not None:
            reason = _identity_is_sound(running)
            return ReceiverResult(None if reason else running, STARTED_BY_CLI, reason)

    return ReceiverResult(None, STARTED_BY_CLI, "receiver-never-ready")
