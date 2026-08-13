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
from mq_agent.workflows.cli import workflow_app

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

app.add_typer(workflow_app, name="workflow")

obsidian_app = typer.Typer(help="Read and action the mqobsidian promotion inbox.")
app.add_typer(obsidian_app, name="obsidian")

obsidian_inbox_app = typer.Typer(help="Read the canonical mqobsidian promotion inbox (read-only).")
obsidian_app.add_typer(obsidian_inbox_app, name="inbox")

agent_views_app = typer.Typer(help="Build compressed agent-view read cards in the mqobsidian vault.")
app.add_typer(agent_views_app, name="agent-views")

context_app = typer.Typer(help="Export compact repo-local .mq/context snapshots.")
app.add_typer(context_app, name="context")

models_app = typer.Typer(help="Ollama model runtime commands.")
app.add_typer(models_app, name="models")

route_app = typer.Typer(help="Inspect advisory local-first model routing.")
app.add_typer(route_app, name="route")

ship_app = typer.Typer(help="Inspect release state, proof, and audit evidence (read-only).")
app.add_typer(ship_app, name="ship")

console = Console()


def _render_ship(payload: dict[str, Any]) -> None:
    state = payload["state"]
    color = "green" if state in ("PREFLIGHT_READY", "AUDITED") else "yellow"
    if state == "BLOCKED":
        color = "red"
    console.print(Panel(
        f"[bold {color}]{state}[/bold {color}]\n"
        f"Safe to release now: {'yes' if payload['safe_to_release'] else 'no'}\n"
        f"Next: {payload['next_action']['label']}",
        title=f"Release Cockpit — {payload['repo']['name']}",
    ))
    if payload["blockers"]:
        table = Table(title="Blockers", show_header=True)
        table.add_column("Code")
        table.add_column("Explanation")
        for blocker in payload["blockers"]:
            table.add_row(blocker["code"], blocker["message"])
        console.print(table)
    command = payload["next_action"].get("command")
    if command:
        console.print(f"[dim]Command: {command}[/dim]")


def _ship_command(command: str, repo: str, target: str | None, json_out: bool) -> None:
    from mq_agent.tools.release_cockpit import release_cockpit

    payload = release_cockpit(command=command, repo_path=repo, target=target)
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        _render_ship(payload)
    if command == "audit" and payload["state"] != "AUDITED":
        raise typer.Exit(1)


