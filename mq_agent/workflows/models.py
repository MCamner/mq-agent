"""Workflow plan data models — the enforced v1 workflow contract.

This module is the *enforcement* counterpart to ``schemas/workflow-plan.v1.json``.
The JSON Schema describes the shape declaratively; the pydantic models here add
the cross-reference and graph constraints JSON Schema cannot express (unique step
ids, dependency existence, cycle detection).

Scope (Phase 1): SHAPE ONLY. There is deliberately no runner, no tool execution,
no state persistence, no approval logic and no adaptive planning here. Those
arrive in later phases. A ``WorkflowPlan`` is a description of intended
structure; it is *not* the truth about live runtime.

v1 invariants locked by this contract:
  * schema == "mq-workflow-plan.v1"
  * unknown fields are rejected (extra="forbid")
  * step ids are unique
  * depends_on only references existing step ids
  * the dependency graph is acyclic
  * 1 <= max_steps <= 10 (default 6); len(steps) <= max_steps and <= 10
  * max_replans in {0, 1}  (Phase 10: a run may adapt at most once)
  * tool names are non-empty and never "shell_exec"
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_ID = "mq-workflow-plan.v1"

#: Hard cap on the number of steps in a v1 plan. ``max_steps`` may be smaller but
#: never larger; the plan's actual step count may never exceed this either.
MAX_STEPS_HARD_CAP = 10
DEFAULT_MAX_STEPS = 6

#: shell_exec is forbidden in v1 plans. Every side effect must be its own typed
#: tool step; a single composed shell string must never count as one step.
FORBIDDEN_TOOLS: frozenset[str] = frozenset({"shell_exec"})


class WorkflowStatus(StrEnum):
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class StepStatus(StrEnum):
    PENDING = "pending"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class StepCondition(StrEnum):
    #: Step is eligible whenever its dependencies are satisfied.
    ALWAYS = "always"
    #: Step is eligible only if every dependency reached ``passed``.
    ALL_DEPS_PASSED = "all_deps_passed"


class StepApproval(StrEnum):
    #: Read-only, no subprocess, no external side effects.
    NONE = "none"
    #: Read-only subprocess / test execution; whole plan approved once.
    PLAN = "plan"
    #: Mutation (file write, network, external app); approve each step.
    STEP = "step"
    #: Push, release, recursive workflow start, or unknown shell exec — not in v1.
    FORBIDDEN = "forbidden"


class WorkflowStep(BaseModel):
    """A single, atomic workflow step bound to exactly one typed tool."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    condition: StepCondition = StepCondition.ALWAYS
    approval: StepApproval = StepApproval.NONE
    status: StepStatus = StepStatus.PENDING
    attempt: int = Field(default=0, ge=0)
    result: dict[str, Any] | None = None
    error: str | None = None

    @field_validator("tool")
    @classmethod
    def _tool_not_forbidden(cls, value: str) -> str:
        if value in FORBIDDEN_TOOLS:
            raise ValueError(
                f"tool {value!r} is forbidden in workflow plans; every side "
                "effect must be its own typed tool step"
            )
        return value

    @field_validator("depends_on")
    @classmethod
    def _depends_on_unique_and_named(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("depends_on contains duplicate step ids")
        return value


class WorkflowPlan(BaseModel):
    """A v1 workflow plan. Locks structure only — never executes anything."""

    model_config = ConfigDict(extra="forbid")

    schema_: str = Field(alias="schema")
    run_id: str = Field(min_length=1)
    template: str = Field(min_length=1)
    task: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    status: WorkflowStatus = WorkflowStatus.PLANNED
    current_step: str | None = None
    max_steps: int = Field(default=DEFAULT_MAX_STEPS)
    max_replans: int = 0
    steps: list[WorkflowStep] = Field(default_factory=list)

    @field_validator("schema_")
    @classmethod
    def _schema_is_v1(cls, value: str) -> str:
        if value != SCHEMA_ID:
            raise ValueError(f"schema must be {SCHEMA_ID!r}, got {value!r}")
        return value

    @field_validator("max_steps")
    @classmethod
    def _max_steps_in_range(cls, value: int) -> int:
        if not 1 <= value <= MAX_STEPS_HARD_CAP:
            raise ValueError(
                f"max_steps must be between 1 and {MAX_STEPS_HARD_CAP}, got {value}"
            )
        return value

    @field_validator("max_replans")
    @classmethod
    def _replans_within_cap(cls, value: int) -> int:
        # Phase 10: limited adaptive planning allows a single replan. The hard
        # cap stays 1 — a run may adapt at most once, never an open loop.
        if value not in (0, 1):
            raise ValueError("max_replans must be 0 or 1")
        return value

    @model_validator(mode="after")
    def _validate_step_graph(self) -> WorkflowPlan:
        ids = [step.id for step in self.steps]

        # Step count limits.
        if len(self.steps) > MAX_STEPS_HARD_CAP:
            raise ValueError(
                f"a plan may not have more than {MAX_STEPS_HARD_CAP} steps, "
                f"got {len(self.steps)}"
            )
        if len(self.steps) > self.max_steps:
            raise ValueError(
                f"plan has {len(self.steps)} steps but max_steps is {self.max_steps}"
            )

        # Unique step ids.
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate step id(s): {', '.join(dupes)}")

        id_set = set(ids)

        # current_step, if set, must reference an existing step.
        if self.current_step is not None and self.current_step not in id_set:
            raise ValueError(
                f"current_step {self.current_step!r} does not reference an existing step"
            )

        # depends_on must reference existing steps (and not the step itself).
        for step in self.steps:
            for dep in step.depends_on:
                if dep == step.id:
                    raise ValueError(f"step {step.id!r} cannot depend on itself")
                if dep not in id_set:
                    raise ValueError(
                        f"step {step.id!r} depends on unknown step {dep!r}"
                    )

        # Acyclic dependency graph (depends_on edges).
        cycle = _find_cycle({s.id: s.depends_on for s in self.steps})
        if cycle is not None:
            raise ValueError(
                "dependency cycle detected: " + " -> ".join(cycle)
            )

        return self


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle as an ordered list of node ids, or ``None`` if acyclic.

    Edges point from a step to the steps it depends on. Uses iterative DFS with
    a recursion stack so a self-loop or back edge is reported as a concrete path.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in graph}

    for start in graph:
        if color[start] != WHITE:
            continue
        # Stack holds (node, iterator over its dependencies).
        stack: list[tuple[str, Any]] = [(start, iter(graph[start]))]
        path: list[str] = [start]
        color[start] = GREY
        while stack:
            node, deps = stack[-1]
            advanced = False
            for dep in deps:
                if dep not in color:  # unknown dep handled elsewhere
                    continue
                if color[dep] == GREY:
                    idx = path.index(dep)
                    return path[idx:] + [dep]
                if color[dep] == WHITE:
                    color[dep] = GREY
                    path.append(dep)
                    stack.append((dep, iter(graph[dep])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
                path.pop()
    return None


def validate_plan(data: dict[str, Any]) -> WorkflowPlan:
    """Validate a raw plan dict against the v1 contract.

    Raises ``pydantic.ValidationError`` on any contract violation. This is the
    single entry point callers should use; it does not touch the filesystem and
    performs no execution.
    """
    return WorkflowPlan.model_validate(data)
