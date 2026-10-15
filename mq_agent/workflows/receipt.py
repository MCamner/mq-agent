"""mq-agent-owned presentation of measured workflow facts, never promotion evidence."""

from __future__ import annotations
from importlib.metadata import version, PackageNotFoundError
from .state import WorkflowRun


def build_receipt(run: WorkflowRun) -> dict:
    steps = []
    incomplete = False
    unknown_work = False
    for step in run.plan.steps:
        result = step.result or {}
        data = result.get("data") or {}
        measured = data.get("completeness")
        coverage = data.get("coverage")
        if measured is None and isinstance(coverage, dict):
            measured = {
                "status": "complete" if coverage.get("complete") is True else "partial",
                **coverage,
            }
        if isinstance(measured, dict):
            incomplete |= measured.get("status") == "partial"
            unknown_work |= measured.get("status") not in ("complete", "partial")
        steps.append(
            {
                "id": step.id,
                "tool": step.tool,
                "status": step.status.value,
                "verification": data.get("verification")
                if data.get("verification") in ("passed", "failed", "unknown")
                else "passed"
                if step.status.value == "passed"
                else "failed"
                if step.status.value == "failed"
                else "unknown",
                "execution_run_id": data.get("execution_run_id"),
                "execution_outcome_recorded": data.get("execution_outcome_recorded"),
                "fallback": data.get("fallback"),
                "completeness": measured,
            }
        )
    total = len(steps)
    passed = sum(s["status"] == "passed" for s in steps)
    failed = sum(s["status"] == "failed" for s in steps)
    skipped = sum(s["status"] == "skipped" for s in steps)
    cancelled = sum(s["status"] == "cancelled" for s in steps)
    pending = total - passed - failed - skipped - cancelled
    complete = bool(total) and passed == total and not incomplete and not unknown_work
    verification = (
        "failed"
        if any(s["verification"] == "failed" for s in steps)
        else "passed"
        if total and all(s["verification"] == "passed" for s in steps)
        else "unknown"
    )
    ok = (
        run.status.value == "completed"
        and complete
        and verification == "passed"
        and run.recording.get("workflow_state") is not False
    )
    try:
        runtime_version = version("mq-agent")
    except PackageNotFoundError:
        runtime_version = None
    summary = run.summary or {}
    if run.recording.get("workflow_state") is False:
        action = (
            "restore workflow storage and inspect the unsaved result before resuming"
        )
    elif ok:
        action = "none"
    elif run.status.value == "awaiting_approval":
        action = "approve plan to execute"
    elif run.status.value in ("failed", "paused"):
        action = "fix the reported cause, then explicitly resume"
    else:
        action = "inspect remaining or unmeasured work"
    return {
        "schema": "mq.workflow-receipt.v1",
        "run_id": run.run_id,
        "template": run.plan.template,
        "status": run.status.value,
        "ok": ok,
        "repo": run.repo_identity or {"root": run.plan.repo, "commit": None},
        "runtime": run.runtime_identity
        or {"name": "mq-agent", "version": runtime_version, "commit": None},
        "steps": steps,
        "completeness": {
            "planned": total,
            "completed": passed,
            "failed": failed,
            "skipped": skipped,
            "cancelled": cancelled,
            "pending": pending,
            "coverage": passed / total if total else None,
            "status": "complete"
            if complete
            else "unknown"
            if not total or unknown_work
            else "partial",
        },
        "verification": {"status": verification},
        "recording": {
            "workflow_state": run.recording.get("workflow_state"),
            "observation": run.recording.get("observation"),
            "execution_outcome": run.recording.get("execution_outcome"),
        },
        "execution_run_id": run.execution_run_id,
        "context_sources": run.context_sources,
        "fallback": "static-read-only-allowlist"
        if summary.get("policy", {}).get("source") == "fallback"
        else None,
        "next_action": {
            "action": action,
            "approval_required": run.status.value
            in ("awaiting_approval", "paused", "failed"),
        },
    }
