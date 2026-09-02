import inspect
from collections.abc import Callable

from .safety import SafetyGate
from .state import AgentState, PlanStep, StepStatus


def invalid_arguments(tool_name: str, tool_fn: Callable, args: dict) -> str | None:
    """Say why these arguments cannot call this tool, or None when they can.

    A plan is model output, and a model naming `directory` where the tool takes
    `path` has written a plausible, wrong call. Passing it through to
    `tool_fn(**args)` turns that into a `TypeError` at call time, which is
    reported as a failed step whose explanation reads like a bug in the tool.
    The failure is real; the description is of the wrong thing.

    Nothing here repairs the call. Mapping `directory` onto `path` would mean
    the run silently did something other than what the plan said, and a plan
    that cannot be trusted to describe its own execution is worse than one that
    fails loudly.
    """
    try:
        signature = inspect.signature(tool_fn)
    except (TypeError, ValueError):
        # A callable whose signature cannot be read is not evidence of a bad
        # plan. Let the call proceed rather than reject on our own blindness.
        return None

    parameters = signature.parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return None

    named = {
        p.name: p
        for p in parameters
        if p.kind
        not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    }
    unknown = sorted(set(args) - set(named))
    missing = sorted(
        name
        for name, parameter in named.items()
        if parameter.default is inspect.Parameter.empty and name not in args
    )
    if not unknown and not missing:
        return None

    lines = ["invalid-tool-arguments", f"tool: {tool_name}"]
    if unknown:
        lines.append(f"unknown: {', '.join(unknown)}")
    if missing:
        lines.append(f"missing: {', '.join(missing)}")
    # Naming what the tool does accept is the part that lets a caller — or the
    # next planning pass — fix the call instead of guessing at it.
    lines.append(f"accepted: {', '.join(named)}")
    return "\n".join(lines)


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

        # Before the call, not as a TypeError during it: an argument the tool
        # cannot accept means the plan was never executable, and that is a
        # different fact from a tool that ran and failed.
        problem = invalid_arguments(step.tool, tool_fn, step.args)
        if problem:
            step.status = StepStatus.FAILED
            step.error = problem
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
