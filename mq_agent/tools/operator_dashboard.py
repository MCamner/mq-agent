"""Operator dashboard snapshot for mq-agent."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


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

    if actionable:
        cockpit_action = cockpit.get("next_action")
        if cockpit_action and cockpit_action != "all green":
            next_action = cockpit_action
        else:
            first = actionable[0]
            next_action = f"{first.get('repo')}: {first.get('next_action')}"
    elif not brain_ready:
        next_action = f"run stack truth-export — brain note is {brain_status}"
    elif not ollama_ok:
        next_action = inventory.get("hint") or inventory.get("detail") or "check Ollama runtime"
    else:
        next_action = "all green"

    overall = "READY" if stack_ready and brain_ready and ollama_ok else "ATTENTION"

    return json.dumps({
        "overall": overall,
        "next_action": next_action,
        "stack": {
            "gate": cockpit.get("overall_gate"),
            "contract": cockpit.get("overall_contract"),
            "repo_count": len(repos),
            "actionable_count": len(actionable),
            "dirty_count": len(dirty),
            "release_blocked_count": len(release_blocked),
        },
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
            }
            for r in repos
        ],
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2, default=str)