@ship_app.command("status")
def ship_status_cmd(
    repo: Annotated[str, typer.Option("--repo", help="Repository path")] = ".",
    target: Annotated[str | None, typer.Option("--target", help="Target version without v prefix")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Answer whether the selected repository can be released safely now."""
    _ship_command("status", repo, target, json_out)


@ship_app.command("proof")
def ship_proof_cmd(
    repo: Annotated[str, typer.Option("--repo", help="Repository path")] = ".",
    target: Annotated[str | None, typer.Option("--target", help="Target version without v prefix")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show bounded release evidence for the current or selected release."""
    _ship_command("proof", repo, target, json_out)


@ship_app.command("audit")
def ship_audit_cmd(
    repo: Annotated[str, typer.Option("--repo", help="Repository path")] = ".",
    target: Annotated[str | None, typer.Option("--target", help="Target version without v prefix")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Audit a published release; exits non-zero unless all evidence passes."""
    _ship_command("audit", repo, target, json_out)


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
            "review_repo failed:",
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
        # A down server and a missing tool need different operator fixes, so the
        # bridge tags the former; the title has to keep them apart too.
        unreachable = isinstance(result, dict) and result.get("reason") == "unreachable"
        title = "mq-mcp not reachable" if unreachable else "mq-mcp review unavailable"
        console.print(Panel(message, title=f"[bold red]{title}[/bold red]", border_style="red"))
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
    repo: Annotated[str | None, typer.Option("--repo", help="External repo path the file lives in (within mq-mcp allowlist)")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review one file through mq-mcp. mq-agent does not implement review logic."""
    if dry_run:
        enabled_flags = [f for f, v in _review_flags(security, architecture or bool(architecture_image), risk, fast).items() if v]
        flag_str = " ".join(f"--{f}" for f in enabled_flags)
        repo_str = f" repo_path={repo}" if repo else ""
        console.print(f"[blue][dry-run][/blue] Would call: [bold]mq-mcp review_file {path}{repo_str}{' ' + flag_str if flag_str else ''}[/bold]")
        if architecture_image:
            console.print(f"[blue][dry-run][/blue] Would first call: [bold]mq-image-analyze observe_architecture image_path={architecture_image}[/bold]")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    flags = _review_flags_with_visual_context(bridge, security, architecture, risk, fast, architecture_image)
    if _is_error_result(flags):
        _run_review("review file", flags, json_out)
        return
    result = bridge.review_file(path, flags, repo_path=repo)
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
    repo: Annotated[str | None, typer.Option("--repo", help="External repo path the file lives in (within mq-mcp allowlist)")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record learn candidate to mqobsidian")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Dry-run extraction of a learn candidate from the last review for a file. Read-only."""
    if dry_run:
        repo_str = f" repo_path={repo}" if repo else ""
        console.print(f"[blue]dry-run:[/blue] Would call: [bold]mq-mcp learn_extract_from_last_review {path}{repo_str}[/bold]")
        if brain:
            console.print("[blue]dry-run:[/blue] With --brain: would write a learn note to mqobsidian")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    result = bridge.learn_extract_from_last_review(path, repo_path=repo)

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
    repo: Annotated[str | None, typer.Option("--repo", help="External repo path the file lives in (within mq-mcp allowlist)")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    brain: Annotated[bool, typer.Option("--brain", help="Record learn candidate to mqobsidian")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be called, no execution")] = False,
):
    """Review a file then extract a dry-run learn candidate in one pass. Read-only."""
    if dry_run:
        repo_str = f" repo_path={repo}" if repo else ""
        console.print(f"[blue]dry-run:[/blue] Would call: [bold]mq-mcp review_file {path}{repo_str}[/bold]")
        console.print(f"[blue]dry-run:[/blue] Then: [bold]mq-mcp learn_extract_from_last_review {path}{repo_str}[/bold]")
        if brain:
            console.print("[blue]dry-run:[/blue] With --brain: would write a learn note to mqobsidian")
        return
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    review_result = bridge.review_file(path, {}, repo_path=repo)
    extract_result = bridge.learn_extract_from_last_review(path, repo_path=repo)

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
    repo: Annotated[str | None, typer.Option("--repo", help="External repo path the file lives in (within mq-mcp allowlist)")] = None,
    approve: Annotated[bool, typer.Option("--approve", help="Allow write to mq-mcp learn layer")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Create a learning record from the last review for a file. Class C write — requires --approve."""
    if dry_run:
        repo_str = f" repo_path={repo}" if repo else ""
        console.print(
            f"[blue][dry-run][/blue] Would call: [bold]mq-mcp learn_from_review relative_path={path}{repo_str}"
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

    result = MultiMCPBridge().learn_from_review(path, task=task, risk=risk, repo_path=repo)

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

@app.command(name="dashboard")
def dashboard_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show the v1.19 operator dashboard snapshot."""
    from mq_agent.tools.operator_dashboard import operator_dashboard

    with console.status("[cyan]Assembling operator dashboard...[/cyan]"):
        raw = operator_dashboard()
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        return

    status = "[green]READY[/green]" if data["overall"] == "READY" else "[yellow]ATTENTION[/yellow]"
    console.print()
    console.rule("[bold]mq-agent Operator Dashboard[/bold]")
    console.print()
    console.print(f"  Overall: {status}   Next: [bold]{data['next_action']}[/bold]")
    console.print()

    table = Table(show_header=True)
    table.add_column("Area", style="cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail")

    stack = data["stack"]
    stack_status = "[green]GO[/green]" if stack["gate"] == "GO" else "[red]NO-GO[/red]"
    table.add_row(
        "Stack",
        stack_status,
        f"{stack['repo_count']} repos, {stack['actionable_count']} action(s), {stack['dirty_count']} dirty",
    )

    contract_status = "[green]READY[/green]" if stack["contract"] == "READY" else "[red]NOT READY[/red]"
    table.add_row("Contracts", contract_status, ", ".join(f"{k}={v}" for k, v in sorted(data["contracts"].items())))

    compat = data.get("compatibility")
    if compat:
        compat_style = {
            "PASS": "green", "WARN": "yellow", "FAIL": "red",
            "SKIPPED": "dim", "UNAVAILABLE": "dim",
        }.get(compat["status"], "dim")
        blocking = compat["blocking_count"]
        table.add_row(
            "Compatibility",
            f"[{compat_style}]{compat['status']}[/{compat_style}]",
            f"{blocking} release blocker(s), {compat['mode']} check",
        )

    brain = data["brain"]
    brain_style = {"fresh": "green", "aging": "yellow", "stale": "red", "none": "red"}.get(brain.get("status"), "dim")
    table.add_row("Brain", f"[{brain_style}]{brain.get('status', 'unknown')}[/{brain_style}]", brain.get("path") or "no stack-truth note")

    ollama = data["ollama"]
    table.add_row(
        "Ollama",
        "[green]OK[/green]" if ollama["ok"] else "[yellow]CHECK[/yellow]",
        f"{ollama['profile']} → {ollama['model']} ({len(ollama['models'])} local model(s))",
    )

    console.print(table)


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

    # Neither mq-mcp nor the bridge raises on failure: a failed tool comes back
    # as the string "<tool> failed: <exc>", and transport problems come back as
    # text too. Printing the result and returning implicitly made every one of
    # those exit 0 — `mqlaunch repo-health` reported "Blocked path outside
    # allowed roots" and told its caller the run succeeded.
    from mq_agent.tools.mcp_bridge import tool_failure
    failure = tool_failure(tool, result)

    if json_out:
        # The document still prints. A caller that asked for JSON needs the
        # payload; the exit status is what tells it the run failed, and that
        # caller is the one least able to notice a message in a panel.
        if isinstance(result, str):
            typer.echo(json.dumps({"tool": tool, "source": spec.source, "result": result}))
        else:
            typer.echo(json.dumps({"tool": tool, "source": spec.source, "result": result}, indent=2))
        if failure:
            raise typer.Exit(code=1)
        return

    if isinstance(result, (dict, list)):
        import pprint
        console.print(Panel(pprint.pformat(result, width=80), title=f"[bold]{tool} ({spec.source})[/bold]"))
    else:
        console.print(Panel(str(result), title=f"[bold]{tool} ({spec.source})[/bold]"))

    if failure:
        raise typer.Exit(code=1)


# ── memory engine ──────────────────────────────────────────────────────────

@memory_app.command("ingest")
def memory_ingest_cmd(
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Scan mqobsidian memory notes into a local read-only index."""
    from mq_agent.tools.memory_engine import memory_ingest

    data = json.loads(memory_ingest(vault))
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["status"] == "OK" else 1)

    if data["status"] != "OK":
        console.print(f"[red]Vault not found:[/red] {data['vault']}")
        raise typer.Exit(1)

    table = Table(title="mqobsidian memory ingest", show_header=True, header_style="bold")
    table.add_column("Section")
    table.add_column("Notes", justify="right")
    for section, count in data["summary"]["sections"].items():
        table.add_row(section, str(count))
    console.print(table)
    console.print(f"[green]OK[/green] {data['summary']['total_notes']} notes indexed from {data['vault']}")


@memory_app.command("emit-cochange")
def memory_emit_cochange_cmd(
    repo: Annotated[str, typer.Argument(help="Path to the repo to analyze")],
    file: Annotated[str, typer.Argument(help="File to find co-change clusters for")],
    window: Annotated[int, typer.Option("--window", help="Commits to scan")] = 300,
    min_confidence: Annotated[float, typer.Option("--min-confidence", help="Cluster confidence gate (weak-signal intake; default low)")] = 0.05,
    min_support: Annotated[int, typer.Option("--min-support", help="Min co-change count")] = 2,
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path")] = None,
):
    """Emit one co-change memory-observation.v1 from Bridget/CG-2 evidence.

    mq-agent is the producer; Bridget/CG-2 is the evidence source. Writes nothing
    when no co-change cluster clears the gate. mqobsidian scores and promotes.
    """
    from mq_agent.memory.cochange_observation import emit_cochange

    path = emit_cochange(
        repo,
        file,
        window=window,
        min_confidence=min_confidence,
        min_support=min_support,
        vault=Path(vault).expanduser() if vault else None,
    )
    if path is None:
        console.print(
            "[yellow]No co-change cluster strong enough to emit[/yellow] "
            "(or co-change unavailable)."
        )
        raise typer.Exit(0)
    console.print(f"[green]OK[/green] emitted co-change observation -> {path}")


@memory_app.command("inbox-cochange")
def memory_inbox_cochange_cmd(
    repo: Annotated[str, typer.Argument(help="Path to the repo to analyze")],
    file: Annotated[str, typer.Argument(help="File to find co-change clusters for")],
    window: Annotated[int, typer.Option("--window", help="Commits to scan")] = 300,
    min_confidence: Annotated[float, typer.Option("--min-confidence", help="Cluster confidence gate (weak-signal intake)")] = 0.05,
    min_support: Annotated[int, typer.Option("--min-support", help="Min co-change count")] = 2,
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path (or $MQ_OBSIDIAN_DIR)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Write nothing; show what would happen")] = False,
    no_writeback: Annotated[bool, typer.Option("--no-writeback", help="Score but do not write learn files")] = False,
):
    """Operator-triggered co-change intake: emit → score → writeback → status.

    Runs the autonomous learning loop end-to-end for one file, but only when you ask
    (not auto-after-workflow). mq-agent orchestrates; Bridget/CG-2 is evidence source;
    mqobsidian owns scoring/writeback/status (invoked via its own local-only CLI).
    """
    from mq_agent.memory.inbox_pipeline import run_pipeline

    result = run_pipeline(
        repo, file,
        window=window, min_confidence=min_confidence, min_support=min_support,
        vault=vault, dry_run=dry_run, no_writeback=no_writeback,
    )

    mode = "  (dry-run — nothing written)" if dry_run else ""
    console.print(f"[bold]MQ memory co-change intake[/bold]{mode}")
    console.print(f"vault: {result['vault']}")
    console.print()

    ev = result["evidence"]
    if ev["found"]:
        console.print(f"1. Bridget/CG-2 evidence: [green]found[/green] run_id {ev['run_id'] or '—'}")
    else:
        console.print("1. Bridget/CG-2 evidence: [yellow]none[/yellow] (co-change unavailable)")

    emit = result["emit"]
    colors = {"emitted": "green", "would-emit": "cyan", "skipped": "yellow", "error": "red"}
    color = colors.get(emit["status"], "white")
    detail = emit["path"] or emit["detail"]
    console.print(f"2. mq-agent observation: [{color}]{emit['status']}[/{color}] {detail}")

    def _stage(n: int, label: str, stage: dict) -> None:
        if stage.get("skipped"):
            console.print(f"{n}. {label}: [yellow]skipped[/yellow] ({stage['skipped']})")
            return
        tag = "[green]ok[/green]" if stage["ok"] else f"[red]failed rc={stage['rc']}[/red]"
        console.print(f"{n}. {label}: {tag}")
        for line in (stage["stdout"] or stage["stderr"]).splitlines():
            console.print(f"     {line}")

    _stage(3, "mqobsidian scoring", result["score"])
    _stage(4, "learn-writeback", result["writeback"])
    _stage(5, "memory status", result["status"])

    raise typer.Exit(0 if result["ok"] else 1)


def _print_delegated(title: str, result: dict) -> None:
    """Render a delegated mqobsidian-CLI result. mq-agent orchestrates; the body is the
    sub-CLI's own output, verbatim."""
    tag = "[green]ok[/green]" if result["ok"] else f"[red]failed rc={result['rc']}[/red]"
    console.print(f"[bold]{title}[/bold] {tag}")
    console.print(f"vault: {result['vault']}")
    for line in (result["stdout"] or result["stderr"]).splitlines():
        console.print(f"  {line}")


# --- obsidian inbox surface (v1.22 Task 10) --------------------------------------
# The stable, machine-readable surface mqlaunch delegates to. Ranking and promotion
# logic stay in mq_agent.memory.inbox_pipeline; these commands only route. The
# mutations are five named verbs, never a generic passthrough, and every one of
# them previews unless the operator passes --confirm.

_VAULT_OPT = typer.Option("--vault", help="mqobsidian vault path (or $MQ_OBSIDIAN_DIR)")


def _obsidian_read(fn, as_json: bool, title: str):
    """Run a read against canonical exports, failing closed on any contract error."""
    from mq_agent.memory.inbox_pipeline import ExportContractError

    try:
        payload = fn()
    except ExportContractError as exc:
        # --json must stay parseable even when failing, or mqlaunch cannot tell a
        # contract error from a crash.
        if as_json:
            console.print_json(json.dumps({"ok": False, "error": str(exc)}))
        else:
            console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc
    if as_json:
        console.print_json(json.dumps(payload))
    else:
        console.print(f"[bold]{title}[/bold]")
    return payload


@obsidian_inbox_app.command("list")
def obsidian_inbox_list_cmd(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """List promotion candidates from mqobsidian's canonical inbox export (read-only)."""
    from mq_agent.memory.inbox_pipeline import list_inbox_candidates

    payload = _obsidian_read(lambda: list_inbox_candidates(vault=vault), as_json, "MQ obsidian inbox")
    if not as_json:
        console.print(f"candidates: {payload['count']}")
        for item in payload["candidates"]:
            console.print(f"  {item['state']:<10} {item['id']}", soft_wrap=True)
    raise typer.Exit(0)


@obsidian_inbox_app.command("read")
def obsidian_inbox_read_cmd(
    memory_id: Annotated[str, typer.Argument(help="Candidate memory_id")],
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Read one promotion candidate. Exits 1 when the candidate is not in the inbox."""
    from mq_agent.memory.inbox_pipeline import read_inbox_candidate

    payload = _obsidian_read(
        lambda: read_inbox_candidate(memory_id, vault=vault), as_json, "MQ obsidian inbox read"
    )
    if not as_json:
        console.print(json.dumps(payload["candidate"], indent=2) if payload["found"]
                      else f"not in inbox: {memory_id}")
    raise typer.Exit(0 if payload["found"] else 1)


@obsidian_inbox_app.command("rank")
def obsidian_inbox_rank_cmd(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Rank candidates under mqobsidian's promotion policy (inbox_promotion_orchestration.v1).

    `auto-promotable` means eligible for approval — never an unattended write.
    """
    from mq_agent.memory.inbox_pipeline import rank_inbox

    payload = _obsidian_read(lambda: rank_inbox(vault=vault), as_json, "MQ obsidian inbox rank")
    if not as_json:
        counts = payload["counts"]
        console.print(f"inbox: {counts['inbox']}  review-needed: {counts['review-needed']}  "
                      f"auto-promotable: {counts['auto-promotable']}")
        for c in payload["candidates"]:
            reasons = f"  ({', '.join(c['review_reasons'])})" if c["review_reasons"] else ""
            console.print(f"  {c['ranked_score']:>7}  {c['bucket']:<16} {c['memory_id']}{reasons}",
                          soft_wrap=True)
    raise typer.Exit(0)


def _obsidian_transition(verb: str, memory_id: str, reason: str, confirm: bool,
                         vault: str | None, as_json: bool, evidence: list[str] | None = None):
    """Route one transition verb to its delegator. Preview unless --confirm."""
    from mq_agent.memory import inbox_pipeline

    fn = getattr(inbox_pipeline, f"run_{verb}")
    kwargs = {"reason": reason, "apply": confirm, "vault": vault}
    if evidence is not None:
        kwargs["evidence"] = evidence
    result = fn(memory_id, **kwargs)
    if as_json:
        console.print_json(json.dumps(result["result"] if result["result"] is not None
                                      else {"ok": result["ok"], "stderr": result["stderr"]}))
    else:
        _print_delegated(f"MQ obsidian {verb}", result)
    raise typer.Exit(0 if result["ok"] else 1)


@obsidian_app.command("promote")
def obsidian_promote_cmd(
    memory_id: Annotated[str, typer.Argument(help="Candidate memory_id")],
    reason: Annotated[str, typer.Option("--reason", help="Why this promotion is justified")],
    evidence: Annotated[list[str] | None, typer.Option("--evidence", help="Published evidence ref (repeatable)")] = None,
    confirm: Annotated[bool, typer.Option("--confirm", help="Apply the transition (default: dry-run)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Promote a candidate (candidate -> promoted). Requires traceable source evidence."""
    _obsidian_transition("promote", memory_id, reason, confirm, vault, as_json, evidence or [])


@obsidian_app.command("reject")
def obsidian_reject_cmd(
    memory_id: Annotated[str, typer.Argument(help="Candidate memory_id")],
    reason: Annotated[str, typer.Option("--reason", help="Why this candidate is rejected")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Apply the transition (default: dry-run)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Reject a candidate (candidate -> archived). No durable learn record."""
    _obsidian_transition("reject", memory_id, reason, confirm, vault, as_json)


@obsidian_app.command("defer")
def obsidian_defer_cmd(
    memory_id: Annotated[str, typer.Argument(help="Candidate memory_id")],
    reason: Annotated[str, typer.Option("--reason", help="Why this candidate is deferred")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Apply the transition (default: dry-run)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Defer a candidate (candidate -> observed). No durable learn record."""
    _obsidian_transition("defer", memory_id, reason, confirm, vault, as_json)


@obsidian_app.command("rollback")
def obsidian_rollback_cmd(
    memory_id: Annotated[str, typer.Argument(help="Promoted memory_id")],
    reason: Annotated[str, typer.Option("--reason", help="Why this promotion is rolled back")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Apply the transition (default: dry-run)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Roll back a promotion (promoted -> candidate). Removes the generated learn projection."""
    _obsidian_transition("rollback", memory_id, reason, confirm, vault, as_json)


@obsidian_app.command("deprecate")
def obsidian_deprecate_cmd(
    memory_id: Annotated[str, typer.Argument(help="Promoted memory_id")],
    reason: Annotated[str, typer.Option("--reason", help="Why this memory is deprecated")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Apply the transition (default: dry-run)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output")] = False,
    vault: Annotated[str | None, _VAULT_OPT] = None,
):
    """Deprecate a promoted memory (promoted -> deprecated). Retains the record."""
    _obsidian_transition("deprecate", memory_id, reason, confirm, vault, as_json)


@memory_app.command("review-status")
def memory_review_status_cmd(
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path (or $MQ_OBSIDIAN_DIR)")] = None,
):
    """Show the mqobsidian scoring review state: tier tally + held review queues (read-only).

    Delegates to mqobsidian's local-only CLI; mq-agent stays the orchestrator so mqlaunch
    never reaches mqobsidian directly.
    """
    from mq_agent.memory.inbox_pipeline import run_review_status

    result = run_review_status(vault=vault)
    _print_delegated("MQ memory review status", result)
    raise typer.Exit(0 if result["ok"] else 1)


@memory_app.command("promote-from-review")
def memory_promote_from_review_cmd(
    memory_id: Annotated[str, typer.Argument(help="memory_id held in the promotion-review queue")],
    apply: Annotated[bool, typer.Option("--apply", help="Persist the promotion (default: dry-run)")] = False,
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path (or $MQ_OBSIDIAN_DIR)")] = None,
):
    """Approve a held promotion-review memory → promote it (co-change never auto-promotes).

    Appends a promotion-event + directive snapshot via mqobsidian's CLI. Dry-run by default.
    """
    from mq_agent.memory.inbox_pipeline import run_promote_from_review

    result = run_promote_from_review(memory_id, apply=apply, vault=vault)
    _print_delegated("MQ memory promote-from-review", result)
    raise typer.Exit(0 if result["ok"] else 1)


@memory_app.command("learn-writeback")
def memory_learn_writeback_cmd(
    apply: Annotated[bool, typer.Option("--apply", help="Persist the writeback (default: dry-run)")] = False,
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path (or $MQ_OBSIDIAN_DIR)")] = None,
):
    """Materialise durable agent-readable memory for PROMOTED memories. Dry-run by default.

    inbox-cochange runs this as stage 4 of intake; this is the same verb standalone,
    for promotions that landed another way. mqobsidian decides what counts as
    promoted — candidate and observed memories are never written.
    """
    from mq_agent.memory.inbox_pipeline import run_learn_writeback

    result = run_learn_writeback(apply=apply, vault=vault)
    _print_delegated("MQ memory learn-writeback", result)
    raise typer.Exit(0 if result["ok"] else 1)


@memory_app.command("resolve-supersede")
def memory_resolve_supersede_cmd(
    memory_id: Annotated[str, typer.Argument(help="memory_id with an open supersede proposal")],
    accept: Annotated[bool, typer.Option("--accept", help="Adopt the new directive as authoritative")] = False,
    reject: Annotated[bool, typer.Option("--reject", help="Keep the promoted directive; dismiss the conflict")] = False,
    apply: Annotated[bool, typer.Option("--apply", help="Persist the resolution (default: dry-run)")] = False,
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path (or $MQ_OBSIDIAN_DIR)")] = None,
):
    """Accept or reject a deep-conflict supersede proposal (exactly one of --accept/--reject)."""
    if accept == reject:
        console.print("[red]error:[/red] pass exactly one of --accept or --reject")
        raise typer.Exit(2)
    from mq_agent.memory.inbox_pipeline import run_resolve_supersede

    result = run_resolve_supersede(memory_id, accept=accept, apply=apply, vault=vault)
    _print_delegated("MQ memory resolve-supersede", result)
    raise typer.Exit(0 if result["ok"] else 1)


@memory_app.command("query")
@memory_app.command("search-vault")
def memory_query_cmd(
    query: Annotated[str, typer.Argument(help="Search query")],
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=50)] = 10,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Search mqobsidian memory notes. Alias: search-vault."""
    from mq_agent.tools.memory_engine import memory_search

    data = json.loads(memory_search(query, vault, limit=limit))
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["status"] == "OK" else 1)

    if data["status"] != "OK":
        console.print(f"[red]Vault not found:[/red] {data['vault']}")
        raise typer.Exit(1)
    if not data["results"]:
        console.print(Panel(f"No mqobsidian memory results for: [bold]{query}[/bold]", border_style="dim"))
        return

    table = Table(title=f"mqobsidian memory: {query}", show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Section")
    table.add_column("Note")
    table.add_column("Excerpt")
    for item in data["results"]:
        table.add_row(str(item["score"]), item["section"], item["path"], item["excerpt"][:100])
    console.print(table)


@memory_app.command("summarize")
def memory_summarize_cmd(
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Summarize mqobsidian memory by section."""
    from mq_agent.tools.memory_engine import memory_summarize

    data = json.loads(memory_summarize(vault))
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["status"] == "OK" else 1)

    if data["status"] != "OK":
        console.print(f"[red]Vault not found:[/red] {data['vault']}")
        raise typer.Exit(1)

    table = Table(title="mqobsidian memory summary", show_header=True, header_style="bold")
    table.add_column("Section")
    table.add_column("Notes", justify="right")
    table.add_column("Words", justify="right")
    table.add_column("Top tags")
    for section, entry in data["sections"].items():
        table.add_row(section, str(entry["notes"]), str(entry["words"]), ", ".join(entry["top_tags"][:5]))
    console.print(table)


@memory_app.command("link")
def memory_link_cmd(
    vault: Annotated[str | None, typer.Option("--vault", help="mqobsidian vault path")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=50)] = 20,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Infer read-only link candidates between mqobsidian notes."""
    from mq_agent.tools.memory_engine import memory_link

    data = json.loads(memory_link(vault, limit=limit))
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["status"] == "OK" else 1)

    if data["status"] != "OK":
        console.print(f"[red]Vault not found:[/red] {data['vault']}")
        raise typer.Exit(1)
    if not data["links"]:
        console.print(Panel("No link candidates found.", border_style="dim"))
        return

    table = Table(title="mqobsidian memory link candidates", show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Source")
    table.add_column("Target")
    table.add_column("Shared tags")
    for item in data["links"]:
        table.add_row(str(item["score"]), item["source"], item["target"], ", ".join(item["shared_tags"]))
    console.print(table)


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


# ── agent-views rebuild ──────────────────────────────────────────────────────

@agent_views_app.command("rebuild")
def agent_views_rebuild_cmd(
    vault: Annotated[str, typer.Option("--vault", help="mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian)")] = "",
    system: Annotated[str, typer.Option("--system", help="Rebuild only this system's view (default: all)")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without writing")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Rebuild compressed agent views from each system's hot.md + index.md.

    Writes ``memory/learn/agent/<system>.md`` (read-order step 0). Pure
    extraction — never edits the curated hot.md/index.md source, and only writes
    inside the agent-views directory. Skips systems with no hot.md/index.md.
    With ``--system`` rebuilds only that one system (the surgical trigger a
    hot/index refresh runs after editing a single system).
    See docs/AGENT_VIEW_CONTRACT.md.
    """
    from mq_agent.tools.agent_views import rebuild_agent_views

    vault_path = Path(vault).expanduser() if vault else None
    report = rebuild_agent_views(vault=vault_path, dry_run=dry_run, system=system or None)

    if json_out:
        typer.echo(json.dumps(report, indent=2, default=str))
        raise typer.Exit(1 if report["errors"] else 0)

    tag = "[blue](dry-run)[/blue] " if dry_run else ""
    console.rule("[bold]agent views[/bold]")
    console.print(f"{tag}vault: {report['vault']}")
    written, updated = report["views_written"], report["views_updated"]
    verb = "Would write" if dry_run else "Wrote"
    if written:
        console.print(f"[green]{verb}:[/green] " + ", ".join(written))
    if updated:
        console.print(f"[green]{'Would update' if dry_run else 'Updated'}:[/green] " + ", ".join(updated))
    if report["views_unchanged"]:
        console.print("[dim]unchanged:[/dim] " + ", ".join(report["views_unchanged"]))
    for name in report["views_skipped_no_source"]:
        console.print(f"[yellow]skip {name}[/yellow] (no hot.md/index.md to compress)")
    for err in report["errors"]:
        console.print(f"[bold red]error:[/bold red] {err}")
    console.print(
        f"\nchecked: {report['repos_checked']}  "
        f"written: {len(written)}  updated: {len(updated)}  "
        f"unchanged: {len(report['views_unchanged'])}  "
        f"skipped: {len(report['views_skipped_no_source'])}"
    )
    if report["errors"]:
        raise typer.Exit(1)


# ── agent-views check (drift guard) ──────────────────────────────────────────

@agent_views_app.command("check")
def agent_views_check_cmd(
    vault: Annotated[str, typer.Option("--vault", help="mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian)")] = "",
    system: Annotated[str, typer.Option("--system", help="Check only this system's view (default: all)")] = "",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Report agent views that are stale vs their hot.md/index.md source.

    Drift guard: rebuilds in dry-run and flags any view that would be written or
    updated. Writes nothing; exits non-zero if any view is stale or errored
    (CI-friendly). This is what makes the per-system trigger trustworthy — and
    the precondition for ever defaulting the rebuild on.
    See docs/AGENT_VIEW_CONTRACT.md.
    """
    from mq_agent.tools.agent_views import rebuild_agent_views

    vault_path = Path(vault).expanduser() if vault else None
    report = rebuild_agent_views(vault=vault_path, dry_run=True, system=system or None)
    stale = report["views_written"] + report["views_updated"]
    drifted = bool(stale) or bool(report["errors"])

    if json_out:
        typer.echo(json.dumps(
            {
                "vault": report["vault"],
                "system": report["system"],
                "stale": stale,
                "fresh": report["views_unchanged"],
                "skipped_no_source": report["views_skipped_no_source"],
                "errors": report["errors"],
            },
            indent=2,
            default=str,
        ))
        raise typer.Exit(1 if drifted else 0)

    console.rule("[bold]agent views — drift check[/bold]")
    console.print(f"vault: {report['vault']}")
    if stale:
        console.print("[bold red]stale:[/bold red] " + ", ".join(stale))
        console.print("[dim]run `mq-agent agent-views rebuild` to refresh.[/dim]")
    if report["views_unchanged"]:
        console.print("[green]fresh:[/green] " + ", ".join(report["views_unchanged"]))
    for name in report["views_skipped_no_source"]:
        console.print(f"[yellow]skip {name}[/yellow] (no hot.md/index.md to compress)")
    for err in report["errors"]:
        console.print(f"[bold red]error:[/bold red] {err}")
    if not drifted:
        console.print("\n[bold green]all views in sync with source.[/bold green]")
    raise typer.Exit(1 if drifted else 0)


# ── context export ───────────────────────────────────────────────────────────

@context_app.command("export")
def context_export_cmd(
    repo: Annotated[str, typer.Option("--repo", help="Repo name to export")] = "",
    all_repos: Annotated[bool, typer.Option("--all", help="Export all core MQ repos")] = False,
    vault: Annotated[str, typer.Option("--vault", help="mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian)")] = "",
    output_root: Annotated[str, typer.Option("--output-root", help="Repo root containing <repo>/ directories (default: ~)")] = "",
    target: Annotated[str, typer.Option("--target", help="Compatibility flag for roadmap command shape: codex, claude, or both")] = "both",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be written without writing")] = False,
    clean: Annotated[bool, typer.Option("--clean", help="Replace existing generated context directory before writing")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Export small `.mq/context/` snapshots from mqobsidian context cards.

    This is Phase 4 orchestration: mqobsidian owns the card content; mq-agent
    selects repos and writes repo-local context files. Use `--output-root` for
    staging/tests before writing into real sibling repos.
    """
    from mq_agent.tools.context_export import CORE_MQ_REPOS, export_repo_contexts

    if target not in {"codex", "claude", "both"}:
        console.print("[bold red]target must be codex, claude, or both[/bold red]")
        raise typer.Exit(2)
    if all_repos and repo:
        console.print("[bold red]Use either --repo or --all, not both.[/bold red]")
        raise typer.Exit(2)
    if not all_repos and not repo:
        console.print("[bold red]Provide --repo or --all.[/bold red]")
        raise typer.Exit(2)

    repos = CORE_MQ_REPOS if all_repos else [repo]
    report = export_repo_contexts(
        repos=repos,
        vault=Path(vault).expanduser() if vault else None,
        output_root=Path(output_root).expanduser() if output_root else None,
        dry_run=dry_run,
        clean=clean,
    )
    report["target"] = target

    if json_out:
        typer.echo(json.dumps(report, indent=2, default=str))
        raise typer.Exit(1 if report["errors"] else 0)

    tag = "[blue](dry-run)[/blue] " if dry_run else ""
    console.rule("[bold]context export[/bold]")
    console.print(f"{tag}target: {target}")
    for item in report["results"]:
        changed = item["would_write"] if dry_run else item["written"]
        console.print(f"[bold]{item['repo']}[/bold] -> {item['context_dir']}")
        if changed:
            console.print(f"  {'would write' if dry_run else 'wrote'}: {len(changed)} file(s)")
        if item["unchanged"]:
            console.print(f"  unchanged: {len(item['unchanged'])} file(s)")
    for err in report["errors"]:
        console.print(f"[bold red]error:[/bold red] {err}")
    if report["errors"]:
        raise typer.Exit(1)


# ── context pack (task-specific, Phase 5) ──────────────────────────────────────

@context_app.command("pack")
def context_pack_cmd(
    task: Annotated[str, typer.Argument(help="Short task description")],
    repo: Annotated[str, typer.Option("--repo", help="Primary repo for the task")] = "",
    relevant_repo: Annotated[list[str], typer.Option("--relevant-repo", help="Extra relevant repo (repeatable)")] = [],
    relevant_file: Annotated[list[str], typer.Option("--relevant-file", help="Extra relevant file/doc path (repeatable)")] = [],
    note: Annotated[list[str], typer.Option("--note", help="Extra operator note (repeatable)")] = [],
    exclude: Annotated[list[str], typer.Option("--exclude", help="Negative context as `kind:item[:reason]` where kind is forbidden|fallback|irrelevant (repeatable)")] = [],
    target: Annotated[str, typer.Option("--target", help="codex, claude, or both")] = "both",
    vault: Annotated[str, typer.Option("--vault", help="mqobsidian vault path (default: $MQ_OBSIDIAN_DIR or ~/mqobsidian)")] = "",
    repos_root: Annotated[str, typer.Option("--repos-root", help="Root holding <repo>/ dirs, used to detect .codegraph/ (default: ~)")] = "",
    codegraph: Annotated[str, typer.Option("--codegraph", help="CodeGraph hint: auto (source-heavy only), on, or off")] = "auto",
    symbol: Annotated[list[str], typer.Option("--symbol", help="Named symbol for a CodeGraph callers/impact query (repeatable)")] = [],
    output: Annotated[str, typer.Option("--output", "--out", help="Write the pack here instead of stdout")] = "",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Generate a small task-specific `context-pack.v1` pack from mqobsidian cards.

    Phase 5 orchestration: mqobsidian owns the durable cards and the pack
    contract; mq-agent selects the relevant repos, cards, and do-not-read
    guidance for one task and adds an optional CodeGraph source-intelligence
    hint when the task is source-structure heavy.
    """
    from mq_agent.tools.context_pack import EXCLUSION_KINDS, build_task_pack, write_task_pack

    if target not in {"codex", "claude", "both"}:
        console.print("[bold red]target must be codex, claude, or both[/bold red]")
        raise typer.Exit(2)
    if codegraph not in {"auto", "on", "off"}:
        console.print("[bold red]codegraph must be auto, on, or off[/bold red]")
        raise typer.Exit(2)

    parsed_exclusions: list[dict[str, str]] = []
    for raw in exclude:
        kind, _, rest = raw.partition(":")
        kind = kind.strip()
        if kind not in EXCLUSION_KINDS or not rest.strip():
            console.print(
                f"[bold red]--exclude must be `kind:item[:reason]` with kind in "
                f"{', '.join(EXCLUSION_KINDS)} (got: {raw!r})[/bold red]"
            )
            raise typer.Exit(2)
        item, _, reason = rest.partition(":")
        parsed_exclusions.append(
            {"kind": kind, "item": item.strip(), "reason": reason.strip()}
        )

    result = build_task_pack(
        task,
        target=target,
        repo=repo or None,
        relevant_repos=relevant_repo,
        relevant_files=relevant_file,
        notes=note,
        exclusions=parsed_exclusions,
        vault=Path(vault).expanduser() if vault else None,
        repos_root=Path(repos_root).expanduser() if repos_root else None,
        codegraph=codegraph,
        codegraph_symbols=symbol,
    )

    if output:
        path = write_task_pack(result["content"], Path(output))
        result["written"] = str(path)

    if json_out:
        payload = {k: v for k, v in result.items() if k != "content"}
        typer.echo(json.dumps(payload, indent=2, default=str))
        raise typer.Exit(0)

    if output:
        console.rule("[bold]context pack[/bold]")
        console.print(f"wrote: {result['written']} ({result['line_count']} lines)")
        console.print(f"repos: {', '.join(result['relevant_repos']) or 'none'}")
        console.print(f"codegraph hint: {'yes' if result['codegraph_applied'] else 'no'}")
    else:
        typer.echo(result["content"])


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


# ── Advisory model routing ────────────────────────────────────────────────

@route_app.command("inspect")
def route_inspect_cmd(
    task: Annotated[str, typer.Argument(help="Task to classify")],
    authoritative_agent: Annotated[
        str, typer.Option("--agent", help="Authoritative coding agent: codex or claude")
    ] = "codex",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Recommend a route without model calls or writes."""
    from mq_agent.tools.model_routing import inspect_route

    try:
        data = inspect_route(task, authoritative_agent=authoritative_agent)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        return

    table = Table(title="Model Route Inspection")
    table.add_column("Field")
    table.add_column("Value")
    for field in ("task_class", "risk", "recommended_route", "local_model", "authoritative_agent"):
        table.add_row(field.replace("_", " ").title(), str(data[field] or "—"))
    console.print(table)
    console.print(f"Reasons: {', '.join(data['reason_codes'])}")
    console.print(f"Escalate when: {', '.join(data['escalation_conditions'])}")


@route_app.command("shadow")
def route_shadow_cmd(
    task: Annotated[str, typer.Argument(help="Task for advisory local evaluation")],
    authoritative_agent: Annotated[
        str, typer.Option("--agent", help="Authoritative coding agent: codex or claude")
    ] = "codex",
    timeout: Annotated[int, typer.Option("--timeout", min=1, help="Ollama timeout in seconds")] = 180,
    context_file: Annotated[
        Path | None,
        typer.Option(
            "--context-file",
            help="Material the candidate must quote verbatim; enables grounding verification",
        ),
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Run and verify an advisory Ollama candidate without accepting it."""
    from mq_agent.tools.model_routing import record_route_outcome, shadow_route

    context: str | None = None
    if context_file is not None:
        if not context_file.is_file():
            raise typer.BadParameter(f"context file not found: {context_file}")
        context = context_file.read_text(encoding="utf-8")
    try:
        data = shadow_route(
            task,
            authoritative_agent=authoritative_agent,
            timeout=timeout,
            context=context,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    record_route_outcome(data["outcome"])
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        return

    decision = data["decision"]
    outcome = data["outcome"]
    table = Table(title="Model Route Shadow")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Task class", str(decision["task_class"]))
    table.add_row("Route", str(decision["recommended_route"]))
    table.add_row("Local model", str(decision["local_model"] or "—"))
    table.add_row("Authoritative agent", str(decision["authoritative_agent"]))
    table.add_row("Verification", str(outcome["verification"]["status"]))
    table.add_row("Escalated", "yes" if outcome["escalated"] else "no")
    console.print(table)
    if data["candidate"]:
        console.print(Panel(str(data["candidate"]["summary"]), title="Advisory candidate"))
    if outcome["escalation_reason"]:
        console.print(f"[yellow]Escalation:[/yellow] {outcome['escalation_reason']}")
    console.print("[dim]Shadow output is advisory; it has not been accepted or executed.[/dim]")


@route_app.command("report")
def route_report_cmd(
    source: Annotated[
        Path | None, typer.Option("--source", help="JSON or JSONL outcome source")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Aggregate validated routing outcomes from a read-only source."""
    from mq_agent.tools.model_routing import route_report

    data = route_report(source)
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        return

    table = Table(title="Model Route Report")
    table.add_column("Stage")
    table.add_column("Count", justify="right")
    for field in (
        "valid_outcomes",
        "invalid_records",
        "attempted",
        "model_output_received",
        "schema_valid",
        "verified",
        "accepted_by_agent",
        "accepted_by_operator",
        "escalated",
    ):
        table.add_row(field.replace("_", " ").title(), str(data[field]))
    console.print(table)
    console.print(f"Source: {data['source']}")


@route_app.command("history")
def route_history_cmd(
    source: Annotated[
        Path | None, typer.Option("--source", help="JSON or JSONL outcome source")
    ] = None,
    decision_id: Annotated[
        str | None, typer.Option("--decision-id", help="Explain a single routing decision")
    ] = None,
    task_class: Annotated[
        str | None, typer.Option("--task-class", help="Limit history to one task class")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", help="Newest entries to return; 0 returns all")
    ] = 20,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List individual routing outcomes newest first, read-only."""
    from mq_agent.tools.model_routing import route_history

    data = route_history(
        source, decision_id=decision_id, task_class=task_class, limit=limit
    )
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        return

    table = Table(title="Model Route History")
    table.add_column("Recorded")
    table.add_column("Decision")
    table.add_column("Task class")
    table.add_column("Verification")
    table.add_column("Escalation")
    for entry in data["entries"]:
        table.add_row(
            str(entry["recorded_at"]),
            str(entry["decision_id"]),
            str(entry["task_class"]),
            str(entry["verification"]["status"]),
            str(entry["escalation_reason"] or "—"),
        )
    console.print(table)
    console.print(f"Showing {data['returned']} of {data['matched']} matched outcomes")
    console.print(f"Source: {data['source']}")


@route_app.command("evidence-review")
def route_evidence_review_cmd(
    task_class: Annotated[str, typer.Argument(help="Task class to review for promotion")],
    source: Annotated[
        Path | None, typer.Option("--source", help="JSON or JSONL outcome source")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Review one task class without promoting it or changing routing policy."""
    from mq_agent.tools.model_routing import review_route_evidence

    try:
        data = review_route_evidence(task_class, source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        typer.echo(json.dumps(data, indent=2))
    else:
        table = Table(title="Model Route Evidence Review")
        table.add_column("Gate")
        table.add_column("Result")
        table.add_column("Actual")
        table.add_column("Required")
        for gate in data["gates"]:
            if not gate["passed"]:
                result = "FAIL"
            elif gate.get("vacuous"):
                result = "PASS (vacuous)"
            else:
                result = "PASS"
            table.add_row(
                str(gate["id"]),
                result,
                str(gate["actual"]),
                str(gate["required"]),
            )
        console.print(table)
        console.print(f"Decision: {data['decision']}")
        if data.get("vacuous_gates"):
            console.print(
                "[dim]Vacuous gates passed because the evidence held nothing that could "
                "fail them; they are not evidence of safety.[/dim]"
            )
        console.print("[dim]Automatic routing remains disabled; promotion requires an operator.[/dim]")
    if data["decision"] == "NOT_ELIGIBLE":
        raise typer.Exit(1)


# ── Ollama model runtime ──────────────────────────────────────────────────

@models_app.command("list")
def models_list_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """List locally available Ollama models."""
    from mq_agent.tools.model_runtime import list_ollama_models

    data = list_ollama_models()
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["ok"] else 1)

    if not data["ok"]:
        console.print(f"[red]✗[/red] {data['detail']}")
        hint = data.get("hint")
        if hint:
            console.print(f"[yellow]next:[/yellow] {hint}")
        raise typer.Exit(1)

    table = Table(title="Ollama Models")
    table.add_column("Model")
    for model in data["models"]:
        table.add_row(model)
    console.print(table)


@models_app.command("current")
def models_current_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Show the active model profile."""
    from mq_agent.tools.model_runtime import current_model

    data = current_model()
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        return

    table = Table(title="Active Model")
    table.add_column("Profile")
    table.add_column("Model")
    table.add_column("Config")
    table.add_row(str(data["profile"]), str(data["model"]), str(data["config_path"]))
    console.print(table)


@models_app.command("doctor")
def models_doctor_cmd(
    smoke: Annotated[bool, typer.Option("--smoke/--no-smoke", help="Run mq-learn JSON smoke test")] = True,
    timeout: Annotated[int, typer.Option("--timeout", help="Smoke-test timeout in seconds")] = 60,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Run read-only diagnostics for Ollama, model profiles, and mq-learn."""
    from mq_agent.tools.model_runtime import model_doctor

    data = model_doctor(smoke=smoke, timeout=timeout)
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["ok"] else 1)

    table = Table(title="Ollama Runtime Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for item in data["items"]:
        status = str(item["status"])
        style = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(status, "dim")
        table.add_row(str(item["check"]), f"[{style}]{status}[/{style}]", str(item.get("detail", "")))
    console.print(table)
    if not data["ok"]:
        raise typer.Exit(1)


@models_app.command("switch")
def models_switch_cmd(
    target: Annotated[str, typer.Argument(help="Profile or model name")],
    profile: Annotated[str | None, typer.Option("--profile", help="Assign model to this profile")] = None,
    approve: Annotated[bool, typer.Option("--approve", help="Write ~/.mq-agent/models.json")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Switch the active profile, or assign a model to a profile."""
    from mq_agent.tools.model_runtime import switch_model

    data = switch_model(target, profile=profile, approve=approve)
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        return

    if not approve:
        console.print(
            f"[blue]dry-run:[/blue] Would switch [bold]{data['profile']}[/bold] "
            f"to [bold]{data['model']}[/bold]."
        )
        console.print("Add [bold]--approve[/bold] to write the models config.")
        return

    console.print(
        f"[green]✓[/green] Active model: [bold]{data['profile']}[/bold] "
        f"→ [bold]{data['model']}[/bold]"
    )
    console.print(f"Config: {data['config_path']}")


@models_app.command("bench")
def models_bench_cmd(
    model: Annotated[str | None, typer.Argument(help="Model name; defaults to active model")] = None,
    prompt: Annotated[str, typer.Option("--prompt", help="Benchmark prompt")] = "Reply with OK.",
    timeout: Annotated[int, typer.Option("--timeout", help="Ollama timeout in seconds")] = 30,
    keep_alive: Annotated[str, typer.Option("--keep-alive", help="Ollama keep_alive value")] = "0",
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Benchmark a local Ollama model with timing and token metrics."""
    from mq_agent.tools.model_runtime import bench_model

    data = bench_model(model, prompt=prompt, timeout=timeout, keep_alive=keep_alive)
    if json_out:
        typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(0 if data["ok"] else 1)

    if data["ok"]:
        metrics = data["metrics"]
        table = Table(title=f"Ollama Benchmark — {data['model']}")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        for label, value in (
            ("Load", f"{metrics['load_duration_ms']} ms"),
            ("Total", f"{metrics['total_duration_ms']} ms"),
            ("Prompt tokens", metrics["prompt_eval_count"]),
            ("Output tokens", metrics["eval_count"]),
            ("Tokens/sec", metrics["tokens_per_second"]),
            ("JSON valid", data["validation"]["json_valid"]),
            ("Schema valid", data["validation"]["schema_valid"]),
        ):
            table.add_row(label, str(value))
        console.print(table)
        console.print(f"[green]✓[/green] {data['output']}")
        return
    console.print(
        f"[red]✗[/red] {data['model']}: "
        f"{data.get('output') or data.get('detail', 'benchmark failed')}"
    )
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
    rebuild_views: Annotated[bool, typer.Option("--rebuild-views", help="Also rebuild agent views after export (opt-in, off by default)")] = False,
):
    """Write the mq-stack truth snapshot (contract + release gates) to mqobsidian.

    Primary name: `stack truth-export`. `stack export` is kept as a
    backwards-compatible alias — both run the same export. Pass
    ``--rebuild-views`` to refresh agent views at the end of the workflow
    (opt-in — see docs/AGENT_VIEW_CONTRACT.md phase C).
    """
    from mq_agent.tools.stack_tools import stack_export
    from mq_agent.tools.stack_truth import stack_truth_export
    from mq_agent.tools.stack_truth import default_stack_truth_path

    dest = output or str(default_stack_truth_path())

    if json_out:
        result = stack_truth_export(output_path=output, write=not dry_run)
        if rebuild_views:
            from mq_agent.tools.agent_views import rebuild_agent_views

            result["agent_views"] = rebuild_agent_views(dry_run=dry_run)
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    if dry_run:
        console.print(f"[blue][dry-run][/blue] Would write to: {dest}")
        if rebuild_views:
            _print_rebuild_views(dry_run=True)
        return

    with console.status("[cyan]Collecting stack truth...[/cyan]"):
        msg = stack_export(output_path=output)

    console.print(f"[green]{msg}[/green]")
    if rebuild_views:
        _print_rebuild_views(dry_run=False)


def _print_rebuild_views(dry_run: bool) -> None:
    """Rebuild agent views and print a one-line summary (used by workflow hooks)."""
    from mq_agent.tools.agent_views import rebuild_agent_views

    report = rebuild_agent_views(dry_run=dry_run)
    tag = "[blue](dry-run)[/blue] " if dry_run else ""
    written = report["views_written"] + report["views_updated"]
    verb = "would refresh" if dry_run else "refreshed"
    detail = ", ".join(written) if written else "nothing changed"
    console.print(f"{tag}agent views {verb}: {detail}")
    for err in report["errors"]:
        console.print(f"[bold red]agent-views error:[/bold red] {err}")


def _stack_sweep_status(overall: int, publish: int, publish_total: int) -> tuple[str, str]:
    """Classify product readiness without hiding an incomplete publish checklist."""
    if overall >= 80 and publish >= publish_total:
        return "green", "✓ ready"
    if overall >= 80:
        return "yellow", "~ publish"
    if overall >= 50:
        return "yellow", "~ review"
    return "red", "✗ weak"


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

        entry = {
            "name": r["name"],
            "overall": overall,
            "publish": result["scores"]["publish"],
            "publish_total": result["scores"]["publish_total"],
            "skipped": False,
        }
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
    table = Table(title="Repository product-readiness sweep — summary", show_header=True)
    table.add_column("Repo", style="cyan", width=18)
    table.add_column("Overall", width=10)
    table.add_column("Publish", width=10)
    table.add_column("Status", width=10)
    for e in results:
        if e.get("skipped"):
            table.add_row(e["name"], "—", "—", "[dim]skipped[/dim]")
            continue
        score = e["overall"]
        color, status = _stack_sweep_status(
            score,
            e.get("publish", 0),
            e.get("publish_total", 16),
        )
        table.add_row(
            e["name"],
            f"[{color}]{score}/100[/{color}]",
            f"{e.get('publish', '?')}/{e.get('publish_total', '?')}",
            f"[{color}]{status}[/{color}]",
        )
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
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand, stack_release_check

    if dry_run:
        console.print("[blue][dry-run][/blue] Would check:")
        for r in MQ_STACK_REPOS:
            p = _expand(r["path"])
            console.print(f"  {r['name']:<18} {'✓' if p.exists() else '✗ (not found)'}")
        return

    with console.status("[cyan]Checking release readiness...[/cyan]"):
        raw = stack_release_check(ci=ci)
        data = json.loads(raw)

    entries = data["repos"]
    all_go = data["overall"] == "GO"

    if json_out:
        typer.echo(raw)
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
        blocked = data["blocked"]
        console.print(f"\n[bold red]✗ NO-GO — blocked: {', '.join(blocked)}[/bold red]")
        unassigned = data.get("compatibility", {}).get("unassigned", [])
        if unassigned:
            console.print(
                f"[red]  compatibility blocks {', '.join(unassigned)} — "
                "run mq-agent stack compatibility --all[/red]"
            )
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


# ── stack compatibility ────────────────────────────────────────────────────

@stack_app.command("compatibility")
def stack_compatibility_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
    all_repos: Annotated[bool, typer.Option("--all", help="Inventory the whole stack instead of the MCP slice")] = False,
    fresh_resolve: Annotated[bool, typer.Option("--fresh-resolve", help="Also resolve declared ranges in a temporary directory and probe critical imports (needs uv and network)")] = False,
    strict: Annotated[bool, typer.Option("--strict", help="Exit 1 on WARN instead of 0")] = False,
):
    """Assess dependency compatibility across MQ repositories (read-only).

    A repo can be green while the stack holds a latent incompatibility: an
    unbounded range, or a lockfile masking what a fresh install would pick.
    This reads declared and locked versions with provenance and never modifies
    dependencies, lockfiles or working trees.

    --fresh-resolve answers what a new installation would select today. It
    resolves outside every working tree, never reads or writes a lockfile, and
    reports an unreachable registry as UNAVAILABLE rather than incompatibility.

    Exit codes: 0 PASS or WARN, 1 WARN under --strict, 2 FAIL, 3 UNAVAILABLE,
    130 interrupted.
    """
    from mq_agent.tools.stack_compatibility import stack_compatibility as _check

    label = (
        "[cyan]Resolving dependencies in a temporary environment...[/cyan]"
        if fresh_resolve
        else "[cyan]Reading dependency sources...[/cyan]"
    )
    try:
        with console.status(label):
            raw = _check(slice_only=not all_repos, fresh_resolve=fresh_resolve)
    except KeyboardInterrupt:
        # A fresh resolution shells out; Ctrl-C must not read as a verdict.
        console.print("\n[dim]Interrupted — no verdict was reached.[/dim]")
        raise typer.Exit(130) from None

    data = json.loads(raw)
    exit_code = {
        "PASS": 0,
        "SKIPPED": 0,
        "WARN": 1 if strict else 0,
        "FAIL": 2,
        "UNAVAILABLE": 3,
    }.get(data["status"], 0)

    if json_out:
        typer.echo(raw)
        raise typer.Exit(exit_code)

    _STATUS = {
        "PASS":        "[green]PASS[/green]",
        "WARN":        "[yellow]WARN[/yellow]",
        "FAIL":        "[bold red]FAIL[/bold red]",
        "SKIPPED":     "[dim]SKIPPED[/dim]",
        "UNAVAILABLE": "[dim]UNAVAILABLE[/dim]",
    }

    console.print()
    console.rule("[bold]MQ Stack Compatibility[/bold]")
    console.print()

    for component in data["components"]:
        status_str = _STATUS.get(component["status"], component["status"])
        console.print(f"  {component['repo']:<20} {status_str}")
        for dep in component["dependencies"]:
            declared = dep["declared"] or "—"
            locked = dep["locked"] or "—"
            bound = "" if dep["bounded"] else " [yellow](unbounded)[/yellow]"
            fresh = f"  resolved {dep['resolved']}" if dep.get("resolved") else ""
            console.print(
                f"    [dim]{dep['name']}[/dim]  declared {declared}  "
                f"locked {locked}{fresh}{bound}"
            )
        if component.get("reason"):
            console.print(f"    [dim]{component['reason']}[/dim]")

    if data["relationships"]:
        console.print()
        console.print("  [bold]Relationships[/bold]")
        for rel in data["relationships"]:
            status_str = _STATUS.get(rel["status"], rel["status"])
            console.print(
                f"    {rel['producer']} ↔ {rel['consumer']}  "
                f"[dim]{rel['subject']}[/dim]  {status_str}"
            )
            console.print(f"      [dim]{rel['detail']}[/dim]")

    console.print()
    if data["findings"]:
        for finding in data["findings"]:
            colour = "red" if finding["severity"] == "FAIL" else "yellow"
            console.print(f"  [{colour}]→[/{colour}] {finding['code']}: {finding['message']}")
        console.print()

    overall = _STATUS.get(data["status"], data["status"])
    console.print(f"[bold]Stack compatibility: {overall}[/bold]")
    if data["next_action"]:
        console.print(f"  [dim]Next: {data['next_action']}[/dim]")

    raise typer.Exit(exit_code)


@stack_app.command("skills-check")
def stack_skills_check_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="CI mode: skip repos missing from the workspace")] = False,
):
    """Validate skill consistency across every mq-stack repo.

    Runs each repo's scripts/check-skills.sh (frontmatter, skill
    cross-references, referenced paths, SKILLS.md sync). No API key required.
    Exits 1 if any repo is DRIFT (skills inconsistent) or BLOCKED.
    With --ci, repos missing from the workspace are SKIPPED.
    """
    from mq_agent.tools.stack_tools import stack_skills_check as _check

    with console.status("[cyan]Checking skills across the stack...[/cyan]"):
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
    console.rule("[bold]MQ Stack Skills Gate[/bold]")
    console.print()

    for e in data["repos"]:
        status_str = _STATUS.get(e["status"], e["status"])
        reason = f"  [dim]{e['reason']}[/dim]" if e.get("reason") else ""
        console.print(f"  {e['name']:<20} {status_str}{reason}")

    console.print()
    if data["overall"] == "READY":
        console.print("[bold green]✓ Stack skills: READY[/bold green]")
    else:
        console.print("[bold red]✗ Stack skills: NOT READY[/bold red]")
        for r in data.get("reasons", []):
            console.print(f"  [red]→[/red] {r}")
        raise typer.Exit(1)


# ── stack release ──────────────────────────────────────────────────────────

@stack_app.command("release")
def stack_release_cmd(
    repo: Annotated[str, typer.Option("--repo", help="Stack repo to release")] = "",
    all_repos: Annotated[bool, typer.Option("--all", help="Plan or execute a release across every stack repo")] = False,
    bump: Annotated[str, typer.Option("--bump", help="Version bump: patch, minor or major")] = "patch",
    version: Annotated[str, typer.Option("--version", help="Explicit target version (overrides --bump)")] = "",
    execute: Annotated[bool, typer.Option("--execute", help="Apply the release (default is dry-run)")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Required with --all --execute: multi-repo release is a write flow")] = False,
    finalize_pr: Annotated[int, typer.Option("--finalize-pr", help="Finalize a merged release PR by number; requires --repo, --version and --approve")] = 0,
    preflight: Annotated[bool, typer.Option("--preflight", help="Read-only multi-repo release preflight (strict blockers; never executes). Requires --all.")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
):
    """Orchestrated single-repo release: gate, bump, changelog, tag, push, truth-export.

    Dry-run by default — shows the plan without touching the repo. With
    --execute the plan is applied step by step; any failed step aborts the
    run and pre-commit file edits are rolled back. Exits 1 on NO-GO or on a
    failed step. Ends with a stack truth-export so the release lands in
    mqobsidian memory.

    With --all, plans a release for every stack repo at once (dry-run by default):
    each repo is reported as ready, blocked, or up-to-date. Exits 1 if any repo
    is blocked. Release a ready repo with --repo <name> --execute.

    With --all --preflight, runs the read-only multi-repo release preflight: the
    strict fail-fast refusal surface (dirty, off-main, unpushed, tag exists,
    version mismatch, and each repo's release-check.sh). Never mutates and never
    executes; exits 1 if any repo is blocked.

    Pull-request repos stop in AWAITING_MERGE without directly releasing other
    repos. Finalize a verified merged release PR explicitly with --finalize-pr,
    --repo, --version and --approve.
    """
    from mq_agent.tools.stack_release import (
        BUMP_PARTS,
        execute_stack_release_all,
        finalize_release_pull_request,
        plan_stack_release_all,
        preflight_stack_release_all,
        stack_release as _release,
    )

    if bump not in BUMP_PARTS:
        console.print(f"[red]Invalid --bump {bump!r} — expected one of: {', '.join(BUMP_PARTS)}[/red]")
        raise typer.Exit(1)

    if finalize_pr:
        from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand

        if all_repos or execute or preflight or not repo or not version or not approve:
            console.print(
                "[bold red]--finalize-pr requires --repo, --version and --approve; "
                "it cannot be combined with --all, --execute or --preflight.[/bold red]"
            )
            raise typer.Exit(1)
        entry = next((item for item in MQ_STACK_REPOS if item["name"] == repo), None)
        if entry is None:
            console.print(f"[bold red]Unknown stack repo: {repo}[/bold red]")
            raise typer.Exit(1)
        data = finalize_release_pull_request(
            _expand(entry["path"]), f"v{version}", finalize_pr,
        )
        if json_out:
            typer.echo(json.dumps(data, indent=2, default=str))
        elif data.get("finalized"):
            suffix = " (already finalized)" if data.get("already_finalized") else ""
            console.print(f"[green]Finalized v{version}{suffix}.[/green]")
        else:
            console.print(f"[bold red]Finalization refused:[/bold red] {data.get('error')}")
        raise typer.Exit(0 if data.get("finalized") else 1)

    if all_repos and repo:
        console.print("[bold red]Use either --repo or --all, not both.[/bold red]")
        raise typer.Exit(1)
    if not all_repos and not repo:
        console.print("[bold red]Provide --repo <name> or --all.[/bold red]")
        raise typer.Exit(1)
    if preflight and not all_repos:
        console.print("[bold red]--preflight requires --all.[/bold red]")
        raise typer.Exit(1)
    if preflight and execute:
        console.print("[bold red]--preflight is read-only and cannot be combined with --execute.[/bold red]")
        raise typer.Exit(1)

    if all_repos:
        if preflight:
            with console.status("[cyan]Preflighting stack release...[/cyan]"):
                data = preflight_stack_release_all(bump=bump)
            if json_out:
                typer.echo(json.dumps(data, indent=2, default=str))
                raise typer.Exit(1 if data["blocked_count"] else 0)
            console.print()
            console.rule("[bold]Stack Release — preflight (read-only)[/bold]")
            console.print()
            console.print(
                f"[dim]bump {data['bump']}  ·  ready {data['ready_count']}  ·  "
                f"blocked {data['blocked_count']}  ·  up-to-date {data['uptodate_count']}[/dim]"
            )
            console.print()
            for r in data["repos"]:
                state = r["preflight_state"]
                if state == "READY":
                    console.print(
                        f"  [green]READY[/green]        {r['repo']:<18} "
                        f"{r['current_version']} → [bold]{r['new_version']}[/bold]"
                    )
                elif state == "UP-TO-DATE":
                    console.print(f"  [dim]UP-TO-DATE[/dim]   {r['repo']:<18} {r['current_version']}")
                else:
                    console.print(f"  [red]BLOCKED[/red]      {r['repo']:<18} {r['current_version']}")
                    for b in r["blockers"]:
                        console.print(f"    [red]→[/red] {b}")
            console.print()
            if data["would_execute"]:
                console.print(
                    "[green]Preflight clean.[/green] "
                    "[dim]Multi-repo execute is not implemented yet (design-locked).[/dim]"
                )
            else:
                console.print(
                    "[bold red]Preflight blocked[/bold red] — a multi-repo execute "
                    "would abort in this phase, before any mutation."
                )
            raise typer.Exit(1 if data["blocked_count"] else 0)
        if execute:
            if version:
                console.print("[bold red]--version applies to a single --repo, not --all.[/bold red]")
                raise typer.Exit(1)
            with console.status("[cyan]Preflighting stack release...[/cyan]"):
                data = execute_stack_release_all(bump=bump, approve=approve)
            if json_out:
                typer.echo(json.dumps(data, indent=2, default=str))
                raise typer.Exit(0 if data["aborted_phase"] == "none" and approve else 1)
            console.print()
            console.rule("[bold]Stack Release — all repos (execute)[/bold]")
            console.print()
            for r in data["repos"]:
                pre, ex = r["preflight_state"], r["execute_state"]
                ver = r["current_version"]
                if r.get("new_version"):
                    ver = f"{r['current_version']} → {r['new_version']}"
                if ex == "RELEASED":
                    label = "[green]RELEASED[/green]  "
                elif ex == "AWAITING_MERGE":
                    label = "[yellow]AWAITING_MERGE[/yellow]"
                elif ex == "FAILED":
                    label = "[bold red]FAILED[/bold red]    "
                elif ex == "SKIPPED":
                    label = "[yellow]SKIPPED[/yellow]   "
                elif pre == "BLOCKED":
                    label = "[red]BLOCKED[/red]   "
                elif pre == "UP-TO-DATE":
                    label = "[dim]UP-TO-DATE[/dim]"
                elif pre == "READY":
                    # Not executed (yet). Showing "—" here would read as
                    # "nothing happens to this repo", which is the opposite of
                    # the truth in the --approve-less refusal report.
                    label = "[green]READY[/green]     "
                else:
                    label = "[dim]—[/dim]         "
                console.print(f"  {label} {r['repo']:<18} {ver}")
                if r.get("detail"):
                    console.print(f"    [dim]{r['detail']}[/dim]")
                for b in r["blockers"]:
                    console.print(f"    [red]→[/red] {b}")
            console.print()
            if not approve:
                console.print(
                    "[bold red]Refused: multi-repo execute requires --approve.[/bold red]"
                )
                console.print(
                    "[dim]The table above is what a run would release. Nothing was touched.[/dim]"
                )
                raise typer.Exit(1)
            if data["aborted_phase"] == "preflight":
                console.print(
                    "[bold red]Aborted in preflight[/bold red] — at least one repo is "
                    "blocked. No repo was touched."
                )
                raise typer.Exit(1)
            if data["aborted_phase"] == "execute":
                console.print(
                    f"[bold red]Stopped at the first failure.[/bold red] "
                    f"released {data['released_count']}  ·  failed {data['failed_count']}  ·  "
                    f"skipped {data['skipped_count']}"
                )
                console.print(
                    "[dim]The stack is partially released. Already-released repos are "
                    "left released — repair by fixing forward, never by deleting a "
                    "pushed tag or rewriting history.[/dim]"
                )
                raise typer.Exit(1)
            if data["aborted_phase"] == "awaiting_merge":
                console.print(
                    "[yellow]Release PR merge required.[/yellow] "
                    "No direct releases were started."
                )
                raise typer.Exit(1)
            console.print(
                f"[green]Released {data['released_count']} repo(s).[/green] "
                f"[dim]up-to-date {data['uptodate_count']}[/dim]"
            )
            raise typer.Exit(0)
        if version:
            console.print("[bold red]--version applies to a single --repo, not --all.[/bold red]")
            raise typer.Exit(1)
        with console.status("[cyan]Planning stack release...[/cyan]"):
            data = plan_stack_release_all(bump=bump)
        if json_out:
            typer.echo(json.dumps(data, indent=2, default=str))
            raise typer.Exit(1 if data["blocked_count"] else 0)
        console.print()
        console.rule("[bold]Stack Release — all repos[/bold]")
        console.print()
        console.print(
            f"[dim]bump {data['bump']}  ·  ready {data['go_count']}  ·  "
            f"blocked {data['blocked_count']}  ·  up-to-date {data['uptodate_count']}[/dim]"
        )
        console.print()
        for r in data["repos"]:
            if r["state"] == "ready":
                console.print(
                    f"  [green]ready[/green]        {r['repo']:<18} "
                    f"{r['current_version']} → [bold]{r['new_version']}[/bold]"
                )
            elif r["state"] == "up-to-date":
                console.print(f"  [dim]up-to-date[/dim]   {r['repo']:<18} {r['current_version']}")
            else:
                console.print(f"  [red]blocked[/red]      {r['repo']:<18} {r['current_version']}")
                for b in r["blockers"]:
                    console.print(f"    [red]→[/red] {b}")
        console.print(
            "\n[dim]Release a ready repo with:  "
            "mq-agent stack release --repo <name> --execute[/dim]"
        )
        raise typer.Exit(1 if data["blocked_count"] else 0)

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

    if data.get("state") == "AWAITING_MERGE":
        console.print(
            f"[bold yellow]Release PR prepared for {repo} {data['tag']} — "
            "AWAITING_MERGE[/bold yellow]"
        )
        if data.get("pull_request"):
            console.print(f"  [dim]{data['pull_request']}[/dim]")
    elif data.get("ok"):
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


@stack_app.command("loop")
def stack_loop_cmd(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Plan only; do not execute the selected loop action")] = True,
    execute: Annotated[bool, typer.Option("--execute", help="Execute one allowlisted loop action; requires --approve")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
    approve: Annotated[bool, typer.Option("--approve", help="Approve controlled execution for one allowlisted action")] = False,
    max_iterations: Annotated[int, typer.Option("--max-iterations", help="Bounded loop count for the plan")] = 1,
):
    """Plan or execute one v1.20 controlled autonomous stack loop.

    Dry-run by default. `--execute --approve` runs one allowlisted action with
    command-specific rollback behaviour.
    """
    from mq_agent.tools.stack_loop import stack_loop as _stack_loop

    with console.status("[cyan]Planning stack loop...[/cyan]"):
        raw = _stack_loop(dry_run=dry_run, approve=approve, execute=execute, max_iterations=max_iterations)
    data = json.loads(raw)

    if json_out:
        typer.echo(raw)
        return

    console.print()
    console.rule("[bold]mq-stack Loop Plan[/bold]")
    console.print()
    console.print(f"  Decision: [bold]{data['decision']}[/bold]   Next: [bold]{data['next_action']}[/bold]")
    if data.get("blocked"):
        console.print(f"  [yellow]Blocked:[/yellow] {data['blocker']}")
    if data.get("execution_result"):
        result = data["execution_result"]
        status = "ok" if result.get("ok") else "failed"
        console.print(f"  Execution: [bold]{status}[/bold]   Action: [bold]{result.get('action')}[/bold]")
    console.print()
    for step in data["steps"]:
        console.print(f"  • [bold]{step['name']}[/bold] — {step['detail']}")


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
