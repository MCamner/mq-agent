from collections.abc import Callable

from .safety import SafetyGate
from .state import AgentState, PlanStep, StepStatus
from .tool_contract import invalid_arguments, produced_items

__all__ = ["Executor", "invalid_arguments"]


#: How many items one dependent step may fan out to.
#:
#: `find_files("*.py")` returns up to 200 paths, and reading all of them is
#: minutes of work for material that is budgeted down to 16k characters
#: downstream anyway. The bound is reported in the step's own output rather
#: than applied quietly, because a review of 25 of 200 files that says it read
#: everything is the failure this whole line of work exists to prevent.
MAX_FAN_OUT = 25


def resolve_dependency(
    step: PlanStep, plan: list[PlanStep], tools: dict[str, Callable]
) -> tuple[list[str] | None, str | None]:
    """The items this step depends on, or why the dependency cannot be met.

    A dependency is a declaration — which step, and which parameter the item
    binds to — resolved here against that step's actual output. It is never
    inferred from an argument that looks suggestive. `<source_file_path>` is
    one of unlimited spellings of the same wish, and treating any of them as a
    protocol makes every other spelling a silent miss.
    """
    reference = step.for_each
    if not isinstance(reference, dict):
        return None, None

    index, parameter = reference.get("step"), reference.get("as")
    if not isinstance(index, int) or not isinstance(parameter, str) or not parameter:
        return None, (
            "unresolved-dependency\n"
            f"step: {step.index}\n"
            "reason: for_each needs an integer 'step' and a parameter name 'as'"
        )

    source = next((other for other in plan if other.index == index), None)
    if source is None:
        return None, (
            f"unresolved-dependency\nstep: {step.index}\n"
            f"reason: no step {index} in this plan"
        )
    if source.index >= step.index:
        return None, (
            f"unresolved-dependency\nstep: {step.index}\n"
            f"reason: step {index} does not run before it"
        )
    if source.status is not StepStatus.SUCCESS:
        return None, (
            f"unresolved-dependency\nstep: {step.index}\n"
            f"reason: step {index} did not succeed, so it produced nothing"
        )

    producer = tools.get(source.tool or "")
    items = produced_items(producer, source.result) if producer else None
    if items is None:
        return None, (
            f"unresolved-dependency\nstep: {step.index}\n"
            f"reason: step {index} ({source.tool}) does not declare what it produces"
        )
    return items, None


def _fan_out_result(
    step: PlanStep, items: list[str], calls: list[dict], outputs: list[str]
) -> str:
    """One string naming which item produced which output.

    Concatenating the contents alone would hand the reviewer material it cannot
    attribute — and a citation that cannot be traced to a file is exactly the
    ungrounded evidence the verifier throws away.
    """
    parameter = str(step.for_each["as"]) if step.for_each else "item"
    blocks = [
        f"=== {call[parameter]} ===\n{output}"
        for call, output in zip(calls, outputs)
    ]
    if len(items) > len(calls):
        # Said out loud, in the material itself: a review that silently saw a
        # quarter of the files would read as a review of all of them.
        blocks.append(
            f"=== truncated ===\nread {len(calls)} of {len(items)} items "
            f"found by step {step.for_each['step'] if step.for_each else '?'}; "
            f"fan-out is capped at {MAX_FAN_OUT}"
        )
    return "\n\n".join(blocks)


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

        items, unresolved = resolve_dependency(step, state.plan, self.tools)
        if unresolved:
            step.status = StepStatus.FAILED
            step.error = unresolved
            return step

        bound = str(step.for_each["as"]) if step.for_each else ""
        calls = (
            [step.args]
            if items is None
            else [{**step.args, bound: item} for item in items[:MAX_FAN_OUT]]
        )

        # Every resolved call is validated, not just the ones written by hand.
        # A dependency that binds an item to a parameter the tool does not take
        # is the same defect as a planner typing it directly.
        for args in calls:
            problem = invalid_arguments(step.tool, tool_fn, args)
            if problem:
                step.status = StepStatus.FAILED
                step.error = problem
                return step

        try:
            outputs = [tool_fn(**args) for args in calls]
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            return step

        if step.min_items is not None:
            actual_items = produced_items(tool_fn, outputs[0]) if outputs else None
            if actual_items is None:
                step.status = StepStatus.FAILED
                step.error = (
                    "collection-integrity\n"
                    f"step: {step.index}\n"
                    f"tool: {step.tool}\n"
                    "reason: collection producer does not declare countable items"
                )
                return step
            if len(actual_items) < step.min_items:
                step.status = StepStatus.FAILED
                step.error = (
                    "collection-integrity\n"
                    f"step: {step.index}\n"
                    f"tool: {step.tool}\n"
                    f"required: {step.min_items}\n"
                    f"produced: {len(actual_items)}"
                )
                return step

        if items is None:
            step.result = outputs[0]
        else:
            step.result = _fan_out_result(step, items, calls, outputs)
        step.status = StepStatus.SUCCESS
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
