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

learn_app = typer.Typer(help="Learn commands — extraction, storage and promotion of review patterns.")
app.add_typer(learn_app, name="learn")

b2_app = typer.Typer(help="B2 prompt OS — route topics to prompts and run workflows.")
app.add_typer(b2_app, name="b2")

stack_app = typer.Typer(help="mq-stack repo inventory, status, and Obsidian export.")
app.add_typer(stack_app, name="stack")

console = Console()


def _extract_mcp_text_result(result: Any) -> str | None:
    """Return text from the common MCP HTTP wrapper shape, if present."""
    if isinstance(result, dict) and isinstance(result.get("result"), str):
        return result["result"]
    if isinstance(result, list):
        for item in result:
            text = _extract_mcp_text_result(item)
            if text:
                return text
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    return text
    return None


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
    command: Annotated[str, typer.Argument(help="Shell command to run")] = "",
    cwd: Annotated[str, typer.Option("--cwd")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Execute the command")] = False,
    stack: Annotated[bool, typer.Option("--stack", help="Run the canonical stack runtime pipeline")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    markdown: Annotated[bool, typer.Option("--markdown", help="Render --stack runtime result as Markdown")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Write stack truth export when combined with --approve and --stack")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="CI mode for --stack runtime gates")] = False,
):
    """Run a shell command safely, or the canonical stack runtime with --stack."""
    from mq_agent.tools.shell_tools import run_command

    if stack:
        from mq_agent.tools.stack_runtime import (
            render_stack_run_markdown,
            stack_run as _stack_run,
        )

        with console.status("[cyan]Running stack runtime...[/cyan]"):
            raw = _stack_run(dry_run=dry_run, brain=brain, ci=ci, approve=approve)
        data = json.loads(raw)
        if json_out:
            typer.echo(raw)
            raise typer.Exit(0 if data["overall"] == "PASS" else 1)
        if markdown:
            typer.echo(render_stack_run_markdown(data))
            raise typer.Exit(0 if data["overall"] == "PASS" else 1)
        _print_stack_runtime(data)
        raise typer.Exit(0 if data["overall"] == "PASS" else 1)

    if not command:
        console.print("[red]Provide a shell command, or use [bold]--stack[/bold] for the stack runtime.[/red]")
        raise typer.Exit(1)

    if dry_run:
        console.print(f"[blue][dry-run][/blue] Would run: [bold]{command}[/bold]")
        return

    if json_out or markdown or brain or ci:
        console.print("[red]--json, --markdown, --brain and --ci are only valid with [bold]--stack[/bold].[/red]")
        raise typer.Exit(1)

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

def _brain_record_review(bridge: Any, source: str, result: Any) -> None:
    """Record a completed review to the mqobsidian second brain. Silent on failure."""
    # Resolve "." or directory paths to a human-readable repo name for the slug.
    source_label = source
    if source not in ("diff",) and (source in (".", "./") or os.path.isdir(source)):
        source_label = os.path.basename(os.path.abspath(source))

    findings = _iter_review_findings(result)
    finding_count = len(findings)

    # Fallback: parse total from text-format review output (e.g. "N total [MISSING=N]").
    if finding_count == 0:
        raw_text = _contract_status_text(result)
        if raw_text:
            finding_count = sum(int(n) for n in re.findall(r":\s*(\d+)\s+total", raw_text))

    top_risks: list[str] = []
    for f in findings:
        sev = _severity_value(f).upper()
        if sev in ("CRITICAL", "HIGH", "BLOCKER", "ERROR"):
            msg = str(f.get("message") or f.get("title") or f.get("summary") or "")
            if msg:
                top_risks.append(f"[{sev}] {msg[:100]}")
    if not top_risks:
        for f in findings[:3]:
            msg = str(f.get("message") or f.get("title") or f.get("summary") or "")
            sev = _severity_value(f).upper()
            if msg:
                top_risks.append(f"[{sev}] {msg[:100]}")

    raw = ""
    if isinstance(result, str):
        raw = result[:4000]
    elif isinstance(result, dict):
        raw = json.dumps(result, indent=2, default=str)[:4000]

    brain_result = bridge.call_tool("brain_record_review", {
        "source": source_label,
        "finding_count": finding_count,
        "top_risks": top_risks[:5],
        "suggested_next_steps": [],
        "confidence": "high" if finding_count > 0 else "medium",
        "raw_summary": raw,
    })

    if isinstance(brain_result, list) and brain_result:
        brain_result = brain_result[0].get("text", brain_result) if isinstance(brain_result[0], dict) else brain_result
    if isinstance(brain_result, str):
        try:
            brain_result = json.loads(brain_result)
        except json.JSONDecodeError:
            pass

    if isinstance(brain_result, dict) and brain_result.get("ok"):
        console.print(f"[dim]→ brain: {brain_result.get('path', 'saved')}[/dim]")
    else:
        err = brain_result.get("error", str(brain_result)) if isinstance(brain_result, dict) else str(brain_result)
        console.print(f"[dim yellow]brain: {err[:80]}[/dim yellow]")


def _brain_record_learning(bridge: Any, path: str, extract_result: Any) -> None:
    """Record a learn extraction to the mqobsidian second brain. Silent on failure."""
    text = _extract_mcp_text_result(extract_result) or ""

    if "NO REVIEW FOUND" in text or not text.strip():
        console.print("[dim]brain: skipped (no review found)[/dim]")
        return

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Parse the key: value text format returned by learn_extract_from_last_review
        for line in text.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key in ("pattern_name", "pattern_type", "confidence", "summary",
                           "recommended_action", "evidence") and val:
                    parsed[key] = val

    from pathlib import Path as _Path
    slug = _Path(path).stem.replace(".", "-")

    raw_evidence = parsed.get("evidence", path)
    evidence_list = raw_evidence if isinstance(raw_evidence, list) else [raw_evidence]

    brain_result = bridge.call_tool("brain_record_learning", {
        "pattern_name": parsed.get("pattern_name", slug),
        "pattern_type": parsed.get("pattern_type", "code_pattern"),
        "summary": parsed.get("summary", text[:1000]) or text[:1000] or "(no content)",
        "evidence": evidence_list,
        "recommended_action": parsed.get("recommended_action", "Review extracted pattern and store if valid."),
        "confidence": parsed.get("confidence", "medium"),
    })

    if isinstance(brain_result, list) and brain_result:
        brain_result = brain_result[0].get("text", brain_result) if isinstance(brain_result[0], dict) else brain_result
    if isinstance(brain_result, str):
        try:
            brain_result = json.loads(brain_result)
        except json.JSONDecodeError:
            pass

    if isinstance(brain_result, dict) and brain_result.get("ok"):
        console.print(f"[dim]→ brain: {brain_result.get('path', 'saved')}[/dim]")
    else:
        err = brain_result.get("error", str(brain_result)) if isinstance(brain_result, dict) else str(brain_result)
        console.print(f"[dim yellow]brain: {err[:80]}[/dim yellow]")


def _review_flags(
    security: bool,
    architecture: bool,
    risk: bool,
    fast: bool = False,
    visual_architecture_observation: Any = None,
) -> dict[str, Any]:
    flags: dict[str, Any] = {
        "security": security,
        "architecture": architecture,
        "risk": risk,
        "fast": fast,
    }
    if visual_architecture_observation is not None:
        flags["visual_architecture_observation"] = visual_architecture_observation
    return flags


def _coerce_mcp_json_payload(value: Any) -> Any:
    """Unwrap common MCP JSON string payloads without interpreting their meaning."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        for key in ("result", "text"):
            nested = value.get(key)
            if isinstance(nested, str):
                coerced = _coerce_mcp_json_payload(nested)
                if coerced is not nested:
                    return coerced
        content = value.get("content")
        if isinstance(content, list) and len(content) == 1:
            return _coerce_mcp_json_payload(content[0])
    return value


def _visual_architecture_observation(bridge: Any, image_path: str | None) -> Any:
    """Delegate visual architecture observation to mq-image-analyze."""
    if not image_path:
        return None
    observation = bridge.call_tool("observe_architecture", {"image_path": image_path})
    if _is_error_result(observation):
        return observation
    return _coerce_mcp_json_payload(observation)


def _review_flags_with_visual_context(
    bridge: Any,
    security: bool,
    architecture: bool,
    risk: bool,
    fast: bool,
    architecture_image: str | None,
) -> dict[str, Any]:
    observation = _visual_architecture_observation(bridge, architecture_image)
    if _is_error_result(observation):
        return {"ok": False, "visual_context_error": observation}
    return {
        **_review_flags(
            security,
            architecture or bool(architecture_image),
            risk,
            fast,
            visual_architecture_observation=observation,
        )
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
    architecture_image: Annotated[str | None, typer.Option("--architecture-image", "--visual", help="Image path to observe via mq-image-analyze and pass as architecture context")] = None,
    risk: Annotated[bool, typer.Option("--risk", help="Use mq-mcp risk review when installed")] = False,
    fast: Annotated[bool, typer.Option("--fast", help="Prefer fast Class A tools over deep AI review")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record review result to mqobsidian second brain")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review one file through mq-mcp. mq-agent does not implement review logic."""
    if dry_run:
        enabled_flags = [f for f, v in _review_flags(security, architecture or bool(architecture_image), risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in enabled_flags)
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_file {path}{' ' + flag_str if flag_str else ''}[/bold]")
        if architecture_image:
            console.print(f"[blue][dry-run][/blue] Would first call: [bold]mq-image-analyze observe_architecture image_path={architecture_image}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    flags = _review_flags_with_visual_context(bridge, security, architecture, risk, fast, architecture_image)
    if _is_error_result(flags):
        _run_review("review file", flags, json_out)
        return
    result = bridge.review_file(path, flags)
    _run_review("review file", result, json_out, bridge=bridge)
    if brain and not _is_error_result(result):
        _brain_record_review(bridge, path, result)


@review_app.command("diff")
def review_diff_cmd(
    security: Annotated[bool, typer.Option("--security", help="Ask mq-mcp for security review mode")] = False,
    architecture: Annotated[bool, typer.Option("--architecture", help="Ask mq-mcp for architecture review mode")] = False,
    architecture_image: Annotated[str | None, typer.Option("--architecture-image", "--visual", help="Image path to observe via mq-image-analyze and pass as architecture context")] = None,
    risk: Annotated[bool, typer.Option("--risk", help="Use mq-mcp risk review when installed")] = False,
    fast: Annotated[bool, typer.Option("--fast", help="Prefer fast Class A tools over deep AI review")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record review result to mqobsidian second brain")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review the current diff through mq-mcp. Findings are passed through."""
    if dry_run:
        enabled_flags = [f for f, v in _review_flags(security, architecture or bool(architecture_image), risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in enabled_flags)
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_diff{' ' + flag_str if flag_str else ''}[/bold]")
        if architecture_image:
            console.print(f"[blue][dry-run][/blue] Would first call: [bold]mq-image-analyze observe_architecture image_path={architecture_image}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    flags = _review_flags_with_visual_context(bridge, security, architecture, risk, fast, architecture_image)
    if _is_error_result(flags):
        _run_review("review diff", flags, json_out)
        return
    result = bridge.review_diff(flags)
    _run_review("review diff", result, json_out, bridge=bridge)
    if brain and not _is_error_result(result):
        _brain_record_review(bridge, "diff", result)


@review_app.command("repo")
def review_repo_cmd(
    path: Annotated[str, typer.Argument(help="Repo path to review")] = ".",
    security: Annotated[bool, typer.Option("--security", help="Ask mq-mcp for security review mode")] = False,
    architecture: Annotated[bool, typer.Option("--architecture", help="Ask mq-mcp for architecture review mode")] = False,
    architecture_image: Annotated[str | None, typer.Option("--architecture-image", "--visual", help="Image path to observe via mq-image-analyze and pass as architecture context")] = None,
    risk: Annotated[bool, typer.Option("--risk", help="Use mq-mcp risk review when installed")] = False,
    fast: Annotated[bool, typer.Option("--fast", help="Prefer fast Class A tools over deep AI review")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record review result to mqobsidian second brain")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review a repo through mq-mcp. mq-agent renders mq-mcp output only."""
    if dry_run:
        enabled_flags = [f for f, v in _review_flags(security, architecture or bool(architecture_image), risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in enabled_flags)
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_repo {path}{' ' + flag_str if flag_str else ''}[/bold]")
        if architecture_image:
            console.print(f"[blue][dry-run][/blue] Would first call: [bold]mq-image-analyze observe_architecture image_path={architecture_image}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    flags = _review_flags_with_visual_context(bridge, security, architecture, risk, fast, architecture_image)
    if _is_error_result(flags):
        _run_review("review repo", flags, json_out)
        return
    result = bridge.review_repo(path, flags)
    _run_review("review repo", result, json_out, bridge=bridge)
    if brain and not _is_error_result(result):
        _brain_record_review(bridge, path, result)


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


@learn_app.command("extract-review")
def learn_extract_review_cmd(
    path: Annotated[str, typer.Argument(help="Repo-relative file path to extract a learn candidate from.")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record learn candidate to mqobsidian")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Dry-run extraction of a learn candidate from the last review for a file. Read-only."""
    if dry_run:
        console.print(f"[blue]dry-run:[/blue] Would call: [bold]mq-mcp learn_extract_from_last_review {path}[/bold]")
        if brain:
            console.print("[blue]dry-run:[/blue] With --brain: would write a learn note to mqobsidian")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    result = bridge.learn_extract_from_last_review(path)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]learn extract unavailable[/bold red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    text_result = _extract_mcp_text_result(result)
    if text_result:
        console.print(Panel(Text(text_result), title=f"[bold]Learn extract: {path}[/bold]"))
    else:
        console.print(Panel(json.dumps(result, indent=2, default=str), title=f"[bold]Learn extract: {path}[/bold]"))

    if brain and not _is_error_result(result):
        _brain_record_learning(bridge, path, result)


@learn_app.command("review-flow")
def learn_review_flow_cmd(
    path: Annotated[str, typer.Argument(help="Repo-relative file path")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record learn candidate to mqobsidian")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review a file then extract a dry-run learn candidate in one pass. Read-only."""
    if dry_run:
        console.print(f"[blue]dry-run:[/blue] Would call: [bold]mq-mcp review_file {path}[/bold]")
        console.print(f"[blue]dry-run:[/blue] Then: [bold]mq-mcp learn_extract_from_last_review {path}[/bold]")
        if brain:
            console.print("[blue]dry-run:[/blue] With --brain: would write a learn note to mqobsidian")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    review_result = bridge.review_file(path, {})
    extract_result = bridge.learn_extract_from_last_review(path)

    if json_out:
        combined = {"path": path, "review": review_result, "extract": extract_result}
        typer.echo(json.dumps(combined, indent=2, default=str))
        if _is_error_result(review_result):
            raise typer.Exit(1)
        return

    console.rule("[bold cyan]Step 1/2 — review file[/bold cyan]")
    _render_review_result("review file", review_result)

    console.rule("[bold cyan]Step 2/2 — learn extract-review[/bold cyan]")
    if _is_error_result(extract_result):
        console.print(Panel(
            str(extract_result.get("error", extract_result)),
            title="[bold yellow]learn extract unavailable[/bold yellow]",
            border_style="yellow",
        ))
        return

    text_result = _extract_mcp_text_result(extract_result)
    if text_result:
        console.print(Panel(Text(text_result), title=f"[bold]Learn extract: {path}[/bold]"))
    else:
        console.print(Panel(json.dumps(extract_result, indent=2, default=str), title=f"[bold]Learn extract: {path}[/bold]"))

    console.rule("[dim]Next safe action[/dim]")
    console.print(
        "  [bold]mq-agent learn search <query>[/bold]   ← check if pattern already exists\n"
        "  [dim]If the candidate is new and correct:[/dim] [bold]mq-agent learn store {path} --approve[/bold]"
    )

    if brain:
        _brain_record_learning(bridge, path, extract_result)


@learn_app.command("store")
def learn_store_cmd(
    path: Annotated[str, typer.Argument(help="Repo-relative file path")],
    approve: Annotated[bool, typer.Option("--approve", help="Allow write to mq-mcp")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Store the last extracted learn candidate for a file. Class C write tool — requires --approve."""
    if dry_run:
        console.print(
            f"[blue][dry-run][/blue] Would call: [bold]mq-mcp record_learning relative_path={path}[/bold]"
        )
        return

    if not approve:
        console.print(
            "[yellow]record_learning is a Class C write tool.[/yellow]\n"
            "Add [bold]--approve[/bold] to execute, or [bold]--dry-run[/bold] to preview."
        )
        raise typer.Exit(1)

    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().learn_record(path)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(
            str(result.get("error", result)),
            title="[bold red]learn store failed[/bold red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    text_result = _extract_mcp_text_result(result)
    if text_result:
        console.print(Panel(Text(text_result), title=f"[bold green]Pattern stored: {path}[/bold green]", border_style="green"))
        return

    console.print(Panel(json.dumps(result, indent=2, default=str), title=f"[bold green]Pattern stored: {path}[/bold green]", border_style="green"))


@learn_app.command("promote")
def learn_promote_cmd(
    slug: Annotated[str, typer.Argument(help="Filename slug (without path or .md)")],
    approve: Annotated[bool, typer.Option("--approve", help="Allow write to mqobsidian vault")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    """Promote learn/<slug>.md to learn/verified/. Class C write — requires --approve."""
    if dry_run:
        console.print(
            f"[blue][dry-run][/blue] Would promote: [bold]learn/{slug}.md[/bold] → [bold]learn/verified/<timestamp>-{slug}.md[/bold]\n"
            "Validates: pattern_name, pattern_type, ## Summary, ## Evidence, ## Recommended action"
        )
        return

    if not approve:
        console.print(
            "[yellow]learn promote is a Class C write operation.[/yellow]\n"
            "Add [bold]--approve[/bold] to execute, or [bold]--dry-run[/bold] to preview."
        )
        raise typer.Exit(1)

    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    with console.status(f"[bold cyan]Promoting learn/{slug}.md...[/bold cyan]"):
        result = MultiMCPBridge().call_tool("brain_promote_learning", {"slug": slug})

    if isinstance(result, list) and result:
        result = result[0].get("text", result) if isinstance(result[0], dict) else result
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass

    if isinstance(result, dict) and result.get("ok"):
        console.print(f"[green]Promoted:[/green] {result.get('path', 'saved')}")
        console.print(f"[dim]Source marked as promoted: {result.get('source', '')}[/dim]")
    else:
        err = result.get("error", str(result)) if isinstance(result, dict) else str(result)
        console.print(f"[red]promote failed:[/red] {err}")
        raise typer.Exit(1)


@learn_app.command("from-review")
def learn_from_review_cmd(
    path: Annotated[str, typer.Argument(help="Repo-relative file path")],
    task: Annotated[str, typer.Option("--task", "-t", help="What was being worked on")] = "",
    risk: Annotated[str, typer.Option("--risk", help="low | medium | high")] = "low",
    approve: Annotated[bool, typer.Option("--approve", help="Allow write to mq-mcp learn layer")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Create a learning record from the last review for a file. Class C write — requires --approve."""
    if dry_run:
        console.print(
            f"[blue][dry-run][/blue] Would call: [bold]mq-mcp learn_from_review relative_path={path}"
            f"{' task=' + task if task else ''} risk={risk}[/bold]"
        )
        return

    if not approve:
        console.print(
            "[yellow]learn_from_review is a Class C write tool.[/yellow]\n"
            "Add [bold]--approve[/bold] to execute, or [bold]--dry-run[/bold] to preview."
        )
        raise typer.Exit(1)

    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().learn_from_review(path, task=task, risk=risk)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(str(result.get("error", result)), title="[bold red]learn from-review failed[/bold red]", border_style="red"))
        raise typer.Exit(1)

    text_result = _extract_mcp_text_result(result)
    msg = text_result or json.dumps(result, indent=2, default=str)
    console.print(Panel(Text(msg), title=f"[bold green]Learning recorded: {path}[/bold green]", border_style="green"))


@learn_app.command("from-diff")
def learn_from_diff_cmd(
    task: Annotated[str, typer.Option("--task", "-t", help="What was being done")] = "",
    lesson: Annotated[str, typer.Option("--lesson", "-l", help="What was learned")] = "",
    risk: Annotated[str, typer.Option("--risk", help="low | medium | high")] = "low",
    validation: Annotated[str, typer.Option("--validation", help="How it was verified")] = "",
    approve: Annotated[bool, typer.Option("--approve", help="Allow write to mq-mcp learn layer")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Create a learning record with the current git diff as context. Class C write — requires --approve."""
    if not task or not lesson:
        console.print("[red]--task and --lesson are required.[/red]")
        raise typer.Exit(1)

    if dry_run:
        console.print(
            f"[blue][dry-run][/blue] Would call: [bold]mq-mcp learn_from_diff "
            f"task={task!r} lesson={lesson!r} risk={risk}[/bold]"
        )
        return

    if not approve:
        console.print(
            "[yellow]learn_from_diff is a Class C write tool.[/yellow]\n"
            "Add [bold]--approve[/bold] to execute, or [bold]--dry-run[/bold] to preview."
        )
        raise typer.Exit(1)

    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().learn_from_diff(task=task, lesson=lesson, risk=risk, validation=validation)

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok") is False:
        console.print(Panel(str(result.get("error", result)), title="[bold red]learn from-diff failed[/bold red]", border_style="red"))
        raise typer.Exit(1)

    text_result = _extract_mcp_text_result(result)
    msg = text_result or json.dumps(result, indent=2, default=str)
    console.print(Panel(Text(msg), title="[bold green]Learning recorded from diff[/bold green]", border_style="green"))


@learn_app.command("hygiene")
def learn_hygiene_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show hygiene report for stored learning records. Read-only."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().learn_hygiene()

    if result is None:
        console.print("[dim]learn_hygiene not available in this mq-mcp version.[/dim]")
        return

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    text_result = _extract_mcp_text_result(result)
    msg = text_result or json.dumps(result, indent=2, default=str)
    console.print(Panel(Text(msg), title="[bold]Learn hygiene report[/bold]"))


@learn_app.command("summarize")
def learn_summarize_cmd(
    limit: Annotated[int, typer.Option("--limit", help="Max number of records to include")] = 20,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Summarize stored learning records. Read-only."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().learn_summarize(limit=limit)

    if result is None:
        console.print("[dim]summarize_learnings not available in this mq-mcp version.[/dim]")
        return

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    text_result = _extract_mcp_text_result(result)
    msg = text_result or json.dumps(result, indent=2, default=str)
    console.print(Panel(Text(msg), title="[bold]Learned patterns — summary[/bold]"))


# ── brain ──────────────────────────────────────────────────────────────────

brain_app = typer.Typer(help="Second brain vault commands (mqobsidian).")
app.add_typer(brain_app, name="brain")


@brain_app.command(name="record-review")
def brain_record_review_cmd(
    source: Annotated[str, typer.Option("--source", help="Review source identifier (e.g. zephyr:file.yaml)")],
    top_risk: Annotated[list[str], typer.Option("--top-risk", help="Top risk finding (repeatable)")] = [],
    next_step: Annotated[list[str], typer.Option("--next-step", help="Suggested next step (repeatable)")] = [],
    finding_count: Annotated[int, typer.Option("--finding-count")] = 0,
    confidence: Annotated[str, typer.Option("--confidence")] = "medium",
    raw_summary: Annotated[str, typer.Option("--raw-summary")] = "",
    approve: Annotated[bool, typer.Option("--approve")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Write a review summary to mqobsidian/reviews/ via brain_record_review.

    Shell-friendly wrapper: accepts --top-risk and --next-step as repeatable
    options instead of list arguments, so any tool (zephyr, shell scripts) can
    call this without Python imports.
    """
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    if not approve:
        console.print(
            "[bold yellow]Blocked:[/bold yellow] brain_record_review is a write operation.\n"
            "Add [bold]--approve[/bold] to proceed."
        )
        raise typer.Exit(code=1)

    bridge = MultiMCPBridge()
    result = bridge.call_tool("brain_record_review", {
        "source": source,
        "finding_count": finding_count or len(top_risk),
        "top_risks": list(top_risk),
        "suggested_next_steps": list(next_step),
        "confidence": confidence,
        "raw_summary": raw_summary,
    })

    if isinstance(result, list) and result:
        result = result[0].get("text", result) if isinstance(result[0], dict) else result
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if not (isinstance(result, dict) and result.get("ok")):
            raise typer.Exit(code=1)
        return

    if isinstance(result, dict) and result.get("ok"):
        console.print(f"[green]brain:[/green] {result.get('path', 'saved')}")
    else:
        err = result.get("error", str(result)) if isinstance(result, dict) else str(result)
        console.print(f"[red]brain: {err[:120]}[/red]")
        raise typer.Exit(code=1)


@brain_app.command(name="structure")
def brain_structure_cmd(
    init: Annotated[bool, typer.Option("--init", help="Create missing standard directories (write)")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Required with --init")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Check the mqobsidian vault against the standard export structure.

    Read-only by default. --init --approve creates the missing standard
    directories (memory/stack-truth, memory/reviews, memory/learn,
    mq-stack/runs, mq-stack/roadmaps), each with a small README. Exit code
    1 unless the structure is complete — usable as a gate.
    """
    from mq_agent.tools.vault_structure import vault_structure

    if init and not approve:
        console.print(
            "[bold yellow]Blocked:[/bold yellow] --init writes to the mqobsidian vault.\n"
            "Add [bold]--approve[/bold] to proceed."
        )
        raise typer.Exit(code=1)

    raw = vault_structure(init=init)
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        if data["status"] != "OK":
            raise typer.Exit(code=1)
        return

    if data["status"] == "NO_VAULT":
        console.print(f"[red]Vault not found:[/red] {data['vault']}")
        raise typer.Exit(code=1)

    console.print()
    console.rule("[bold]mqobsidian export structure[/bold]")
    console.print()

    table = Table(show_header=True)
    table.add_column("Directory", style="cyan", no_wrap=True)
    table.add_column("Purpose")
    table.add_column("Notes", justify="right", no_wrap=True)
    table.add_column("Newest", no_wrap=True)
    table.add_column("Status", no_wrap=True)

    for d in data["dirs"]:
        table.add_row(
            d["path"] + "/",
            d["purpose"],
            str(d["notes"]) if d["exists"] else "—",
            d["newest"] or "—",
            "[green]ok[/green]" if d["exists"] else "[red]missing[/red]",
        )
    console.print(table)

    for created in data["created"]:
        console.print(f"  [green]created:[/green] {created}/")
    for legacy in data["legacy"]:
        console.print(
            f"  [yellow]legacy:[/yellow] {legacy['path']}/ — {legacy['notes']} note(s)"
            f" (standard: {legacy['standard']}/)"
        )

    console.print()
    status_str = "[green]OK[/green]" if data["status"] == "OK" else "[red]INCOMPLETE[/red]"
    console.print(f"  Structure: {status_str}   Vault: [dim]{data['vault']}[/dim]")
    if data["status"] != "OK":
        console.print("  Next: [bold]mq-agent brain structure --init --approve[/bold]")
        raise typer.Exit(code=1)


# ── decide ─────────────────────────────────────────────────────────────────

@app.command()
def decide(
    title: Annotated[str, typer.Argument(help="Short decision title")],
    context: Annotated[str, typer.Option("--context", "-c", help="What prompted this decision")] = "",
    decision: Annotated[str, typer.Option("--decision", "-d", help="What was decided")] = "",
    rationale: Annotated[str, typer.Option("--rationale", "-r", help="Why this decision was made")] = "",
    consequences: Annotated[str, typer.Option("--consequences", help="Known trade-offs or follow-ups")] = "",
    tag: Annotated[list[str], typer.Option("--tag", help="Tag (repeatable)")] = [],
    json_out: Annotated[bool, typer.Option("--json")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Required: decide is a write operation")] = False,
):
    """Record an architecture decision to mqobsidian/decisions/. Class C write."""
    if not context or not decision or not rationale:
        console.print(
            "[yellow]Provide --context, --decision, and --rationale.[/yellow]\n"
            "Example: mq-agent decide 'ADR title' --context '...' --decision '...' --rationale '...' --approve"
        )
        raise typer.Exit(1)

    if not approve:
        console.print(
            "[bold yellow]Blocked:[/bold yellow] decide is a write operation (mqobsidian decisions).\n"
            "Add [bold]--approve[/bold] to proceed."
        )
        raise typer.Exit(1)

    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    result = MultiMCPBridge().call_tool("brain_record_decision", {
        "title": title,
        "context": context,
        "decision": decision,
        "rationale": rationale,
        "consequences": consequences,
        "tags": list(tag),
    })

    if json_out:
        typer.echo(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and result.get("ok") is False:
            raise typer.Exit(1)
        return

    if isinstance(result, dict) and result.get("ok"):
        console.print(f"[green]Decision recorded:[/green] {result.get('path', 'saved')}")
    else:
        err = result.get("error", str(result)) if isinstance(result, dict) else str(result)
        console.print(f"[red]decide failed:[/red] {err}")
        raise typer.Exit(1)


# ── signal ─────────────────────────────────────────────────────────────────

@app.command()
def signal(
    path: Annotated[str, typer.Argument(help="Repo path to analyse")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record signal result to mqobsidian second brain")] = False,
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

    if brain and not dry_run:
        from mq_agent.tools.mcp_bridge import MultiMCPBridge
        _brain_record_review(
            MultiMCPBridge(),
            f"repo-signal:{result.get('repo', path)}",
            {
                "findings": [
                    {"severity": "info", "message": f, "summary": f}
                    for f in result.get("focus_areas", [])
                ],
                "scores": result.get("scores"),
                "publish": result.get("publish"),
            },
        )


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
    local_tasks = Path("tasks")
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
        local_tasks = Path("tasks")
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


# ── b2 — B2 prompt OS bridge ───────────────────────────────────────────────

@b2_app.command("route")
def b2_route_cmd(
    topic: Annotated[str, typer.Argument(help="Topic or context to route")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Route a topic to the matching B2 prompt route and primary prompt ID."""
    from mq_agent.tools.b2tui_tools import b2_route_info

    raw = b2_route_info(topic)
    if json_out:
        typer.echo(raw)
        return
    data = json.loads(raw)
    console.print(Panel(
        f"[bold]Route:[/bold]      {data['route']}\n"
        f"[bold]Prompt ID:[/bold]  {data['prompt_id']}\n"
        f"[bold]Prompt:[/bold]     {data['prompt_name']}",
        title="[cyan]B2 route[/cyan]",
    ))


@b2_app.command("prompt")
def b2_prompt_cmd(
    prompt_id: Annotated[str, typer.Argument(help="Prompt ID, e.g. 02.11")],
):
    """Print the full content of a B2 prompt by ID."""
    from mq_agent.tools.b2tui_tools import b2_get_prompt

    content = b2_get_prompt(prompt_id)
    console.print(content)


@b2_app.command("list")
def b2_list_cmd(
    category: Annotated[str, typer.Option("--category", "-c", help="Filter by category")] = "",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List available B2 prompts."""
    from mq_agent.tools.b2tui_tools import b2_list_prompts

    output = b2_list_prompts(category=category)
    if json_out:
        rows = []
        for line in output.splitlines():
            parts = line.split("  ", 2)
            if len(parts) == 3:
                rows.append({"id": parts[0].strip(), "category": parts[1].strip("[]"), "name": parts[2].strip()})
        typer.echo(json.dumps(rows, indent=2))
        return
    table = Table(title="B2 Prompts", show_header=True)
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Category", style="yellow")
    table.add_column("Name")
    for line in output.splitlines():
        parts = line.split("  ", 2)
        if len(parts) == 3:
            table.add_row(parts[0].strip(), parts[1].strip("[]"), parts[2].strip())
    console.print(table)


@b2_app.command("history")
def b2_history_cmd(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show recent b2tui workflow run history."""
    from mq_agent.tools.b2tui_tools import b2_history

    raw = b2_history(limit=limit)
    if json_out:
        typer.echo(raw)
        return
    entries = json.loads(raw)
    if not entries:
        console.print("[dim]No history yet.[/dim]")
        return
    table = Table(title="B2 Run History", show_header=True)
    table.add_column("Timestamp", style="dim", width=22)
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Prompt")
    table.add_column("Context")
    table.add_column("Source", style="dim")
    for e in reversed(entries):
        table.add_row(
            e.get("timestamp", "")[:19],
            e.get("prompt_id", ""),
            e.get("prompt_name", ""),
            (e.get("context", "") or "")[:40],
            e.get("source", ""),
        )
    console.print(table)


@b2_app.command("run")
def b2_run_cmd(
    context: Annotated[str, typer.Argument(help="Topic or context for this workflow run")] = "",
    route: Annotated[str | None, typer.Option("--route", "-r", help="Force a specific route name")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Run the B2 plan→compose→review→output workflow for a given context."""
    from mq_agent.tools.b2tui_tools import (
        ROUTE_PRIMARY,
        b2_get_prompt,
        b2_log_run,
        b2_route_info,
    )
    from mq_agent.tools.mcp_bridge import MCPBridge

    if not context:
        console.print("[red]Provide a topic or context as argument.[/red]")
        raise typer.Exit(1)

    # ── Plan ──────────────────────────────────────────────────────────────────
    if route:
        if route not in ROUTE_PRIMARY:
            console.print(f"[red]Unknown route: {route!r}. Valid: {list(ROUTE_PRIMARY)}[/red]")
            raise typer.Exit(1)
        prompt_id = ROUTE_PRIMARY[route]
        route_name = route
        route_raw = json.dumps({"route": route_name, "prompt_id": prompt_id})
    else:
        route_raw = b2_route_info(context)
        route_data = json.loads(route_raw)
        route_name = route_data["route"]
        prompt_id = route_data["prompt_id"]

    if dry_run:
        console.print(f"[blue][dry-run][/blue] route={route_name}  prompt_id={prompt_id}")
        return

    console.print(f"[cyan]route[/cyan]  {route_name}  [dim]→[/dim]  [bold]{prompt_id}[/bold]")

    # ── Compose ───────────────────────────────────────────────────────────────
    with console.status("[cyan]Loading prompt...[/cyan]"):
        prompt_content = b2_get_prompt(prompt_id)

    console.print(Panel(
        prompt_content[:600] + ("…" if len(prompt_content) > 600 else ""),
        title=f"[bold]{prompt_id}[/bold] prompt (truncated)",
        border_style="dim",
    ))

    # ── Review (best-effort via mq-mcp) ───────────────────────────────────────
    bridge = MCPBridge()
    review_result = ""
    if bridge.is_available():
        with console.status("[cyan]mq-mcp review pass...[/cyan]"):
            try:
                review_result = str(bridge.call_tool("review_repo", {}))
                console.print(Panel(
                    (review_result[:400] + "…") if len(review_result) > 400 else review_result,
                    title="[green]mq-mcp review[/green]",
                    border_style="green",
                ))
            except Exception as exc:
                console.print(f"[yellow]mq-mcp review skipped: {exc}[/yellow]")
    else:
        console.print("[dim]mq-mcp offline — review pass skipped[/dim]")

    # ── Output / log ──────────────────────────────────────────────────────────
    log_msg = b2_log_run(prompt_id=prompt_id, context=context, result=review_result)
    console.print(f"[dim]{log_msg}[/dim]")

    if json_out:
        typer.echo(json.dumps({
            "route": route_name,
            "prompt_id": prompt_id,
            "prompt_preview": prompt_content[:200],
            "review_preview": review_result[:200],
            "logged": log_msg,
        }, indent=2))


# ── stack — history persistence ────────────────────────────────────────────

def _sweep_history_append(results: list[dict]) -> None:
    """Append a sweep snapshot to ~/.mq-agent/sweep-history.jsonl."""
    import datetime
    history_file = Path.home() / ".mq-agent" / "sweep-history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.datetime.now(datetime.UTC).isoformat(),
        "results": results,
    }
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _stack_history_diff(sweep_a: dict, sweep_b: dict) -> None:
    """Print a diff table between two sweep snapshots."""
    ts_a = sweep_a["ts"][:16].replace("T", " ")
    ts_b = sweep_b["ts"][:16].replace("T", " ")
    results_a = {e["name"]: e for e in sweep_a["results"]}
    results_b = {e["name"]: e for e in sweep_b["results"]}
    all_names = list(dict.fromkeys(list(results_a) + list(results_b)))

    table = Table(title=f"Sweep diff: {ts_a} → {ts_b}", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column(ts_a, width=12)
    table.add_column(ts_b, width=12)
    table.add_column("Delta", width=10)

    def _fmt(e: dict | None) -> str:
        if e is None or e.get("skipped"):
            return "[dim]—[/dim]"
        score = e.get("overall", 0)
        color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
        return f"[{color}]{score}[/{color}]"

    def _score(e: dict | None) -> int | None:
        if e is None or e.get("skipped"):
            return None
        return e.get("overall")

    for name in all_names:
        sa = _score(results_a.get(name))
        sb = _score(results_b.get(name))
        if sa is None or sb is None:
            delta_str = "[dim]—[/dim]"
        elif sb > sa:
            delta_str = f"[green]+{sb - sa}[/green]"
        elif sb < sa:
            delta_str = f"[red]{sb - sa}[/red]"
        else:
            delta_str = "[dim]==[/dim]"
        table.add_row(name, _fmt(results_a.get(name)), _fmt(results_b.get(name)), delta_str)

    console.print(table)


# ── stack — alert helpers ──────────────────────────────────────────────────

def _compute_alerts(sweeps: list[dict], threshold: int = 10, min_score: int = 80) -> list[dict]:
    """Return alert entries by comparing the last two sweep snapshots."""
    if len(sweeps) < 2:
        return []
    prev_map = {e["name"]: e for e in sweeps[-2]["results"]}
    curr_map = {e["name"]: e for e in sweeps[-1]["results"]}
    alerts: list[dict] = []
    for name, e in curr_map.items():
        if e.get("skipped"):
            continue
        score = e.get("overall", 0)
        p = prev_map.get(name)
        prev_score: int | None = p.get("overall") if p and not p.get("skipped") else None
        reasons: list[str] = []
        if prev_score is not None and (prev_score - score) >= threshold:
            reasons.append(f"dropped {prev_score - score} pts")
        if score < min_score:
            reasons.append(f"below {min_score}")
        if reasons:
            alerts.append({
                "name": name,
                "prev": prev_score,
                "current": score,
                "delta": (score - prev_score) if prev_score is not None else None,
                "reasons": reasons,
            })
    return alerts


def _print_alerts(alerts: list[dict], ts_prev: str, ts_curr: str) -> None:
    """Render alert table to console."""
    table = Table(title=f"[bold red]Stack alerts[/bold red]  {ts_prev[:16].replace('T', ' ')} → {ts_curr[:16].replace('T', ' ')}", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column("Prev", width=6)
    table.add_column("Now", width=6)
    table.add_column("Delta", width=8)
    table.add_column("Reason", style="yellow")
    for a in alerts:
        prev_str = str(a["prev"]) if a["prev"] is not None else "—"
        score = a["current"]
        color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
        delta = a["delta"]
        delta_str = f"[red]{delta}[/red]" if delta is not None and delta < 0 else (f"[green]+{delta}[/green]" if delta and delta > 0 else "[dim]==[/dim]")
        table.add_row(a["name"], prev_str, f"[{color}]{score}[/{color}]", delta_str, ", ".join(a["reasons"]))
    console.print(table)


# ── stack — mq-stack repo status ───────────────────────────────────────────

@stack_app.command("status")
def stack_status_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show version, branch, last activity, drift risk and readiness for all mq-stack repos."""
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _repo_entry

    with console.status("[cyan]Scanning mq-stack repos...[/cyan]"):
        entries = [_repo_entry(r) for r in MQ_STACK_REPOS]

    if json_out:
        typer.echo(json.dumps(entries, indent=2))
        return

    table = Table(title="mq-stack Status", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column("Version", width=9)
    table.add_column("Branch", width=28)
    table.add_column("Last activity", width=14)
    table.add_column("Drift", width=8)
    table.add_column("Ready", width=7)
    table.add_column("Next", style="dim")

    for e in entries:
        drift_style = {"Low": "green", "Medium": "yellow", "High": "red"}.get(e["drift_risk"], "")
        table.add_row(
            e["name"],
            e["version"],
            e["branch"],
            e["last_activity"],
            f"[{drift_style}]{e['drift_risk']}[/{drift_style}]" if drift_style else e["drift_risk"],
            e["readiness"],
            (e["next_action"] or "—")[:50],
        )
    console.print(table)


@stack_app.command("report")
def stack_report_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Consolidated stack health view: score, trend, alert and readiness per repo.

    Reads sweep history for scores and trend; no API key required.
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS

    history_file = Path.home() / ".mq-agent" / "sweep-history.jsonl"
    sweeps: list[dict] = []
    if history_file.exists():
        with history_file.open(encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line:
                    try:
                        sweeps.append(json.loads(_line))
                    except json.JSONDecodeError:
                        continue

    alerts = _compute_alerts(sweeps) if len(sweeps) >= 2 else []
    alert_names = {a["name"] for a in alerts}
    latest = {e["name"]: e for e in sweeps[-1]["results"]} if sweeps else {}
    prev = {e["name"]: e for e in sweeps[-2]["results"]} if len(sweeps) >= 2 else {}

    rows: list[dict] = []
    for r in MQ_STACK_REPOS:
        name = r["name"]
        curr = latest.get(name)
        prv = prev.get(name)
        if curr is None or curr.get("skipped"):
            score: int | None = None
            trend = "—"
        else:
            score = curr["overall"]
            ps = prv.get("overall") if prv and not prv.get("skipped") else None
            if ps is None:
                trend = "new"
            elif score > ps:
                trend = f"↑+{score - ps}"
            elif score < ps:
                trend = f"↓{score - ps}"
            else:
                trend = "=="
        has_alert = name in alert_names
        ready = score is not None and score >= 80 and not has_alert
        rows.append({"name": name, "score": score, "trend": trend, "alert": has_alert, "ready": ready})

    if json_out:
        typer.echo(json.dumps(rows, indent=2))
        return

    ts_note = f"  [dim]{sweeps[-1]['ts'][:16].replace('T', ' ')}[/dim]" if sweeps else ""
    table = Table(title=f"mq-stack Report{ts_note}", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column("Score", width=9)
    table.add_column("Trend", width=8)
    table.add_column("Alert", width=7)
    table.add_column("Ready", width=7)

    for row in rows:
        if row["score"] is None:
            score_str = "[dim]—[/dim]"
        else:
            c = "green" if row["score"] >= 80 else "yellow" if row["score"] >= 50 else "red"
            score_str = f"[{c}]{row['score']}/100[/{c}]"
        t = row["trend"]
        trend_str = f"[green]{t}[/green]" if t.startswith("↑") else (f"[red]{t}[/red]" if t.startswith("↓") else f"[dim]{t}[/dim]")
        alert_str = "[yellow]⚠[/yellow]" if row["alert"] else ("[green]✓[/green]" if row["score"] is not None else "[dim]—[/dim]")
        ready_str = "[green]✓[/green]" if row["ready"] else ("[dim]—[/dim]" if row["score"] is None else "[yellow]~[/yellow]")
        table.add_row(row["name"], score_str, trend_str, alert_str, ready_str)

    console.print(table)
    if not sweeps:
        console.print("\n[dim yellow]No sweep history — run:[/dim yellow] [bold]mq-agent stack sweep[/bold]")
    else:
        ready_count = sum(1 for r in rows if r["ready"])
        total = sum(1 for r in rows if r["score"] is not None)
        console.print(f"\n[dim]{ready_count}/{total} repos ready (score ≥ 80, no alert)[/dim]")


@stack_app.command("truth-export")
@stack_app.command("export")
def stack_export_cmd(
    output: Annotated[str, typer.Option("--output", "-o", help="Output path (default: dated note under mqobsidian/memory/stack-truth/)")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Write the mq-stack truth snapshot (contract + release gates) to mqobsidian.

    Primary name: `stack truth-export`. `stack export` is kept as a
    backwards-compatible alias — both run the same export.
    """
    from mq_agent.tools.stack_tools import stack_export
    from mq_agent.tools.stack_truth import stack_truth_export
    from mq_agent.tools.stack_truth import default_stack_truth_path

    dest = output or str(default_stack_truth_path())

    if json_out:
        result = stack_truth_export(output_path=output, write=not dry_run)
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    if dry_run:
        console.print(f"[blue][dry-run][/blue] Would write to: {dest}")
        return

    with console.status("[cyan]Collecting stack truth...[/cyan]"):
        msg = stack_export(output_path=output)

    console.print(f"[green]{msg}[/green]")


@stack_app.command("sweep")
def stack_sweep_cmd(
    brain: Annotated[bool, typer.Option("--brain", help="Record signal result for each repo to mqobsidian")] = False,
    decide: Annotated[bool, typer.Option("--decide", help="Write a brain ADR summarising the stack health snapshot")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    alert: Annotated[bool, typer.Option("--alert", help="Warn when a repo drops or falls below min-score")] = False,
    threshold: Annotated[int, typer.Option("--threshold", help="Point drop that triggers an alert")] = 10,
):
    """Run repo-signal over every mq-stack repo and optionally write brain notes + an ADR snapshot.

    For each reachable repo: runs mq-agent signal --brain (read + optional write).
    With --decide: writes a brain ADR via mq-agent decide capturing overall health.
    With --alert: exits 1 if any repo dropped >= threshold points or is below 80.
    """
    from mq_agent.agents.signal_agent import SignalAgent
    from mq_agent.tools.mcp_bridge import MultiMCPBridge
    from mq_agent.tools.signal_tools import signal_available
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand

    if not signal_available():
        console.print("[bold red]repo-signal not installed.[/bold red]\nRun: [bold]uv pip install repo-signal[/bold]")
        raise typer.Exit(1)

    if dry_run:
        console.print("[blue][dry-run][/blue] Would run signal on:")
        for r in MQ_STACK_REPOS:
            p = _expand(r["path"])
            reachable = "✓" if p.exists() else "✗ (not found)"
            console.print(f"  {r['name']:<18} {reachable}")
        if brain:
            console.print("\n  Each result → brain note via --brain")
        if decide:
            console.print("  Final snapshot → brain decide ADR")
        return

    client = _client()
    agent = SignalAgent(client)
    bridge = MultiMCPBridge()

    results: list[dict] = []
    for r in MQ_STACK_REPOS:
        p = _expand(r["path"])
        if not p.exists():
            console.print(f"[dim]  {r['name']}: path not found — skipped[/dim]")
            results.append({"name": r["name"], "skipped": True})
            continue

        console.rule(f"[bold cyan]{r['name']}[/bold cyan]")
        with console.status(f"[cyan]Scanning {r['name']}...[/cyan]"):
            result = agent.run(str(p), dry_run=False)

        overall = result["scores"]["overall"]
        color = "green" if overall >= 80 else "yellow" if overall >= 50 else "red"
        console.print(Panel(
            f"Overall: [{color}]{overall}/100[/{color}]  "
            f"README: {result['scores']['readme']}/{result['scores']['readme_max']}  "
            f"Publish: {result['scores']['publish']}/{result['scores']['publish_total']}",
            title=f"[bold]{r['name']}[/bold] · {result.get('project_type', '')}",
        ))

        entry = {"name": r["name"], "overall": overall, "publish": result["scores"]["publish"], "skipped": False}
        results.append(entry)

        if brain:
            _brain_record_review(
                bridge,
                f"repo-signal:{r['name']}",
                {
                    "findings": [{"severity": "info", "message": f, "summary": f} for f in result.get("focus_areas", [])],
                    "scores": result.get("scores"),
                    "publish": result.get("publish"),
                },
            )

    _sweep_history_append(results)

    if json_out:
        typer.echo(json.dumps(results, indent=2, default=str))
        return

    # Summary table
    table = Table(title="Stack health sweep — summary", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column("Overall", width=10)
    table.add_column("Publish", width=10)
    table.add_column("Status", width=8)
    for e in results:
        if e.get("skipped"):
            table.add_row(e["name"], "—", "—", "[dim]skipped[/dim]")
            continue
        score = e["overall"]
        color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
        table.add_row(e["name"], f"[{color}]{score}/100[/{color}]", str(e.get("publish", "?")), "[green]✓[/green]" if score >= 80 else "[yellow]~[/yellow]")
    console.print(table)

    if alert:
        history_file = Path.home() / ".mq-agent" / "sweep-history.jsonl"
        sweeps: list[dict] = []
        if history_file.exists():
            with history_file.open(encoding="utf-8") as _hf:
                for _line in _hf:
                    _line = _line.strip()
                    if _line:
                        try:
                            sweeps.append(json.loads(_line))
                        except json.JSONDecodeError:
                            continue
        found_alerts = _compute_alerts(sweeps, threshold=threshold)
        if found_alerts:
            _print_alerts(found_alerts, sweeps[-2]["ts"] if len(sweeps) >= 2 else "", sweeps[-1]["ts"] if sweeps else "")
            raise typer.Exit(1)
        else:
            console.print("[green]✓ No alerts — all repos healthy or stable.[/green]")

    if decide:
        healthy = [e["name"] for e in results if not e.get("skipped") and e.get("overall", 0) >= 80]
        needs_work = [e["name"] for e in results if not e.get("skipped") and e.get("overall", 0) < 80]
        skipped = [e["name"] for e in results if e.get("skipped")]
        context = f"Stack sweep ran on {len(results)} repos. Healthy (≥80): {healthy or 'none'}. Needs work: {needs_work or 'none'}. Skipped: {skipped or 'none'}."
        decision = f"Stack is {'ready' if not needs_work else 'not fully ready'} — {len(healthy)}/{len(results) - len(skipped)} repos healthy."
        rationale = f"Based on repo-signal overall scores. Repos below 80: {needs_work or 'none'}."

        from mq_agent.tools.mcp_bridge import MultiMCPBridge as _B
        bridge2 = _B()
        adr_result = bridge2.call_tool("brain_record_decision", {
            "title": "MQ Stack Health Snapshot",
            "context": context,
            "decision": decision,
            "rationale": rationale,
            "tags": ["stack", "health", "sweep"],
        })
        if isinstance(adr_result, list) and adr_result:
            adr_result = adr_result[0].get("text", adr_result) if isinstance(adr_result[0], dict) else adr_result
        if isinstance(adr_result, str):
            try:
                adr_result = json.loads(adr_result)
            except json.JSONDecodeError:
                pass
        if isinstance(adr_result, dict) and adr_result.get("ok"):
            console.print(f"\n[dim]→ brain ADR: {adr_result.get('path', 'saved')}[/dim]")
        else:
            console.print("\n[dim yellow]brain decide: skipped or unavailable[/dim yellow]")


# ── stack history ──────────────────────────────────────────────────────────

@stack_app.command("history")
def stack_history_cmd(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of past sweeps to show")] = 5,
    diff: Annotated[bool, typer.Option("--diff", help="Diff the two most recent sweeps")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show repo health scores from past stack sweeps."""
    history_file = Path.home() / ".mq-agent" / "sweep-history.jsonl"
    if not history_file.exists():
        console.print("[yellow]No sweep history yet.[/yellow]  Run: [bold]mq-agent stack sweep[/bold]")
        return

    sweeps: list[dict] = []
    with history_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    sweeps.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not sweeps:
        console.print("[yellow]History file is empty.[/yellow]  Run: [bold]mq-agent stack sweep[/bold]")
        return

    if diff:
        if len(sweeps) < 2:
            console.print("[yellow]Need at least 2 sweeps to diff.[/yellow]")
            return
        _stack_history_diff(sweeps[-2], sweeps[-1])
        return

    recent = sweeps[-limit:]

    if json_out:
        typer.echo(json.dumps(recent, indent=2, default=str))
        return

    repo_names: list[str] = []
    for sweep in recent:
        for e in sweep["results"]:
            if e["name"] not in repo_names:
                repo_names.append(e["name"])

    table = Table(title=f"Stack health history — last {len(recent)} sweep(s)", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    for sweep in recent:
        ts = sweep["ts"][:16].replace("T", " ")
        table.add_column(ts, width=12)

    for name in repo_names:
        row: list[str] = [name]
        for sweep in recent:
            entry = next((e for e in sweep["results"] if e["name"] == name), None)
            if entry is None:
                row.append("[dim]—[/dim]")
            elif entry.get("skipped"):
                row.append("[dim]skip[/dim]")
            else:
                score = entry["overall"]
                color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
                row.append(f"[{color}]{score}[/{color}]")
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]History: {history_file}  ({len(sweeps)} sweep(s) total)[/dim]")


# ── stack alert ────────────────────────────────────────────────────────────

@stack_app.command("alert")
def stack_alert_cmd(
    threshold: Annotated[int, typer.Option("--threshold", "-t", help="Point drop that triggers an alert")] = 10,
    min_score: Annotated[int, typer.Option("--min-score", help="Score below this always alerts")] = 80,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Warn when a repo dropped >= threshold points or is below min-score since the last sweep.

    Exits 0 when no alerts, exits 1 when alerts are found (CI-friendly).
    """
    history_file = Path.home() / ".mq-agent" / "sweep-history.jsonl"
    if not history_file.exists():
        console.print("[yellow]No sweep history yet.[/yellow]  Run: [bold]mq-agent stack sweep[/bold]")
        return

    sweeps: list[dict] = []
    with history_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    sweeps.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not sweeps:
        console.print("[yellow]History file is empty.[/yellow]  Run: [bold]mq-agent stack sweep[/bold]")
        return

    if len(sweeps) < 2:
        console.print("[yellow]Need at least 2 sweeps to compare.[/yellow]  Run: [bold]mq-agent stack sweep[/bold] again.")
        return

    alerts = _compute_alerts(sweeps, threshold=threshold, min_score=min_score)

    if json_out:
        typer.echo(json.dumps(alerts, indent=2))
        raise typer.Exit(1 if alerts else 0)

    if not alerts:
        console.print("[green]✓ No alerts — all repos healthy or stable.[/green]")
        console.print(f"[dim]Compared: {sweeps[-2]['ts'][:16].replace('T', ' ')} → {sweeps[-1]['ts'][:16].replace('T', ' ')}[/dim]")
        return

    _print_alerts(alerts, sweeps[-2]["ts"], sweeps[-1]["ts"])
    raise typer.Exit(1)


# ── stack release-check ────────────────────────────────────────────────────

@stack_app.command("release-check")
def stack_release_check_cmd(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="CI mode: skip repos missing from the workspace")] = False,
):
    """Run release-readiness checks across all mq-stack repos.

    Checks per repo: VERSION file, CHANGELOG entry, clean working tree,
    on main/master branch. No API key required. Exits 1 on any blocker.
    With --ci, sibling repos missing from the workspace are skipped instead
    of blocking — only repos that are present (e.g. the CI checkout) gate.
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand, _release_entry

    if dry_run:
        console.print("[blue][dry-run][/blue] Would check:")
        for r in MQ_STACK_REPOS:
            p = _expand(r["path"])
            console.print(f"  {r['name']:<18} {'✓' if p.exists() else '✗ (not found)'}")
        return

    with console.status("[cyan]Checking release readiness...[/cyan]"):
        entries = [_release_entry(r, ci=ci) for r in MQ_STACK_REPOS if r["name"] != "mqobsidian"]

    all_go = all(e.get("go", False) for e in entries)

    if json_out:
        typer.echo(json.dumps({
            "overall": "GO" if all_go else "NO-GO",
            "mode": "ci" if ci else "local",
            "repos": entries,
        }, indent=2, default=str))
        raise typer.Exit(0 if all_go else 1)

    table = Table(title="mq-stack Release Check", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column("Version", width=9)
    table.add_column("Branch", width=10)
    table.add_column("Blockers", style="red", width=22)
    table.add_column("Warnings", style="yellow")

    for e in entries:
        if e.get("skipped"):
            table.add_row(e["name"], "—", "—", "", "[dim]skipped (CI)[/dim]")
            continue
        if not e.get("exists", True):
            table.add_row(e["name"], "—", "—", "repo not found", "")
            continue
        branch = e.get("branch", "—")
        branch_str = f"[green]{branch}[/green]" if e.get("on_main") else f"[yellow]{branch}[/yellow]"
        blockers = ", ".join(e.get("blockers", [])) or "[green]none[/green]"
        warnings = ", ".join(e.get("warnings", [])) or "[dim]none[/dim]"
        table.add_row(
            e["name"],
            e.get("version", "?"),
            branch_str,
            blockers,
            warnings,
        )
    console.print(table)

    if all_go:
        console.print("\n[bold green]✓ All repos clear — stack is GO.[/bold green]")
    else:
        blocked = [e["name"] for e in entries if not e.get("go", False)]
        console.print(f"\n[bold red]✗ NO-GO — blocked: {', '.join(blocked)}[/bold red]")
        raise typer.Exit(1)


# ── stack release-notes ────────────────────────────────────────────────────

@stack_app.command("release-notes")
def stack_release_notes_cmd(
    repo_filter: Annotated[str | None, typer.Option("--repo", help="Limit to one repo")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Draft release notes from git commits since the last tag, per repo.

    Reads git log since last tag for each mq-stack repo.
    No API key required. Always exits 0 (informational).
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _release_notes_entry

    repos = [r for r in MQ_STACK_REPOS if r["name"] != "mqobsidian"]
    if repo_filter:
        repos = [r for r in repos if r["name"] == repo_filter]
        if not repos:
            console.print(f"[red]Repo '{repo_filter}' not found in stack.[/red]")
            raise typer.Exit(1)

    with console.status("[cyan]Reading git history...[/cyan]"):
        entries = [_release_notes_entry(r) for r in repos]

    if json_out:
        typer.echo(json.dumps(entries, indent=2, default=str))
        return

    has_any = any(e.get("has_changes") for e in entries)
    console.print()
    console.rule("[bold]mq-stack Release Notes[/bold]")
    console.print()

    for e in entries:
        if not e.get("exists"):
            console.print(f"[dim]{e['name']:<18}  not found locally[/dim]")
            console.print()
            continue

        last_tag = e.get("last_tag") or "—"
        version = e.get("version", "?")
        since = f"since {last_tag}" if last_tag else "all commits (no tag)"
        console.print(f"[cyan bold]{e['name']}[/cyan bold]  [dim]v{version}  ({since})[/dim]")

        commits = e.get("commits", [])
        if commits:
            for c in commits:
                console.print(f"  [dim]•[/dim] {c}")
        else:
            console.print("  [dim]no unreleased commits[/dim]")
        console.print()

    if not has_any:
        console.print("[green]✓ All repos are up to date — no unreleased commits.[/green]")


# ── stack contract-check ───────────────────────────────────────────────────

@stack_app.command("contract-check")
def stack_contract_check_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="CI mode: skip repos missing from the workspace")] = False,
):
    """Validate that every mq-stack repo declares a contract manifest.

    Reads .mq/repo-contract.json per repo and checks VERSION sync.
    No API key required. Exits 1 if any repo is BLOCKED or DRIFT.
    With --ci, repos missing from the workspace are SKIPPED instead of
    BLOCKED — the CI checkout itself is still fully validated.
    """
    from mq_agent.tools.stack_tools import stack_contract_check as _check

    with console.status("[cyan]Reading contract manifests...[/cyan]"):
        raw = _check(ci=ci)

    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        raise typer.Exit(0 if data["overall"] == "READY" else 1)

    _STATUS = {
        "READY":   "[green]READY[/green]",
        "REVIEW":  "[yellow]REVIEW[/yellow]",
        "DRIFT":   "[red]DRIFT[/red]",
        "BLOCKED": "[bold red]BLOCKED[/bold red]",
        "SKIPPED": "[dim]SKIPPED[/dim]",
    }

    console.print()
    console.rule("[bold]MQ Stack Contract Gate[/bold]")
    console.print()

    for e in data["repos"]:
        status_str = _STATUS.get(e["status"], e["status"])
        reason = f"  [dim]{e['reason']}[/dim]" if e.get("reason") else ""
        console.print(f"  {e['name']:<20} {status_str}{reason}")

    console.print()
    if data["overall"] == "READY":
        console.print("[bold green]✓ Stack contract: READY[/bold green]")
    else:
        console.print("[bold red]✗ Stack contract: NOT READY[/bold red]")
        for r in data.get("reasons", []):
            console.print(f"  [red]→[/red] {r}")
        raise typer.Exit(1)


# ── stack release ──────────────────────────────────────────────────────────

@stack_app.command("release")
def stack_release_cmd(
    repo: Annotated[str, typer.Option("--repo", help="Stack repo to release")],
    bump: Annotated[str, typer.Option("--bump", help="Version bump: patch, minor or major")] = "patch",
    version: Annotated[str, typer.Option("--version", help="Explicit target version (overrides --bump)")] = "",
    execute: Annotated[bool, typer.Option("--execute", help="Apply the release (default is dry-run)")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Orchestrated single-repo release: gate, bump, changelog, tag, push, truth-export.

    Dry-run by default — shows the plan without touching the repo. With
    --execute the plan is applied step by step; any failed step aborts the
    run and pre-commit file edits are rolled back. Exits 1 on NO-GO or on a
    failed step. Ends with a stack truth-export so the release lands in
    mqobsidian memory.
    """
    from mq_agent.tools.stack_release import BUMP_PARTS, stack_release as _release

    if bump not in BUMP_PARTS:
        console.print(f"[red]Invalid --bump {bump!r} — expected one of: {', '.join(BUMP_PARTS)}[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Planning release...[/cyan]" if not execute else "[cyan]Releasing...[/cyan]"):
        raw = _release(repo, bump=bump, version=version, execute=execute)
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        ok = data.get("go", False) if not execute else data.get("ok", False)
        raise typer.Exit(0 if ok else 1)

    console.print()
    console.rule(f"[bold]Stack Release — {repo}[/bold]")
    console.print()

    if not execute:
        if not data.get("go"):
            console.print(f"[bold red]✗ NO-GO — {repo} cannot be released:[/bold red]")
            for b in data.get("blockers", []):
                console.print(f"  [red]→[/red] {b}")
            raise typer.Exit(1)
        console.print(f"[blue]dry-run:[/blue] {data['current_version']} → [bold]{data['new_version']}[/bold]  (tag {data['tag']})")
        console.print()
        for s in data.get("steps", []):
            console.print(f"  [dim]•[/dim] {s['step']:<18} {s.get('detail', '')}")
        for w in data.get("warnings", []):
            console.print(f"  [yellow]⚠ {w}[/yellow]")
        console.print("\n[dim]Run again with --execute to apply.[/dim]")
        return

    _STEP = {"done": "[green]done[/green]", "failed": "[bold red]failed[/bold red]", "aborted": "[dim]aborted[/dim]"}
    for s in data.get("steps", []):
        status_str = _STEP.get(s["status"], s["status"])
        detail = f"  [dim]{s['detail']}[/dim]" if s.get("detail") else ""
        console.print(f"  {s['step']:<18} {status_str}{detail}")
    console.print()

    if data.get("ok"):
        console.print(f"[bold green]✓ Released {repo} {data['tag']}[/bold green]  [dim]truth note: {data.get('truth_note', '—')}[/dim]")
    elif data.get("released"):
        console.print(f"[yellow]⚠ Released {repo} {data['tag']}, but: {data.get('warning')}[/yellow]")
        raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Release aborted — {data.get('error', 'unknown error')}[/bold red]")
        if data.get("blockers"):
            for b in data["blockers"]:
                console.print(f"  [red]→[/red] {b}")
        if data.get("rolled_back"):
            console.print(f"  [dim]rolled back: {', '.join(data['rolled_back'])}[/dim]")
        raise typer.Exit(1)


@stack_app.command("cockpit")
def stack_cockpit_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """One-table stack cockpit: repo, version, branch, dirty, contract,
    release gate, unreleased work, brain-export freshness and next action.

    Read-only — combines stack status, contract-check, release-check and
    the latest mqobsidian stack-truth note into a single view. Later the
    input to mq-hal.
    """
    from mq_agent.tools.stack_cockpit import stack_cockpit as _cockpit

    with console.status("[cyan]Assembling stack cockpit...[/cyan]"):
        raw = _cockpit()
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        return

    console.print()
    console.rule("[bold]mq-stack Cockpit[/bold]")
    console.print()

    table = Table(show_header=True)
    table.add_column("Repo", style="cyan", no_wrap=True)
    table.add_column("Version", no_wrap=True)
    table.add_column("Branch", no_wrap=True, max_width=14)
    table.add_column("Dirty", no_wrap=True)
    table.add_column("Contract", no_wrap=True)
    table.add_column("Gate", no_wrap=True)
    table.add_column("Next action", style="dim")

    _CONTRACT_STYLE = {"READY": "green", "REVIEW": "yellow", "DRIFT": "red", "BLOCKED": "red"}
    for r in data["repos"]:
        c_style = _CONTRACT_STYLE.get(r["contract"], "")
        table.add_row(
            r["repo"],
            r["version"],
            r["branch"],
            "[yellow]yes[/yellow]" if r["dirty"] else "no",
            f"[{c_style}]{r['contract']}[/{c_style}]" if c_style else r["contract"],
            "[green]GO[/green]" if r["gate"] == "GO" else ("[red]NO-GO[/red]" if r["gate"] == "NO-GO" else r["gate"]),
            r["next_action"][:60],
        )
    console.print(table)

    brain = data["brain_export"]
    _BRAIN_STYLE = {"fresh": "green", "aging": "yellow", "stale": "red", "none": "red"}
    b_style = _BRAIN_STYLE.get(brain["status"], "")
    brain_str = f"{brain['date'] or '—'} ([{b_style}]{brain['status']}[/{b_style}])" if b_style else "—"
    console.print()
    console.print(f"  Release gate: {'[green]GO[/green]' if data['overall_gate'] == 'GO' else '[red]NO-GO[/red]'}"
                  f"   Contract: {'[green]READY[/green]' if data['overall_contract'] == 'READY' else '[red]NOT READY[/red]'}"
                  f"   Brain export: {brain_str}")
    console.print(f"  Next: [bold]{data['next_action']}[/bold]")


def _print_stack_runtime(data: dict[str, Any]) -> None:
    console.print()
    console.rule("[bold]mq-stack Runtime[/bold]")
    console.print()
    for step in data["steps"]:
        mark = "[green]✓[/green]" if step["status"] == "PASS" else "[red]✗[/red]"
        console.print(f"  {mark} [bold]{step['name']:<13}[/bold] {step['detail']}")
        if step.get("hint"):
            console.print(f"      [dim]→ {step['hint']}[/dim]")

    console.print()
    if data["overall"] == "PASS":
        suffix = "  [dim](dry-run)[/dim]" if data["dry_run"] else ""
        console.print(f"  Runtime: [bold green]PASS[/bold green]{suffix}")
    else:
        console.print(f"  Runtime: [bold red]FAIL[/bold red]   Next: [bold]{data['next_action']}[/bold]")


@stack_app.command("run")
def stack_run_cmd(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    markdown: Annotated[bool, typer.Option("--markdown", help="Render the runtime result as Markdown")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Write the stack truth export when combined with --approve")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="CI mode: skip repos missing from the workspace in release gates")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Allow write steps requested by --brain")] = False,
):
    """Run the v1.16 stack runtime gate.

    Checks repo-signal, mq-mcp, Ollama, brain export rendering and release
    readiness in one operator-facing pass. Read-only by default; `--brain`
    writes the truth export only when `--approve` is also supplied.
    """
    from mq_agent.tools.stack_runtime import (
        render_stack_run_markdown,
        stack_run as _stack_run,
    )

    with console.status("[cyan]Running stack runtime...[/cyan]"):
        raw = _stack_run(dry_run=dry_run, brain=brain, ci=ci, approve=approve)
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        raise typer.Exit(0 if data["overall"] == "PASS" else 1)

    if markdown:
        typer.echo(render_stack_run_markdown(data))
        raise typer.Exit(0 if data["overall"] == "PASS" else 1)

    _print_stack_runtime(data)
    if data["overall"] != "PASS":
        raise typer.Exit(1)


@stack_app.command("brain-gate")
def stack_brain_gate_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Brain release gate: contract-check + release-check + truth-export
    dry-run + vault structure + the review→brain write path, all green
    before a release. Read-only; exit 1 on NO-GO.
    """
    from mq_agent.tools.brain_gate import brain_release_gate

    with console.status("[cyan]Running brain release gate...[/cyan]"):
        raw = brain_release_gate()
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        if data["overall"] != "GO":
            raise typer.Exit(code=1)
        return

    console.print()
    console.rule("[bold]Brain release gate[/bold]")
    console.print()
    for check in data["checks"]:
        mark = "[green]✓[/green]" if check["status"] == "PASS" else "[red]✗[/red]"
        console.print(f"  {mark} [bold]{check['name']:<16}[/bold] {check['detail']}")
        if check.get("hint"):
            console.print(f"      [dim]→ {check['hint']}[/dim]")

    console.print()
    if data["overall"] == "GO":
        console.print("  Brain gate: [bold green]GO[/bold green] — all green, release away")
    else:
        console.print(f"  Brain gate: [bold red]NO-GO[/bold red]   Next: [bold]{data['next_action']}[/bold]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
