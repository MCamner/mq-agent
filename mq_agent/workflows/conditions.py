"""Step condition evaluation (Phase 4).

Pure functions: given a step and its plan, decide whether the step should run.
No I/O, no execution. A step is only evaluated once its dependencies are
resolved (terminal); see the runner's selection logic.
"""
from __future__ import annotations

from .models import StepCondition, StepStatus, WorkflowPlan, WorkflowStep


def _dep_steps(plan: WorkflowPlan, step: WorkflowStep) -> list[WorkflowStep]:
    by_id = {s.id: s for s in plan.steps}
    return [by_id[d] for d in step.depends_on if d in by_id]


def evaluate(step: WorkflowStep, plan: WorkflowPlan) -> bool:
    """Return ``True`` if ``step`` should execute given current plan state.

    * ``always``          → always run.
    * ``all_deps_passed`` → run only if every dependency reached ``passed``.

    An unrecognized condition is treated as ``False`` (fail closed).
    """
    if step.condition is StepCondition.ALWAYS:
        return True
    if step.condition is StepCondition.ALL_DEPS_PASSED:
        return all(
            dep.status is StepStatus.PASSED for dep in _dep_steps(plan, step)
        )
    return False
