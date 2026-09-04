"""A dependency is declared and resolved, or it is not a dependency.

The defect: a plan said "read the files the previous step found" and the model,
having no way to say that, wrote `<source_file_path>`. `read_file` ran, reported
truthfully that no such file exists, and the step was marked SUCCESS. Every gate
passed and the review read the wrong files.
"""
from __future__ import annotations

from mq_agent.core.executor import MAX_FAN_OUT, Executor, resolve_dependency
from mq_agent.core.safety import SafetyGate, SafetyMode
from mq_agent.core.state import AgentState, PlanStep, StepStatus
from mq_agent.core.tool_contract import describe_tool, produced_items, produces
from mq_agent.tools.repo_tools import find_files, list_files, read_file, repo_summary


@produces("paths")
def _finder(path: str = ".", pattern: str = "*") -> str:
    return "one.md\ntwo.md\n"


def _reader(path: str = "") -> str:
    return f"contents of {path}"


def _plan(*steps: PlanStep) -> AgentState:
    state = AgentState(goal="g")
    state.plan = list(steps)
    return state


def _run(state: AgentState, tools: dict) -> None:
    executor = Executor(SafetyGate(SafetyMode.DANGEROUS), tools)
    for step in state.plan:
        executor.run_step(step, state)


def test_a_dependent_step_runs_once_per_item_the_earlier_step_produced() -> None:
    find = PlanStep(index=0, description="find", tool="finder")
    read = PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "path"})
    state = _plan(find, read)

    _run(state, {"finder": _finder, "reader": _reader})

    assert read.status is StepStatus.SUCCESS
    assert "contents of one.md" in str(read.result)
    assert "contents of two.md" in str(read.result)
    assert read.source_item_count == 2
    assert read.executed_call_count == 2
    assert read.fan_out_complete is True


def test_a_required_collection_that_produces_too_few_items_fails() -> None:
    @produces("paths")
    def empty() -> str:
        return ""

    find = PlanStep(
        index=0,
        description="find required files",
        tool="empty",
        min_items=1,
    )
    state = _plan(find)

    _run(state, {"empty": empty})

    assert find.status is StepStatus.FAILED
    assert find.error is not None
    assert "collection-integrity" in find.error
    assert "required: 1" in find.error
    assert "produced: 0" in find.error


def test_an_optional_collection_may_be_empty() -> None:
    @produces("paths")
    def empty() -> str:
        return ""

    find = PlanStep(
        index=0,
        description="find optional files",
        tool="empty",
        min_items=0,
    )
    state = _plan(find)

    _run(state, {"empty": empty})

    assert find.status is StepStatus.SUCCESS
    assert find.result == ""


def test_each_output_is_attributed_to_the_item_that_produced_it() -> None:
    # Material a reviewer cannot attribute to a file produces citations the
    # verifier cannot ground.
    find = PlanStep(index=0, description="find", tool="finder")
    read = PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "path"})
    state = _plan(find, read)

    _run(state, {"finder": _finder, "reader": _reader})

    assert "=== one.md ===" in str(read.result)
    assert "=== two.md ===" in str(read.result)


def test_a_placeholder_is_not_a_dependency() -> None:
    """The exact shape of the original defect, held down.

    `<source_file_path>` is one of unlimited spellings of the same wish.
    Nothing interprets it, so the step fails on the argument instead of
    succeeding on a file that does not exist.
    """
    read = PlanStep(
        index=0, description="read", tool="reader", args={"path": "<source_file_path>"}
    )
    state = _plan(read)

    _run(state, {"reader": _reader})

    # It runs, because `path` is a real parameter — but nothing pretended the
    # placeholder referred to an earlier step.
    assert read.for_each is None
    assert resolve_dependency(read, state.plan, {"reader": _reader}) == (None, None)


def test_depending_on_a_step_that_declares_nothing_fails_explicitly() -> None:
    # repo_summary returns prose. Splitting it into "paths" would produce
    # confident nonsense, so the dependency is refused instead.
    summary = PlanStep(index=0, description="summarize", tool="repo_summary")
    read = PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "path"})
    state = _plan(summary, read)

    _run(state, {"repo_summary": repo_summary, "reader": _reader})

    assert read.status is StepStatus.FAILED
    assert read.error is not None
    assert "unresolved-dependency" in read.error
    assert "does not declare what it produces" in read.error


