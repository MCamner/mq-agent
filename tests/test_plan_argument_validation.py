"""A plan whose calls were never valid must fail as that, not as a TypeError.

The defect this covers was found by the first two real Era C runs, not by a
test: the planner wrote `directory=` where `list_files` takes `path`, four of
seven steps died on `got an unexpected keyword argument`, and the docs review
went on to verify the three steps that happened to survive. Every part of that
was reported truthfully and none of it described the actual failure.
"""
from __future__ import annotations

import inspect

import pytest

from mq_agent.core.executor import Executor, invalid_arguments
from mq_agent.core.safety import SafetyGate, SafetyMode
from mq_agent.core.state import AgentState, PlanStep, StepStatus
from mq_agent.tools.repo_tools import find_files, list_files


class _Recording:
    """A tool that records whether it was ever reached."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, path: str = ".", pattern: str = "*") -> str:
        self.calls.append({"path": path, "pattern": pattern})
        return "ran"


def _run(tool_name: str, tool_fn, args: dict) -> PlanStep:
    executor = Executor(SafetyGate(SafetyMode.READ_ONLY), {tool_name: tool_fn})
    step = PlanStep(index=1, description="d", tool=tool_name, args=args)
    return executor.run_step(step, AgentState(goal="t"))


def test_the_defect_that_produced_this_test() -> None:
    # list_files(path=..., pattern=...) — the planner wrote `directory`.
    assert invalid_arguments("list_files", list_files, {"directory": "."}) == (
        "invalid-tool-arguments\ntool: list_files\nunknown: directory\n"
        "accepted: path, pattern"
    )
    assert invalid_arguments("find_files", find_files, {"directory": "."}) is not None


def test_an_unknown_argument_stops_the_call_before_it_happens() -> None:
    """The point of the change: the tool is never reached.

    A TypeError raised inside the call is indistinguishable, in the step
    record, from a tool that ran and blew up on its own inputs.
    """
    tool = _Recording()

    step = _run("list_files", tool, {"directory": "."})

    assert step.status is StepStatus.FAILED
    assert tool.calls == []
    assert "unexpected keyword argument" not in (step.error or "")


def test_the_error_names_what_the_tool_does_accept() -> None:
    # Without this line the message says what is wrong and leaves the reader
    # to guess what would be right.
    step = _run("list_files", _Recording(), {"directory": "."})

    assert step.error is not None
    assert "accepted: path, pattern" in step.error


def test_a_missing_required_argument_is_caught_too() -> None:
    def needs_path(path: str, pattern: str = "*") -> str:
        return path

    problem = invalid_arguments("needs_path", needs_path, {"pattern": "*.md"})

    assert problem is not None
    assert "missing: path" in problem


def test_unknown_and_missing_are_reported_together() -> None:
    def needs_path(path: str, pattern: str = "*") -> str:
        return path

    problem = invalid_arguments("needs_path", needs_path, {"directory": "."})

    assert problem is not None
    assert "unknown: directory" in problem
    assert "missing: path" in problem


def test_a_valid_call_still_runs() -> None:
    tool = _Recording()

    step = _run("list_files", tool, {"path": ".", "pattern": "*.md"})

    assert step.status is StepStatus.SUCCESS
    assert tool.calls == [{"path": ".", "pattern": "*.md"}]


def test_no_argument_at_all_is_valid_when_everything_has_a_default() -> None:
    tool = _Recording()

    step = _run("list_files", tool, {})

    assert step.status is StepStatus.SUCCESS
    assert tool.calls == [{"path": ".", "pattern": "*"}]


def test_a_synonym_is_never_repaired() -> None:
    """No silent rewriting of model output.

    Mapping `directory` onto `path` would make the run do something other than
    what the plan said, and a plan that cannot be trusted to describe its own
    execution is worse than one that fails loudly.
    """
    tool = _Recording()

    step = _run("list_files", tool, {"directory": "/somewhere"})

    assert tool.calls == []
    assert step.status is StepStatus.FAILED
    assert step.result is None


def test_a_tool_taking_kwargs_accepts_anything() -> None:
    def flexible(**kwargs) -> str:
        return "ok"

    assert invalid_arguments("flexible", flexible, {"anything": 1}) is None


def test_an_unreadable_signature_is_not_treated_as_a_bad_plan() -> None:
    # Rejecting a call because we could not introspect it would fail the plan
    # for our own blindness rather than for anything the plan got wrong.
    class _Opaque:
        @property
        def __signature__(self):
            raise ValueError("no signature here")

        def __call__(self, **kwargs) -> str:
            return "ran"

    opaque = _Opaque()
    with pytest.raises(ValueError):
        inspect.signature(opaque)

    assert invalid_arguments("opaque", opaque, {"whatever": 1}) is None


def test_an_unknown_tool_is_still_reported_as_an_unknown_tool() -> None:
    # The pre-existing check keeps its own message; a missing tool and a
    # mis-called tool are different plan defects. Read-only mode never reaches
    # the registry — the gate refuses an unlisted tool first — so the check is
    # exercised where it actually lives.
    executor = Executor(SafetyGate(SafetyMode.DANGEROUS), {})
    step = PlanStep(index=1, description="d", tool="nope", args={})

    executor.run_step(step, AgentState(goal="t"))

    assert step.error is not None
    assert "Unknown tool" in step.error


def test_a_skipped_step_is_not_validated() -> None:
    # Safety refusal comes first and stays first: a step the gate blocks was
    # never going to run, and reporting its arguments would be noise.
    executor = Executor(SafetyGate(SafetyMode.READ_ONLY), {"write_file": _Recording()})
    step = PlanStep(index=1, description="d", tool="write_file", args={"directory": "."})

    executor.run_step(step, AgentState(goal="t"))

    assert step.status is StepStatus.SKIPPED
