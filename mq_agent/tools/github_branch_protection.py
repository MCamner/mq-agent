"""Inspect and apply conservative GitHub default-branch protection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from typing import Any


IGNORED_CHECKS = {"build", "deploy", "report-build-status"}


class ApprovalRequired(RuntimeError):
    pass


class ExistingProtectionError(RuntimeError):
    pass


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


def discover_pr_checks(gh: Gh, repo: str) -> list[str]:
    pulls = gh.json(
        "pr",
        "list",
        "-R",
        repo,
        "--state",
        "merged",
        "--limit",
        "1",
        "--json",
        "headRefOid",
    )
    if not pulls:
        raise ValueError(
            "No merged pull request found. Pass --checks or --no-required-checks."
        )

    sha = pulls[0].get("headRefOid")
    if not sha:
        raise ValueError("Latest merged pull request has no head commit.")

    result = gh.json("api", f"repos/{repo}/commits/{sha}/check-runs")
    checks = {
        run["name"]
        for run in result.get("check_runs", [])
        if run.get("name") not in IGNORED_CHECKS
        and run.get("app", {}).get("slug") == "github-actions"
    }
    if not checks:
        raise ValueError(
            "No GitHub Actions checks found on the latest merged pull request. "
            "Pass --checks or --no-required-checks."
        )
    return sorted(checks)


def build_protection_payload(checks: list[str]) -> dict[str, Any]:
    required_status_checks = (
        {"strict": True, "contexts": checks} if checks else None
    )
    return {
        "required_status_checks": required_status_checks,
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
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
