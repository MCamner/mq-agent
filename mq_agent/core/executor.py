from collections.abc import Callable

from .safety import SafetyGate
from .state import AgentState, PlanStep, StepStatus


class Executor:
    """Runs plan steps through the tool registry, enforcing safety and dry-run."""

    def __init__(
        self,
        safety: SafetyGate,
        tool_registry: dict[str, Callable],
        dry_run: bool = False,
    ):
        self.safety = safety
        self.tools = tool_registry
        self.dry_run = dry_run

    def run_step(self, step: PlanStep, state: AgentState) -> PlanStep:
        step.status = StepStatus.RUNNING

        allowed, reason = self.safety.check(step)
        if not allowed:
            step.status = StepStatus.SKIPPED
            step.result = reason
            return step

        if self.dry_run:
            step.status = StepStatus.SUCCESS
            step.result = f"[dry-run] Would call {step.tool}({step.args})"
            return step

        if not step.tool:
            step.status = StepStatus.FAILED
            step.error = "Step has no tool assigned"
            return step

        tool_fn = self.tools.get(step.tool)
        if not tool_fn:
            step.status = StepStatus.FAILED
            step.error = f"Unknown tool: '{step.tool}'"
            return step

        try:
            result = tool_fn(**step.args)
            step.result = result
            step.status = StepStatus.SUCCESS
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)

        return step

    def run_plan(self, state: AgentState) -> AgentState:
        for i, step in enumerate(state.plan):
            state.current_step = i
            self.run_step(step, state)
            # Read-only: continue past failures to collect as much info as possible.
            # Execute/suggest: stop on first failure to avoid cascading side effects.
            if (
                step.status == StepStatus.FAILED
                and self.safety.mode.value not in ("read-only", "dangerous")
            ):
                break
        return state
