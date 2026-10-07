"""CLI for the evidence-grounded feedback engine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .canary import (
    canary_status,
    create_canary_plan,
    run_canary,
)
from .candidates import (
    candidate_detail,
    list_candidates,
    maybe_create_candidate,
    memory_handoff,
    set_candidate_state,
)
from .engine import (
    DEFAULT_MAX_CONTEXT_BYTES,
    DEFAULT_MAX_SOURCES,
    DEFAULT_TIMEOUT_MS,
    run_context_experiment,
)
from .evaluation import compare_feedback_run, latest_comparison
from .readiness import activation_readiness
from .control import (
    activate as activate_policy,
    approval_receipt,
    policy_status,
    post_activation_check,
    rollback as rollback_policy,
    validate_canary,
)
from .store import purge_feedback_state
from .views import (
    feedback_inspect,
    feedback_recent,
    feedback_report,
    feedback_status,
)

app = typer.Typer(
    help="Run and inspect evidence-grounded feedback experiments.",
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
    table.add_row("Experiments", str(payload["valid_records"]))
    table.add_row("Comparisons", str(payload.get("comparison_records", 0)))
    table.add_row("Candidate events", str(payload.get("candidate_events", 0)))
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


def _render_comparison(comparison: dict[str, Any]) -> None:
    table = Table(title=f"Comparison — {comparison['verdict']}")
    table.add_column("Metric")
    table.add_column("Active", justify="right")
    table.add_column("Shadow", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Direction")
    table.add_column("Material")
    for name, metric in comparison["metrics"].items():
        table.add_row(
            name,
            str(metric["active"]) if metric["active"] is not None else "unavailable",
            str(metric["shadow"]) if metric["shadow"] is not None else "unavailable",
            str(metric["delta"]) if metric["delta"] is not None else "unavailable",
            str(metric["direction"]),
            "yes" if metric["material"] else "no",
        )
    console.print(table)
    console.print(f"Comparison id: {comparison['comparison_id']}")
    console.print(f"Evidence refs: {len(comparison['evidence_refs'])}")


@app.command("inspect")
def feedback_inspect_cmd(
    feedback_run_id: Annotated[str, typer.Argument(help="Feedback run identifier")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explain one immutable experiment, comparison and candidate chain."""
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
        table.add_row(
            "snapshot",
            f"{record['snapshot']['ref']}@{record['snapshot']['commit']}",
        )
        table.add_row("store ref", f"{ref['file']}:{ref['line']}")
        console.print(table)
    else:
        console.print(
            f"[yellow]Ambiguous immutable id: {len(payload['duplicate_records'])} records.[/yellow]"
        )

    comparison = payload["comparison"]
    if isinstance(comparison, dict) and "record" in comparison:
        _render_comparison(comparison["record"])
    else:
        console.print(f"Comparison: unavailable ({comparison['reason']})")

    candidate = payload["candidate"]
    if isinstance(candidate, dict) and "record" in candidate:
        record = candidate["record"]
        console.print(
            f"Candidate: {record['candidate_id']} "
            f"{record['state']} -> {record['proposed_strategy']}"
        )
    else:
        console.print(f"Candidate: unavailable ({candidate['reason']})")

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
    """Aggregate feedback evidence without recomputing a verdict."""
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
    summary.add_row("Comparisons", str(payload["comparison"]["records"] or 0))
    summary.add_row("Latest verdict", str(payload["comparison"]["reason"]))
    console.print(summary)

    metrics = Table(title="Latest comparison deltas")
    metrics.add_column("Metric")
    metrics.add_column("Status")
    metrics.add_column("Delta")
    for name, metric in payload["metrics"].items():
        metrics.add_row(
            name,
            str(metric["status"]),
            str(metric["value"]) if metric["value"] is not None else "unavailable",
        )
    console.print(metrics)
    for reason in payload["degraded_reasons"]:
        console.print(f"[yellow]degraded:[/yellow] {reason}")


