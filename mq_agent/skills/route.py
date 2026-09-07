"""Compose local I/O with the pure selector into mq.skill-route.v1."""

from pathlib import Path

from mq_agent.skills.inventory import load_inventory, repository_name
from mq_agent.skills.profile import profile_task
from mq_agent.skills.selector import select_skills
from mq_agent.skills.vocabulary import ContractError, load_contracts, reason, validate


def route_skills(
    task: str,
    repo: Path,
    *,
    target: str = "codex",
    vault: Path | None = None,
    explain: list | None = None,
) -> dict:
    if target not in ("codex", "claude", "both"):
        raise ValueError("target must be codex, claude, or both")
    result = dict(
        schema="mq.skill-route.v1",
        task=task,
        repo=repository_name(repo),
        target=target,
        profile=dict(intents=[], domains=[], risks=[]),
        selected=[],
        missing_required=[],
        selection_state="invalid",
        reasons=[],
        candidate_count=0,
    )
    try:
        vocabulary, schemas = load_contracts(vault)
    except ContractError as exc:
        result["reasons"] = [reason(exc.code, str(exc))]
        return result
    profile = profile_task(task, repository_name(repo), target, vocabulary)
    inventory = load_inventory(repo, vocabulary, schemas["mq.skill-profile.v1"])
    selection, explanation = select_skills(profile, inventory, vocabulary)
    result.update(selection, profile=profile.facets())
    if explain is not None:
        explain.extend(explanation)
    validate(result, schemas["mq.skill-route.v1"])
    return result
