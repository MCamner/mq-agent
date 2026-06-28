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

Phase 6: the per-step allow/deny gate now comes from machine-readable tool
policy fetched from mq-mcp (PolicyProvider), not a hardcoded allowlist. Policy
is snapshotted into run state at start; on resume, policy drift stops the run.
A plan-approval gate runs once before execution when any step needs it.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Callable, Protocol

from . import conditions
from .adapter import Replanner, apply_replan, validate_replan
from .evaluator import normalize_result
from .models import (
    StepStatus,
    WorkflowPlan,
    WorkflowStep,
    WorkflowStatus,
)
from .policy import PolicyProvider, diff_policies
from .state import WorkflowRun, touch
from .storage import WorkflowStore

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
        policy_provider: PolicyProvider | None = None,
        plan_approver: Callable[[str], bool] | None = None,
        on_step: Any = None,
        replanner: Replanner | None = None,
        observer: Callable[[WorkflowRun, dict[str, Any]], None] | None = None,
    ) -> None:
        self.store = store
        self.executor = executor or MCPBridgeExecutor()
        self.step_timeout = step_timeout
        self.max_steps = max_steps
        # v1 fixes this to True; the parameter exists for later phases/tests.
        self.stop_on_failure = stop_on_failure
        self.policy_provider = policy_provider or PolicyProvider()
        # Phase 10: optional adaptive replanner. None = static plan (Phase 6).
        self._replanner = replanner
        # Applied/denied adaptive moves, surfaced in the run summary.
        self._replan_log: list[dict[str, Any]] = []
        # Plan-approval hook: receives a side-effect summary, returns approve y/n.
        # Default auto-approves (programmatic/trusted callers); the CLI prompts.
        self._plan_approver = plan_approver or (lambda summary: True)
        # Optional callback(step) for surfacing progress; defaults to no-op.
        self._on_step = on_step or (lambda step: None)
        # Per-step policy decisions for the current run (set in run()).
        self._policy_decisions: dict[str, Any] = {}
        # Runner-level failure reason (e.g. policy drift, step cap), if any.
        self._fail_reason: str | None = None
        # Optional observation emitter (run, meta) -> None; default no emission.
        self._observer = observer
        # Wall-clock start (set in run()) and approvals taken, for the observation.
        self._start: float | None = None
        self._approval_count = 0

    # -- public ---------------------------------------------------------

    def run(self, run: WorkflowRun) -> WorkflowRun:
        """Execute the run from its current state. Persists after every change."""
        self._start = time.monotonic()
        # 1. Fetch tool policy BEFORE doing anything (deny/allow source of truth).
        current = self.policy_provider.load()
        plan_tools = {s.tool for s in run.plan.steps}

        # 2. Policy snapshot + drift guard. A fresh run snapshots policy; a
        #    resumed run (snapshot already present) stops if policy drifted.
        if run.policy_snapshot is not None:
            drift = diff_policies(run.policy_snapshot, current, plan_tools)
            if drift:
                self._fail(
                    run, None,
                    f"tool policy changed during paused run: {', '.join(drift)}",
                )
                self._finalize(run)
                return run
        elif self.policy_provider.source == "policy":
            run.policy_snapshot = {t: current[t] for t in plan_tools if t in current}

        # 3. Per-step decisions (computed once, recorded for observability).
        decisions = {
            s.id: self.policy_provider.decide(s, read_only=True)
            for s in run.plan.steps
        }
        self._policy_decisions = decisions

        # 4. Plan-approval gate: ask once if any runnable step needs it.
        if self._needs_plan_approval(run.plan, decisions):
            if not self._plan_approver(self._approval_summary(run.plan, decisions)):
                run.plan.status = WorkflowStatus.AWAITING_APPROVAL
                run.pid = None
                run.summary = self._summarize(run.plan, approved=False)
                touch(run)
                self.store.save_run(run)
                return run
            # Plan was approved once — record it for the observation metrics.
            self._approval_count = 1

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

            # A step added by an adaptive move has no precomputed decision yet —
            # gate it through the same policy path before it can run.
            if step.id not in decisions:
                decisions[step.id] = self.policy_provider.decide(step, read_only=True)

            # Policy gate happens BEFORE any tool call — no execution without it.
            decision = decisions[step.id]
            if not decision.allowed:
                self._fail(run, step, f"policy denied: {decision.reason}")
                break
            # Never auto re-run a step the policy marks not retry-safe.
            if step.attempt > 0 and not self.policy_provider.retry_safe(step.tool):
                self._fail(run, step, f"{step.tool!r} is not retry-safe; manual rerun required")
                break

            self._execute_step(run, step)
            executed += 1

            if step.status is StepStatus.FAILED and self.stop_on_failure:
                run.plan.status = WorkflowStatus.FAILED
                self.store.save_run(run)
                break

            # Phase 10: offer the replanner one bounded, validated adaptation.
            self._maybe_replan(run, step, decisions)

        self._finalize(run)
        return run

    # -- adaptive planning (Phase 10) -----------------------------------

    def _maybe_replan(
        self, run: WorkflowRun, last_step: WorkflowStep, decisions: dict
    ) -> None:
        """Ask the replanner for one move; validate and apply it if safe.

        No-op without a replanner (Phase 6 behavior). Every proposal passes the
        central ``validate_replan`` gate before ``apply_replan``; a denied
        proposal is recorded and ignored. A newly added step is gated by the same
        per-step policy decision the loop enforces.
        """
        if self._replanner is None or run.replans_used >= run.plan.max_replans:
            return
        proposal = self._replanner.propose(run, run.plan, last_step)
        if proposal is None:
            return
        decision = validate_replan(
            proposal, run.plan, run, policy_provider=self.policy_provider
        )
        if not decision.allowed:
            self._replan_log.append(
                {"move": proposal.move.value, "applied": False, "reason": decision.reason}
            )
            return
        apply_replan(proposal, run.plan, run)
        # An added step needs its own policy decision before the loop runs it.
        for step in run.plan.steps:
            if step.id not in decisions:
                decisions[step.id] = self.policy_provider.decide(step, read_only=True)
        self._replan_log.append(
            {"move": proposal.move.value, "applied": True, "reason": proposal.reason}
        )
        self.store.save_run(run)

    def _finalize(self, run: WorkflowRun) -> None:
        if run.plan.status is WorkflowStatus.RUNNING:
            failed = any(s.status is StepStatus.FAILED for s in run.plan.steps)
            run.plan.status = (
                WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
            )
        run.pid = None
        run.summary = self._summarize(run.plan)
        self.store.save_run(run)
        self._observe(run)

    def _observe(self, run: WorkflowRun) -> None:
        """Hand a terminal run to the observer (e.g. emit an observation).

        No-op without an observer. The observer is responsible for being
        best-effort; it runs after state is persisted so emission can never
        affect the run's recorded outcome.
        """
        if self._observer is None:
            return
        if run.plan.status not in (
            WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED
        ):
            return
        duration_ms = (time.monotonic() - self._start) * 1000 if self._start else None
        self._observer(
            run, {"duration_ms": duration_ms, "approval_count": self._approval_count}
        )

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

    def _needs_plan_approval(self, plan: WorkflowPlan, decisions: dict) -> bool:
        """True if any allowed step requires plan-level (or stricter) approval."""
        return any(
            decisions[s.id].allowed and decisions[s.id].approval != "none"
            for s in plan.steps
        )

    def _approval_summary(self, plan: WorkflowPlan, decisions: dict) -> str:
        """Human-readable plan-approval prompt body listing side effects."""
        lines = [
            f"Workflow: {plan.template}",
            f"Repository: {plan.repo}",
            "",
        ]
        for i, step in enumerate(plan.steps, 1):
            d = decisions[step.id]
            note = "denied: " + d.reason if not d.allowed else f"approval={d.approval}"
            lines.append(f"{i}. {step.name}  [{step.tool}]  {note}")
        lines += ["", "No files will be changed. No commits, pushes or releases."]
        return "\n".join(lines)

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
        self._fail_reason = message
        if step is not None:
            step.status = StepStatus.FAILED
            step.error = message
            run.plan.current_step = step.id
        run.plan.status = WorkflowStatus.FAILED
        run.pid = None
        touch(run)
        self.store.save_run(run)

    # -- summary --------------------------------------------------------

    def _summarize(self, plan: WorkflowPlan, *, approved: bool = True) -> dict[str, Any]:
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
        decisions = getattr(self, "_policy_decisions", {})
        return {
            "ok": plan.status is WorkflowStatus.COMPLETED,
            "status": plan.status.value,
            "passed": passed,
            "total": len(plan.steps),
            "current_step": plan.current_step,
            "error": self._fail_reason,
            "steps": steps,
            "adaptive": {
                "max_replans": plan.max_replans,
                "replans_used": sum(1 for m in self._replan_log if m.get("applied")),
                "moves": list(self._replan_log),
            },
            "policy": {
                "source": self.policy_provider.source,
                "error": self.policy_provider.error,
                "plan_approved": approved,
                "decisions": [d.to_dict() for d in decisions.values()],
            },
        }
