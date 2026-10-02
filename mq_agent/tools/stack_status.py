"""Exact-head verification status for the MQ stack.

This module answers a narrower question than product-readiness or release
gates: what evidence exists for the exact commit currently checked out?

A repo is VERIFIED only when:
- its working tree is clean;
- every required GitHub Actions check declared by the branch-protection
  contract reported success for the exact local HEAD SHA; and
- the complete evidence set is not older than the configured freshness window.

Missing or in-progress evidence is UNVERIFIED, a completed non-success required
check is FAIL, and complete green evidence outside the freshness window is
STALE. No state is inferred from a previous commit.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mq_agent.tools.branch_protection_contract import (
    GITHUB_ACTIONS_APP_ID,
    GhJsonClient,
    GhReadOnly,
    load_contract,
)
from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand, _git, _last_activity, _version

STACK_STATUS_SCHEMA = "mq.stack-status.v2"
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
STACK_GITHUB_REPO_ALIASES = {"mqlaunch": "macos-scripts"}

_STATUS_PRIORITY = {
    "VERIFIED": 0,
    "STALE": 1,
    "UNVERIFIED": 2,
    "FAIL": 3,
}


def _configured_max_age_seconds() -> int:
    raw = os.environ.get("MQ_STACK_VERIFY_MAX_AGE_SECONDS", "")
    if not raw:
        return DEFAULT_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_AGE_SECONDS
    return value if value > 0 else DEFAULT_MAX_AGE_SECONDS


def _github_repo_name(entry: dict[str, str]) -> str:
    return entry.get("github_repo") or STACK_GITHUB_REPO_ALIASES.get(
        entry["name"], entry["name"]
    )


def _parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_evidence_age(age_seconds: int | None) -> str:
    """Compact age for the human stack-status table."""
    if age_seconds is None:
        return "—"
    if age_seconds < 60:
        return f"{age_seconds}s"
    if age_seconds < 3600:
        return f"{age_seconds // 60}m"
    if age_seconds < 86400:
        return f"{age_seconds // 3600}h"
    return f"{age_seconds // 86400}d"


def _latest_run(
    runs: list[dict[str, Any]],
    *,
    name: str,
    app_id: int | None,
) -> dict[str, Any] | None:
    candidates = []
    for run in runs:
        if run.get("name") != name:
            continue
        observed_app = (run.get("app") or {}).get("id")
        if app_id is not None and observed_app != app_id:
            continue
        candidates.append(run)
    if not candidates:
        return None

    def sort_key(run: dict[str, Any]) -> str:
        return str(run.get("completed_at") or run.get("started_at") or "")

    return max(candidates, key=sort_key)


def _scope_entry(run: dict[str, Any] | None, expected: dict[str, Any]) -> dict[str, Any]:
    name = str(expected["name"])
    if run is None:
        return {
            "name": name,
            "status": "MISSING",
            "conclusion": None,
            "completed_at": None,
            "details_url": None,
        }

    run_status = str(run.get("status") or "")
    conclusion = run.get("conclusion")
    completed_at = run.get("completed_at")
    details_url = run.get("details_url")

    if run_status != "completed":
        scope_status = "PENDING"
    elif conclusion == "success":
        scope_status = "PASS"
    else:
        scope_status = "FAIL"

    return {
        "name": name,
        "status": scope_status,
        "conclusion": conclusion,
        "completed_at": completed_at,
        "details_url": details_url,
    }


def _base_repo_entry(entry: dict[str, str], path: Path) -> dict[str, Any]:
    github_repo = _github_repo_name(entry)
    if not path.exists():
        return {
            "name": entry["name"],
            "github_repo": github_repo,
            "role": entry["role"],
            "exists": False,
            "version": None,
            "branch": None,
            "commit": None,
            "dirty": None,
            "last_activity": None,
        }

    return {
        "name": entry["name"],
        "github_repo": github_repo,
        "role": entry["role"],
        "exists": True,
        "version": _version(path),
        "branch": _git(["branch", "--show-current"], path) or None,
        "commit": _git(["rev-parse", "HEAD"], path) or None,
        "dirty": bool(_git(["status", "--porcelain"], path)),
        "last_activity": _last_activity(path),
    }


def _unverified(
    base: dict[str, Any],
    reason: str,
    *,
    expected_scopes: list[str] | None = None,
    evidence_source: str = "github-check-runs",
) -> dict[str, Any]:
    expected = expected_scopes or []
    return {
        **base,
        "verification": {
            "status": "UNVERIFIED",
            "evidence_source": evidence_source,
            "expected_scopes": expected,
            "verified_scopes": [],
            "verified_count": 0,
            "required_count": len(expected),
            "verified_at": None,
            "age_seconds": None,
            "reason": reason,
            "scopes": [],
        },
    }


def repo_verification_entry(
    entry: dict[str, str],
    *,
    gh: GhJsonClient,
    contract: dict[str, Any],
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    """Build one exact-head verification entry without mutating the repo."""
    path = _expand(entry["path"])
    base = _base_repo_entry(entry, path)
    repo_name = base["github_repo"]

    if not base["exists"]:
        return _unverified(base, "repo-not-found")

    sha = base["commit"]
    if not sha:
        return _unverified(base, "no-head-commit")

    contract_repo = (contract.get("repos") or {}).get(repo_name)
    if contract_repo is None:
        return _unverified(base, "verification-contract-missing")

    required = list(contract_repo.get("required_checks") or [])
    expected_names = [str(item["name"]) for item in required]
    if not required:
        return _unverified(base, "verification-contract-has-no-required-checks")

    owner = str(contract.get("owner") or "")
    if not owner:
        return _unverified(base, "verification-contract-owner-missing", expected_scopes=expected_names)

    try:
        payload = gh.json(
            "api",
            f"repos/{owner}/{repo_name}/commits/{sha}/check-runs?per_page=100",
        )
    except RuntimeError as exc:
        return _unverified(
            base,
            f"github-unavailable: {exc}",
            expected_scopes=expected_names,
        )

    runs = list((payload or {}).get("check_runs") or [])
    scopes = [
        _scope_entry(
            _latest_run(
                runs,
                name=str(expected["name"]),
                app_id=expected.get("app_id", GITHUB_ACTIONS_APP_ID),
            ),
            expected,
        )
        for expected in required
    ]

    failed = [scope["name"] for scope in scopes if scope["status"] == "FAIL"]
    incomplete = [
        scope["name"] for scope in scopes if scope["status"] in {"MISSING", "PENDING"}
    ]
    verified_scopes = [scope["name"] for scope in scopes if scope["status"] == "PASS"]

    completed_times = [
        parsed
        for scope in scopes
        if scope["status"] == "PASS"
        for parsed in [_parse_github_time(scope.get("completed_at"))]
        if parsed is not None
    ]
    # Verification becomes complete when the final required check finishes.
    verified_at_dt = max(completed_times) if len(completed_times) == len(scopes) else None
    age_seconds = (
        max(0, int((now - verified_at_dt).total_seconds()))
        if verified_at_dt is not None
        else None
    )

    if failed:
        status = "FAIL"
        reason = f"required-check-failed: {', '.join(failed)}"
    elif incomplete:
        status = "UNVERIFIED"
        reason = f"required-check-evidence-incomplete: {', '.join(incomplete)}"
    elif base["dirty"]:
        status = "UNVERIFIED"
        reason = "working-tree-dirty"
    elif verified_at_dt is None:
        status = "UNVERIFIED"
        reason = "required-check-completion-time-missing"
    elif age_seconds is not None and age_seconds > max_age_seconds:
        status = "STALE"
        reason = f"evidence-older-than-{max_age_seconds}s"
    else:
        status = "VERIFIED"
        reason = "all-required-checks-passed"

    return {
        **base,
        "verification": {
            "status": status,
            "evidence_source": "github-check-runs",
            "expected_scopes": expected_names,
            "verified_scopes": verified_scopes,
            "verified_count": len(verified_scopes),
            "required_count": len(expected_names),
            "verified_at": verified_at_dt.isoformat() if verified_at_dt else None,
            "age_seconds": age_seconds,
            "reason": reason,
            "scopes": scopes,
        },
    }


def build_stack_status_v2(
    *,
    gh: GhJsonClient | None = None,
    contract: dict[str, Any] | None = None,
    repos: list[dict[str, str]] | None = None,
    now: datetime | None = None,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    """Collect exact-head verification evidence for the configured stack."""
    client = gh or GhReadOnly()
    declared = contract or load_contract()
    inventory = repos or MQ_STACK_REPOS
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    freshness = max_age_seconds or _configured_max_age_seconds()

    entries = [
        repo_verification_entry(
            entry,
            gh=client,
            contract=declared,
            now=checked_at,
            max_age_seconds=freshness,
        )
        for entry in inventory
    ]
    overall = max(
        (item["verification"]["status"] for item in entries),
        key=lambda status: _STATUS_PRIORITY[status],
        default="UNVERIFIED",
    )

    return {
        "schema": STACK_STATUS_SCHEMA,
        "checked_at": checked_at.isoformat(),
        "max_age_seconds": freshness,
        "overall": overall,
        "repos": entries,
    }


def stack_status_v2(**kwargs: Any) -> str:
    """JSON serialization wrapper used by the CLI and tool registry."""
    return json.dumps(build_stack_status_v2(**kwargs), indent=2)