def test_depending_on_a_step_that_failed_fails() -> None:
    def broken(path: str = ".") -> str:
        raise RuntimeError("no")

    find = PlanStep(index=0, description="find", tool="finder")
    read = PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "path"})
    state = _plan(find, read)

    _run(state, {"finder": broken, "reader": _reader})

    assert read.status is StepStatus.FAILED
    assert read.error is not None
    assert "did not succeed" in read.error


def test_depending_on_a_step_that_does_not_exist_fails() -> None:
    read = PlanStep(index=0, description="read", tool="reader", for_each={"step": 9, "as": "path"})
    state = _plan(read)

    _run(state, {"reader": _reader})

    assert read.status is StepStatus.FAILED
    assert read.error is not None
    assert "no step 9" in read.error


def test_a_backwards_dependency_fails() -> None:
    # A step cannot consume something produced after it.
    read = PlanStep(index=0, description="read", tool="reader", for_each={"step": 1, "as": "path"})
    find = PlanStep(index=1, description="find", tool="finder")
    state = _plan(read, find)

    _run(state, {"finder": _finder, "reader": _reader})

    assert read.status is StepStatus.FAILED
    assert read.error is not None
    assert "does not run before it" in read.error


def test_a_malformed_dependency_fails_rather_than_being_guessed_at() -> None:
    read = PlanStep(index=0, description="read", tool="reader", for_each={"step": "zero"})
    state = _plan(read)

    _run(state, {"reader": _reader})

    assert read.status is StepStatus.FAILED
    assert read.error is not None
    assert "integer 'step'" in read.error


def test_every_resolved_call_is_validated() -> None:
    """Binding to a parameter the tool does not take is the same old defect.

    A dependency that resolves cleanly and then calls `reader(folder=...)` is
    no better than a planner typing `folder` by hand.
    """
    find = PlanStep(index=0, description="find", tool="finder")
    read = PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "folder"})
    state = _plan(find, read)

    _run(state, {"finder": _finder, "reader": _reader})

    assert read.status is StepStatus.FAILED
    assert read.error is not None
    assert "invalid-tool-arguments" in read.error
    assert "unknown: folder" in read.error


def test_the_fan_out_bound_is_stated_in_the_material() -> None:
    """A review of 25 of 200 files must not read as a review of all of them."""
    @produces("paths")
    def many(path: str = ".") -> str:
        return "\n".join(f"f{i}.md" for i in range(MAX_FAN_OUT + 5))

    find = PlanStep(index=0, description="find", tool="many")
    read = PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "path"})
    state = _plan(find, read)

    _run(state, {"many": many, "reader": _reader})

    assert read.status is StepStatus.SUCCESS
    assert f"read {MAX_FAN_OUT} of {MAX_FAN_OUT + 5} items" in str(read.result)
    assert "=== truncated ===" in str(read.result)
    assert read.source_item_count == MAX_FAN_OUT + 5
    assert read.executed_call_count == MAX_FAN_OUT
    assert read.fan_out_complete is False


def test_a_step_without_a_dependency_is_unchanged() -> None:
    read = PlanStep(index=0, description="read", tool="reader", args={"path": "x.md"})
    state = _plan(read)

    _run(state, {"reader": _reader})

    assert read.status is StepStatus.SUCCESS
    assert read.result == "contents of x.md"


def test_discovery_tools_produce_paths_a_reader_can_open() -> None:
    """The half of the chain that lives in the tools, not the executor.

    A name relative to a search root the consumer never saw is meaningful only
    inside the producer. `read_file` given `tool_contract.py` looks in the
    wrong place and truthfully reports that no such file exists.
    """
    found = find_files("mq_agent/core", "tool_contract.py")

    assert found == "mq_agent/core/tool_contract.py"
    assert "File not found" not in read_file(found)


def test_the_planner_is_told_which_tools_can_be_depended_on() -> None:
    assert describe_tool("list_files", list_files)["produces"] == "paths"
    assert describe_tool("find_files", find_files)["produces"] == "paths"
    assert "produces" not in describe_tool("repo_summary", repo_summary)


def test_only_a_declared_kind_is_split() -> None:
    # An undeclared tool's output is never broken into items on a hunch.
    assert produced_items(repo_summary, "Repo: x\nBranch: y") is None
    assert produced_items(_finder, "a\n\nb\n") == ["a", "b"]
