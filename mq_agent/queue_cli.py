"""Operator-driven task ownership and handoff commands."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

queue_app = typer.Typer(
    help="Coordinate agent tasks, isolated worktrees, verification and handoffs.",
    no_args_is_help=True,
)
Json = Annotated[bool, typer.Option("--json", help="Emit JSON.")]
Owner = Annotated[str, typer.Option("--owner", help="Agent claiming or owning this task.")]
TaskId = Annotated[str, typer.Argument(help="Task id returned by queue add.")]


def _call(method: str, json_output: bool, *args: Any, **kwargs: Any) -> None:
    from mq_agent.task_queue import TaskQueue, TaskQueueError

    try:
        value = getattr(TaskQueue(), method)(*args, **kwargs)
    except (TaskQueueError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if json_output:
        typer.echo(json.dumps(value, indent=2))
    elif isinstance(value, list):
        if not value:
            typer.echo("No tasks.")
        for task in value:
            typer.echo(f"{task['id']}  {task['status']}  {task.get('owner') or '-'}  {task['goal']}")
    else:
        typer.echo(f"{value['id']}: {value['status']} — {value['goal']}")
        if value.get("worktree"):
            typer.echo(f"Worktree: {value['worktree']}")
        typer.echo(f"Base commit: {value['base_commit']}")
        typer.echo(f"Time budget: {value['budget_minutes']} minutes (advisory)")
        if method == "show":
            typer.echo(json.dumps(value, indent=2))


@queue_app.command("add")
def add_cmd(
    goal: Annotated[str, typer.Argument(help="Bounded task goal.")],
    repo: Annotated[Path, typer.Option("--repo", help="Source Git repository.")],
    budget_minutes: Annotated[int, typer.Option("--budget-minutes", help="Advisory time budget.")] = 60,
    json_output: Json = False,
) -> None:
    """Queue a task at the repository's current commit without executing it."""
    _call("add", json_output, goal, repo, budget_minutes=budget_minutes)


@queue_app.command("list")
def list_cmd(json_output: Json = False) -> None:
    """List persisted tasks and their owners."""
    _call("list", json_output)


@queue_app.command("show")
def show_cmd(task_id: TaskId, json_output: Json = False) -> None:
    """Show task state, worktree, verification and handoff history."""
    _call("show", json_output, task_id)


@queue_app.command("claim")
def claim_cmd(
    task_id: TaskId,
    owner: Owner,
    worktree: Annotated[Path | None, typer.Option("--worktree", help="Use an existing separate linked worktree.")] = None,
    json_output: Json = False,
) -> None:
    """Claim or resume a task; create an isolated worktree unless one is supplied."""
    _call("claim", json_output, task_id, owner, worktree=worktree)


@queue_app.command("pause")
def pause_cmd(task_id: TaskId, owner: Owner, json_output: Json = False) -> None:
    """Pause work while retaining the owner and worktree reservation."""
    _call("pause", json_output, task_id, owner)


@queue_app.command("handoff")
def handoff_cmd(
    task_id: TaskId,
    owner: Owner,
    to_owner: Annotated[str, typer.Option("--to", help="Named agent allowed to accept this handoff.")],
    summary: Annotated[str, typer.Option("--summary", help="Completed work and review context.")],
    remaining: Annotated[str, typer.Option("--remaining", help="Outstanding work or problems.")],
    json_output: Json = False,
) -> None:
    """Record a structured handoff without starting the receiving agent."""
    _call("handoff", json_output, task_id, owner, to_owner, summary, remaining)


@queue_app.command("link-run")
def link_run_cmd(
    task_id: TaskId,
    run_id: Annotated[str, typer.Argument(help="Existing workflow run targeting this task's worktree.")],
    owner: Owner,
    json_output: Json = False,
) -> None:
    """Link existing workflow state; never execute or approve the workflow."""
    _call("link_run", json_output, task_id, owner, run_id)


@queue_app.command("complete")
def complete_cmd(task_id: TaskId, owner: Owner, json_output: Json = False) -> None:
    """Complete only with a fresh PASS verification receipt against the task base."""
    _call("complete", json_output, task_id, owner)


@queue_app.command("cancel")
def cancel_cmd(
    task_id: TaskId,
    owner: Annotated[str | None, typer.Option("--owner", help="Required for an owned task.")] = None,
    json_output: Json = False,
) -> None:
    """Cancel a task and release its reservation; retain worktrees and branches."""
    _call("cancel", json_output, task_id, owner=owner)
