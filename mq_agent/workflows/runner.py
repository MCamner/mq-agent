"""Read-only workflow runner (Phase 4).

Executes a workflow plan one step at a time, persisting state before and after
every tool call. This is where the workflow engine first actually runs tools —
within hard v1 limits:

    max_steps      = 6        (runner-level cap, independent of the plan)
    max_replans    = 0
    parallelism    = 1
    stop_on_failure = True
    shell_exec      = forbidden
    mutation        = forbidden  (read-only runner)

Tool execution is injected (``ToolExecutor``) so the runner is testable without a
live mq-mcp server. The default executor calls mq-mcp over the local bridge.
Selection resolves dependencies first (a step is considered only once all its
dependencies are terminal), then the condition decides run-vs-skip.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Protocol

from . import conditions
from .evaluator import normalize_result
from .models import (
    FORBIDDEN_TOOLS,
    StepApproval,
    StepStatus,
    WorkflowPlan,
    WorkflowStep,
    WorkflowStatus,
)
from .state import WorkflowRun, touch
from .storage import WorkflowStore
from .templates import ALLOWED_TOOLS

#: Runner-level hard cap on executed steps, independent of the plan's max_steps.
RUNNER_MAX_STEPS = 6
DEFAULT_STEP_TIMEOUT = 120.0

_TERMINAL_STEP = frozenset(
    {
        StepStatus.PASSED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
        StepStatus.CANCELLED,
    }
)
#: Approval levels that imply mutation — forbidden in the read-only runner.
_MUTATING = frozenset({StepApproval.STEP, StepApproval.FORBIDDEN})


class ToolExecutor(Protocol):
    """Callable that executes a tool and returns its raw result."""

    def __call__(self, tool: str, args: dict[str, Any], repo: str) -> Any: ...


class MCPBridgeExecutor:
    """Default executor: call an mq-mcp tool over the local bridge."""

    def __init__(self, endpoint: str | None = None) -> None:
        from ..tools.mcp_bridge import MCPBridge

        self._bridge = MCPBridge(endpoint) if endpoint else MCPBridge()

    def __call__(self, tool: str, args: dict[str, Any], repo: str) -> Any:
        payload = dict(args)
        # Repo-scoped tools expect a repo_path; harmless for tools that ignore it.
        payload.setdefault("repo_path", repo)
        return self._bridge.call_tool(tool, payload)


class Runner:
    """Drives a workflow run to completion under the v1 read-only limits."""

    def __init__(
        self,
        store: WorkflowStore,
        executor: ToolExecutor | None = None,
        *,
        step_timeout: float = DEFAULT_STEP_TIMEOUT,
        max_steps: int = RUNNER_MAX_STEPS,
        stop_on_failure: bool = True,
        on_step: Any = None,
    ) -> None:
        self.store = store
        self.executor = executor or MCPBridgeExecutor()
        self.step_timeout = step_timeout
        self.max_steps = max_steps
        # v1 fixes this to True; the parameter exists for later phases/tests.
        self.stop_on_failure = stop_on_failure
        # Optional callback(step) for surfacing progress; defaults to no-op.
        self._on_step = on_step or (lambda step: None)

    # -- public ---------------------------------------------------------

    def run(self, run: WorkflowRun) -> WorkflowRun:
        """Execute the run from its current state. Persists after every change."""
        run.plan.status = WorkflowStatus.RUNNING
        run.pid = os.getpid()
        self.store.save_run(run)

        executed = 0
        while (step := self._select_next(run.plan)) is not None:
            if executed >= self.max_steps:
                self._fail(run, None, f"runner step cap ({self.max_steps}) reached")
                break

            # Condition decides run vs skip (dependencies already resolved).
            if not conditions.evaluate(step, run.plan):
                step.status = StepStatus.SKIPPED
                self.store.save_run(run)
                continue

            # Policy check happens BEFORE any tool call.
            violation = self._verify_policy(step)
            if violation is not None:
                self._fail(run, step, violation)
                break

            self._execute_step(run, step)
            executed += 1

            if step.status is StepStatus.FAILED and self.stop_on_failure:
                run.plan.status = WorkflowStatus.FAILED
                self.store.save_run(run)
                break

        if run.plan.status is WorkflowStatus.RUNNING:
            failed = any(s.status is StepStatus.FAILED for s in run.plan.steps)
            run.plan.status = (
                WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
            )
        run.pid = None
        run.summary = self._summarize(run.plan)
        self.store.save_run(run)
        return run

    # -- selection / policy --------------------------------------------

    def _select_next(self, plan: WorkflowPlan) -> WorkflowStep | None:
        by_id = {s.id: s for s in plan.steps}
        for step in plan.steps:
            if step.status is not StepStatus.PENDING:
                continue
            deps = [by_id[d] for d in step.depends_on if d in by_id]
            if all(d.status in _TERMINAL_STEP for d in deps):
                return step
        return None

    def _verify_policy(self, step: WorkflowStep) -> str | None:
        """Return a violation message, or ``None`` if the step may run."""
        if step.tool in FORBIDDEN_TOOLS:
            return f"tool {step.tool!r} is forbidden (shell_exec)"
        if step.tool not in ALLOWED_TOOLS:
            return f"unknown tool {step.tool!r} is not in the workflow allowlist"
        if step.approval in _MUTATING:
            return f"mutation (approval={step.approval.value!r}) is forbidden in the read-only runner"
        return None

    # -- execution ------------------------------------------------------

    def _execute_step(self, run: WorkflowRun, step: WorkflowStep) -> None:
        run.plan.current_step = step.id
        call_args = dict(step.args)  # snapshot before persistence sanitizes
        step.status = StepStatus.RUNNING
        step.attempt += 1
        self._on_step(step)
        self.store.save_run(run)  # persist BEFORE the call

        timed_out = False
        error: BaseException | None = None
        raw: Any = None
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.executor, step.tool, call_args, run.plan.repo)
            try:
                raw = future.result(timeout=self.step_timeout)
            except FuturesTimeout:
                timed_out = True
            except Exception as exc:  # noqa: BLE001 - tool failures are data
                error = exc

        result = normalize_result(raw, timed_out=timed_out, error=error)
        step.result = result
        step.error = None if result["ok"] else result["summary"]
        step.status = StepStatus.PASSED if result["ok"] else StepStatus.FAILED
        self.store.save_run(run)  # persist AFTER the call

    def _fail(self, run: WorkflowRun, step: WorkflowStep | None, message: str) -> None:
        if step is not None:
            step.status = StepStatus.FAILED
            step.error = message
            run.plan.current_step = step.id
        run.plan.status = WorkflowStatus.FAILED
        run.pid = None
        touch(run)
        self.store.save_run(run)

    # -- summary --------------------------------------------------------

    def _summarize(self, plan: WorkflowPlan) -> dict[str, Any]:
        steps = [
            {
                "id": s.id,
                "status": s.status.value,
                "code": (s.result or {}).get("code"),
                "summary": (s.result or {}).get("summary") or s.error,
            }
            for s in plan.steps
        ]
        passed = sum(1 for s in plan.steps if s.status is StepStatus.PASSED)
        return {
            "ok": plan.status is WorkflowStatus.COMPLETED,
            "status": plan.status.value,
            "passed": passed,
            "total": len(plan.steps),
            "current_step": plan.current_step,
            "steps": steps,
        }
