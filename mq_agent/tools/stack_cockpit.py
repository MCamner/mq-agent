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


def _next_action(
    name: str, release: dict[str, Any], contract: dict[str, Any] | None, notes: dict[str, Any],
    excluded: bool = False,
) -> str:
    """Single recommended next step for one repo, highest-severity first."""
    if excluded:
        # Gate-excluded repos (the memory vault) only surface local hygiene.
        return "commit or stash uncommitted changes" if release.get("dirty") else "—"
    if contract and contract.get("status") in ("BLOCKED", "DRIFT"):
        return f"fix contract: {contract.get('reason', contract['status'])}"
    if release.get("blockers"):
        return f"fix blocker: {release['blockers'][0]}"
    if release.get("dirty"):
        return "commit or stash uncommitted changes"
    if not release.get("on_main"):
        return f"switch to main (on {release.get('branch')})"
    if release.get("unpushed", 0) > 0:
        return f"push {release['unpushed']} commit(s)"
    if notes.get("has_changes"):
        return f"stack release --repo {name}"
    return "up to date"


def _cockpit_entry(entry: dict[str, str]) -> dict[str, Any]:
    from mq_agent.tools.stack_tools import (
        _contract_entry,
        _release_entry,
        _release_notes_entry,
    )

    name = entry["name"]
    release = _release_entry(entry)
    if not release.get("exists"):
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
            "next_action": "clone repo locally",
        }

    excluded = name in GATE_EXCLUDED
    contract = None if excluded else _contract_entry(entry)
    notes = _release_notes_entry(entry)

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
        "next_action": _next_action(name, release, contract, notes, excluded=excluded),
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
    elif truth["status"] in ("stale", "none"):
        stack_next = "run stack truth-export — brain note is " + truth["status"]
    else:
        stack_next = "all green"

    return json.dumps({
        "overall_gate": overall_gate,
        "overall_contract": overall_contract,
        "brain_export": truth,
        "next_action": stack_next,
        "repos": repos,
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2)
