"""Read-only drift check between the declared branch-protection contract,
GitHub's actual protection, and the contexts a real pull request reports.

Three layers, because two of them can agree while the third is wrong:

    declared (branch_protection.yaml)
        -> GitHub branch protection
        -> the check-runs a pull_request event actually produces

Two defect classes fall out of that, and this module names them separately
because the fix is different:

  PROTECTION_DRIFT
      GitHub no longer matches the contract: a required check is gone, an
      `app_id` was un-pinned, `strict` or `enforce_admins` was turned off.

  CHECK_SURFACE_DRIFT
      Protection matches the contract, but the workflows moved underneath it.
      Three shapes, one layer:

        - a required context is no longer reported by `pull_request`, which
          leaves every PR waiting forever with no visible cause;
        - the same context is reported twice, because a workflow carries a
          bare `push:` as well as `pull_request:`, in which case which run
          satisfies the requirement is undefined;
        - a context is reported that the contract neither requires nor
          excludes. That one is a gate that can go red without blocking
          anything, which is how a real check quietly becomes decorative.
          Every reported context must be classified, either as required or
          as excluded with a stated reason.

Both were found by hand in one session. This exists so they are found by a
command instead.

Deliberately read-only: every GitHub call is a GET. Applying protection is a
separate, explicit operation (`github_branch_protection.py --apply --approve`),
because a PUT replaces the entire protection object and silently drops
anything the payload omits.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

CONTRACT_SCHEMA = "mq.branch-protection-contract.v1"

# GitHub Actions. A required context with app_id null can be satisfied by any
# app that can post a check run.
GITHUB_ACTIONS_APP_ID = 15368

_SOURCE_CONTRACT = Path(__file__).resolve().parents[1] / "data" / "branch_protection.yaml"


class GhJsonClient(Protocol):
    def json(self, *args: str) -> Any: ...


class GhReadOnly:
    """A gh client that can only read. Every method here issues a GET."""

    def json(self, *args: str) -> Any:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout)


def load_contract(path: Path | None = None) -> dict[str, Any]:
    """Read and sanity-check the declared contract."""
    source = path or _SOURCE_CONTRACT
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if data.get("schema") != CONTRACT_SCHEMA:
        raise ValueError(f"{source}: expected schema {CONTRACT_SCHEMA}, got {data.get('schema')!r}")
    for name, repo in data.get("repos", {}).items():
        if not repo.get("required_checks"):
            raise ValueError(f"{source}: {name} declares no required_checks")
    return data


def declared_for(contract: dict[str, Any], repo: str) -> dict[str, Any]:
    """Merge the stack defaults with one repo's entry."""
    entry = contract["repos"][repo]
    merged = dict(contract.get("defaults", {}))
    merged.update({k: v for k, v in entry.items() if k != "required_checks"})
    merged["required_checks"] = entry["required_checks"]
    return merged


def read_protection(gh: GhJsonClient, owner: str, repo: str, branch: str) -> dict[str, Any] | None:
    """GET the protection object, or None when the branch is unprotected."""
    try:
        return gh.json("api", f"repos/{owner}/{repo}/branches/{branch}/protection")
    except RuntimeError as exc:
        if "Branch not protected" in str(exc) or "404" in str(exc):
            return None
        raise


