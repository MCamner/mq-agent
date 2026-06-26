"""``mq-agent workflow`` CLI surface (Phase 3).

Read-only template commands: ``list``, ``show`` and ``plan``. ``plan`` builds and
prints a validated plan for a repo but **does not persist or execute** it — the
runner arrives in Phase 4. This module imports only the workflows package and
typer (no TUI), so it stays importable and testable on its own.
"""
from __future__ import annotations

import json

import typer

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
