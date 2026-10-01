"""Read-only CLI for the feedback evidence surface."""
from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .views import (
    feedback_inspect,
    feedback_recent,
    feedback_report,
    feedback_status,
)

app = typer.Typer(
    help="Inspect feedback experiment evidence (read-only).",
    no_args_is_help=True,
)
console = Console()


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _render_status(payload: dict[str, Any]) -> None:
    table = Table(title="Feedback Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Health", str(payload["health"]))
    table.add_row("Valid records", str(payload["valid_records"]))
    table.add_row("Invalid records", str(payload["invalid_records"]))
    table.add_row("Newest", str(payload["newest_recorded_at"] or "unavailable"))
    task_classes = payload["task_classes"]
    table.add_row(
        "Task classes",
        ", ".join(f"{name}={count}" for name, count in task_classes.items())
        if task_classes
        else "none",
    )
    states = payload["states"]
    table.add_row(
        "States",
        ", ".join(f"{name}={count}" for name, count in states.items())
        if states
        else "none",
    )
    table.add_row("Source", str(payload["source_root"]))
    console.print(table)
    for reason in payload["degraded_reasons"]:
        console.print(f"[yellow]degraded:[/yellow] {reason}")


@app.command("status")
def feedback_status_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show feedback storage health and experiment coverage."""
    payload = feedback_status()
    if json_out:
        _emit_json(payload)
        return
    _render_status(payload)


@app.command("inspect")
def feedback_inspect_cmd(
    feedback_run_id: Annotated[str, typer.Argument(help="Feedback run identifier")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explain one immutable feedback experiment chain."""
    try:
        payload = feedback_inspect(feedback_run_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        _emit_json(payload)
        return

    console.print(
        Panel(
            f"Health: {payload['health']}\n"
            f"Feedback run: {payload['feedback_run_id']}",
            title="Feedback Inspect",
        )
    )
    experiment = payload["experiment"]
    if experiment is not None:
        record = experiment["record"]
        ref = experiment["store_ref"]
        table = Table(title="Experiment")
        table.add_column("Field")
        table.add_column("Value")
        for field in (
            "recorded_at",
            "task_class",
            "repository",
            "active_strategy",
            "shadow_strategy",
            "state",
            "execution_run_id",
        ):
            table.add_row(field, str(record.get(field, "unavailable")))
        table.add_row("snapshot", f"{record['snapshot']['ref']}@{record['snapshot']['commit']}")
        table.add_row("store ref", f"{ref['file']}:{ref['line']}")
        console.print(table)
    else:
        duplicates = payload["duplicate_records"]
        console.print(
            f"[yellow]Ambiguous immutable id: {len(duplicates)} records share this id.[/yellow]"
        )
        for item in duplicates:
            ref = item["store_ref"]
            console.print(f"  {ref['file']}:{ref['line']}")

    console.print(
        f"Comparison: {payload['comparison']['status']} "
        f"({payload['comparison']['reason']})"
    )
    console.print(
        f"Candidate: {payload['candidate']['status']} "
        f"({payload['candidate']['reason']})"
    )
    for reason in payload["degraded_reasons"]:
        console.print(f"[yellow]degraded:[/yellow] {reason}")


@app.command("recent")
def feedback_recent_cmd(
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=200, help="Newest records to return (1-200)"),
    ] = 20,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List retained feedback experiments newest first."""
    try:
        payload = feedback_recent(limit=limit)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        _emit_json(payload)
        return

    table = Table(title="Feedback Recent")
    table.add_column("Recorded")
    table.add_column("Feedback run")
    table.add_column("Task class")
    table.add_column("State")
    table.add_column("Active")
    table.add_column("Shadow")
    for item in payload["entries"]:
        record = item["record"]
        table.add_row(
            str(record["recorded_at"]),
            str(record["feedback_run_id"]),
            str(record["task_class"]),
            str(record["state"]),
            str(record["active_strategy"]),
            str(record["shadow_strategy"]),
        )
    console.print(table)
    console.print(f"Showing {payload['returned']} of {payload['matched']} valid records")
    if payload["invalid_records"]:
        console.print(f"[yellow]Invalid records: {payload['invalid_records']}[/yellow]")


@app.command("report")
def feedback_report_cmd(
    task_class: Annotated[
        str | None, typer.Option("--task-class", help="Limit report to one task class")
    ] = None,
    since: Annotated[
        str | None, typer.Option("--since", help="Positive day window, e.g. 30d")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Aggregate feedback evidence without deriving a winner."""
    try:
        payload = feedback_report(task_class=task_class, since=since)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        _emit_json(payload)
        return

    summary = Table(title="Feedback Report")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Health", str(payload["health"]))
    summary.add_row("Matched", str(payload["matched_records"]))
    summary.add_row("Total", str(payload["total_records"]))
    summary.add_row("Invalid", str(payload["invalid_records"]))
    summary.add_row("Newest", str(payload["newest_recorded_at"] or "unavailable"))
    summary.add_row("Task class", str(payload["filter"]["task_class"] or "all"))
    summary.add_row("Window", str(payload["filter"]["since"] or "all"))
    summary.add_row("Source", str(payload["source_root"]))
    console.print(summary)

    coverage = Table(title="Coverage")
    coverage.add_column("Dimension")
    coverage.add_column("Values")
    coverage.add_row(
        "Task classes",
        ", ".join(f"{k}={v}" for k, v in payload["by_task_class"].items()) or "none",
    )
    coverage.add_row(
        "States",
        ", ".join(f"{k}={v}" for k, v in payload["by_state"].items()) or "none",
    )
    coverage.add_row("Repositories", ", ".join(payload["repositories"]) or "none")
    coverage.add_row(
        "Active strategies", ", ".join(payload["active_strategies"]) or "none"
    )
    coverage.add_row(
        "Shadow strategies", ", ".join(payload["shadow_strategies"]) or "none"
    )
    coverage.add_row(
        "Network backends", ", ".join(payload["network_backends"]) or "none"
    )
    console.print(coverage)

    metrics = Table(title="Metrics")
    metrics.add_column("Metric")
    metrics.add_column("Status")
    metrics.add_column("Value")
    for name, metric in payload["metrics"].items():
        metrics.add_row(
            name,
            str(metric["status"]),
            str(metric["value"]) if metric["value"] is not None else "unavailable",
        )
    console.print(metrics)
    console.print(
        f"Comparison: {payload['comparison']['status']} "
        f"({payload['comparison']['reason']})"
    )
    for reason in payload["degraded_reasons"]:
        console.print(f"[yellow]degraded:[/yellow] {reason}")