def compare_protection(declared: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Return one message per difference between the contract and GitHub.

    Reads `required_status_checks.checks`, not the deprecated `contexts`,
    because only `checks` carries `app_id` — and an un-pinned context is a
    real weakening that `contexts` cannot show.
    """
    problems: list[str] = []
    rsc = actual.get("required_status_checks") or {}

    if rsc.get("strict") != declared["strict"]:
        problems.append(f"strict is {rsc.get('strict')!r}, contract says {declared['strict']!r}")

    for field, path in (
        ("enforce_admins", "enforce_admins"),
        ("allow_force_pushes", "allow_force_pushes"),
        ("allow_deletions", "allow_deletions"),
    ):
        got = (actual.get(path) or {}).get("enabled")
        if got != declared[field]:
            problems.append(f"{field} is {got!r}, contract says {declared[field]!r}")

    conv = (actual.get("required_conversation_resolution") or {}).get("enabled")
    if conv != declared["required_conversation_resolution"]:
        problems.append(
            f"required_conversation_resolution is {conv!r}, contract says "
            f"{declared['required_conversation_resolution']!r}"
        )

    # None means the whole required_pull_request_reviews object is absent, which
    # is a different state from "present, requiring zero approvals".
    reviews = actual.get("required_pull_request_reviews")
    approvals = reviews.get("required_approving_review_count") if reviews else None
    if approvals != declared["required_approving_reviews"]:
        problems.append(
            f"required approving reviews is {approvals!r}, contract says "
            f"{declared['required_approving_reviews']!r}"
        )

    want = {c["name"]: c["app_id"] for c in declared["required_checks"]}
    have = {c["context"]: c.get("app_id") for c in rsc.get("checks", [])}

    for name in sorted(set(want) - set(have)):
        problems.append(f"required check {name!r} is not enforced")
    for name in sorted(set(have) - set(want)):
        problems.append(f"{name!r} is enforced but not in the contract")
    for name in sorted(set(want) & set(have)):
        if have[name] != want[name]:
            got = have[name]
            detail = "any app may satisfy it" if got is None else f"app_id {got}"
            problems.append(f"required check {name!r} is not pinned to app {want[name]}: {detail}")

    return problems


def compare_check_surface(declared: dict[str, Any], check_runs: list[dict[str, Any]]) -> list[str]:
    """Return one message per difference between the contract and a real PR.

    `check_runs` is the raw list from
    `repos/{owner}/{repo}/commits/{sha}/check-runs` for the head of a pull
    request.

    Counting matters: a name appearing twice means the workflow fires on both
    `push` and `pull_request` for the same SHA, and GitHub matches required
    checks on the name while ignoring the event.

    So does the reverse direction. Every GitHub Actions context the pull
    request reports must be classified — required, or excluded with a reason.
    An unclassified one is a gate nobody decided about: it runs on every PR,
    can go red, and blocks nothing. Checks from other apps are left alone,
    because a third-party integration posting a check run is not a gate this
    contract governs.
    """
    problems: list[str] = []
    counts: dict[str, int] = {}
    ours: set[str] = set()
    for run in check_runs:
        name = run.get("name", "")
        counts[name] = counts.get(name, 0) + 1
        if (run.get("app") or {}).get("id") == GITHUB_ACTIONS_APP_ID:
            ours.add(name)

    required = {check["name"] for check in declared["required_checks"]}
    excluded = {item["name"] for item in declared.get("excluded_checks", [])}

    for name in sorted(required):
        seen = counts.get(name, 0)
        if seen == 0:
            problems.append(
                f"required context {name!r} was not reported by the sampled pull request"
            )
        elif seen > 1:
            problems.append(
                f"context {name!r} was reported {seen} times on one commit "
                "(a workflow fires on both push and pull_request)"
            )

    for name in sorted(ours - required - excluded):
        problems.append(
            f"context {name!r} runs on pull requests but the contract neither "
            "requires nor excludes it: it can go red without blocking anything"
        )

    return problems


def latest_pr_head(gh: GhJsonClient, owner: str, repo: str) -> str | None:
    """Head SHA of the most recent pull request, merged or not."""
    pulls = gh.json(
        "pr", "list", "-R", f"{owner}/{repo}", "--state", "all",
        "--limit", "1", "--json", "headRefOid",
    )
    if not pulls:
        return None
    return pulls[0].get("headRefOid") or None


def protection_entry(gh: GhJsonClient, contract: dict[str, Any], repo: str) -> dict[str, Any]:
    """Check one repo across all three layers.

    Status meanings:
      PASS                 contract, GitHub and the sampled PR all agree
      MISSING              the branch has no protection at all
      PROTECTION_DRIFT     GitHub does not match the contract
      CHECK_SURFACE_DRIFT  GitHub matches, but the workflows moved under it
      BLOCKED              the check could not run (no gh, no network, no PRs)
    """
    owner = contract["owner"]
    branch = contract["branch"]
    declared = declared_for(contract, repo)
    entry: dict[str, Any] = {"name": repo, "branch": branch}

    try:
        actual = read_protection(gh, owner, repo, branch)
    except RuntimeError as exc:
        return {**entry, "status": "BLOCKED", "reasons": [f"could not read protection: {exc}"]}

    if actual is None:
        return {
            **entry,
            "status": "MISSING",
            "reasons": [f"{branch} is not protected; contract declares "
                        f"{len(declared['required_checks'])} required checks"],
        }

    problems = compare_protection(declared, actual)
    if problems:
        return {**entry, "status": "PROTECTION_DRIFT", "reasons": problems}

    try:
        sha = latest_pr_head(gh, owner, repo)
    except RuntimeError as exc:
        return {**entry, "status": "BLOCKED", "reasons": [f"could not list pull requests: {exc}"]}

    if sha is None:
        return {
            **entry,
            "status": "BLOCKED",
            "reasons": ["no pull request to sample the check surface from"],
        }

    try:
        runs = gh.json("api", f"repos/{owner}/{repo}/commits/{sha}/check-runs?per_page=100")
    except RuntimeError as exc:
        return {**entry, "status": "BLOCKED", "reasons": [f"could not read check runs: {exc}"]}

    surface = compare_check_surface(declared, runs.get("check_runs", []))
    if surface:
        return {**entry, "status": "CHECK_SURFACE_DRIFT", "sampled_commit": sha, "reasons": surface}

    return {
        **entry,
        "status": "PASS",
        "sampled_commit": sha,
        "reasons": [],
        "required_checks": [c["name"] for c in declared["required_checks"]],
    }


FAILING = ("MISSING", "PROTECTION_DRIFT", "CHECK_SURFACE_DRIFT")


def stack_protection_check(
    gh: GhJsonClient | None = None,
    contract_path: Path | None = None,
    only: str | None = None,
) -> str:
    """Compare every declared repo against GitHub and a real pull request."""
    contract = load_contract(contract_path)
    client = gh or GhReadOnly()

    names = list(contract["repos"])
    if only:
        if only not in contract["repos"]:
            raise ValueError(f"{only!r} is not in the contract; known: {', '.join(names)}")
        names = [only]

    entries = [protection_entry(client, contract, name) for name in names]
    failed = [e for e in entries if e["status"] in FAILING]

    return json.dumps(
        {
            "overall": "PASS" if not failed else "DRIFT",
            "contract": contract["schema"],
            "owner": contract["owner"],
            "branch": contract["branch"],
            "reasons": [f"{e['name']}: {r}" for e in failed for r in e["reasons"]],
            "repos": entries,
            "checked_at": datetime.now(UTC).isoformat(),
        },
        indent=2,
    )