@app.command("run")
def feedback_run_cmd(
    task: Annotated[str, typer.Option("--task", help="Task used only in-memory for context selection")],
    repo: Annotated[Path, typer.Option("--repo", help="Clean Git repository to evaluate")] = Path("."),
    task_class: Annotated[
        str, typer.Option("--task-class", help="Feedback task class")
    ] = "repo-review",
    vault: Annotated[
        Path | None, typer.Option("--vault", help="mqobsidian vault override")
    ] = None,
    timeout_ms: Annotated[
        int, typer.Option("--timeout-ms", min=1, help="Hard per-strategy collection deadline")
    ] = DEFAULT_TIMEOUT_MS,
    max_context_bytes: Annotated[
        int, typer.Option("--max-context-bytes", min=1)
    ] = DEFAULT_MAX_CONTEXT_BYTES,
    max_sources: Annotated[
        int, typer.Option("--max-sources", min=1)
    ] = DEFAULT_MAX_SOURCES,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run one zero-effect active-versus-shadow repo-review experiment."""
    try:
        payload = run_context_experiment(
            task,
            repo,
            task_class=task_class,
            vault=vault,
            timeout_ms=timeout_ms,
            max_context_bytes=max_context_bytes,
            max_sources=max_sources,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        _emit_json(payload)
    else:
        experiment = payload["experiment"]
        console.print(
            Panel(
                f"Run: {experiment['feedback_run_id']}\n"
                f"State: {experiment['state']}\n"
                f"Snapshot: {experiment['snapshot']['ref']}@{experiment['snapshot']['commit']}",
                title="Feedback Experiment",
            )
        )
        if payload["comparison"] is not None:
            _render_comparison(payload["comparison"])
        elif payload["reason"]:
            console.print(f"[yellow]Blocked:[/yellow] {payload['reason']}")
    if payload["status"] != "PASS":
        raise typer.Exit(1)


@app.command("compare")
def feedback_compare_cmd(
    feedback_run_id: Annotated[str, typer.Argument(help="Feedback run identifier")],
    fixture: Annotated[
        Path | None,
        typer.Option("--fixture", help="Explicit deterministic relevance fixture JSON"),
    ] = None,
    atlas_evaluation: Annotated[
        Path | None,
        typer.Option(
            "--atlas-evaluation",
            help="Optional Atlas Core advisory evaluation bound to observed evidence refs",
        ),
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Read the latest comparison or derive one from explicit relevance evidence."""
    try:
        if fixture is None:
            if atlas_evaluation is not None:
                raise ValueError("--atlas-evaluation requires --fixture")
            comparison = latest_comparison(feedback_run_id)
            candidate = None
        else:
            comparison = compare_feedback_run(
                feedback_run_id,
                fixture_path=fixture,
                atlas_evaluation=atlas_evaluation,
            )
            candidate, _created = maybe_create_candidate(comparison)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        _emit_json(comparison)
        return
    _render_comparison(comparison)
    if candidate is not None:
        console.print(
            f"Candidate: {candidate['candidate_id']} ({candidate['state']})"
        )


@app.command("candidates")
def feedback_candidates_cmd(
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List effective reviewable improvement candidates."""
    payload = list_candidates()
    if json_out:
        _emit_json(payload)
        return
    table = Table(title="Feedback Candidates")
    table.add_column("Candidate")
    table.add_column("Task class")
    table.add_column("State")
    table.add_column("Current")
    table.add_column("Proposed")
    table.add_column("Evidence")
    for item in payload["candidates"]:
        table.add_row(
            str(item["candidate_id"]),
            str(item["task_class"]),
            str(item["state"]),
            str(item["current_strategy"]),
            str(item["proposed_strategy"]),
            str(len(item["comparison_ids"])),
        )
    console.print(table)


@app.command("candidate")
def feedback_candidate_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Feedback candidate identifier")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show one candidate with its immutable comparison evidence."""
    try:
        payload = candidate_detail(candidate_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    candidate = payload["candidate"]
    console.print(
        Panel(
            f"State: {candidate['state']}\n"
            f"Task class: {candidate['task_class']}\n"
            f"Current: {candidate['current_strategy']}\n"
            f"Proposed: {candidate['proposed_strategy']}\n"
            f"Rollback: {candidate['rollback_target']}",
            title=f"Candidate {candidate_id}",
        )
    )
    console.print(f"Rationale: {candidate['rationale']}")
    console.print("Gains:")
    for item in candidate["gains"]:
        console.print(f"  + {item}")
    console.print("Regressions:")
    for item in candidate["regressions"]:
        console.print(f"  - {item}")
    console.print(f"Comparisons: {', '.join(candidate['comparison_ids'])}")


@app.command("candidate-state")
def feedback_candidate_state_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Feedback candidate identifier")],
    state: Annotated[
        str,
        typer.Option(
            "--state",
            help="deferred, rejected, or approved-for-handoff",
        ),
    ],
    reason: Annotated[str, typer.Option("--reason", help="Human review reason")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Append a human review state; never activates a policy."""
    try:
        payload = set_candidate_state(candidate_id, state, reason=reason)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
    else:
        console.print(f"{candidate_id}: {payload['state']} — {payload['state_reason']}")


@app.command("activation-readiness")
def feedback_activation_readiness_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Feedback candidate identifier")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check evidence readiness for human activation approval; never activates."""
    try:
        payload = activation_readiness(candidate_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_out:
        _emit_json(payload)
    else:
        table = Table(title=f"Activation Readiness — {payload['status']}")
        table.add_column("Requirement")
        table.add_column("Status")
        table.add_column("Detail")
        for item in payload["requirements"]:
            table.add_row(
                str(item["id"]),
                str(item["status"]),
                str(item["detail"]),
            )
        console.print(
            Panel(
                f"Candidate: {payload['candidate_id']}\n"
                f"Task class: {payload['task_class']}\n"
                f"Strategy: {payload['current_strategy']} -> {payload['proposed_strategy']}\n"
                f"Rollback: {payload['rollback_target']}\n"
                f"Human approval required: yes\n"
                f"Canary required: yes\n"
                f"Activation available: no",
                title="Feedback Activation Readiness",
            )
        )
        console.print(table)
        console.print(f"Next: {payload['next_action']}")

    if payload["status"] == "INSUFFICIENT_EVIDENCE":
        raise typer.Exit(1)
    if payload["status"] == "BLOCKED":
        raise typer.Exit(2)


@app.command("approve")
def feedback_approve_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Feedback candidate identifier")],
    reason: Annotated[str, typer.Option("--reason", help="Human approval reason")],
    expires_hours: Annotated[int, typer.Option("--expires-hours", min=1, max=168)] = 24,
    approve: Annotated[bool, typer.Option("--approve", help="Required: issue approval receipt")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Issue an expiring approval receipt bound to exact candidate evidence."""
    if not approve:
        raise typer.BadParameter("feedback approve requires --approve")
    try:
        payload = approval_receipt(
            candidate_id,
            reason=reason,
            expires_hours=expires_hours,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    console.print(
        Panel(
            f"Approval: {payload['approval_id']}\n"
            f"Candidate: {payload['candidate_id']}\n"
            f"Task class: {payload['task_class']}\n"
            f"Strategy: {payload['current_strategy']} -> {payload['proposed_strategy']}\n"
            f"Expires: {payload['expires_at']}",
            title="Feedback Approval",
        )
    )


@app.command("canary-plan")
def feedback_canary_plan_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Approved feedback candidate")],
    approval_id: Annotated[str, typer.Option("--approval-id")],
    execution_budget: Annotated[int, typer.Option("--executions", min=1, max=20)] = 3,
    min_executions: Annotated[int, typer.Option("--min-executions", min=1, max=20)] = 3,
    max_duration_seconds: Annotated[int, typer.Option("--max-duration-seconds", min=1, max=3600)] = 300,
    max_failure_rate: Annotated[float, typer.Option("--max-failure-rate", min=0.0, max=1.0)] = 0.0,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create one immutable Canary v2 plan; no experiment is executed."""
    try:
        payload = create_canary_plan(
            candidate_id,
            approval_id=approval_id,
            execution_budget=execution_budget,
            min_executions=min_executions,
            max_duration_seconds=max_duration_seconds,
            max_failure_rate=max_failure_rate,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    console.print(
        Panel(
            f"Canary: {payload['canary_id']}\n"
            f"Candidate: {payload['candidate_id']}\n"
            f"Approval: {payload['approval_id']}\n"
            f"Task class: {payload['task_class']}\n"
            f"Strategy: {payload['current_strategy']} -> {payload['proposed_strategy']}\n"
            f"Executions: {payload['plan']['execution_budget']} "
            f"(minimum {payload['plan']['min_executions']})\n"
            f"Max duration: {payload['plan']['max_duration_seconds']}s\n"
            f"Max failure rate: {payload['plan']['max_failure_rate']}",
            title="Canary v2 Plan",
        )
    )


@app.command("canary-run")
def feedback_canary_run_cmd(
    canary_id: Annotated[str, typer.Argument(help="Canary v2 identifier")],
    task: Annotated[str, typer.Option("--task", help="Task used only for zero-effect context selection")],
    fixture: Annotated[Path, typer.Option("--fixture", help="Deterministic relevance fixture JSON")],
    repo: Annotated[Path, typer.Option("--repo", help="Clean Git repository to evaluate")] = Path("."),
    vault: Annotated[Path | None, typer.Option("--vault", help="mqobsidian vault override")] = None,
    timeout_ms: Annotated[int, typer.Option("--timeout-ms", min=1)] = DEFAULT_TIMEOUT_MS,
    max_context_bytes: Annotated[int, typer.Option("--max-context-bytes", min=1)] = DEFAULT_MAX_CONTEXT_BYTES,
    max_sources: Annotated[int, typer.Option("--max-sources", min=1)] = DEFAULT_MAX_SOURCES,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Execute one bounded Canary v2 plan and append one immutable RESULT."""
    try:
        payload = run_canary(
            canary_id,
            task=task,
            fixture_path=fixture,
            repo=repo,
            vault=vault,
            timeout_ms=timeout_ms,
            max_context_bytes=max_context_bytes,
            max_sources=max_sources,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
    else:
        style = (
            "green" if payload["verdict"] == "PASS"
            else "red" if payload["verdict"] == "FAIL"
            else "yellow"
        )
        console.print(
            Panel(
                f"Canary: {payload['canary_id']}\n"
                f"Verdict: {payload['verdict']}\n"
                f"Executions: {payload['executions_completed']}/"
                f"{payload['executions_requested']}\n"
                f"Successes: {payload['successes']}\n"
                f"Failures: {payload['failures']}\n"
                f"Inconclusive: {payload['inconclusive']}\n"
                f"Failure rate: {payload['failure_rate']}",
                title=f"[bold {style}]Canary v2 {payload['verdict']}[/bold {style}]",
                border_style=style,
            )
        )
    if payload["verdict"] == "FAIL":
        raise typer.Exit(2)
    if payload["verdict"] == "INSUFFICIENT_EVIDENCE":
        raise typer.Exit(1)


@app.command("canary-status")
def feedback_canary_status_cmd(
    canary_id: Annotated[str, typer.Argument(help="Canary v2 identifier")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show authoritative append-only PLAN/RESULT state for one canary."""
    try:
        payload = canary_status(canary_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    result = payload["result"]
    verdict = result["verdict"] if isinstance(result, dict) else "not-run"
    console.print(
        Panel(
            f"Canary: {payload['canary_id']}\n"
            f"State: {payload['state']}\n"
            f"Verdict: {verdict}\n"
            f"Plan hash: {payload['plan']['plan_sha256']}",
            title="Canary v2 Status",
        )
    )


@app.command("canary-check")
def feedback_canary_check_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Feedback candidate identifier")],
    approval_id: Annotated[str, typer.Option("--approval-id")],
    comparison_id: Annotated[str, typer.Option("--comparison-id", help="Post-approval canary comparison")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate one legacy v1.31 comparison; read-only and not activation-authorizing."""
    try:
        payload = validate_canary(candidate_id, approval_id, comparison_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    console.print(
        f"[bold green]PASS[/bold green] canary {payload['comparison_id']} "
        f"for {payload['candidate_id']}"
    )


@app.command("activate")
def feedback_activate_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Feedback candidate identifier")],
    approval_id: Annotated[str, typer.Option("--approval-id")],
    canary_id: Annotated[str, typer.Option("--canary-id", help="Passing Canary v2 identifier")],
    reason: Annotated[str, typer.Option("--reason")],
    approve: Annotated[bool, typer.Option("--approve", help="Required: change one task-class policy")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Activate one task-class strategy after approval and a passing Canary v2 result."""
    if not approve:
        raise typer.BadParameter("feedback activate requires --approve")
    try:
        payload = activate_policy(
            candidate_id,
            approval_id=approval_id,
            canary_id=canary_id,
            reason=reason,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    console.print(
        f"[bold green]ACTIVATED[/bold green] {payload['task_class']}: "
        f"{payload['from_strategy']} -> {payload['to_strategy']}"
    )


@app.command("rollback")
def feedback_rollback_cmd(
    task_class: Annotated[str, typer.Argument(help="Task class to roll back")],
    reason: Annotated[str, typer.Option("--reason")],
    approve: Annotated[bool, typer.Option("--approve", help="Required: append rollback event")] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Roll one task class back to the immediately previous strategy."""
    if not approve:
        raise typer.BadParameter("feedback rollback requires --approve")
    try:
        payload = rollback_policy(task_class, reason=reason)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
        return
    console.print(
        f"[bold yellow]ROLLED BACK[/bold yellow] {payload['task_class']}: "
        f"{payload['from_strategy']} -> {payload['to_strategy']}"
    )


@app.command("post-activation-check")
def feedback_post_activation_check_cmd(
    task_class: Annotated[str, typer.Argument(help="Activated task class")],
    comparison_id: Annotated[str, typer.Option("--comparison-id")],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Surface material regressions against the measured shadow baseline."""
    try:
        payload = post_activation_check(task_class, comparison_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
    else:
        style = "red" if payload["status"] == "REGRESSION" else (
            "green" if payload["status"] == "PASS" else "yellow"
        )
        console.print(
            Panel(
                f"Task class: {task_class}\n"
                f"Active: {payload['active_strategy']}\n"
                f"Comparison: {comparison_id}\n"
                f"Regressions: {', '.join(payload['regressions']) or 'none'}",
                title=f"[bold {style}]{payload['status']}[/bold {style}]",
                border_style=style,
            )
        )
    if payload["status"] != "PASS":
        raise typer.Exit(1)


@app.command("policy")
def feedback_policy_cmd(
    task_class: Annotated[str, typer.Argument(help="Task class")] = "repo-review",
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the effective feedback-controlled task-class policy."""
    payload = policy_status(task_class)
    if json_out:
        _emit_json(payload)
        return
    console.print(
        Panel(
            f"Task class: {payload['task_class']}\n"
            f"Baseline: {payload['baseline_strategy']}\n"
            f"Effective: {payload['effective_strategy']}\n"
            f"Kill switch: {payload['kill_switch']}\n"
            f"Events: {payload['events']}",
            title="Feedback Policy",
        )
    )


@app.command("candidate-handoff")
def feedback_candidate_handoff_cmd(
    candidate_id: Annotated[str, typer.Argument(help="Approved memory candidate")],
    confidence: Annotated[
        float, typer.Option("--confidence", min=0.0, max=1.0)
    ],
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Submit an approved memory candidate to mqobsidian's review inbox."""
    try:
        payload = memory_handoff(candidate_id, confidence=confidence)
    except (ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_out:
        _emit_json(payload)
    else:
        console.print(
            f"{payload['candidate_id']}: {payload['status']} "
            f"({payload['observation_id']})"
        )


@app.command("purge")
def feedback_purge_cmd(
    approve: Annotated[
        bool,
        typer.Option("--approve", help="Required: delete local runtime feedback evidence"),
    ] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete local runtime feedback evidence; production behavior is unchanged."""
    if not approve:
        raise typer.BadParameter("feedback purge requires --approve")
    deleted = purge_feedback_state()
    payload = {
        "schema": "feedback-purge-result.v1",
        "deleted_artifacts": deleted,
        "production_behavior_changed": False,
    }
    if json_out:
        _emit_json(payload)
    else:
        console.print(
            f"Deleted {deleted} feedback artifact(s); production behavior unchanged."
        )
