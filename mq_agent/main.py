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

mcp_app = typer.Typer(help="Inspect and manage the local mq-mcp tool server.")
app.add_typer(mcp_app, name="mcp")

memory_app = typer.Typer(help="Semantic repository memory commands.")
app.add_typer(memory_app, name="memory")

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


# ── docs-audit ─────────────────────────────────────────────────────────────

@app.command(name="docs-audit")
def docs_audit(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Audit repository documentation: README, CHANGELOG, docstrings, /docs."""
    from mq_agent.agents.docs_agent import DocsAgent

    with console.status("[bold cyan]Auditing docs...[/bold cyan]"):
        result = DocsAgent(_client()).audit(path)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    _print_steps(result["steps"], title="Docs Audit")
    if result["verification"]["all_passed"]:
        console.print("\n[bold green]✓ Docs audit passed[/bold green]")
    else:
        console.print("\n[bold red]✗ Docs audit found issues[/bold red]")
        for f in result["verification"].get("failures", []):
            console.print(f"  [red]•[/red] {f['step']}: {f['note']}")


# ── tui ────────────────────────────────────────────────────────────────────

@app.command()
def tui():
    """Launch the Textual TUI dashboard."""
    from mq_agent.tui.app import MQAgentApp

    MQAgentApp().run()


# ── tools ──────────────────────────────────────────────────────────────────

@app.command()
def tools(
    describe: Annotated[str | None, typer.Option("--describe", help="Show details for a specific tool")] = None,
    include_mcp: Annotated[bool, typer.Option("--mcp", help="Include discovered MCP tools")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List registered tools. Use --describe <name> for details, --mcp to include MCP tools."""
    from mq_agent.tools import tool_names
    from mq_agent.tools.mcp_bridge import MCPBridge

    if describe:
        bridge = MCPBridge()
        spec = bridge.describe_tool(describe)
        if json_out:
            typer.echo(json.dumps(spec.to_dict(), indent=2))
            return
        _print_tool_spec(spec)
        return

    built_in = tool_names()

    if include_mcp:
        bridge = MCPBridge()
        mcp_specs = bridge.list_tool_specs()
        if json_out:
            data = {
                "built_in": built_in,
                "mcp": [s.to_dict() for s in mcp_specs],
            }
            typer.echo(json.dumps(data, indent=2))
            return
        console.print("[bold]Built-in tools:[/bold]")
        for name in built_in:
            console.print(f"  [cyan]•[/cyan] {name}")
        console.print(f"\n[bold]MCP tools ({len(mcp_specs)} discovered):[/bold]")
        _print_mcp_tool_table(mcp_specs)
        return

    if json_out:
        typer.echo(json.dumps({"built_in": built_in}, indent=2))
        return

    for name in built_in:
        console.print(f"  [cyan]•[/cyan] {name}")


# ── mcp start ──────────────────────────────────────────────────────────────

@mcp_app.command("start")
def mcp_start(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Start mq-mcp server in the background."""
    from mq_agent.mcp.manager import start

    already_running, pid, msg = start()

    if json_out:
        typer.echo(json.dumps({
            "already_running": already_running,
            "pid": pid,
            "message": msg,
            "ok": pid is not None,
        }, indent=2))
        if pid is None:
            raise typer.Exit(1)
        return

    if pid is None:
        console.print(Panel(
            f"[bold red]Failed to start mq-mcp[/bold red]\n{msg}",
            title="[bold]mq-mcp Start[/bold]",
            border_style="red",
        ))
        raise typer.Exit(1)

    if already_running:
        console.print(Panel(
            f"[bold yellow]mq-mcp already running[/bold yellow]\n{msg}",
            title="[bold]mq-mcp Start[/bold]",
            border_style="yellow",
        ))
        return

    console.print(Panel(
        f"[bold green]mq-mcp started[/bold green]\n{msg}",
        title="[bold]mq-mcp Start[/bold]",
        border_style="green",
    ))


# ── mcp stop ───────────────────────────────────────────────────────────────

@mcp_app.command("stop")
def mcp_stop(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Stop the background mq-mcp server."""
    from mq_agent.mcp.manager import stop

    was_running, pid, msg = stop()

    if json_out:
        typer.echo(json.dumps({
            "was_running": was_running,
            "pid": pid,
            "message": msg,
        }, indent=2))
        return

    border = "green" if was_running else "yellow"
    icon = "[bold green]mq-mcp stopped[/bold green]" if was_running else "[bold yellow]mq-mcp not running[/bold yellow]"
    console.print(Panel(f"{icon}\n{msg}", title="[bold]mq-mcp Stop[/bold]", border_style=border))


# ── mcp status ─────────────────────────────────────────────────────────────

@mcp_app.command("status")
def mcp_status(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Check whether mq-mcp is reachable and show tool counts by safety class."""
    from mq_agent.tools.mcp_bridge import MCPBridge
    from mq_agent.tools.mcp_registry import MCPSafetyClass

    bridge = MCPBridge()
    available = bridge.is_available()

    from mq_agent.mcp.manager import is_running as process_is_running, read_pid

    process_running = process_is_running()
    pid = read_pid()

    if available:
        specs = bridge.list_tool_specs()
        counts: dict[str, int] = {}
        for s in specs:
            counts[s.safety_class] = counts.get(s.safety_class, 0) + 1
    else:
        specs = []
        counts = {}

    if json_out:
        typer.echo(json.dumps({
            "available": available,
            "process_running": process_running,
            "pid": pid,
            "endpoint": bridge.endpoint,
            "tools": len(specs),
            "counts": counts,
        }, indent=2))
        return

    pid_line = f"process:  PID {pid}" if pid else "process:  not started"

    if available:
        lines = (
            f"[bold green]mq-mcp: reachable[/bold green]\n"
            f"endpoint: {bridge.endpoint}\n"
            f"{pid_line}\n"
            f"tools:    {len(specs)}\n"
            + "\n".join(
                f"  {cls}: {counts.get(cls, 0)}"
                for cls in [
                    MCPSafetyClass.READ_ONLY,
                    MCPSafetyClass.WRITE_CAPABLE,
                    MCPSafetyClass.SUBPROCESS,
                    MCPSafetyClass.DANGEROUS,
                    MCPSafetyClass.UNKNOWN,
                ]
                if counts.get(cls, 0) > 0
            )
        )
        console.print(Panel(lines, title="[bold]mq-mcp Status[/bold]", border_style="green"))
    elif process_running:
        console.print(Panel(
            f"[bold yellow]mq-mcp: process running, HTTP not reachable[/bold yellow]\n\n"
            f"{pid_line}\n"
            f"endpoint: {bridge.endpoint}\n\n"
            f"mq-mcp runs in stdio mode — the HTTP bridge at :8765 is not available.",
            title="[bold]mq-mcp Status[/bold]",
            border_style="yellow",
        ))
    else:
        console.print(
            Panel(
                f"[bold red]mq-mcp: not running[/bold red]\n\n"
                f"Start with:\n  mq-agent mcp start",
                title="[bold]mq-mcp Status[/bold]",
                border_style="red",
            )
        )


# ── mcp tools ──────────────────────────────────────────────────────────────

@mcp_app.command("tools")
def mcp_tools_list(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List all tools discovered from mq-mcp with safety classes."""
    from mq_agent.tools.mcp_bridge import MCPBridge

    bridge = MCPBridge()
    if not bridge.is_available():
        console.print(f"[bold red]mq-mcp not reachable[/bold red]\n{bridge.not_reachable_message()}")
        raise typer.Exit(code=1)

    specs = bridge.list_tool_specs()

    if json_out:
        typer.echo(json.dumps([s.to_dict() for s in specs], indent=2))
        return

    _print_mcp_tool_table(specs)


# ── run-tool ───────────────────────────────────────────────────────────────

@app.command(name="run-tool")
def run_tool(
    tool: Annotated[str, typer.Argument(help="MCP tool name to run")],
    arg: Annotated[list[str], typer.Option("--arg", help="key=value argument (repeatable)")] = [],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without executing")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Allow write-capable and subprocess tools")] = False,
    dangerous: Annotated[bool, typer.Option("--dangerous", help="Allow dangerous-class tools")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Run a specific MCP tool through mq-agent safety gates."""
    from mq_agent.tools.mcp_bridge import MCPBridge
    from mq_agent.tools.mcp_registry import MCPSafetyClass

    bridge = MCPBridge()
    spec = bridge.describe_tool(tool)

    # Parse --arg key=value pairs
    args: dict[str, str] = {}
    for item in arg:
        if "=" in item:
            k, _, v = item.partition("=")
            args[k.strip()] = v.strip()
        else:
            console.print(f"[yellow]Warning:[/yellow] --arg '{item}' is not key=value, skipping")

    # Safety gate
    cls = spec.safety_class
    if cls == MCPSafetyClass.UNKNOWN:
        console.print(
            f"[bold red]Blocked:[/bold red] tool '{tool}' has unknown safety class.\n"
            "Only tools with a known safety class can be run."
        )
        raise typer.Exit(code=1)

    if cls == MCPSafetyClass.DANGEROUS and not dangerous:
        console.print(
            f"[bold red]Blocked:[/bold red] tool '{tool}' is classified [red]dangerous[/red].\n"
            "Add [bold]--dangerous[/bold] to run it."
        )
        raise typer.Exit(code=1)

    if cls in (MCPSafetyClass.WRITE_CAPABLE, MCPSafetyClass.SUBPROCESS) and not approve and not dangerous:
        console.print(
            f"[bold yellow]Blocked:[/bold yellow] tool '{tool}' is classified [yellow]{cls}[/yellow].\n"
            "Add [bold]--approve[/bold] to run it."
        )
        raise typer.Exit(code=1)

    if dry_run:
        preview = {
            "tool": tool,
            "args": args,
            "safety_class": cls,
            "would_execute": not dry_run,
        }
        if json_out:
            typer.echo(json.dumps(preview, indent=2))
        else:
            console.print(
                Panel(
                    f"[blue][dry-run][/blue] Would call [bold]{tool}[/bold]\n"
                    f"args:         {args}\n"
                    f"safety class: {cls}",
                    title="[bold]Dry Run[/bold]",
                )
            )
        return

    if not bridge.is_available():
        console.print(f"[bold red]mq-mcp not reachable[/bold red]\n{bridge.not_reachable_message()}")
        raise typer.Exit(code=1)

    with console.status(f"[bold cyan]Running {tool}...[/bold cyan]"):
        result = bridge.call_tool(tool, args)

    if json_out:
        if isinstance(result, str):
            typer.echo(json.dumps({"tool": tool, "result": result}))
        else:
            typer.echo(json.dumps({"tool": tool, "result": result}, indent=2))
        return

    if isinstance(result, (dict, list)):
        import pprint
        console.print(Panel(pprint.pformat(result, width=80), title=f"[bold]{tool}[/bold]"))
    else:
        console.print(Panel(str(result), title=f"[bold]{tool}[/bold]"))


# ── memory status ──────────────────────────────────────────────────────────

@memory_app.command("status")
def memory_status_cmd(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Check semantic repository memory availability."""
    from mq_agent.memory.semantic import status as mem_status

    state = mem_status(path)

    if json_out:
        typer.echo(json.dumps({
            "status": state.status,
            "enabled": state.enabled,
            "vector_store_id": state.vector_store_id,
            "repo_signal_available": state.repo_signal_available,
            "repo_path": state.repo_path,
        }, indent=2))
        return

    color = "green" if state.enabled else "yellow" if state.status == "missing-repo-signal" else "red"
    lines = (
        f"[bold]status:[/bold]       [{color}]{state.status}[/{color}]\n"
        f"[bold]vector store:[/bold] {state.vector_store_id or '[dim](not set — export OPENAI_VECTOR_STORE_ID)[/dim]'}\n"
        f"[bold]repo-signal:[/bold]  {'[green]available[/green]' if state.repo_signal_available else '[yellow]not found[/yellow]'}\n"
        f"[bold]repo:[/bold]         {state.repo_path}"
    )
    console.print(Panel(lines, title="[bold]Semantic Memory[/bold]",
                        border_style="green" if state.enabled else "yellow"))


# ── memory build ───────────────────────────────────────────────────────────

@memory_app.command("build")
def memory_build_cmd(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run/--no-dry-run")] = True,
):
    """Upload semantic repo memory via repo-signal. Dry-run by default."""
    from mq_agent.memory.semantic import build as mem_build

    if dry_run:
        console.print("[blue][dry-run][/blue] Would run: [bold]repo-signal semantic-upload[/bold]")
        console.print("Add [bold]--no-dry-run[/bold] to execute, or use [bold]memory refresh --approve[/bold].")
        return

    with console.status("[bold cyan]Building semantic memory...[/bold cyan]"):
        result = mem_build(path, dry_run=False)

    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(f"[yellow]{result.stderr}[/yellow]")
    if result.returncode != 0:
        console.print(f"[bold red]Build failed (exit {result.returncode})[/bold red]")
        raise typer.Exit(result.returncode)
    console.print("[bold green]✓ Semantic memory built[/bold green]")


# ── memory refresh ─────────────────────────────────────────────────────────

@memory_app.command("refresh")
def memory_refresh_cmd(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    approve: Annotated[bool, typer.Option("--approve", help="Allow upload")] = False,
):
    """Refresh semantic repo memory. Requires --approve to upload."""
    from mq_agent.memory.semantic import build as mem_build

    if not approve:
        console.print("[yellow]Refusing to upload semantic memory without [bold]--approve[/bold].[/yellow]")
        console.print("Run [bold]mq-agent memory build .[/bold] first to preview.")
        raise typer.Exit(1)

    with console.status("[bold cyan]Refreshing semantic memory...[/bold cyan]"):
        result = mem_build(path, dry_run=False)

    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(f"[yellow]{result.stderr}[/yellow]")
    if result.returncode != 0:
        console.print(f"[bold red]Refresh failed (exit {result.returncode})[/bold red]")
        raise typer.Exit(result.returncode)
    console.print("[bold green]✓ Semantic memory refreshed[/bold green]")


# ── memory doctor ───────────────────────────────────────────────────────────

@memory_app.command("doctor")
def memory_doctor_cmd(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Diagnose semantic memory environment."""
    from mq_agent.memory.semantic import doctor as mem_doctor

    report = mem_doctor(path)

    if json_out:
        typer.echo(json.dumps({
            "healthy": report.healthy,
            "items": [
                {"ok": item.ok, "label": item.label, "detail": item.detail, "fix": item.fix}
                for item in report.items
            ],
        }, indent=2))
        if not report.healthy:
            raise typer.Exit(1)
        return

    lines = []
    for item in report.items:
        icon = "[green]✓[/green]" if item.ok else "[red]✗[/red]"
        line = f"{icon} [bold]{item.label}:[/bold] {item.detail}"
        if not item.ok and item.fix:
            line += f"\n  [dim]fix:[/dim] [yellow]{item.fix}[/yellow]"
        lines.append(line)

    border = "green" if report.healthy else "red"
    title = "[bold]Memory Doctor[/bold]"
    console.print(Panel("\n".join(lines), title=title, border_style=border))

    if not report.healthy:
        raise typer.Exit(1)


# ── helpers ────────────────────────────────────────────────────────────────

def _print_tool_spec(spec) -> None:
    """Print a single MCPToolSpec in human-readable form."""
    lines = (
        f"[bold]Tool:[/bold]        {spec.name}\n"
        f"[bold]Source:[/bold]      {spec.source}\n"
        f"[bold]Safety:[/bold]      {spec.safety_class}\n"
    )
    if spec.description:
        lines += f"\n[bold]Description:[/bold]\n{spec.description}\n"
    if spec.input_schema:
        import pprint
        lines += f"\n[bold]Input schema:[/bold]\n{pprint.pformat(spec.input_schema, width=60)}\n"
    if spec.examples:
        lines += "\n[bold]Examples:[/bold]\n" + "\n".join(f"  {e}" for e in spec.examples)
    console.print(Panel(lines, title=f"[bold]{spec.name}[/bold]"))


def _print_mcp_tool_table(specs: list) -> None:
    """Print a table of MCPToolSpec objects."""
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("Tool", style="cyan")
    table.add_column("Safety", width=14)
    table.add_column("Description", overflow="fold")

    safety_colors = {
        "read-only": "green",
        "write-capable": "yellow",
        "subprocess": "yellow",
        "dangerous": "red",
        "unknown": "dim",
    }

    for spec in sorted(specs, key=lambda s: (s.safety_class, s.name)):
        color = safety_colors.get(spec.safety_class, "white")
        table.add_row(spec.name, f"[{color}]{spec.safety_class}[/{color}]", spec.description)

    console.print(table)


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
