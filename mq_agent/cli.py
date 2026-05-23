import json
import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def _client():
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        console.print("[bold red]Error:[/bold red] OPENAI_API_KEY not set.")
        sys.exit(1)
    return OpenAI(api_key=key)


@click.group()
@click.version_option(version="0.1.0", prog_name="mq-agent")
def main():
    """mq-agent — terminal-native AI agent orchestrator."""


# ── audit ──────────────────────────────────────────────────────────────────

@main.command()
@click.argument("path", default=".")
@click.option("--dry-run", is_flag=True, help="Plan only, no tool execution")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def audit(path: str, dry_run: bool, json_out: bool):
    """Audit a repository (read-only)."""
    from .agents.audit_agent import AuditAgent

    with console.status("[bold cyan]Auditing...[/bold cyan]"):
        result = AuditAgent(_client()).run(path, dry_run=dry_run)

    if json_out:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    console.print(Panel(result["summary"], title=f"[bold]Repo: {path}[/bold]"))
    _print_steps_table(result["steps"], title="Audit Steps")

    if result["passed"]:
        console.print("\n[bold green]✓ Audit passed[/bold green]")
    else:
        console.print("\n[bold red]✗ Audit found issues[/bold red]")
        for f in result["verification"].get("failures", []):
            console.print(f"  [red]•[/red] {f['step']}: {f['note']}")


# ── release-plan ───────────────────────────────────────────────────────────

@main.command("release-plan")
@click.option("--json", "json_out", is_flag=True)
def release_plan(json_out: bool):
    """Show the release plan."""
    from .agents.release_agent import ReleaseAgent

    steps = ReleaseAgent(_client()).create_plan()

    if json_out:
        click.echo(json.dumps({"steps": steps}, indent=2))
        return

    lines = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    console.print(Panel(lines, title="[bold]Release Plan[/bold]", border_style="cyan"))


# ── release-check ──────────────────────────────────────────────────────────

@main.command("release-check")
@click.argument("path", default=".")
@click.option("--dry-run", is_flag=True, default=True, show_default=True)
@click.option("--approve", is_flag=True, help="Allow write operations")
@click.option("--json", "json_out", is_flag=True)
def release_check(path: str, dry_run: bool, approve: bool, json_out: bool):
    """Validate the repo is ready for a release."""
    from .agents.release_agent import ReleaseAgent

    with console.status("[bold cyan]Running release checks...[/bold cyan]"):
        result = ReleaseAgent(_client()).run_check(path, dry_run=dry_run, approve=approve)

    if json_out:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    _print_steps_table(result["steps"], title="Release Checks")

    label = "[bold green]✓ Ready to release[/bold green]" if result["ready"] \
        else "[bold red]✗ Not ready — see issues above[/bold red]"
    console.print(f"\n{label}")


# ── repo-summary ───────────────────────────────────────────────────────────

@main.command("repo-summary")
@click.argument("path", default=".")
@click.option("--json", "json_out", is_flag=True)
def repo_summary_cmd(path: str, json_out: bool):
    """Print a concise repo summary."""
    from .tools.repo_tools import repo_summary

    summary = repo_summary(path)
    if json_out:
        click.echo(json.dumps({"summary": summary}))
    else:
        console.print(Panel(summary, title=f"[bold]{path}[/bold]"))


