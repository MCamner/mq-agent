"""mq-agent CLI — Typer entry point."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

load_dotenv(Path.home() / "mq-agent" / ".env", override=False)
load_dotenv(Path(".env"), override=False)

app = typer.Typer(
    name="mq-agent",
    help="Terminal-native AI agent orchestrator.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()


def _client():
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        console.print("[bold red]Error:[/bold red] OPENAI_API_KEY is not set.")
        raise typer.Exit(code=1)
    return OpenAI(api_key=key)


# ── audit ──────────────────────────────────────────────────────────────────

@app.command()
def audit(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Plan only, no execution")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
):
    """Audit a repository (read-only)."""
    from mq_agent.agents.audit_agent import AuditAgent

    with console.status("[bold cyan]Auditing...[/bold cyan]"):
        result = AuditAgent(_client()).run(path, dry_run=dry_run)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    console.print(Panel(result["summary"], title=f"[bold]Repo: {path}[/bold]"))
    _print_steps(result["steps"], title="Audit Steps")

    if result["passed"]:
        console.print("\n[bold green]✓ Audit passed[/bold green]")
    else:
        console.print("\n[bold red]✗ Audit found issues[/bold red]")
        for f in result["verification"].get("failures", []):
            console.print(f"  [red]•[/red] {f['step']}: {f['note']}")


# ── plan ───────────────────────────────────────────────────────────────────

@app.command()
def plan(
    goal: Annotated[str, typer.Argument(help="Goal to plan")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Create a plan for a goal using the AI planner."""
    from mq_agent.core.planner import Planner
    from mq_agent.core.state import AgentState, SafetyMode
    from mq_agent.tools import tool_names

    state = AgentState(goal=goal, safety_mode=SafetyMode.SUGGEST)

    with console.status("[bold cyan]Planning...[/bold cyan]"):
        steps = Planner(_client()).create_plan(state, tool_names())

    if json_out:
        typer.echo(json.dumps({"goal": goal, "steps": [s.description for s in steps]}, indent=2))
        return

    lines = "\n".join(f"{i + 1}. {s.description}" for i, s in enumerate(steps))
    console.print(Panel(lines, title=f"[bold]PLAN: {goal}[/bold]", border_style="cyan"))


# ── release-plan ───────────────────────────────────────────────────────────

