"""Applying a route, as opposed to recommending one.

Until now routing only ever advised: `inspect_route` classified and
`shadow_route` evaluated, and neither affected any run. This module is the first
path where a routing decision actually governs work, under mqobsidian ADR-010
and the behaviour decisions on mq-agent #214.

Authorization and evidence are separate questions, and conflating them produced
a bootstrap circle worth stating so it is not reintroduced:

    eligible          needs readiness
    readiness         needs >= 2 applied routes
    applied routes    need eligible

So readiness is **not** an eligibility condition. It never was one in spirit
either — `route_readiness` reports `automatic_routing_enabled: False` and
`operator_approval_required: True`, which is the language of promoting a learned
policy, not of permitting a route to run.

    may this route run?        explicit allowlist + route-level safety   <- here
    is there enough evidence?  route_readiness
    may the system choose?     readiness + explicit operator approval    <- later

Authorization comes from a human editing the allowlist. Accumulating telemetry
never grants execution rights on its own.
"""
from __future__ import annotations

import os
from typing import Any

from mq_agent.core.state import SafetyMode
from mq_agent.tools.model_routing import _outcome, inspect_route, shadow_route

# Operator-controlled. A routing task class may be applied only by appearing
# here, and only a person adds one. Deliberately one entry: #214 proves a single
# applied-route chain end to end before widening.
APPLIED_ROUTE_ALLOWLIST: frozenset[str] = frozenset({"docs-review"})

_OFF_VALUES = frozenset({"0", "off", "false", "no"})


def applied_routing_enabled() -> bool:
    """Applied routing is on unless the operator turns it off."""
    return (
        os.environ.get("MQ_AGENT_APPLIED_ROUTING", "on").strip().lower()
        not in _OFF_VALUES
    )


def route_level_safety(
    decision: dict[str, Any], safety_mode: SafetyMode
) -> tuple[bool, str | None]:
    """Veto a candidate route before it executes. Returns (allowed, reason).

    This sits **after** route selection and **before** execution, and it is
    additive: `SafetyGate.check` still gates every `PlanStep` inside whichever
    executor runs (`core/safety.py:38`). Reading this as a replacement for the
    per-step gate would weaken safety while appearing to add a check.

    Choosing a route can never raise what the work is permitted to do. The
    applied local route in this module makes no tool calls and writes nothing —
    it summarizes evidence the enclosing execution already gathered under the
    per-step gate — so it cannot reach anything the canonical path could not.
    """
    if decision["recommended_route"] == "cloud-required":
        return False, "policy-requires-cloud"
    if safety_mode is SafetyMode.SUGGEST:
        # Suggest mode executes nothing at all (`SafetyGate.check` refuses every
        # step). A route that ran here would be the one thing in the process
        # doing real work in a mode that promised to do none.
        return False, "operator-required"
    return True, None


def apply_route(
    task: str,
    *,
    execution_run_id: str,
    safety_mode: SafetyMode,
    context: str | None = None,
    authoritative_agent: str = "codex",
    timeout: int = 180,
) -> dict[str, Any]:
    """Run one routing decision through the local route when permitted.

    Returns `{"decision", "candidate", "outcome"}`. `candidate` is the work
    product when the route governed it, and `None` otherwise.

    `application` records what actually happened:

        applied    the local model was called and governed this decision,
                   including when it then escalated — it did govern
        advisory   nothing ran: not allowlisted, vetoed by safety, or the
                   runtime was unavailable

    A candidate stopped before execution is never applied evidence. That
    distinction is the whole reason `route readiness` can trust the store.
    """
    decision = inspect_route(task, authoritative_agent=authoritative_agent)
    task_class = str(decision["task_class"])

    def rejected(reason: str) -> dict[str, Any]:
        return {
            "decision": decision,
            "candidate": None,
            "outcome": _outcome(
                decision,
                verification_status="SKIPPED",
                escalated=True,
                escalation_reason=reason,
                application="advisory",
                execution_run_id=execution_run_id,
            ),
        }

    if not applied_routing_enabled():
        return rejected("operator-required")

    if task_class not in APPLIED_ROUTE_ALLOWLIST:
        # Not an error and not a safety failure: the operator has simply not
        # authorized this class. The canonical route keeps the work.
        return rejected("policy-requires-cloud")

    allowed, reason = route_level_safety(decision, safety_mode)
    if not allowed:
        return rejected(str(reason))

    result = shadow_route(
        task,
        authoritative_agent=authoritative_agent,
        timeout=timeout,
        context=context,
    )
    outcome = dict(result["outcome"])

    # `attempted` is the honest line between the two modes: it is true exactly
    # when the local model was called to do the work. A route that ran and then
    # failed still governed this decision; one that never started did not.
    outcome["application"] = "applied" if outcome["attempted"] else "advisory"
    outcome["execution_run_id"] = execution_run_id

    return {"decision": decision, "candidate": result["candidate"], "outcome": outcome}