# ── run ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("command")
@click.option("--cwd", default=".", show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--approve", is_flag=True, help="Execute the command")
def run(command: str, cwd: str, dry_run: bool, approve: bool):
    """Run a shell command safely.

    Requires --approve to actually execute. Use --dry-run to preview.
    """
    from .tools.shell_tools import run_command

    if dry_run:
        console.print(f"[blue][dry-run][/blue] Would run: [bold]{command}[/bold]")
        return

    if not approve:
        console.print(f"[yellow]?[/yellow] Would run: [bold]{command}[/bold]")
        console.print("Add [bold]--approve[/bold] to execute or [bold]--dry-run[/bold] to preview.")
        return

    with console.status(f"Running: {command}"):
        output = run_command(command, cwd=cwd)
    console.print(output)


# ── fix-ci ─────────────────────────────────────────────────────────────────

@main.command("fix-ci")
@click.argument("path", default=".")
@click.option("--dry-run", is_flag=True, default=True, show_default=True)
@click.option("--approve", is_flag=True)
@click.option("--json", "json_out", is_flag=True)
def fix_ci(path: str, dry_run: bool, approve: bool, json_out: bool):
    """Diagnose CI failures and suggest fixes."""
    from .agents.ci_agent import CIAgent

    with console.status("[bold cyan]Diagnosing CI...[/bold cyan]"):
        result = CIAgent(_client()).diagnose(path, dry_run=dry_run, approve=approve)

    if json_out:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    # Print CI context
    for label, key in [("Tests", "tests"), ("Lint", "lint"), ("Types", "types")]:
        ctx = result["ci_context"].get(key, "")
        if ctx and ctx != "(could not run: )":
            console.print(Panel(ctx[:800], title=f"[bold]{label}[/bold]", border_style="dim"))

    _print_steps_table(result["steps"], title="CI Fix Plan")


# ── doctor ─────────────────────────────────────────────────────────────────

@main.command()
def doctor():
    """Check mq-agent environment and dependencies."""
    import subprocess

    checks: list[tuple[str, bool, str]] = []

    # OpenAI key
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    checks.append(("OPENAI_API_KEY", has_key, "Set OPENAI_API_KEY in your shell"))

    # git
    git_ok = subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    checks.append(("git", git_ok, "Install git"))

    # uv
    uv_ok = subprocess.run(["uv", "--version"], capture_output=True).returncode == 0
    checks.append(("uv", uv_ok, "Install uv: https://github.com/astral-sh/uv"))

    # Python version
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python ≥ 3.11", py_ok, f"Upgrade Python (currently {sys.version.split()[0]})"))

    # mq-mcp reachable
    try:
        import httpx
        mcp_ok = httpx.get("http://localhost:8765/health", timeout=1).status_code == 200
    except Exception:
        mcp_ok = False
    checks.append(("mq-mcp (local)", mcp_ok, "Start mq-mcp server on :8765 (optional)"))

    table = Table(title="mq-agent Doctor", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Action")

    for name, ok, action in checks:
        status = Text("✓ OK", style="bold green") if ok else Text("✗ FAIL", style="bold red")
        table.add_row(name, status, "" if ok else action)

    console.print(table)

    all_ok = all(ok for _, ok, _ in checks[:4])  # optional mq-mcp excluded
    if all_ok:
        console.print("\n[bold green]All required checks passed.[/bold green]")
    else:
        console.print("\n[bold red]Fix the issues above before using mq-agent.[/bold red]")


# ── tui ────────────────────────────────────────────────────────────────────

@main.command()
def tui():
    """Launch the Textual TUI."""
    from .tui.app import MQAgentApp

    MQAgentApp().run()


# ── tools ──────────────────────────────────────────────────────────────────

@main.command()
def tools():
    """List registered tools."""
    from .tools import tool_names

    for name in tool_names():
        console.print(f"  [cyan]•[/cyan] {name}")


# ── helpers ────────────────────────────────────────────────────────────────

def _print_steps_table(steps: list[dict], title: str = "Steps"):
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Step")
    table.add_column("Status", width=10)
    table.add_column("Note", overflow="fold")

    for i, s in enumerate(steps, 1):
        status = s.get("status", "")
        color = {
            "success": "green",
            "failed": "red",
            "skipped": "yellow",
            "running": "cyan",
        }.get(status, "white")
        note = s.get("error") or s.get("note") or str(s.get("result", ""))[:120]
        table.add_row(str(i), s.get("description", ""), f"[{color}]{status}[/{color}]", note)

    console.print(table)
