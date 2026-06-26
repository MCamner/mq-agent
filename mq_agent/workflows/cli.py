"""``mq-agent workflow`` CLI surface (Phase 3).

Read-only template commands: ``list``, ``show`` and ``plan``. ``plan`` builds and
prints a validated plan for a repo but **does not persist or execute** it — the
runner arrives in Phase 4. This module imports only the workflows package and
typer (no TUI), so it stays importable and testable on its own.
"""
from __future__ import annotations

import json

import typer

from .runner import Runner
from .state import WorkflowStateError, new_run
from .state import resume as resume_state
from .storage import WorkflowStore
from .templates import TemplateError, instantiate, list_templates, load_template

workflow_app = typer.Typer(
    help="Bounded multi-step workflow templates (list/show/plan). Read-only in v1."
)


@workflow_app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List the available workflow templates."""
    names = list_templates()
    if json_output:
        typer.echo(json.dumps({"templates": names}))
    else:
        for name in names:
            typer.echo(name)


@workflow_app.command("show")
def show_cmd(
    template: str = typer.Argument(..., help="Template name, e.g. repo-preflight."),
) -> None:
    """Show a template's raw definition as JSON."""
    try:
        raw = load_template(template)
    except TemplateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(raw, indent=2))


@workflow_app.command("plan")
def plan_cmd(
    template: str = typer.Argument(..., help="Template name, e.g. repo-preflight."),
    repo: str = typer.Option(..., "--repo", help="Target repository path."),
) -> None:
    """Build and print a validated plan for REPO. Does not run or persist it."""
    run_id = WorkflowStore().generate_run_id()
    try:
        plan = instantiate(template, repo=repo, run_id=run_id)
    except TemplateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(plan.model_dump(mode="json", by_alias=True), indent=2))


def _print_summary(run, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(run.summary or {}, indent=2))
        return
    summary = run.summary or {}
    typer.echo(f"\nRun {run.run_id}: {summary.get('status', run.status.value)}")
    for s in summary.get("steps", []):
        mark = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}.get(
            s["status"], s["status"].upper()
        )
        typer.echo(f"  [{mark}] {s['id']}  {s.get('summary') or ''}".rstrip())


def _make_plan_approver(json_output: bool, yes: bool):
    """Return a plan-approval callback that prompts unless --yes was given."""
    def _approve(summary: str) -> bool:
        if yes:
            return True
        if json_output:
            return False  # never block on a prompt in JSON mode
        typer.echo("\n" + summary + "\n")
        return typer.confirm("Approve this plan?", default=False)

    return _approve


@workflow_app.command("run")
def run_cmd(
    template: str = typer.Argument(..., help="Template name, e.g. repo-preflight."),
    repo: str = typer.Option(..., "--repo", help="Target repository path."),
    json_output: bool = typer.Option(False, "--json", help="Emit the summary as JSON."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve the plan without prompting."),
) -> None:
    """Instantiate, persist and execute a workflow against REPO (read-only)."""
    store = WorkflowStore()
    run_id = store.generate_run_id()
    try:
        plan = instantiate(template, repo=repo, run_id=run_id)
    except TemplateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    run = new_run(plan)
    store.save_run(run)
    total = len(plan.steps)

    def _progress(step) -> None:
        typer.echo(f"[{step.attempt}] {step.id} — running {step.tool} …")

    if not json_output:
        typer.echo(f"Workflow: {template}  repo: {repo}  ({total} steps)  run: {run_id}")
    Runner(
        store,
        plan_approver=_make_plan_approver(json_output, yes),
        on_step=_progress if not json_output else None,
    ).run(run)
    _print_summary(run, json_output)
    raise typer.Exit(0 if (run.summary or {}).get("ok") else 1)


@workflow_app.command("status")
def status_cmd(
    run_id: str = typer.Argument(..., help="Run id, e.g. run_20260626_001."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show a run's current state. Does not execute anything."""
    store = WorkflowStore()
    try:
        run = store.load_run(run_id)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    if run.summary is None:
        run.summary = {
            "status": run.status.value,
            "steps": [
                {"id": s.id, "status": s.status.value,
                 "summary": (s.result or {}).get("summary") or s.error}
                for s in run.plan.steps
            ],
        }
    _print_summary(run, json_output)


@workflow_app.command("resume")
def resume_cmd(
    run_id: str = typer.Argument(..., help="Run id of a paused or failed run."),
    json_output: bool = typer.Option(False, "--json"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve the plan without prompting."),
) -> None:
    """Resume a paused or failed run from where it stopped."""
    store = WorkflowStore()
    try:
        run = store.load_run(run_id)
        resume_state(run)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    store.save_run(run)
    Runner(store, plan_approver=_make_plan_approver(json_output, yes)).run(run)
    _print_summary(run, json_output)
    raise typer.Exit(0 if (run.summary or {}).get("ok") else 1)


@workflow_app.command("cancel")
def cancel_cmd(
    run_id: str = typer.Argument(..., help="Run id to cancel."),
) -> None:
    """Cancel a run."""
    store = WorkflowStore()
    try:
        run = store.cancel_run(run_id)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(f"Run {run.run_id}: {run.status.value}")
