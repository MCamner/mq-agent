"""``mq-agent workflow`` CLI surface (Phase 3).

Read-only template commands: ``list``, ``show`` and ``plan``. ``plan`` builds and
prints a validated plan for a repo but **does not persist or execute** it — the
runner arrives in Phase 4. This module imports only the workflows package and
typer (no TUI), so it stays importable and testable on its own.
"""

from __future__ import annotations

import json
import os
from typing import Any

import typer

from .observation import emit_observation
from .runner import Runner
from .state import WorkflowStateError, new_run
from .state import resume as resume_state
from .storage import WorkflowStore
from .templates import TemplateError, instantiate, list_templates, load_template
from .target import bind_target
from .receipt import build_receipt

workflow_app = typer.Typer(
    help="Bounded multi-step workflow templates (list/show/plan). Read-only in v1."
)

checkpoint_app = typer.Typer(
    help="Create, inspect, and resume bounded workflow session checkpoints."
)
workflow_app.add_typer(checkpoint_app, name="checkpoint")


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
    run = new_run(plan)
    try:
        bind_target(run)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(run.plan.model_dump(mode="json", by_alias=True), indent=2))


def _print_summary(run, json_output: bool) -> None:
    if json_output:
        report = dict(run.summary or {})
        report["run_id"] = run.run_id
        report["receipt"] = build_receipt(run)
        typer.echo(json.dumps(report, indent=2))
        return
    summary = run.summary or {}
    receipt = build_receipt(run)
    typer.echo(
        f"Coverage: {receipt['completeness']['completed']}/{receipt['completeness']['planned']}; verification: {receipt['verification']['status']}; state recorded: {receipt['recording']['workflow_state']}"
    )
    typer.echo(f"\nRun {run.run_id}: {summary.get('status', run.status.value)}")
    for s in summary.get("steps", []):
        mark = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}.get(
            s["status"], s["status"].upper()
        )
        typer.echo(f"  [{mark}] {s['id']}  {s.get('summary') or ''}".rstrip())


def _default_observer():
    """Return an observer that emits a workflow observation, or None if opted out.

    Real runs emit a sanitized ``workflow-observation.v1`` record to mqobsidian's
    local inbox so usage evidence accumulates. Best-effort and opt-out via
    ``MQ_WORKFLOW_OBSERVE=0``; emission never affects the run.
    """
    if os.environ.get("MQ_WORKFLOW_OBSERVE") == "0":
        return None

    def _observe(run, meta) -> None:
        import uuid
        from mq_agent.tools.execution_outcome import (
            emit_execution_outcome,
            execution_completeness_from_steps,
        )

        receipt = build_receipt(run)
        if not any(step.attempt > 0 for step in run.plan.steps):
            run.recording.update(observation=False, execution_outcome=False)
            return
        # Generated now and passed directly to the producer; never infer links
        # by scanning an outcome store or matching timestamps.
        run.execution_run_id = str(uuid.uuid4())
        fallback = None
        if receipt["fallback"]:
            fallback = {
                "from": "mq-mcp-tool-policy",
                "to": receipt["fallback"],
                "reason": "policy-unavailable-or-invalid",
                "stage": "workflow-policy",
                "source": "measured",
            }
        projected = []
        for step in run.plan.steps:
            data = (step.result or {}).get("data") or {}
            status = {
                "passed": "success",
                "failed": "failed",
                "skipped": "skipped",
            }.get(step.status.value, "pending")
            coverage = data.get("coverage")
            item: dict[str, Any] = {"status": status}
            if isinstance(coverage, dict):
                item.update(
                    source_item_count=coverage.get("changed_files"),
                    executed_call_count=coverage.get("reviewed_files"),
                    fan_out_complete=coverage.get("complete"),
                )
            projected.append(item)
        import contextlib
        import sys

        with contextlib.redirect_stdout(sys.stderr):
            written = emit_execution_outcome(
                run_id=run.execution_run_id,
                runtime="task-runner",
                task_class="task",
                result="PASS" if receipt["ok"] else "FAIL",
                exit_status="ok" if receipt["ok"] else "error",
                latency_ms=max(0, int(meta.get("duration_ms") or 0)),
                tool_calls=sum(step.attempt > 0 for step in run.plan.steps),
                fallbacks=1 if fallback else None,
                fallback=fallback,
                completeness=execution_completeness_from_steps(projected),
            )
        run.recording["execution_outcome"] = written is not None
        observed = emit_observation(
            run,
            duration_ms=meta.get("duration_ms"),
            approval_count=meta.get("approval_count", 0),
        )
        run.recording["observation"] = observed is not None

    return _observe


