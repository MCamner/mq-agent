"""Inspect and apply conservative GitHub default-branch protection.

The declared standard lives in `mq_agent/data/branch_protection.yaml` and is
verified read-only by `mq-agent stack protection-check`. This module is the
write half, and it must produce exactly what that contract declares — a writer
that emits something else turns every apply into drift by construction.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from typing import Any, Protocol


# GitHub Actions. A required context whose app_id is null can be satisfied by
# any app able to post a check run, so every context is pinned.
GITHUB_ACTIONS_APP_ID = 15368

# Jobs that never report on a pull request, so requiring them would leave every
# PR waiting forever. This is a blunt denylist and it is not enough on its own:
# `examples` (push-to-main only) and `Contract and release gates` (skipped on
# PRs by its own `if:`) are excluded per repo in branch_protection.yaml, with a
# reason each. Always confirm against a real pull_request event.
IGNORED_CHECKS = {"build", "deploy", "report-build-status"}


class ApprovalRequired(RuntimeError):
    pass


class ExistingProtectionError(RuntimeError):
    pass


class GhJsonClient(Protocol):
    def json(self, *args: str) -> Any: ...


class Gh:
    def json(self, *args: str) -> Any:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout)

    def put_json(self, endpoint: str, payload: dict[str, Any]) -> Any:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump(payload, handle)
            handle.flush()
            return self.json("api", "--method", "PUT", endpoint, "--input", handle.name)


def parse_checks(value: str) -> list[str]:
    return sorted({item.strip() for item in value.split(",") if item.strip()})


def discover_pr_checks(gh: GhJsonClient, repo: str) -> list[str]:
    """Context names reported by the most recent pull request.

    Refuses when a name appears more than once on the same commit. That means a
    workflow carries a bare `push:` as well as `pull_request:` and fires twice
    on one SHA; required checks match on the name and ignore the event, so
    which run satisfies the requirement is undefined. Discovering a name from
    an ambiguous surface and then requiring it bakes the ambiguity in, so the
    duplicate has to be fixed first.
    """
    pulls = gh.json(
        "pr",
        "list",
        "-R",
        repo,
        "--state",
        "all",
        "--limit",
        "1",
        "--json",
        "headRefOid",
    )
    if not pulls:
        raise ValueError(
            "No pull request found. Pass --checks or --no-required-checks."
        )

    sha = pulls[0].get("headRefOid")
    if not sha:
        raise ValueError("Latest pull request has no head commit.")

    result = gh.json("api", f"repos/{repo}/commits/{sha}/check-runs")
    counts: dict[str, int] = {}
    for run in result.get("check_runs", []):
        name = run.get("name")
        if name in IGNORED_CHECKS or run.get("app", {}).get("slug") != "github-actions":
            continue
        counts[name] = counts.get(name, 0) + 1

    duplicated = sorted(name for name, n in counts.items() if n > 1)
    if duplicated:
        raise ValueError(
            "These contexts are reported more than once on the same commit, so "
            "which run satisfies a required check is undefined: "
            + ", ".join(duplicated)
            + ". Scope the workflow's `push:` trigger to the default branch first."
        )

    if not counts:
        raise ValueError(
            "No GitHub Actions checks found on the latest pull request. "
            "Pass --checks or --no-required-checks."
        )
    return sorted(counts)


def build_protection_payload(
    checks: list[str], app_id: int = GITHUB_ACTIONS_APP_ID
) -> dict[str, Any]:
    """The PUT body for one branch, matching branch_protection.yaml.

    Uses the `checks` form, never the deprecated `contexts` form. They look
    equivalent and are not: `contexts` sets every app_id to null, which means
    any app that can post a check run satisfies that context. A read-back shows
    the same context names either way, so the weakening is invisible unless you
    look at app_id.

    A PUT replaces the entire protection object, so every nullable field is
    sent explicitly. Anything omitted is cleared.
    """
    required_status_checks = (
        {
            "strict": True,
            "checks": [{"context": name, "app_id": app_id} for name in checks],
        }
        if checks
        else None
    )
    return {
        "required_status_checks": required_status_checks,
        "enforce_admins": True,
        # No review requirement: these are single-maintainer repos, and a
        # required approval nobody can give blocks every PR. The gate here is
        # the status checks, not a second pair of eyes.
        "required_pull_request_reviews": None,
        "restrictions": None,
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": False,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def require_apply_approval(*, apply: bool, approve: bool) -> None:
    if apply and not approve:
        raise ApprovalRequired("--apply requires explicit --approve")


def ensure_replace_allowed(
    status: dict[str, Any], *, replace_existing: bool
) -> None:
    if status.get("protected") and not replace_existing:
        raise ExistingProtectionError(
            "Default branch already has protection. Inspect it first and pass "
            "--replace-existing only when replacement is intentional."
        )


def repo_info(gh: Gh, repo: str | None) -> tuple[str, str, str]:
    args = ["repo", "view"]
    if repo:
        args.append(repo)
    args.extend(["--json", "nameWithOwner,defaultBranchRef,viewerPermission"])
    result = gh.json(*args)
    return (
        result["nameWithOwner"],
        result["defaultBranchRef"]["name"],
        result["viewerPermission"],
    )


def protection_status(gh: Gh, repo: str, branch: str) -> dict[str, Any]:
    try:
        protection = gh.json("api", f"repos/{repo}/branches/{branch}/protection")
    except RuntimeError as exc:
        if "Branch not protected" in str(exc) or "HTTP 404" in str(exc):
            return {"repo": repo, "branch": branch, "protected": False}
        raise
    return {
        "repo": repo,
        "branch": branch,
        "protected": True,
        "strict": protection.get("required_status_checks", {}).get("strict"),
        "checks": protection.get("required_status_checks", {}).get("contexts", []),
        "enforce_admins": protection.get("enforce_admins", {}).get("enabled"),
        "required_approvals": protection.get("required_pull_request_reviews", {}).get(
            "required_approving_review_count"
        ),
        "conversation_resolution": protection.get(
            "required_conversation_resolution", {}
        ).get("enabled"),
        "force_pushes": protection.get("allow_force_pushes", {}).get("enabled"),
        "deletions": protection.get("allow_deletions", {}).get("enabled"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or protect a GitHub repository's default branch."
    )
    parser.add_argument("repo", nargs="?", help="OWNER/REPO; defaults to current repo")
    parser.add_argument("--apply", action="store_true", help="Apply branch protection")
    parser.add_argument(
        "--approve", action="store_true", help="Approve the external GitHub mutation"
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace an existing protection rule after inspecting it",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--checks", help="Comma-separated required check contexts"
    )
    group.add_argument(
        "--no-required-checks",
        action="store_true",
        help="Require pull requests without status checks",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_apply_approval(apply=args.apply, approve=args.approve)
        gh = Gh()
        repo, branch, permission = repo_info(gh, args.repo)
        if not args.apply:
            print(json.dumps(protection_status(gh, repo, branch), indent=2))
            return 0
        if permission != "ADMIN":
            raise RuntimeError(f"Admin permission required; current permission: {permission}")
        ensure_replace_allowed(
            protection_status(gh, repo, branch),
            replace_existing=args.replace_existing,
        )

        if args.no_required_checks:
            checks = []
        elif args.checks:
            checks = parse_checks(args.checks)
        else:
            checks = discover_pr_checks(gh, repo)

        endpoint = f"repos/{repo}/branches/{branch}/protection"
        gh.put_json(endpoint, build_protection_payload(checks))
        status = protection_status(gh, repo, branch)
        if not status.get("protected"):
            raise RuntimeError("GitHub did not report the branch as protected after apply")
        print(json.dumps(status, indent=2))
        return 0
    except (ApprovalRequired, ExistingProtectionError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
