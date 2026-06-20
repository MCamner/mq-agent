"""Stack cockpit — one merged view of the whole mq-stack.

Combines per-repo git state, contract gate, release gate, unreleased work,
and mqobsidian brain-export freshness into a single read-only snapshot with
a recommended next action per repo. Later the input to mq-hal.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

# Repos that are part of the stack but excluded from contract/release gates
# (kept in sync with the gate exclusions in stack_tools).
GATE_EXCLUDED = {"mqobsidian"}


def _truth_note_freshness() -> dict[str, Any]:
    """Locate the latest stack-truth note in mqobsidian and rate its age."""
    from mq_agent.tools.stack_truth import DEFAULT_STACK_TRUTH_DIR

    notes = (
        sorted(DEFAULT_STACK_TRUTH_DIR.glob("*-mq-stack-truth.md"))
        if DEFAULT_STACK_TRUTH_DIR.exists()
        else []
    )
    if not notes:
        return {"path": None, "date": None, "age_days": None, "status": "none"}
    latest = notes[-1]
    try:
        note_date = datetime.strptime(latest.name[:10], "%Y-%m-%d").date()
    except ValueError:
        return {"path": str(latest), "date": None, "age_days": None, "status": "unknown"}
    age = (datetime.now(UTC).date() - note_date).days
    status = "fresh" if age <= 1 else "aging" if age <= 7 else "stale"
    return {"path": str(latest), "date": note_date.isoformat(), "age_days": age, "status": status}


def _action_contract(
    text: str,
    *,
    source_command: str,
    severity: str,
    suggested_route: str,
    requires_approval: bool,
    repo: str | None = None,
) -> dict[str, Any]:
    """Machine-readable next-action contract for mq-hal."""
    payload: dict[str, Any] = {
        "text": text,
        "source_command": source_command,
        "severity": severity,
        "suggested_route": suggested_route,
        "requires_approval": requires_approval,
    }
    if repo:
        payload["repo"] = repo
    return payload


def _next_action_contract(
    name: str,
    release: dict[str, Any],
    contract: dict[str, Any] | None,
    notes: dict[str, Any],
    excluded: bool = False,
) -> dict[str, Any]:
    """Single recommended next step for one repo, highest-severity first."""
    source = "mq-agent stack cockpit"
    if excluded:
        # Gate-excluded repos (the memory vault) only surface local hygiene.
        if release.get("dirty"):
            return _action_contract(
                "commit or stash uncommitted changes",
                source_command=source,
                severity="attention",
                suggested_route="git hygiene",
                requires_approval=True,
                repo=name,
            )
        return _action_contract(
            "—",
            source_command=source,
            severity="info",
            suggested_route="none",
            requires_approval=False,
            repo=name,
        )
    if contract and contract.get("status") in ("BLOCKED", "DRIFT"):
        return _action_contract(
            f"fix contract: {contract.get('reason', contract['status'])}",
            source_command=source,
            severity="blocked",
            suggested_route="mq-agent stack contract-check",
            requires_approval=True,
            repo=name,
        )
    if release.get("blockers"):
        return _action_contract(
            f"fix blocker: {release['blockers'][0]}",
            source_command=source,
            severity="blocked",
            suggested_route="mq-agent stack release-check",
            requires_approval=True,
            repo=name,
        )
    if release.get("dirty"):
        return _action_contract(
            "commit or stash uncommitted changes",
            source_command=source,
            severity="attention",
            suggested_route="git hygiene",
            requires_approval=True,
            repo=name,
        )
    if not release.get("on_main"):
        return _action_contract(
            f"switch to main (on {release.get('branch')})",
            source_command=source,
            severity="attention",
            suggested_route="git switch main",
            requires_approval=True,
            repo=name,
        )
    if release.get("unpushed", 0) > 0:
        return _action_contract(
            f"push {release['unpushed']} commit(s)",
            source_command=source,
            severity="attention",
            suggested_route="git push",
            requires_approval=True,
            repo=name,
        )
    if notes.get("has_changes"):
        return _action_contract(
            f"stack release --repo {name}",
            source_command=source,
            severity="attention",
            suggested_route=f"mq-agent stack release --repo {name}",
            requires_approval=True,
            repo=name,
        )
    return _action_contract(
        "up to date",
        source_command=source,
        severity="info",
        suggested_route="none",
        requires_approval=False,
        repo=name,
    )


def _cockpit_entry(entry: dict[str, str]) -> dict[str, Any]:
    from mq_agent.tools.stack_tools import (
        _contract_entry,
        _release_entry,
        _release_notes_entry,
    )

    name = entry["name"]
    release = _release_entry(entry)
    if not release.get("exists"):
        action = _action_contract(
            "clone repo locally",
            source_command="mq-agent stack cockpit",
            severity="blocked",
            suggested_route="git clone",
            requires_approval=True,
            repo=name,
        )
        return {
            "repo": name,
            "role": entry["role"],
            "exists": False,
            "version": "—",
            "branch": "—",
            "dirty": False,
            "contract": "—",
            "gate": "NO-GO",
            "unreleased": 0,
            "next_action": action["text"],
            "next_action_contract": action,
        }

    excluded = name in GATE_EXCLUDED
    contract = None if excluded else _contract_entry(entry)
    notes = _release_notes_entry(entry)
    action = _next_action_contract(name, release, contract, notes, excluded=excluded)

    return {
        "repo": name,
        "role": entry["role"],
        "exists": True,
        "version": release.get("version", "?"),
        "branch": release.get("branch", "—"),
        "dirty": bool(release.get("dirty")),
        "contract": contract["status"] if contract else "—",
        "gate": "—" if excluded else ("GO" if release.get("go") else "NO-GO"),
        "unreleased": len(notes.get("commits", [])),
        "last_tag": notes.get("last_tag"),
        "warnings": release.get("warnings", []),
        "blockers": release.get("blockers", []),
        "next_action": action["text"],
        "next_action_contract": action,
    }


def stack_cockpit() -> str:
    """One-table stack cockpit: repo, version, branch, dirty, contract,
    release gate, unreleased commits, brain-export freshness, next action.

    Read-only. Returns JSON with per-repo rows plus a stack-level summary.
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS

    repos = [_cockpit_entry(r) for r in MQ_STACK_REPOS]
    gated = [r for r in repos if r["repo"] not in GATE_EXCLUDED]
    truth = _truth_note_freshness()

    overall_gate = "GO" if all(r["gate"] == "GO" for r in gated) else "NO-GO"
    overall_contract = (
        "READY"
        if all(r["contract"] in ("READY", "REVIEW") for r in gated)
        else "NOT READY"
    )

    pending = [r for r in repos if r["next_action"] not in ("up to date", "—")]
    if pending:
        stack_next = f"{pending[0]['repo']}: {pending[0]['next_action']}"
        stack_action = {**pending[0]["next_action_contract"], "text": stack_next}
    elif truth["status"] in ("stale", "none"):
        stack_next = "run stack truth-export — brain note is " + truth["status"]
        stack_action = _action_contract(
            stack_next,
            source_command="mq-agent stack cockpit",
            severity="attention",
            suggested_route="mq-agent stack truth-export",
            requires_approval=True,
        )
    else:
        stack_next = "all green"
        stack_action = _action_contract(
            stack_next,
            source_command="mq-agent stack cockpit",
            severity="info",
            suggested_route="none",
            requires_approval=False,
        )

    return json.dumps({
        "overall_gate": overall_gate,
        "overall_contract": overall_contract,
        "brain_export": truth,
        "next_action": stack_next,
        "next_action_contract": stack_action,
        "repos": repos,
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2)
