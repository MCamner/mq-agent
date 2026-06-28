"""Limited adaptive planning (Phase 10).

The runner executes a static plan. Phase 10 lets a run adapt **at most once**
(``max_replans`` ∈ {0, 1}) via exactly four bounded moves, and never across the
safety boundary:

    CHOOSE_TEMPLATE  pick another already-approved template (pre-run only)
    SKIP_STEP        skip an irrelevant read-only step
    ADD_DIAGNOSTIC   add one approved read-only diagnostic step
    STOP_EARLY       stop when the goal is already reached

Forbidden, enforced centrally in ``validate_replan``: arbitrary tool chains,
mutations, ``shell_exec``, changing a step's approval level, exceeding
``max_steps``, starting another workflow, or exceeding the single replan budget.
A proposal is only ever *applied* after it passes ``validate_replan``; the
resulting plan is re-checked with ``validate_plan`` so no structural violation
slips through regardless of move type.

This module owns the *contract and safety gate*. The decision of *which* move to
make is delegated to an injected ``Replanner`` — the default one is deterministic
and conservative, proposing only the two evidence-free moves. ADD_DIAGNOSTIC and
CHOOSE_TEMPLATE are validated here but the default replanner never proposes them
(they wait for real usage evidence; see docs/roadmap-workflow-orchestration.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from . import conditions
from .models import (
    StepApproval,
    StepStatus,
    WorkflowPlan,
    WorkflowStep,
    validate_plan,
)
from .policy import PolicyProvider
from .state import WorkflowRun
from .templates import list_templates

#: Curated read-only diagnostic tools an ADD_DIAGNOSTIC move may introduce.
#: A strict subset of templates.ALLOWED_TOOLS — only cheap, side-effect-free
#: inspection. Adding anything else is denied.
DIAGNOSTIC_TOOLS: frozenset[str] = frozenset(
    {"git_status", "git_diff", "repo_signal_status"}
)

#: Approval levels a non-escalating adaptive step may carry.
_READ_ONLY_APPROVALS = frozenset({StepApproval.NONE, StepApproval.PLAN})


class ReplanMove(StrEnum):
    CHOOSE_TEMPLATE = "choose_template"
    SKIP_STEP = "skip_step"
    ADD_DIAGNOSTIC = "add_diagnostic"
    STOP_EARLY = "stop_early"


class ReplanProposal(BaseModel):
    """A single, typed adaptive move. Payload fields are move-specific."""

    model_config = ConfigDict(extra="forbid")

    move: ReplanMove
    reason: str = ""
    #: SKIP_STEP — id of the pending read-only step to skip.
    step_id: str | None = None
    #: CHOOSE_TEMPLATE — name of the template to switch to (pre-run only).
    template: str | None = None
    #: ADD_DIAGNOSTIC — the new read-only diagnostic step (WorkflowStep dict).
    step: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReplanDecision:
    allowed: bool
    reason: str


def _deny(reason: str) -> ReplanDecision:
    return ReplanDecision(False, reason)


def _allow(reason: str = "ok") -> ReplanDecision:
    return ReplanDecision(True, reason)


def _find_step(plan: WorkflowPlan, step_id: str | None) -> WorkflowStep | None:
    return next((s for s in plan.steps if s.id == step_id), None)


def _any_terminal(plan: WorkflowPlan) -> bool:
    terminal = {
        StepStatus.PASSED, StepStatus.FAILED,
        StepStatus.SKIPPED, StepStatus.CANCELLED,
    }
    return any(s.status in terminal for s in plan.steps)


def validate_replan(
    proposal: ReplanProposal,
    plan: WorkflowPlan,
    run: WorkflowRun,
    *,
    policy_provider: PolicyProvider,
) -> ReplanDecision:
    """The single safety gate. Returns allow/deny with a reason; never mutates."""
    # -- budget (global, applies to every move) ----------------------------
    if plan.max_replans <= 0:
        return _deny("adaptive planning disabled (max_replans=0)")
    if run.replans_used >= plan.max_replans:
        return _deny(
            f"replan budget exhausted ({run.replans_used}/{plan.max_replans})"
        )

    move = proposal.move

    if move is ReplanMove.STOP_EARLY:
        # Adds no capability: only marks remaining pending steps skipped.
        return _allow("stop early is structurally safe")

    if move is ReplanMove.SKIP_STEP:
        step = _find_step(plan, proposal.step_id)
        if step is None:
            return _deny(f"unknown step {proposal.step_id!r}")
        if step.status is not StepStatus.PENDING:
            return _deny("only a pending step may be skipped")
        decision = policy_provider.decide(step, read_only=True)
        if not decision.allowed:
            return _deny(f"step not allowed by policy: {decision.reason}")
        if step.approval not in _READ_ONLY_APPROVALS:
            return _deny("only a read-only step may be skipped")
        return _allow(f"skip read-only step {step.id!r}")

    if move is ReplanMove.ADD_DIAGNOSTIC:
        if not proposal.step:
            return _deny("ADD_DIAGNOSTIC requires a step payload")
        try:
            new_step = WorkflowStep.model_validate(proposal.step)
        except Exception as exc:  # noqa: BLE001 — invalid step is a denial, not a crash
            return _deny(f"invalid diagnostic step: {exc}")
        if new_step.tool not in DIAGNOSTIC_TOOLS:
            return _deny(f"{new_step.tool!r} is not an allowed diagnostic tool")
        if new_step.approval not in _READ_ONLY_APPROVALS:
            return _deny("diagnostic step may not escalate approval")
        decision = policy_provider.decide(new_step, read_only=True)
        if not decision.allowed:
            return _deny(f"diagnostic tool not allowed by policy: {decision.reason}")
        # Re-validate the whole post-move plan: catches max_steps overflow,
        # duplicate ids, unknown/cyclic deps and forbidden tools centrally.
        candidate = _plan_with_added_step(plan, new_step)
        try:
            validate_plan(candidate)
        except Exception as exc:  # noqa: BLE001 — contract violation is a denial
            return _deny(f"resulting plan invalid: {exc}")
        return _allow(f"add diagnostic step {new_step.id!r}")

    if move is ReplanMove.CHOOSE_TEMPLATE:
        if _any_terminal(plan):
            return _deny("template choice only allowed before execution starts")
        if proposal.template not in list_templates():
            return _deny(f"unknown template {proposal.template!r}")
        return _allow(f"choose template {proposal.template!r}")

    return _deny(f"unknown move {move!r}")


def _plan_with_added_step(plan: WorkflowPlan, new_step: WorkflowStep) -> dict[str, Any]:
    data = plan.model_dump(mode="json", by_alias=True)
    data["steps"].append(new_step.model_dump(mode="json"))
    return data


def apply_replan(
    proposal: ReplanProposal,
    plan: WorkflowPlan,
    run: WorkflowRun,
) -> None:
    """Apply a *validated* proposal in place and consume one replan from budget.

    Call only after ``validate_replan`` returned allowed. Increments
    ``run.replans_used`` exactly once.
    """
    move = proposal.move
    if move is ReplanMove.STOP_EARLY:
        for step in plan.steps:
            if step.status is StepStatus.PENDING:
                step.status = StepStatus.SKIPPED
    elif move is ReplanMove.SKIP_STEP:
        target = _find_step(plan, proposal.step_id)
        if target is not None:
            target.status = StepStatus.SKIPPED
    elif move is ReplanMove.ADD_DIAGNOSTIC:
        plan.steps.append(WorkflowStep.model_validate(proposal.step))
    elif move is ReplanMove.CHOOSE_TEMPLATE:
        # A pre-run planner move; the in-run loop never applies it.
        raise ValueError("CHOOSE_TEMPLATE is applied by the planner, not the runner")
    else:  # pragma: no cover — guarded by validate_replan
        raise ValueError(f"unknown move {move!r}")
    run.replans_used += 1


# --- replanner (which move to make) ----------------------------------------


class Replanner(Protocol):
    """Decides whether to adapt after a step. Returns a proposal or ``None``."""

    def propose(
        self, run: WorkflowRun, plan: WorkflowPlan, last_step: WorkflowStep | None
    ) -> ReplanProposal | None: ...


class DefaultReplanner:
    """Deterministic, conservative replanner — the only evidence-free moves.

    Proposes at most:
      * SKIP_STEP   — a pending read-only diagnostic step whose tool already
                      passed earlier in this run (redundant re-inspection);
      * STOP_EARLY  — when steps remain pending but none can still pass because
                      their dependencies were skipped/failed.

    It never proposes ADD_DIAGNOSTIC or CHOOSE_TEMPLATE: those wait for real
    usage evidence to drive them safely.
    """

    def propose(
        self, run: WorkflowRun, plan: WorkflowPlan, last_step: WorkflowStep | None
    ) -> ReplanProposal | None:
        if run.replans_used >= plan.max_replans:
            return None

        passed_tools = {s.tool for s in plan.steps if s.status is StepStatus.PASSED}
        for step in plan.steps:
            if (
                step.status is StepStatus.PENDING
                and step.tool in DIAGNOSTIC_TOOLS
                and step.tool in passed_tools
            ):
                return ReplanProposal(
                    move=ReplanMove.SKIP_STEP,
                    step_id=step.id,
                    reason=f"{step.tool} already ran in this run",
                )

        if self._has_pending(plan) and not self._any_runnable(plan):
            return ReplanProposal(
                move=ReplanMove.STOP_EARLY,
                reason="no remaining step can pass; stopping early",
            )
        return None

    @staticmethod
    def _has_pending(plan: WorkflowPlan) -> bool:
        return any(s.status is StepStatus.PENDING for s in plan.steps)

    @staticmethod
    def _any_runnable(plan: WorkflowPlan) -> bool:
        by_id = {s.id: s for s in plan.steps}
        terminal = {
            StepStatus.PASSED, StepStatus.FAILED,
            StepStatus.SKIPPED, StepStatus.CANCELLED,
        }
        for step in plan.steps:
            if step.status is not StepStatus.PENDING:
                continue
            deps = [by_id[d] for d in step.depends_on if d in by_id]
            if all(d.status in terminal for d in deps) and conditions.evaluate(step, plan):
                return True
        return False
