"""Controlled autonomous stack loop planning."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LOOP_CONTRACT: dict[str, Any] = {
    "schema": "mq_stack_loop_plan.v1",
    "execution": "controlled",
    "approval_required_for_writes": True,
    "writes_require_execute": True,
    "allowed_actions": ["truth-export", "stack-release"],
    "rollback_required": True,
}


def _planned_action(next_action: str) -> dict[str, Any] | None:
    """Map a dashboard next action to an allowlisted loop action."""
    if next_action.startswith("run stack truth-export"):
        return {
            "action": "truth-export",
            "command": "mq-agent stack truth-export --dry-run",
            "execute_command": "mq-agent stack truth-export",
            "writes": True,
            "rollback": "restore or delete the generated stack-truth note if execution fails",
        }
    if ": stack release --repo " in next_action:
        repo = next_action.rsplit("stack release --repo ", 1)[-1].strip()
        return {
            "action": "stack-release",
            "repo": repo,
            "command": f"mq-agent stack release --repo {repo}",
            "execute_command": f"mq-agent stack release --repo {repo} --execute",
            "writes": True,
            "rollback": "delegated to stack_release rollback before commit; aborts on failed step",
        }
    if next_action.startswith("stack release --repo "):
        repo = next_action.rsplit("stack release --repo ", 1)[-1].strip()
        return {
            "action": "stack-release",
            "repo": repo,
            "command": f"mq-agent stack release --repo {repo}",
            "execute_command": f"mq-agent stack release --repo {repo} --execute",
            "writes": True,
            "rollback": "delegated to stack_release rollback before commit; aborts on failed step",
        }
    if next_action in ("all green", "check Ollama runtime"):
        return None
    return None


def _restore_file(path: Path, existed: bool, before: str) -> dict[str, Any]:
    if existed:
        path.write_text(before, encoding="utf-8")
        return {"status": "restored", "path": str(path)}
    if path.exists():
        path.unlink()
        return {"status": "deleted", "path": str(path)}
    return {"status": "not-needed", "path": str(path)}


def _execute_action(action: dict[str, Any]) -> dict[str, Any]:
    """Execute an allowlisted action through local tool APIs, not a shell."""
    name = action["action"]
    if name == "truth-export":
        from mq_agent.tools.stack_truth import default_stack_truth_path, stack_truth_export

        planned = stack_truth_export(write=False)
        dest = Path(planned["path"]).expanduser() if planned.get("path") else default_stack_truth_path()
        existed = dest.exists()
        before = dest.read_text(encoding="utf-8") if existed else ""
        try:
            result = stack_truth_export(output_path=str(dest), write=True)
        except Exception as exc:
            rollback = _restore_file(dest, existed, before)
            return {"ok": False, "action": name, "error": str(exc), "rollback": rollback}
        if not result.get("written"):
            rollback = _restore_file(dest, existed, before)
            return {
                "ok": False,
                "action": name,
                "error": "truth export did not report a written note",
                "rollback": rollback,
            }
        return {
            "ok": bool(result.get("written")),
            "action": name,
            "path": result.get("path"),
            "status": result.get("status"),
            "rollback": {
                "status": "available",
                "strategy": "restore-previous-file" if existed else "delete-created-file",
                "path": str(dest),
            },
        }

    if name == "stack-release":
        from mq_agent.tools.stack_release import stack_release

        repo = str(action.get("repo", ""))
        result = json.loads(stack_release(repo, execute=True))
        return {
            "ok": bool(result.get("released")),
            "action": name,
            "repo": repo,
            "result": result,
            "rollback": {
                "status": "delegated",
                "strategy": "stack_release.execute_stack_release",
            },
        }

    return {"ok": False, "action": name, "error": "action is not allowlisted"}


def stack_loop(
    *,
    dry_run: bool = True,
    approve: bool = False,
    execute: bool = False,
    max_iterations: int = 1,
) -> str:
    """Plan or execute one controlled stack loop iteration."""
    from mq_agent.tools.operator_dashboard import operator_dashboard

    dashboard = json.loads(operator_dashboard())
    next_action = str(dashboard.get("next_action") or "")
    action = _planned_action(next_action)
    bounded_iterations = max(1, min(max_iterations, 5))
    requested_execution = execute or not dry_run
    execution_result: dict[str, Any] | None = None

    if dashboard.get("overall") == "READY":
        decision = "idle"
        reason = "operator dashboard is ready"
    elif action:
        decision = "preview"
        reason = "safe preview command available"
    else:
        decision = "manual"
        reason = "next action requires operator judgement"

    blocked = False
    blocker = None
    mode = "dry-run"

    if requested_execution:
        mode = "approved-execution" if approve else "blocked"
        if not approve:
            blocked = True
            blocker = "execution requires --approve"
        elif decision == "idle":
            mode = "idle"
        elif action is None:
            blocked = True
            mode = "blocked"
            blocker = "next action is not allowlisted for controlled execution"
        else:
            execution_result = _execute_action(action)
            if not execution_result.get("ok"):
                mode = "blocked"
                blocked = True
                blocker = str(execution_result.get("error") or "controlled execution failed")

    steps: list[dict[str, Any]] = [
        {
            "name": "observe",
            "status": "done" if execution_result else "planned",
            "detail": "read operator dashboard snapshot",
        },
        {
            "name": "decide",
            "status": "done" if execution_result else "planned",
            "detail": reason,
            "decision": decision,
            "next_action": next_action,
        },
    ]
    if action:
        steps.append({
            "name": "preview",
            "status": "planned",
            "detail": action["command"],
            "writes": False,
            "execute_detail": action["execute_command"],
            "rollback": action["rollback"],
        })
    if requested_execution:
        if execution_result:
            steps.append({
                "name": "execute",
                "status": "done" if execution_result.get("ok") else "failed",
                "detail": action["execute_command"] if action else "no allowlisted action",
                "writes": bool(action and action.get("writes")),
            })
        else:
            steps.append({
                "name": "execute",
                "status": "blocked",
                "detail": blocker or "no execution needed",
                "writes": False,
            })

    return json.dumps({
        "contract": LOOP_CONTRACT,
        "overall": "PLAN",
        "mode": mode,
        "approved": approve,
        "writes_enabled": bool(requested_execution and approve and action and action.get("writes") and not blocked),
        "max_iterations": bounded_iterations,
        "dashboard_overall": dashboard.get("overall"),
        "next_action": next_action,
        "decision": decision,
        "steps": steps,
        "blocked": blocked,
        "blocker": blocker,
        "execution_result": execution_result,
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2, default=str)