@app.command(name="release-plan")
def release_plan(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show the standard release plan."""
    from mq_agent.agents.release_agent import ReleaseAgent

    steps = ReleaseAgent(_client()).create_plan()

    if json_out:
        typer.echo(json.dumps({"steps": steps}, indent=2))
        return

    lines = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    console.print(Panel(lines, title="[bold]Release Plan[/bold]", border_style="cyan"))


# ── release-check ──────────────────────────────────────────────────────────

@app.command(name="release-check")
def release_check(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = True,
    approve: Annotated[bool, typer.Option("--approve", help="Allow write operations")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Validate the repo is ready for a release."""
    from mq_agent.agents.release_agent import ReleaseAgent

    with console.status("[bold cyan]Running release checks...[/bold cyan]"):
        result = ReleaseAgent(_client()).run_check(path, dry_run=dry_run, approve=approve)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    _print_steps(result["steps"], title="Release Checks")
    label = (
        "[bold green]✓ Ready to release[/bold green]"
        if result["ready"]
        else "[bold red]✗ Not ready — see issues above[/bold red]"
    )
    console.print(f"\n{label}")


# ── repo-summary ───────────────────────────────────────────────────────────

@app.command(name="repo-summary")
def repo_summary_cmd(
    path: Annotated[str, typer.Argument()] = ".",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Print a concise repo summary."""
    from mq_agent.tools.repo_tools import repo_summary

    summary = repo_summary(path)
    if json_out:
        typer.echo(json.dumps({"summary": summary}))
    else:
        console.print(Panel(summary, title=f"[bold]{path}[/bold]"))


# ── run ────────────────────────────────────────────────────────────────────

@app.command()
def run(
    command: Annotated[str, typer.Argument(help="Shell command to run")],
    cwd: Annotated[str, typer.Option("--cwd")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Execute the command")] = False,
):
    """Run a shell command safely. Requires --approve to execute."""
    from mq_agent.tools.shell_tools import run_command

    if dry_run:
        console.print(f"[blue][dry-run][/blue] Would run: [bold]{command}[/bold]")
        return

    if not approve:
        console.print(f"[yellow]?[/yellow] Would run: [bold]{command}[/bold]")
        console.print("Add [bold]--approve[/bold] to execute or [bold]--dry-run[/bold] to preview.")
        raise typer.Exit()

    with console.status(f"Running: {command}"):
        output = run_command(command, cwd=cwd)
    console.print(output)


# ── fix-ci ─────────────────────────────────────────────────────────────────

@app.command(name="fix-ci")
def fix_ci(
    path: Annotated[str, typer.Argument()] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = True,
    approve: Annotated[bool, typer.Option("--approve")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Diagnose CI failures and suggest fixes."""
    from mq_agent.agents.ci_agent import CIAgent

    with console.status("[bold cyan]Diagnosing CI...[/bold cyan]"):
        result = CIAgent(_client()).diagnose(path, dry_run=dry_run, approve=approve)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    for label, key in [("Tests", "tests"), ("Lint", "lint"), ("Types", "types")]:
        ctx = result["ci_context"].get(key, "")
        if ctx and "(could not run" not in ctx:
            console.print(Panel(ctx[:800], title=f"[bold]{label}[/bold]", border_style="dim"))

    _print_steps(result["steps"], title="CI Fix Plan")


# ── doctor ─────────────────────────────────────────────────────────────────

@app.command()
def doctor():
    """Check mq-agent environment and dependencies."""
    import subprocess

    checks: list[tuple[str, bool, str]] = []

    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    checks.append(("OPENAI_API_KEY", has_key, "export OPENAI_API_KEY=sk-..."))

    git_ok = subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    checks.append(("git", git_ok, "Install git"))

    uv_ok = subprocess.run(["uv", "--version"], capture_output=True).returncode == 0
    checks.append(("uv", uv_ok, "curl -LsSf https://astral.sh/uv/install.sh | sh"))

    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python ≥ 3.11", py_ok, f"Upgrade Python (have {sys.version.split()[0]})"))

    from mq_agent.tools.signal_tools import signal_available
    checks.append(("repo-signal", signal_available(), "uv pip install repo-signal"))

    try:
        import httpx
        mcp_ok = httpx.get("http://localhost:8765/health", timeout=1).status_code == 200
    except Exception:
        mcp_ok = False
    checks.append(("mq-mcp (optional)", mcp_ok, "Start mq-mcp on :8765"))

    table = Table(title="mq-agent Doctor", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Action")

    for name, ok, action in checks:
        status = Text("✓ OK", style="bold green") if ok else Text("✗ FAIL", style="bold red")
        table.add_row(name, status, "" if ok else action)

    console.print(table)

    required_ok = all(ok for _, ok, _ in checks[:4])
    if required_ok:
        console.print("\n[bold green]All required checks passed.[/bold green]")
    else:
        console.print("\n[bold yellow]Fix the issues above before using mq-agent.[/bold yellow]")


# ── signal ─────────────────────────────────────────────────────────────────

@app.command()
def signal(
    path: Annotated[str, typer.Argument(help="Repo path to analyse")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """
    Run a full repo-signal assessment: scan + README score + publish checklist + AI plan.

    Requires repo-signal to be installed:
      uv pip install repo-signal
    """
    from mq_agent.agents.signal_agent import SignalAgent
    from mq_agent.tools.signal_tools import signal_available

    if not signal_available():
        console.print(
            "[bold red]repo-signal not installed.[/bold red]\n"
            "Run: [bold]uv pip install repo-signal[/bold]"
        )
        raise typer.Exit(code=1)

    with console.status("[bold cyan]Running repo-signal assessment...[/bold cyan]"):
        result = SignalAgent(_client()).run(path, dry_run=dry_run)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    scores = result["scores"]
    readme = result["readme"]
    publish = result["publish"]

    # Score panel
    overall = scores["overall"]
    color = "green" if overall >= 80 else "yellow" if overall >= 50 else "red"
    score_lines = (
        f"Overall:  [{color}]{overall}/100[/{color}]\n"
        f"README:   {scores['readme']}/{scores['readme_max']}\n"
        f"Publish:  {scores['publish']}/{scores['publish_total']}  [{publish['status'].upper()}]"
    )
    console.print(Panel(score_lines, title=f"[bold]{result['repo']}[/bold] · {result['project_type']}"))

    # README gaps
    if readme["missing"]:
        console.print("\n[bold yellow]README gaps:[/bold yellow]")
        for m in readme["missing"]:
            console.print(f"  [yellow]✗[/yellow] {m}")

    # Focus areas
    if result["focus_areas"]:
        console.print("\n[bold]Focus areas:[/bold]")
        for i, f in enumerate(result["focus_areas"], 1):
            console.print(f"  {i}. {f}")

    # AI plan steps
    if result["steps"]:
        _print_steps(result["steps"], title="AI Improvement Plan")

    # Verdict
    if overall >= 80:
        console.print("\n[bold green]✓ Repo looks healthy[/bold green]")
    elif overall >= 50:
        console.print("\n[bold yellow]~ Repo needs some work[/bold yellow]")
    else:
        console.print("\n[bold red]✗ Repo needs significant improvement[/bold red]")

    if publish["next_action"]:
        console.print(f"\n[dim]Next: {publish['next_action']}[/dim]")


@app.command()
def score(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """
    Quick README score (0–100) and publish checklist — no AI, instant result.

    Requires repo-signal to be installed:
      uv pip install repo-signal
    """
    from mq_agent.tools.signal_tools import (
        repo_publish_checklist,
        repo_readme_score,
        signal_available,
    )

    if not signal_available():
        console.print(
            "[bold red]repo-signal not installed.[/bold red]\n"
            "Run: [bold]uv pip install repo-signal[/bold]"
        )
        raise typer.Exit(code=1)

    if json_out:
        from mq_agent.tools.signal_tools import repo_signal_json
        typer.echo(json.dumps(repo_signal_json(path), indent=2, default=str))
        return

    console.print(Panel(repo_readme_score(path), title="[bold]README Score[/bold]"))
    console.print(Panel(repo_publish_checklist(path), title="[bold]Publish Checklist[/bold]"))


# ── tui ────────────────────────────────────────────────────────────────────

@app.command()
def tui():
    """Launch the Textual TUI dashboard."""
    from mq_agent.tui.app import MQAgentApp

    MQAgentApp().run()


# ── tools ──────────────────────────────────────────────────────────────────

@app.command()
def tools():
    """List all registered tools."""
    from mq_agent.tools import tool_names

    for name in tool_names():
        console.print(f"  [cyan]•[/cyan] {name}")


# ── helpers ────────────────────────────────────────────────────────────────

def _print_steps(steps: list[dict], title: str = "Steps") -> None:
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Step")
    table.add_column("Status", width=10)
    table.add_column("Note", overflow="fold")

    colors = {"success": "green", "failed": "red", "skipped": "yellow", "running": "cyan"}

    for i, s in enumerate(steps, 1):
        status = s.get("status", "")
        color = colors.get(status, "white")
        note = s.get("error") or s.get("note") or str(s.get("result", ""))[:120]
        table.add_row(str(i), s.get("description", ""), f"[{color}]{status}[/{color}]", note)

    console.print(table)


if __name__ == "__main__":
    app()
