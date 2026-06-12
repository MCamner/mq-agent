"""Controlled autonomous stack loop planning."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


LOOP_CONTRACT: dict[str, Any] = {
    "schema": "mq_stack_loop_plan.v1",
    "execution": "read-only",
    "writes_enabled": False,
    "approval_required_for_writes": True,
    "rollback_required_before_execution": True,
    "rollback": {
        "strategy": "preflight-only",
        "guarantee": "no repository, brain, model, or process mutations are attempted",
    },
}


def _planned_command(next_action: str) -> str | None:
    """Map a dashboard next action to a safe preview command when possible."""
    if next_action.startswith("run stack truth-export"):
        return "mq-agent stack truth-export --dry-run"
    if ": stack release --repo " in next_action:
        repo = next_action.rsplit("stack release --repo ", 1)[-1].strip()
        return f"mq-agent stack release --repo {repo}"
    if next_action.startswith("stack release --repo "):
        repo = next_action.rsplit("stack release --repo ", 1)[-1].strip()
        return f"mq-agent stack release --repo {repo}"
    if next_action in ("all green", "check Ollama runtime"):
        return None
    return None


def stack_loop(
    *,
    dry_run: bool = True,
    approve: bool = False,
    max_iterations: int = 1,
) -> str:
    """Plan one controlled stack loop iteration.

    The v1.20 loop is intentionally read-only for now: it observes the
    operator dashboard, picks the highest-priority next action, and returns
    a plan. It does not execute commands or write to repos.
    """
    from mq_agent.tools.operator_dashboard import operator_dashboard

    dashboard = json.loads(operator_dashboard())
    next_action = str(dashboard.get("next_action") or "")
    command = _planned_command(next_action)
    bounded_iterations = max(1, min(max_iterations, 5))

    if dashboard.get("overall") == "READY":
        decision = "idle"
        reason = "operator dashboard is ready"
    elif command:
        decision = "preview"
        reason = "safe preview command available"
    else:
        decision = "manual"
        reason = "next action requires operator judgement"

    steps: list[dict[str, Any]] = [
        {
            "name": "observe",
            "status": "planned",
            "detail": "read operator dashboard snapshot",
        },
        {
            "name": "decide",
            "status": "planned",
            "detail": reason,
            "decision": decision,
            "next_action": next_action,
        },
    ]
    if command:
        steps.append({
            "name": "preview",
            "status": "planned",
            "detail": command,
            "writes": False,
        })

    return json.dumps({
        "contract": LOOP_CONTRACT,
        "overall": "PLAN",
        "mode": "dry-run" if dry_run else "blocked",
        "approved": approve,
        "writes_enabled": False,
        "max_iterations": bounded_iterations,
        "dashboard_overall": dashboard.get("overall"),
        "next_action": next_action,
        "decision": decision,
        "steps": steps,
        "blocked": not dry_run,
        "blocker": None if dry_run else "autonomous execution is not enabled in v1.20 preview",
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2, default=str)
