"""Operator dashboard snapshot for mq-agent."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

OPERATOR_DASHBOARD_SCHEMA = "mq_operator_dashboard.v1"


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _dashboard_action_contract(
    text: str,
    *,
    severity: str,
    suggested_route: str,
    requires_approval: bool,
) -> dict[str, Any]:
    return {
        "text": text,
        "source_command": "mq-agent dashboard",
        "severity": severity,
        "suggested_route": suggested_route,
        "requires_approval": requires_approval,
    }


def _compatibility_summary() -> dict[str, Any]:
    """Static compatibility verdict for the dashboard.

    Static only: the dashboard is a fast read-only snapshot, and a fresh
    resolution shells out to uv and needs a registry. A summary that cannot be
    produced is UNAVAILABLE — the dashboard must not fail because one section
    could not be read.

    The whole stack, not the MCP slice: the dashboard speaks for the stack, and
    reporting two repos' verdict as the stack's would hide an incompatibility
    between any of the others.
    """
    from mq_agent.tools.stack_compatibility import build_report

    try:
        report = build_report(slice_only=False)
    except Exception:
        return {
            "status": "UNAVAILABLE",
            "mode": "static",
            "blocking_count": 0,
            "next_action": "run mq-agent stack compatibility to see why",
        }

    return {
        "status": report["status"],
        "mode": report["mode"],
        "blocking_count": sum(1 for f in report["findings"] if f["blocks_release"]),
        "next_action": report["next_action"],
    }


def operator_dashboard() -> str:
    """Return a read-only operator snapshot for stack, brain, Ollama and contracts."""
    from mq_agent.tools.model_runtime import current_model, list_ollama_models
    from mq_agent.tools.stack_cockpit import stack_cockpit

    cockpit = json.loads(stack_cockpit())
    repos = cockpit.get("repos", [])
    actionable = [r for r in repos if r.get("next_action") not in ("up to date", "—")]
    dirty = [r for r in repos if r.get("dirty")]
    release_blocked = [r for r in repos if r.get("gate") == "NO-GO"]
    contract_counts = _count_by(repos, "contract")

    model = current_model()
    inventory = list_ollama_models()
    ollama_ok = bool(inventory.get("ok"))

    stack_ready = (
        cockpit.get("overall_gate") == "GO"
        and cockpit.get("overall_contract") == "READY"
        and not actionable
    )
    brain_status = cockpit.get("brain_export", {}).get("status")
    brain_ready = brain_status in ("fresh", "aging")

    # Only a proven incompatibility counts against the dashboard. WARN is the
    # normal state while repos are still declaring their boundary, and
    # UNAVAILABLE says the check could not run, not that the stack is broken.
    compatibility = _compatibility_summary()
    compatible = compatibility["status"] != "FAIL"

    # A release-blocking incompatibility comes before repo chores: it outranks
    # a dirty tree or an unswitched branch, and nothing else in the stack can
    # be finished around it.
    if not compatible:
        next_action = compatibility["next_action"] or "resolve the stack incompatibility"
        next_action_contract = _dashboard_action_contract(
            next_action,
            severity="attention",
            suggested_route="mq-agent stack compatibility",
            requires_approval=True,
        )
    elif actionable:
        cockpit_action = cockpit.get("next_action")
        if cockpit_action and cockpit_action != "all green":
            next_action = cockpit_action
            next_action_contract = cockpit.get("next_action_contract")
        else:
            first = actionable[0]
            next_action = f"{first.get('repo')}: {first.get('next_action')}"
            next_action_contract = {
                **first.get("next_action_contract", {}),
                "text": next_action,
            } if first.get("next_action_contract") else _dashboard_action_contract(
                next_action,
                severity="attention",
                suggested_route="mq-agent stack cockpit",
                requires_approval=True,
            )
    elif not brain_ready:
        next_action = f"run stack truth-export — brain note is {brain_status}"
        next_action_contract = _dashboard_action_contract(
            next_action,
            severity="attention",
            suggested_route="mq-agent stack truth-export",
            requires_approval=True,
        )
    elif not ollama_ok:
        next_action = inventory.get("hint") or inventory.get("detail") or "check Ollama runtime"
        next_action_contract = _dashboard_action_contract(
            next_action,
            severity="attention",
            suggested_route="ollama runtime",
            requires_approval=False,
        )
    else:
        next_action = "all green"
        next_action_contract = _dashboard_action_contract(
            next_action,
            severity="info",
            suggested_route="none",
            requires_approval=False,
        )

    overall = (
        "READY"
        if stack_ready and brain_ready and ollama_ok and compatible
        else "ATTENTION"
    )

    return json.dumps({
        "schema": OPERATOR_DASHBOARD_SCHEMA,
        "overall": overall,
        "next_action": next_action,
        "next_action_contract": next_action_contract,
        "stack": {
            "gate": cockpit.get("overall_gate"),
            "contract": cockpit.get("overall_contract"),
            "repo_count": len(repos),
            "actionable_count": len(actionable),
            "dirty_count": len(dirty),
            "release_blocked_count": len(release_blocked),
        },
        "compatibility": compatibility,
        "brain": cockpit.get("brain_export", {}),
        "ollama": {
            "ok": ollama_ok,
            "profile": model.get("profile"),
            "model": model.get("model"),
            "models": inventory.get("models", []),
            "detail": inventory.get("detail") or inventory.get("raw", ""),
            "hint": inventory.get("hint"),
        },
        "contracts": contract_counts,
        "repos": [
            {
                "repo": r.get("repo"),
                "role": r.get("role"),
                "version": r.get("version"),
                "branch": r.get("branch"),
                "dirty": r.get("dirty"),
                "contract": r.get("contract"),
                "gate": r.get("gate"),
                "next_action": r.get("next_action"),
                "next_action_contract": r.get("next_action_contract"),
            }
            for r in repos
        ],
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2, default=str)