def _make_plan_approver(json_output: bool, yes: bool):
    """Return a plan-approval callback that prompts unless --yes was given."""

    def _approve(summary: str) -> bool:
        if yes:
            return True
        if json_output:
            return False  # never block on a prompt in JSON mode
        typer.echo("\n" + summary + "\n")
        return typer.confirm("Approve this plan?", default=False)

    return _approve


@workflow_app.command("run")
def run_cmd(
    template: str = typer.Argument(..., help="Template name, e.g. repo-preflight."),
    repo: str = typer.Option(..., "--repo", help="Target repository path."),
    json_output: bool = typer.Option(False, "--json", help="Emit the summary as JSON."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Approve the plan without prompting."
    ),
) -> None:
    """Instantiate, persist and execute a workflow against REPO (read-only)."""
    store = WorkflowStore()
    run_id = store.generate_run_id()
    try:
        plan = instantiate(template, repo=repo, run_id=run_id)
    except TemplateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    run = new_run(plan)
    try:
        bind_target(run)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    try:
        store.save_run(run)
    except OSError as exc:
        run.recording["workflow_state"] = False
        run.summary = {"ok": False, "status": "storage_failed", "error": str(exc)}
        _print_summary(run, json_output)
        raise typer.Exit(1)
    total = len(plan.steps)

    def _progress(step) -> None:
        typer.echo(f"[{step.attempt}] {step.id} — running {step.tool} …")

    if not json_output:
        typer.echo(
            f"Workflow: {template}  repo: {repo}  ({total} steps)  run: {run_id}"
        )
    try:
        Runner(
            store,
            plan_approver=_make_plan_approver(json_output, yes),
            on_step=_progress if not json_output else None,
            observer=_default_observer(),
        ).run(run)
    except OSError as exc:
        run.recording["workflow_state"] = False
        run.summary = {"ok": False, "status": "storage_failed", "error": str(exc)}
    _print_summary(run, json_output)
    raise typer.Exit(0 if (run.summary or {}).get("ok") else 1)


