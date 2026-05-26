"""Rich rendering helpers for the mq-agent CLI.

All functions take an explicit `console` argument so they can be used
in any context without depending on a module-level console instance.
"""
from __future__ import annotations

import pprint

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_SAFETY_COLORS: dict[str, str] = {
    "read-only": "green",
    "write-capable": "yellow",
    "subprocess": "yellow",
    "dangerous": "red",
    "unknown": "dim",
}

_STEP_COLORS: dict[str, str] = {
    "success": "green",
    "failed": "red",
    "skipped": "yellow",
    "running": "cyan",
}

_STATUS_ICONS: dict[str, str] = {
    "ok": "[bold green]✓[/bold green]",
    "dry-run": "[bold blue]~[/bold blue]",
    "skipped": "[dim]–[/dim]",
    "error": "[bold red]✗[/bold red]",
}


def print_steps(console: Console, steps: list[dict], title: str = "Steps") -> None:
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Step")
    table.add_column("Status", width=10)
    table.add_column("Note", overflow="fold")

    for i, s in enumerate(steps, 1):
        status = s.get("status", "")
        color = _STEP_COLORS.get(status, "white")
        note = s.get("error") or s.get("note") or str(s.get("result", ""))[:120]
        table.add_row(str(i), s.get("description", ""), f"[{color}]{status}[/{color}]", note)

    console.print(table)


def print_tool_spec(console: Console, spec) -> None:
    lines = (
        f"[bold]Tool:[/bold]        {spec.name}\n"
        f"[bold]Source:[/bold]      {spec.source}\n"
        f"[bold]Safety:[/bold]      {spec.safety_class}\n"
    )
    if spec.description:
        lines += f"\n[bold]Description:[/bold]\n{spec.description}\n"
    if spec.input_schema:
        lines += f"\n[bold]Input schema:[/bold]\n{pprint.pformat(spec.input_schema, width=60)}\n"
    if spec.examples:
        lines += "\n[bold]Examples:[/bold]\n" + "\n".join(f"  {e}" for e in spec.examples)
    console.print(Panel(lines, title=f"[bold]{spec.name}[/bold]"))


def print_mcp_tool_table(console: Console, specs: list) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Tool", style="cyan")
    table.add_column("Safety", width=14)
    table.add_column("Description", overflow="fold")

    for spec in sorted(specs, key=lambda s: (s.safety_class, s.name)):
        color = _SAFETY_COLORS.get(spec.safety_class, "white")
        table.add_row(spec.name, f"[{color}]{spec.safety_class}[/{color}]", spec.description)

    console.print(table)


def print_swarm_result(console: Console, result) -> None:
    table = Table(show_header=True, header_style="bold", title=f"Swarm: {result.config}")
    table.add_column("Agent", style="cyan")
    table.add_column("Status", width=10)
    table.add_column("Elapsed", width=9)
    table.add_column("Note", overflow="fold")

    for r in result.results:
        icon = _STATUS_ICONS.get(r.status, r.status)
        note = r.error if r.error else ""
        if not note and r.status == "ok":
            passed = r.output.get("passed", r.output.get("ready", ""))
            if passed is not None:
                note = "passed" if passed else "issues found"
        table.add_row(r.agent, icon, f"{r.elapsed_s:.1f}s", note)

    console.print(table)
    console.print(f"[dim]Total: {result.elapsed_s:.1f}s · path: {result.path}[/dim]")

    if result.passed:
        console.print("\n[bold green]✓ Swarm passed[/bold green]")
    else:
        console.print(f"\n[bold red]✗ Swarm failed — {', '.join(result.failed_agents)}[/bold red]")
