"""Read-only skill inventory, task profile and route commands."""

import json
from pathlib import Path
from typing import Annotated

import typer

from mq_agent.skills.inventory import load_inventory, repository_name, resolve_repo
from mq_agent.skills.profile import profile_task
from mq_agent.skills.render import render_route
from mq_agent.skills.route import route_skills
from mq_agent.skills.vocabulary import ContractError, load_contracts, reason

app = typer.Typer(
    help="Inspect and select local skills for a task.", no_args_is_help=True
)
Repo = Annotated[str, typer.Option("--repo", help="Repository name or directory")]
Vault = Annotated[
    Path | None,
    typer.Option(
        "--vault",
        help="mqobsidian contracts; defaults to MQ_OBSIDIAN_DIR or ~/mqobsidian",
    ),
]
Target = Annotated[str, typer.Option("--target", help="codex, claude, or both")]
Json = Annotated[bool, typer.Option("--json")]


def _repo(value: str) -> Path:
    try:
        return resolve_repo(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--repo") from exc


def _contracts(vault: Path | None) -> tuple[dict, dict]:
    try:
        return load_contracts(vault)
    except ContractError as exc:
        typer.echo(
            json.dumps(
                {"selection_state": "invalid", "reasons": [reason(exc.code, str(exc))]}
            )
        )
        raise typer.Exit(2) from exc


def _target(value: str) -> None:
    if value not in ("codex", "claude", "both"):
        raise typer.BadParameter("Use codex, claude, or both", param_hint="--target")


@app.command("route")
def route(
    task: str,
    repo: Repo = ".",
    target: Target = "codex",
    vault: Vault = None,
    json_out: Json = False,
    explain: Annotated[bool, typer.Option("--explain")] = False,
):
    """Select skills deterministically; 0 complete/empty, 1 partial, 2 invalid."""
    _target(target)
    details: list = []
    result = route_skills(
        task, _repo(repo), target=target, vault=vault, explain=details
    )
    typer.echo(
        json.dumps(result, indent=2)
        if json_out
        else render_route(result, details if explain else None)
    )
    raise typer.Exit({"partial": 1, "invalid": 2}.get(result["selection_state"], 0))


@app.command("inventory")
def inventory(repo: Repo = ".", vault: Vault = None, json_out: Json = False):
    """Show profiles, support and actual discovery separately."""
    root = _repo(repo)
    vocabulary, schemas = _contracts(vault)
    result = load_inventory(root, vocabulary, schemas["mq.skill-profile.v1"])
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        for entry in result["entries"]:
            p = entry["profile"]
            typer.echo(
                f"{p['skill']}: supported={','.join(p['supported_targets'])}; discovered={','.join(entry['discoverable_targets']) or 'none'}"
            )
        typer.echo("Unprofiled: " + (", ".join(result["unprofiled"]) or "none"))
        for item in result["reasons"]:
            typer.echo(f"{item['code']}: {item['skill']} — {item['message']}")
    raise typer.Exit(2 if result["reasons"] else 0)


@app.command("profile")
def profile(
    task: str,
    repo: Repo = ".",
    target: Target = "codex",
    vault: Vault = None,
    json_out: Json = False,
):
    """Show vocabulary matches without selecting or running skills."""
    _target(target)
    root = _repo(repo)
    vocabulary, _ = _contracts(vault)
    result = profile_task(task, repository_name(root), target, vocabulary)
    payload = dict(
        task=task,
        repo=repository_name(root),
        target=target,
        **result.facets(),
        matched_terms=list(result.matched_terms),
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2))
    else:
        for key, value in payload.items():
            typer.echo(
                f"{key}: {', '.join(value) if isinstance(value, list) else value}"
            )