@workflow_app.command("status")
def status_cmd(
    run_id: str = typer.Argument(..., help="Run id, e.g. run_20260626_001."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show a run's current state. Does not execute anything."""
    store = WorkflowStore()
    try:
        run = store.load_run(run_id)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    if run.summary is None:
        run.summary = {
            "status": run.status.value,
            "steps": [
                {
                    "id": s.id,
                    "status": s.status.value,
                    "summary": (s.result or {}).get("summary") or s.error,
                }
                for s in run.plan.steps
            ],
        }
    _print_summary(run, json_output)


@workflow_app.command("resume")
def resume_cmd(
    run_id: str = typer.Argument(..., help="Run id of a paused or failed run."),
    json_output: bool = typer.Option(False, "--json"),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Approve the plan without prompting."
    ),
) -> None:
    """Resume a paused or failed run from where it stopped."""
    store = WorkflowStore()
    try:
        run = store.load_run(run_id)
        resume_state(run)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    try:
        store.save_run(run)
        Runner(
            store,
            plan_approver=_make_plan_approver(json_output, yes),
            observer=_default_observer(),
        ).run(run)
    except OSError as exc:
        run.recording["workflow_state"] = False
        run.summary = {"ok": False, "status": "storage_failed", "error": str(exc)}
    _print_summary(run, json_output)
    raise typer.Exit(0 if (run.summary or {}).get("ok") else 1)


def _print_checkpoint_status(report: dict, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return
    typer.echo(
        f"Checkpoint {report['checkpoint_id']}: {report['status']}  "
        f"run={report['run_id']}  expires={report['expires_at']}"
    )
    typer.echo("  passed: " + (", ".join(report["passed_steps"]) or "(none)"))
    typer.echo("  resumable: " + (", ".join(report["resumable_steps"]) or "(none)"))
    for error in report.get("errors", []):
        typer.echo(f"  REFUSE: {error}")


@checkpoint_app.command("create")
def checkpoint_create_cmd(
    run_id: str = typer.Argument(..., help="Paused or failed workflow run id."),
    owner: str = typer.Option(..., "--owner", help="Explicit checkpoint owner label."),
    ttl_hours: int = typer.Option(
        24,
        "--ttl-hours",
        min=1,
        max=168,
        help="Checkpoint lifetime in hours (1-168).",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Create a bounded content-addressed checkpoint over one workflow run."""
    from .checkpoint import WorkflowCheckpointError, WorkflowCheckpointStore

    checkpoints = WorkflowCheckpointStore()
    try:
        payload = checkpoints.create(
            run_id,
            owner=owner,
            ttl_hours=ttl_hours,
        )
    except WorkflowCheckpointError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(
        f"Checkpoint {payload['checkpoint_id']} created for {run_id}; "
        f"expires {payload['expires_at']}"
    )


@checkpoint_app.command("status")
def checkpoint_status_cmd(
    checkpoint_id: str = typer.Argument(..., help="sha256 checkpoint id."),
    owner: str = typer.Option(..., "--owner", help="Expected checkpoint owner label."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify checkpoint integrity, expiry, run identity, and template identity."""
    from .checkpoint import WorkflowCheckpointError, WorkflowCheckpointStore

    checkpoints = WorkflowCheckpointStore()
    try:
        report = checkpoints.verify(checkpoint_id, owner=owner)
    except WorkflowCheckpointError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    _print_checkpoint_status(report, json_output)
    if report["status"] != "READY":
        raise typer.Exit(1)


@checkpoint_app.command("resume")
def checkpoint_resume_cmd(
    checkpoint_id: str = typer.Argument(..., help="sha256 checkpoint id."),
    owner: str = typer.Option(..., "--owner", help="Expected checkpoint owner label."),
    approve: bool = typer.Option(
        False,
        "--approve",
        help="Required to persist resume state and execute remaining workflow steps.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Verify checkpoint and show the resume plan without writing or executing.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Resume exactly one verified checkpoint; fail closed on drift or expiry."""
    from .checkpoint import WorkflowCheckpointError, WorkflowCheckpointStore

    if not dry_run and not approve:
        raise typer.BadParameter(
            "workflow checkpoint resume requires --approve unless --dry-run is used"
        )

    store = WorkflowStore()
    checkpoints = WorkflowCheckpointStore(store)
    try:
        payload, run = checkpoints.prepare_resume(
            checkpoint_id,
            owner=owner,
        )
    except WorkflowCheckpointError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    if dry_run:
        report = checkpoints.verify(checkpoint_id, owner=owner)
        report["action"] = "WOULD_RESUME"
        report["would_execute_steps"] = list(payload["run"]["resumable_steps"])
        _print_checkpoint_status(report, json_output)
        return

    try:
        resume_state(run)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    # Persist first. This intentionally changes the run fingerprint and makes
    # the checkpoint single-use before any tool execution begins.
    store.save_run(run)
    Runner(
        store,
        plan_approver=lambda summary: True,
        observer=_default_observer(),
    ).run(run)
    _print_summary(run, json_output)
    raise typer.Exit(0 if (run.summary or {}).get("ok") else 1)


@workflow_app.command("cancel")
def cancel_cmd(
    run_id: str = typer.Argument(..., help="Run id to cancel."),
) -> None:
    """Cancel a run."""
    store = WorkflowStore()
    try:
        run = store.cancel_run(run_id)
    except WorkflowStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(f"Run {run.run_id}: {run.status.value}")


@workflow_app.command("do")
def do_cmd(
    task: str = typer.Argument(
        ..., help="Explicit supported task, e.g. granska ändringarna."
    ),
    repo: str = typer.Option(..., "--repo"),
    plan_only: bool = typer.Option(
        False, "--plan", help="Show selection and plan without execution or writes."
    ),
    json_output: bool = typer.Option(False, "--json"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Select one approved template deterministically, then use its policy gates."""
    from dataclasses import asdict
    from .selection import select_task, SelectionError

    try:
        selection = select_task(task)
        store = WorkflowStore()
        run = new_run(instantiate(selection.template, repo, store.generate_run_id()))
        bind_target(run)
    except (SelectionError, TemplateError, ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    run.selection = asdict(selection)
    report = {
        "selection": run.selection,
        "target": run.repo_identity,
        "requirements": {
            "required": ["mq-mcp"]
            + (
                ["OpenAI review credential in MCP server"]
                if selection.template == "review-and-test"
                else []
            ),
            "optional": ["repo-signal", "codegraph"]
            if selection.template == "review-and-test"
            else [],
            "effects": [
                "workflow state",
                "sanitized observation",
                "tests may write caches",
            ],
        },
        "plan": run.plan.model_dump(mode="json", by_alias=True),
    }
    if plan_only:
        typer.echo(json.dumps(report, indent=2))
        return
    if not json_output:
        typer.echo(f"Selected {selection.template}: {selection.reason}")
    try:
        store.save_run(run)
        Runner(
            store,
            plan_approver=_make_plan_approver(json_output, yes),
            observer=_default_observer(),
        ).run(run)
    except OSError as exc:
        run.recording["workflow_state"] = False
        run.summary = {"ok": False, "status": "storage_failed", "error": str(exc)}
    _print_summary(run, json_output)
    raise typer.Exit(0 if (run.summary or {}).get("ok") else 1)


@workflow_app.command("receipt")
def receipt_cmd(
    run_id: str = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Read the current measured receipt; does not execute workflow tools."""
    try:
        run = WorkflowStore().load_run(run_id)
    except WorkflowStateError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(build_receipt(run), indent=2))
    else:
        _print_summary(run, False)
