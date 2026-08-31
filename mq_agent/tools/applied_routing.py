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

# Operator-controlled. A (routing task class, route) pair may be applied only by
# appearing here, and only a person adds one. The pair, not the task class alone:
# authorizing `docs-review` once would silently authorize every future strategy
# added to it, and which strategy runs is exactly the thing being compared.
APPLIED_ROUTE_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("docs-review", "local-shadow"),
        ("docs-review", "deterministic-local"),
    }
)

#: The route applied when the caller names none. The policy's recommendation,
#: so an operator who asks for nothing gets what the policy advised.
DEFAULT_ROUTE = "local-shadow"

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
    route: str = DEFAULT_ROUTE,
    context: str | None = None,
    authoritative_agent: str = "codex",
    timeout: int = 180,
) -> dict[str, Any]:
    """Run one routing decision through the named route when permitted.

    Returns `{"decision", "candidate", "outcome"}`. `candidate` is the work
    product when the route governed it, and `None` otherwise.

    `route` is the execution strategy the operator asked for, and it may differ
    from `decision["recommended_route"]`. That is not a policy violation: both
    allowlisted strategies are local and read-only, and `deterministic-local`
    runs strictly less than the policy already permitted. The record keeps both
    facts — what was recommended, and what was applied.

    `application` records what actually happened:

        applied    the route ran and governed this decision, including when it
                   then failed verification — it did govern
        advisory   nothing ran: not allowlisted, vetoed by safety, or the
                   runtime was unavailable

    A candidate stopped before execution is never applied evidence. That
    distinction is the whole reason `route readiness` can trust the store.
    """
    decision = inspect_route(task, authoritative_agent=authoritative_agent)
    task_class = str(decision["task_class"])
    deterministic = route == "deterministic-local"

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
                # Name the route that was refused, not the one that was advised.
                # Otherwise a refusal of the deterministic route is recorded
                # against `local-shadow`, which never asked to run.
                selected_route=route if deterministic else None,
            ),
        }

    if not applied_routing_enabled():
        return rejected("operator-required")

    # Order matters, because the reason is evidence rather than a label. The
    # policy check runs first: when the policy forbids the local route, that is
    # true whatever the allowlist says, and it is the more informative fact.
    # Checking the allowlist first would record every cloud-required class as
    # merely unauthorized and hide the policy refusal underneath it.
    allowed, reason = route_level_safety(decision, safety_mode)
    if not allowed:
        return rejected(str(reason))

    if (task_class, route) not in APPLIED_ROUTE_ALLOWLIST:
        # Not an error and not a safety failure: the operator has simply not
        # authorized this class through this route. The canonical route keeps
        # the work.
        #
        # `operator-required`, not `policy-requires-cloud`. The policy did
        # recommend the local route here; only the human authorization is
        # missing. Recording the policy's reason for a refusal the policy never
        # made would put untrue escalation data in the store on day one.
        return rejected("operator-required")

    if deterministic:
        return _apply_deterministic(decision, context, execution_run_id)

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


def _apply_deterministic(
    decision: dict[str, Any], context: str | None, execution_run_id: str
) -> dict[str, Any]:
    """Run the no-inference route through the same verification the model gets.

    Determinism is a property of how the candidate is produced, never a licence
    to skip proving it (ADR-010 D8). The candidate is shape-checked and grounded
    exactly like a model's, so the two routes' verification records mean the
    same thing and can be compared at all.
    """
    from mq_agent.tools.deterministic_route import deterministic_candidate
    from mq_agent.tools.model_routing import _candidate_is_valid, verify_evidence

    task_class = str(decision["task_class"])

    def outcome(
        *,
        status: str,
        checks: list[str] | None = None,
        grounding: tuple[int, int] | None = None,
        schema_valid: bool = False,
        escalation_reason: str | None = None,
    ) -> dict[str, Any]:
        return _outcome(
            decision,
            attempted=True,
            # No model ran, so no model output was received. Read together with
            # `selected_route`, which D8 makes the field that says *how* the work
            # was done, this is unambiguous: a strategy with no model has no
            # model output.
            model_output_received=False,
            schema_valid=schema_valid,
            verification_status=status,
            verification_checks=checks,
            grounding=grounding,
            escalated=status != "PASS",
            escalation_reason=escalation_reason,
            application="applied",
            execution_run_id=execution_run_id,
            selected_route="deterministic-local",
            local_model=None,
        )

    candidate = deterministic_candidate(task_class, context or "")
    if candidate is None or not _candidate_is_valid(candidate, task_class):
        # Too little quotable material to reach the verifier's floor. Failing is
        # the honest result: padding the array to five would be the fabrication
        # the verifier exists to catch, committed by the baseline.
        return {
            "decision": decision,
            "candidate": None,
            "outcome": outcome(
                status="FAIL",
                schema_valid=candidate is not None,
                escalation_reason="verification-failed",
            ),
        }

    checks = ["candidate-schema", "task-class-match"]
    if context is None:
        # Nothing to quote from means nothing to ground against. The route
        # produced a candidate and it is unverifiable, which is not a PASS.
        return {
            "decision": decision,
            "candidate": None,
            "outcome": outcome(
                status="FAIL",
                checks=checks,
                schema_valid=True,
                escalation_reason="verification-failed",
            ),
        }

    verified, grounding = verify_evidence(candidate, context)
    if verified is None:
        return {
            "decision": decision,
            "candidate": None,
            "outcome": outcome(
                status="FAIL",
                checks=checks,
                grounding=grounding,
                schema_valid=True,
                escalation_reason="verification-failed",
            ),
        }

    return {
        "decision": decision,
        "candidate": verified,
        "outcome": outcome(
            status="PASS",
            checks=[*checks, "evidence-grounded"],
            grounding=grounding,
            schema_valid=True,
        ),
    }
