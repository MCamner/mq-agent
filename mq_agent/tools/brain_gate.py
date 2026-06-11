"""Brain release gate — the pre-release checklist for the brain-integrated stack.

Before a release, the whole memory loop must be green, not just the repo
gates: contracts valid, release gate GO, the truth note renderable, the vault
structured, and the review→brain write path wired. This gate runs all of it
read-only — nothing is written, no review is executed.

The five checks:

1. contract-check  — stack contract gate overall READY
2. release-check   — stack release gate overall GO
3. truth-export    — dry-run: the truth note renders and has a target path
4. vault-structure — the standard mqobsidian export structure is complete
5. brain-review    — mq-mcp reachable with review_repo + brain_record_review,
                     i.e. `review repo --brain` would have a working path

Safety class: A — read-only.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

BRAIN_REVIEW_TOOLS = ("review_repo", "brain_record_review")


def _check(name: str, ok: bool, detail: str, hint: str = "") -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "status": "PASS" if ok else "FAIL", "detail": detail}
    if not ok and hint:
        entry["hint"] = hint
    return entry


def _contract_check() -> dict[str, Any]:
    from mq_agent.tools.stack_tools import stack_contract_check

    data = json.loads(stack_contract_check())
    overall = data.get("overall", "UNKNOWN")
    reasons = data.get("reasons", [])
    detail = overall if not reasons else f"{overall} — {reasons[0]}"
    return _check("contract-check", overall == "READY", detail,
                  hint="mq-agent stack contract-check")


def _release_check() -> dict[str, Any]:
    from mq_agent.tools.stack_tools import stack_release_check

    data = json.loads(stack_release_check())
    overall = data.get("overall", "UNKNOWN")
    blockers = [
        f"{r.get('name')}: {b}"
        for r in data.get("repos", []) for b in r.get("blockers", [])
    ]
    detail = overall if not blockers else f"{overall} — {blockers[0]}"
    return _check("release-check", overall == "GO", detail,
                  hint="mq-agent stack release-check")


def _truth_export_dry_run() -> dict[str, Any]:
    from mq_agent.tools.stack_truth import stack_truth_export

    result = stack_truth_export(write=False)
    ok = bool(result.get("markdown")) and bool(result.get("path")) and not result.get("written")
    detail = f"dry-run ok — would write {result.get('path')}" if ok else "truth note did not render"
    return _check("truth-export", ok, detail,
                  hint="mq-agent stack truth-export --dry-run")


def _vault_structure_check() -> dict[str, Any]:
    from mq_agent.tools.vault_structure import vault_structure

    data = json.loads(vault_structure())
    status = data.get("status", "UNKNOWN")
    missing = [d["path"] for d in data.get("dirs", []) if not d.get("exists")]
    detail = status if not missing else f"{status} — missing: {', '.join(missing)}"
    return _check("vault-structure", status == "OK", detail,
                  hint="mq-agent brain structure --init --approve")


def _brain_review_path() -> dict[str, Any]:
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    if not bridge.is_available():
        return _check("brain-review", False, "mq-mcp not reachable",
                      hint="mq-agent mcp start")
    names = {spec.name for spec in bridge.list_tool_specs()}
    missing = [t for t in BRAIN_REVIEW_TOOLS if t not in names]
    if missing:
        return _check("brain-review", False, f"missing tools: {', '.join(missing)}",
                      hint="upgrade mq-mcp, then run mq-agent mcp tools")
    return _check("brain-review", True,
                  "review repo --brain path wired (review_repo + brain_record_review)")


def brain_release_gate() -> str:
    """Run the brain release gate. Read-only; returns a JSON string."""
    checks = [
        _contract_check(),
        _release_check(),
        _truth_export_dry_run(),
        _vault_structure_check(),
        _brain_review_path(),
    ]
    failed = [c for c in checks if c["status"] == "FAIL"]
    return json.dumps({
        "overall": "GO" if not failed else "NO-GO",
        "checks": checks,
        "next_action": failed[0].get("hint", failed[0]["detail"]) if failed
        else "all green — release away",
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2)
