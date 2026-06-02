"""mq-agent CLI — Typer entry point."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mq_agent.cli.render import (
    print_mcp_tool_table,
    print_steps,
    print_swarm_result,
    print_tool_spec,
)
from mq_agent.core.diagnostics import required_checks_pass, run_checks

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

task_app = typer.Typer(help="Run declarative YAML task workflows.")
app.add_typer(task_app, name="task")

browser_app = typer.Typer(help="Browser-safe URL inspection and release verification.")
app.add_typer(browser_app, name="browser")

swarm_app = typer.Typer(help="Multi-agent swarm workflows.")
app.add_typer(swarm_app, name="swarm")

review_app = typer.Typer(help="Pass-through mq-mcp review orchestration.")
app.add_typer(review_app, name="review")

learn_app = typer.Typer(help="Read-only access to mq-mcp learned review patterns.")
app.add_typer(learn_app, name="learn")

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
    print_steps(console, result["steps"], title="Audit Steps")

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

    print_steps(console, result["steps"], title="Release Checks")
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

    print_steps(console, result["steps"], title="CI Fix Plan")


# ── doctor ─────────────────────────────────────────────────────────────────

@app.command()
def doctor():
    """Check mq-agent environment and dependencies."""
    checks = run_checks()

    table = Table(title="mq-agent Doctor", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Action")

    for name, ok, action in checks:
        status = Text("✓ OK", style="bold green") if ok else Text("✗ FAIL", style="bold red")
        table.add_row(name, status, "" if ok else action)

    console.print(table)

    if required_checks_pass(checks):
        console.print("\n[bold green]All required checks passed.[/bold green]")
    else:
        console.print("\n[bold yellow]Fix the issues above before using mq-agent.[/bold yellow]")


# ── review ─────────────────────────────────────────────────────────────────

def _review_flags(security: bool, architecture: bool, risk: bool, fast: bool = False) -> dict[str, bool]:
    return {
        "security": security,
        "architecture": architecture,
        "risk": risk,
        "fast": fast,
    }


def _is_error_result(result: Any) -> bool:
    if isinstance(result, dict):
        return result.get("ok") is False and "error" in result
    if isinstance(result, str):
        return result.startswith((
            "mq-mcp error",
            "MCP bridge error",
            "mq-mcp is not reachable",
            "Tool ",
            "httpx not installed",
        ))
    return False


def _iter_review_findings(value: Any) -> list[dict[str, Any]]:
    """Extract findings for display without changing their labels or meaning."""
    if isinstance(value, dict):
        findings = value.get("findings")
        if isinstance(findings, list):
            return [item for item in findings if isinstance(item, dict)]
        result = value.get("result")
        if result is not value:
            return _iter_review_findings(result)
    return []


def _severity_value(item: dict[str, Any]) -> str:
    for key in ("severity", "label", "type", "category"):
        value = item.get(key)
        if value:
            return str(value)
    return "UNSPECIFIED"


def _render_review_result(command: str, result: Any) -> None:
    if _is_error_result(result):
        message = str(result.get("error") if isinstance(result, dict) else result)
        console.print(Panel(message, title="[bold red]mq-mcp review unavailable[/bold red]", border_style="red"))
        if isinstance(result, dict):
            hint = result.get("hint")
            if hint:
                console.print(f"[dim]{hint}[/dim]")
        raise typer.Exit(1)

    findings = _iter_review_findings(result)
    table = Table(title=f"mq-mcp {command}", show_header=True, header_style="bold")
    table.add_column("Severity")
    table.add_column("Source")
    table.add_column("Finding")

    counts: dict[str, int] = {}
    for item in findings:
        severity = _severity_value(item)
        counts[severity] = counts.get(severity, 0) + 1
        source = str(item.get("file") or item.get("path") or item.get("source") or "")
        line = item.get("line")
        if line:
            source = f"{source}:{line}" if source else str(line)
        message = str(item.get("message") or item.get("title") or item.get("summary") or item)
        table.add_row(severity, source or "-", message)

    if findings:
        console.print(table)
        summary = ", ".join(f"{label}: {count}" for label, count in counts.items())
        console.print(f"\n[bold]Severity summary:[/bold] {summary}")
        return

    if isinstance(result, str):
        console.print(Panel(result, title=f"[bold]{command}[/bold]"))
    else:
        console.print(Panel(json.dumps(result, indent=2, default=str), title=f"[bold]{command}[/bold]"))


def _render_arch_context(bridge: Any) -> None:
    """Show architecture decisions from mq-mcp when available. Silent when not."""
    decisions = bridge.list_architecture_decisions()
    if not decisions:
        return
    items: list[Any] = decisions if isinstance(decisions, list) else decisions.get("decisions") or []
    if not items:
        return
    lines = "\n".join(
        f"  {item.get('id', '?')}: {item.get('title') or item.get('summary') or str(item)[:80]}"
        for item in items[:5]
        if isinstance(item, dict)
    )
    console.print(Panel(lines, title="[dim]Architecture context (mq-mcp)[/dim]", border_style="dim"))


def _run_review(command: str, result: Any, json_out: bool, bridge: Any = None) -> None:
    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if _is_error_result(result):
            raise typer.Exit(1)
        return
    _render_review_result(command, result)
    if bridge is not None:
        _render_arch_context(bridge)


@review_app.command("file")
def review_file_cmd(
    path: Annotated[str, typer.Argument(help="File path to review")],
    security: Annotated[bool, typer.Option("--security", help="Ask mq-mcp for security review mode")] = False,
    architecture: Annotated[bool, typer.Option("--architecture", help="Ask mq-mcp for architecture review mode")] = False,
    risk: Annotated[bool, typer.Option("--risk", help="Use mq-mcp risk review when installed")] = False,
    fast: Annotated[bool, typer.Option("--fast", help="Prefer fast Class A tools over deep AI review")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review one file through mq-mcp. mq-agent does not implement review logic."""
    if dry_run:
        flags = [f for f, v in _review_flags(security, architecture, risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in flags)
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_file {path}{' ' + flag_str if flag_str else ''}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    result = bridge.review_file(path, _review_flags(security, architecture, risk, fast))
    _run_review("review file", result, json_out, bridge=bridge)


@review_app.command("diff")
def review_diff_cmd(
    security: Annotated[bool, typer.Option("--security", help="Ask mq-mcp for security review mode")] = False,
    architecture: Annotated[bool, typer.Option("--architecture", help="Ask mq-mcp for architecture review mode")] = False,
    risk: Annotated[bool, typer.Option("--risk", help="Use mq-mcp risk review when installed")] = False,
    fast: Annotated[bool, typer.Option("--fast", help="Prefer fast Class A tools over deep AI review")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review the current diff through mq-mcp. Findings are passed through."""
    if dry_run:
        flags = [f for f, v in _review_flags(security, architecture, risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in flags)
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_diff{' ' + flag_str if flag_str else ''}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    result = bridge.review_diff(_review_flags(security, architecture, risk, fast))
    _run_review("review diff", result, json_out, bridge=bridge)


@review_app.command("repo")
def review_repo_cmd(
    path: Annotated[str, typer.Argument(help="Repo path to review")] = ".",
    security: Annotated[bool, typer.Option("--security", help="Ask mq-mcp for security review mode")] = False,
    architecture: Annotated[bool, typer.Option("--architecture", help="Ask mq-mcp for architecture review mode")] = False,
    risk: Annotated[bool, typer.Option("--risk", help="Use mq-mcp risk review when installed")] = False,
    fast: Annotated[bool, typer.Option("--fast", help="Prefer fast Class A tools over deep AI review")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review a repo through mq-mcp. mq-agent renders mq-mcp output only."""
    if dry_run:
        flags = [f for f, v in _review_flags(security, architecture, risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in flags)
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_repo {path}{' ' + flag_str if flag_str else ''}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    result = bridge.review_repo(path, _review_flags(security, architecture, risk, fast))
    _run_review("review repo", result, json_out, bridge=bridge)


def _contract_status_text(value: Any) -> str:
    """Flatten MCP content wrappers into text for status rendering."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key in ("text", "result", "content"):
            if key in value:
                parts.append(_contract_status_text(value[key]))
        return " ".join(part for part in parts if part)
    if isinstance(value, list):
        return " ".join(_contract_status_text(item) for item in value)
    return ""


def _contract_status_ok(contract: Any) -> bool:
    """Return whether a validate_orchestration_contract result is passing."""
    if isinstance(contract, dict) and "ok" in contract:
        return contract.get("ok") is not False

    text = _contract_status_text(contract).lower()
    if not text:
        return False
    failed_count = re.search(r"(\d+)\s+failed", text)
    if failed_count is not None and int(failed_count.group(1)) > 0:
        return False
    return "[fail]" not in text and "pass" in text


# ── learn ───────────────────────────────────────────────────────────────────

@learn_app.command("status")
def learn_status_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Check availability of the mq-mcp learn system. Read-only."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().learn_status()

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]learn system unavailable[/bold red]",
            border_style="red",
        ))
        hint = result.get("hint")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
        raise typer.Exit(1)

    console.print(Panel(json.dumps(result, indent=2, default=str), title="[bold]Learn system status[/bold]"))


@learn_app.command("search")
def learn_search_cmd(
    query: Annotated[str, typer.Argument(help="Search query for learned patterns")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Search mq-mcp learned review patterns. Read-only."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().search_learned_patterns(query)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]learn system unavailable[/bold red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    items: list[Any] = result if isinstance(result, list) else result.get("patterns") or result.get("items") or []
    if not items:
        console.print(Panel(f"No patterns found for: [bold]{query}[/bold]", border_style="dim"))
        return

    table = Table(title=f"Learned patterns: {query}", show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Pattern")
    for item in items:
        pid = str(item.get("id") or item.get("pattern_id") or "")
        summary = str(item.get("title") or item.get("summary") or item.get("pattern") or item)[:120]
        table.add_row(pid, summary)
    console.print(table)


@learn_app.command("explain")
def learn_explain_cmd(
    pattern_id: Annotated[str, typer.Argument(help="Pattern ID to explain")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Fetch a detailed explanation of a learned pattern from mq-mcp. Read-only."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().explain_learned_pattern(pattern_id)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]pattern not found[/bold red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    console.print(Panel(json.dumps(result, indent=2, default=str), title=f"[bold]Pattern: {pattern_id}[/bold]"))


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
        print_steps(console, result["steps"], title="AI Improvement Plan")

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

    print_steps(console, result["steps"], title="Docs Audit")
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
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    if describe:
        bridge = MultiMCPBridge()
        spec = bridge.describe_tool(describe)
        if json_out:
            typer.echo(json.dumps(spec.to_dict(), indent=2))
            return
        print_tool_spec(console, spec)
        return

    built_in = tool_names()

    if include_mcp:
        bridge = MultiMCPBridge()
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
        print_mcp_tool_table(console, mcp_specs)
        return

    if json_out:
        typer.echo(json.dumps({"built_in": built_in}, indent=2))
        return

    for name in built_in:
        console.print(f"  [cyan]•[/cyan] {name}")


# ── mcp connect ────────────────────────────────────────────────────────────

@mcp_app.command("connect")
def mcp_connect(
    name: Annotated[str, typer.Argument(help="Server name (e.g. RepoPrompt)")],
    url: Annotated[str, typer.Argument(help="MCP server URL (e.g. http://localhost:PORT)")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Register an external MCP server."""
    from mq_agent.core.config import add_mcp_server

    add_mcp_server(name, url)

    if json_out:
        typer.echo(json.dumps({"name": name, "url": url, "status": "connected"}))
        return

    console.print(Panel(
        f"[bold green]Connected to {name}[/bold green]\nURL: {url}",
        title="[bold]MCP Connect[/bold]",
        border_style="green",
    ))


@mcp_app.command("disconnect")
def mcp_disconnect(
    name: Annotated[str, typer.Argument(help="Server name to remove")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Remove a registered MCP server."""
    from mq_agent.core.config import remove_mcp_server

    removed = remove_mcp_server(name)

    if json_out:
        typer.echo(json.dumps({"name": name, "removed": removed}))
        return

    if removed:
        console.print(f"[bold green]Disconnected from {name}[/bold green]")
    else:
        console.print(f"[bold yellow]Server '{name}' not found[/bold yellow]")


# ── mcp start ──────────────────────────────────────────────────────────────


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
    """Check whether MCP servers are reachable and show tool counts."""
    from mq_agent.mcp.manager import is_running as process_is_running
    from mq_agent.mcp.manager import read_pid
    from mq_agent.tools.mcp_bridge import MultiMCPBridge
    from mq_agent.tools.mcp_registry import MCPSafetyClass

    bridge = MultiMCPBridge()
    statuses = bridge.get_server_statuses()

    mq_mcp_pid = read_pid()
    mq_mcp_running = process_is_running()

    if json_out:
        typer.echo(json.dumps({
            "servers": statuses,
            "mq_mcp_process": {
                "running": mq_mcp_running,
                "pid": mq_mcp_pid,
            }
        }, indent=2, default=str))
        return

    for name, s in statuses.items():
        available = s["available"]
        endpoint = s["endpoint"]
        tools_count = s["tools"]
        specs = s["specs"]

        counts: dict[str, int] = {}
        for spec in specs:
            counts[spec.safety_class] = counts.get(spec.safety_class, 0) + 1

        color = "green" if available else "red"
        status_text = "[bold green]reachable[/bold green]" if available else "[bold red]not reachable[/bold red]"
        
        lines = (
            f"status:   {status_text}\n"
            f"endpoint: {endpoint}\n"
        )
        
        if name == "mq-mcp":
            pid_line = f"process:  PID {mq_mcp_pid}" if mq_mcp_pid else "process:  not started"
            lines += f"{pid_line}\n"

        if available:
            lines += f"tools:    {tools_count}\n"
            lines += "\n".join(
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
            mem_count = s.get("semantic_memory_count")
            if mem_count is not None:
                lines += f"\nsemantic memory: {mem_count} item(s)"
            contract = s.get("contract")
            if contract is not None:
                contract_ok = _contract_status_ok(contract)
                contract_status = "[green]valid[/green]" if contract_ok else "[red]invalid[/red]"
                lines += f"\ncontract: {contract_status}"

        console.print(Panel(lines, title=f"[bold]{name} Status[/bold]", border_style=color))


# ── mcp tools ──────────────────────────────────────────────────────────────

@mcp_app.command("tools")
def mcp_tools_list(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List all tools discovered from all connected MCP servers."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    if not bridge.is_available():
        console.print("[bold red]No MCP servers reachable[/bold red]")
        raise typer.Exit(code=1)

    specs = bridge.list_tool_specs()

    if json_out:
        typer.echo(json.dumps([s.to_dict() for s in specs], indent=2))
        return

    print_mcp_tool_table(console, specs)


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
    from mq_agent.tools.mcp_bridge import MultiMCPBridge
    from mq_agent.tools.mcp_registry import MCPSafetyClass

    bridge = MultiMCPBridge()
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
            "source": spec.source,
            "would_execute": not dry_run,
        }
        if json_out:
            typer.echo(json.dumps(preview, indent=2))
        else:
            console.print(
                Panel(
                    f"[blue][dry-run][/blue] Would call [bold]{tool}[/bold]\n"
                    f"source:       {spec.source}\n"
                    f"args:         {args}\n"
                    f"safety class: {cls}",
                    title="[bold]Dry Run[/bold]",
                )
            )
        return

    if not bridge.is_available():
        console.print("[bold red]No MCP servers reachable[/bold red]")
        raise typer.Exit(code=1)

    with console.status(f"[bold cyan]Running {tool} ({spec.source})...[/bold cyan]"):
        result = bridge.call_tool(tool, args)

    if json_out:
        if isinstance(result, str):
            typer.echo(json.dumps({"tool": tool, "source": spec.source, "result": result}))
        else:
            typer.echo(json.dumps({"tool": tool, "source": spec.source, "result": result}, indent=2))
        return

    if isinstance(result, (dict, list)):
        import pprint
        console.print(Panel(pprint.pformat(result, width=80), title=f"[bold]{tool} ({spec.source})[/bold]"))
    else:
        console.print(Panel(str(result), title=f"[bold]{tool} ({spec.source})[/bold]"))


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


# ── memory search ──────────────────────────────────────────────────────────

@memory_app.command("search")
def memory_search_cmd(
    query: Annotated[str, typer.Argument(help="Search query")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Search mq-mcp semantic memory. Read-only. Requires mq-mcp v1.4.0+."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().search_semantic_memory(query)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]semantic memory unavailable[/bold red]",
            border_style="red",
        ))
        hint = result.get("hint")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
        raise typer.Exit(1)

    items: list[Any] = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        items = result.get("items") or result.get("results") or []

    if not items:
        console.print(Panel(f"No results for: [bold]{query}[/bold]", border_style="dim"))
        return

    table = Table(title=f"Semantic memory: {query}", show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Excerpt")
    for item in items:
        key = str(item.get("key") or item.get("id") or "")
        excerpt = str(item.get("value") or item.get("content") or item.get("summary") or item)[:120]
        table.add_row(key, excerpt)
    console.print(table)


# ── memory store ────────────────────────────────────────────────────────────

@memory_app.command("store")
def memory_store_cmd(
    key: Annotated[str, typer.Argument(help="Memory key")],
    value: Annotated[str, typer.Argument(help="Memory value")],
    approve: Annotated[bool, typer.Option("--approve", help="Allow write to mq-mcp")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Store an item in mq-mcp semantic memory. Class C write tool — requires --approve."""
    if dry_run:
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp store_semantic_memory key={key}[/bold]")
        return

    if not approve:
        console.print(
            "[yellow]store_semantic_memory is a Class C write tool.[/yellow]\n"
            "Add [bold]--approve[/bold] to execute, or [bold]--dry-run[/bold] to preview."
        )
        raise typer.Exit(1)

    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().store_semantic_memory(key, value)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]store failed[/bold red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    console.print(f"[bold green]✓[/bold green] Stored [bold]{key}[/bold] in mq-mcp semantic memory.")


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


# ── task list ──────────────────────────────────────────────────────────────

@task_app.command("list")
def task_list(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List available task definitions."""
    from mq_agent.core.task_runner import find_task_files, load_task

    package_tasks = Path(__file__).parent.parent / "tasks"
    local_tasks = Path(".") / "tasks"
    files = find_task_files(package_tasks, local_tasks)

    if json_out:
        items = []
        for f in files:
            try:
                t = load_task(f)
                items.append({"name": t.name, "description": t.description, "steps": len(t.steps), "file": str(f)})
            except Exception:
                items.append({"name": f.stem, "file": str(f), "error": "failed to load"})
        typer.echo(json.dumps(items, indent=2))
        return

    if not files:
        console.print("[yellow]No task files found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Steps", justify="right")
    table.add_column("Description")
    for f in files:
        try:
            t = load_task(f)
            table.add_row(t.name, str(len(t.steps)), t.description or "—")
        except Exception as exc:
            table.add_row(f.stem, "?", f"[red]load error: {exc}[/red]")
    console.print(table)


# ── task run ───────────────────────────────────────────────────────────────

@task_app.command("run")
def task_run(
    name: Annotated[str, typer.Argument(help="Task name or path to YAML file")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Run a declarative YAML task workflow."""
    from mq_agent.core.task_runner import find_task_files, load_task, run_task

    # Resolve task file — direct path, stem match, or internal name match
    direct_path = Path(name)
    task_path: Path | None = direct_path if direct_path.exists() else None
    if task_path is None:
        package_tasks = Path(__file__).parent.parent / "tasks"
        local_tasks = Path(".") / "tasks"
        all_files = find_task_files(package_tasks, local_tasks)
        # stem match first (fast)
        task_path = next((f for f in all_files if f.stem == name), None)  # type: ignore[arg-type]
        # fall back to internal name match
        if task_path is None:
            for f in all_files:
                try:
                    t = load_task(f)
                    if t.name == name:
                        task_path = f
                        break
                except Exception:
                    pass
        if task_path is None:
            console.print(f"[bold red]Task not found:[/bold red] {name}")
            raise typer.Exit(1)

    try:
        task = load_task(task_path)
    except Exception as exc:
        console.print(f"[bold red]Failed to load task:[/bold red] {exc}")
        raise typer.Exit(1)

    results = run_task(task, dry_run=dry_run)

    passed = all(r.status in ("ok", "dry-run") for r in results)

    if json_out:
        typer.echo(json.dumps({
            "task": task.name,
            "dry_run": dry_run,
            "passed": passed,
            "steps": [{"step": r.step, "tool": r.tool, "status": r.status, "output": r.output} for r in results],
        }, indent=2))
        if not passed:
            raise typer.Exit(1)
        return

    mode_label = "[dim](dry-run)[/dim] " if dry_run else ""
    console.print(f"\n[bold]Task:[/bold] {task.name} {mode_label}— {task.description}\n")

    for r in results:
        icon = {
            "ok": "[bold green]✓[/bold green]",
            "dry-run": "[bold blue]~[/bold blue]",
            "error": "[bold red]✗[/bold red]",
            "unknown-tool": "[bold red]?[/bold red]",
        }.get(r.status, "[dim]•[/dim]")
        console.print(f"  {icon} [bold]{r.step}[/bold] ({r.tool})")
        if r.output:
            for line in r.output.splitlines()[:6]:
                console.print(f"      [dim]{line}[/dim]")
            if len(r.output.splitlines()) > 6:
                console.print(f"      [dim]... ({len(r.output.splitlines())} lines total)[/dim]")

    border = "green" if passed else "red"
    label = "[bold green]✓ All steps passed[/bold green]" if passed else "[bold red]✗ Some steps failed[/bold red]"
    console.print(Panel(label, border_style=border))

    if not passed:
        raise typer.Exit(1)


# ── browser inspect ────────────────────────────────────────────────────────

@browser_app.command("inspect")
def browser_inspect(
    url: Annotated[str, typer.Argument(help="URL to inspect")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
    timeout: Annotated[int, typer.Option("--timeout")] = 10,
):
    """Fetch a URL and show structured metadata: title, headings, links, word count."""
    from mq_agent.tools.browser_tools import inspect_url

    with console.status(f"[bold cyan]Inspecting {url}...[/bold cyan]"):
        meta = inspect_url(url, timeout=timeout)

    if json_out:
        typer.echo(json.dumps(meta, indent=2))
        if not meta.get("ok"):
            raise typer.Exit(1)
        return

    if not meta.get("ok"):
        console.print(f"[bold red]Error:[/bold red] {meta.get('error', 'fetch failed')}")
        raise typer.Exit(1)

    lines = [
        f"[bold]URL:[/bold]         {meta['url']}",
        f"[bold]Status:[/bold]      {meta['status_code']}",
        f"[bold]Title:[/bold]       {meta['title'] or '[dim](none)[/dim]'}",
        f"[bold]Description:[/bold] {meta['description'] or '[dim](none)[/dim]'}",
        f"[bold]Word count:[/bold]  {meta['word_count']}",
        f"[bold]Links:[/bold]       {len(meta['links'])} found",
    ]
    if meta["h1s"]:
        lines.append("[bold]H1:[/bold]          " + " / ".join(meta["h1s"]))
    if meta["h2s"]:
        lines.append("[bold]H2:[/bold]          " + " / ".join(meta["h2s"][:5]))

    console.print(Panel("\n".join(lines), title=f"[bold]Inspect: {url[:60]}[/bold]", border_style="cyan"))


# ── browser summarize ──────────────────────────────────────────────────────

@browser_app.command("summarize")
def browser_summarize(
    url: Annotated[str, typer.Argument(help="URL to summarize")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
    timeout: Annotated[int, typer.Option("--timeout")] = 10,
):
    """Fetch a URL and return a plain-text content summary."""
    from mq_agent.tools.browser_tools import summarize_url

    with console.status(f"[bold cyan]Summarizing {url}...[/bold cyan]"):
        summary = summarize_url(url, timeout=timeout)

    if json_out:
        typer.echo(json.dumps({"url": url, "summary": summary}))
        return

    console.print(Panel(summary, title=f"[bold]Summary: {url[:60]}[/bold]", border_style="cyan"))


# ── browser verify-release ─────────────────────────────────────────────────

@browser_app.command("verify-release")
def browser_verify_release(
    url: Annotated[str, typer.Argument(help="Release page URL to verify")],
    tag: Annotated[str, typer.Option("--tag", help="Expected version tag (e.g. v0.7.0)")] = "",
    json_out: Annotated[bool, typer.Option("--json")] = False,
    timeout: Annotated[int, typer.Option("--timeout")] = 10,
):
    """Inspect a release page and verify expected release fields are present."""
    from mq_agent.tools.browser_tools import verify_release_url

    with console.status("[bold cyan]Verifying release page...[/bold cyan]"):
        result = verify_release_url(url, expected_tag=tag, timeout=timeout)

    if json_out:
        typer.echo(json.dumps(result, indent=2))
        if not result.get("passed"):
            raise typer.Exit(1)
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Status", width=8)
    table.add_column("Note", overflow="fold")

    for check in result["checks"]:
        icon = "[green]✓[/green]" if check["passed"] else "[red]✗[/red]"
        table.add_row(check["check"], icon, check.get("note", ""))

    console.print(table)

    if result["passed"]:
        console.print("\n[bold green]✓ Release page verified[/bold green]")
    else:
        console.print("\n[bold red]✗ Release page verification failed[/bold red]")
        raise typer.Exit(1)


# ── swarm list ─────────────────────────────────────────────────────────────

@swarm_app.command("list")
def swarm_list(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List available swarm configurations and their agents."""
    from mq_agent.agents.swarm_registry import list_swarms

    items = list_swarms()

    if json_out:
        typer.echo(json.dumps(items, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Agents")
    table.add_column("Approve?", width=9)
    table.add_column("Description", overflow="fold")

    for item in items:
        approve = "[yellow]yes[/yellow]" if item["requires_approve"] else "[green]no[/green]"
        table.add_row(
            item["name"],
            " + ".join(item["agents"]),
            approve,
            item["description"],
        )
    console.print(table)


# ── swarm plan ─────────────────────────────────────────────────────────────

@swarm_app.command("plan")
def swarm_plan(
    config: Annotated[str, typer.Argument(help="Swarm config name (audit, release-check, ci)")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show which agents would run — no execution, no API calls."""
    from mq_agent.agents.swarm_registry import get_swarm
    from mq_agent.core.swarm import SwarmRunner

    try:
        cfg = get_swarm(config)
    except KeyError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(1)

    plan = SwarmRunner(None).plan(cfg)

    if json_out:
        typer.echo(json.dumps({"config": config, "goal": cfg.goal, "agents": plan}, indent=2))
        return

    console.print(f"\n[bold]Swarm:[/bold] {cfg.name} — {cfg.description}")
    console.print(f"[dim]{cfg.goal}[/dim]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Agent", style="cyan")
    table.add_column("Safety", width=14)
    table.add_column("Approve?", width=9)
    table.add_column("On failure", width=8)
    table.add_column("Purpose", overflow="fold")

    safety_colors = {"read-only": "green", "write-capable": "yellow", "subprocess": "yellow"}
    for i, step in enumerate(plan, 1):
        color = safety_colors.get(step["safety_class"], "white")
        approve = "[yellow]yes[/yellow]" if step["requires_approve"] else "[green]no[/green]"
        table.add_row(
            str(i),
            step["agent"],
            f"[{color}]{step['safety_class']}[/{color}]",
            approve,
            step["failure_behavior"],
            step["purpose"],
        )
    console.print(table)


# ── swarm run ──────────────────────────────────────────────────────────────

@swarm_app.command("run")
def swarm_run(
    config: Annotated[str, typer.Argument(help="Swarm config name (audit, release-check, ci)")],
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Allow write-capable agents")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Run a named swarm config against a repo path."""
    from mq_agent.agents.swarm_registry import get_swarm
    from mq_agent.core.swarm import SwarmRunner

    try:
        cfg = get_swarm(config)
    except KeyError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(1)

    client = None if dry_run else _client()
    with console.status(f"[bold cyan]Running swarm '{config}'...[/bold cyan]"):
        result = SwarmRunner(client).run(cfg, path=path, dry_run=dry_run, approve=approve)

    if json_out:
        typer.echo(json.dumps(result.to_dict(), indent=2, default=str))
        if not result.passed:
            raise typer.Exit(1)
        return

    print_swarm_result(console, result)
    if not result.passed:
        raise typer.Exit(1)


# ── swarm audit ────────────────────────────────────────────────────────────

@swarm_app.command("audit")
def swarm_audit(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Full read-only repo health check: audit + signal + docs."""
    from mq_agent.agents.swarm_registry import SWARM_AUDIT
    from mq_agent.core.swarm import SwarmRunner

    client = None if dry_run else _client()
    with console.status("[bold cyan]Running audit swarm...[/bold cyan]"):
        result = SwarmRunner(client).run(SWARM_AUDIT, path=path, dry_run=dry_run)

    if json_out:
        typer.echo(json.dumps(result.to_dict(), indent=2, default=str))
        if not result.passed:
            raise typer.Exit(1)
        return

    print_swarm_result(console, result)
    if not result.passed:
        raise typer.Exit(1)


# ── swarm release-check ────────────────────────────────────────────────────

@swarm_app.command("release-check")
def swarm_release_check(
    path: Annotated[str, typer.Argument(help="Repo path")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = True,
    approve: Annotated[bool, typer.Option("--approve")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Release readiness swarm: CI + audit + release validation."""
    from mq_agent.agents.swarm_registry import SWARM_RELEASE_CHECK
    from mq_agent.core.swarm import SwarmRunner

    client = None if dry_run else _client()
    with console.status("[bold cyan]Running release-check swarm...[/bold cyan]"):
        result = SwarmRunner(client).run(
            SWARM_RELEASE_CHECK, path=path, dry_run=dry_run, approve=approve
        )

    if json_out:
        typer.echo(json.dumps(result.to_dict(), indent=2, default=str))
        if not result.passed:
            raise typer.Exit(1)
        return

    print_swarm_result(console, result)
    if not result.passed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
