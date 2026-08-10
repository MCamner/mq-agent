"""Read-only release cockpit state, evidence, and operator guidance."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "mq_release_cockpit.v1"
STATES = (
    "IDLE", "BLOCKED", "PREFLIGHT_READY", "PREPARED_PR", "PR_GREEN",
    "MERGED", "FINALIZED", "PUBLISHED", "AUDITED",
)


@dataclass(frozen=True)
class ReleaseEvidence:
    repo: str
    path: str
    path_exists: bool
    current_version: str
    target_version: str | None
    latest_tag: str | None
    latest_tag_type: str | None
    latest_tag_target: str | None
    head_commit: str | None
    origin_main_commit: str | None
    branch: str | None
    clean: bool
    synced_main: bool
    release_mode: str | None
    release_check: str
    contract_check: str
    stack_preflight: str
    main_ci: str
    pull_request: dict[str, Any] | None
    github_release: dict[str, Any]
    unavailable: list[str] = field(default_factory=list)
    check_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StateResult:
    state: str
    blockers: list[dict[str, str]]
    next_action: dict[str, Any]


def _blockers(evidence: ReleaseEvidence) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        blockers.append({"code": code, "message": message})

    if not evidence.path_exists:
        add("REPO_MISSING", f"{evidence.repo}: repository path does not exist")
        return blockers
    if not evidence.clean:
        add("DIRTY_TREE", f"{evidence.repo}: working tree has uncommitted changes")
    if evidence.branch not in ("main", "master"):
        add("WRONG_BRANCH", f"{evidence.repo}: expected main, found {evidence.branch or 'detached HEAD'}")
    if not evidence.synced_main:
        add("MAIN_NOT_SYNCED", f"{evidence.repo}: local main differs from origin/main")
    if evidence.release_mode not in ("direct", "pull_request"):
        add("RELEASE_MODE_BLOCKED", f"{evidence.repo}: release_mode is {evidence.release_mode!r}")
    if evidence.release_check != "READY":
        add("RELEASE_CHECK_FAILED", f"{evidence.repo}: release-check is {evidence.release_check}")
    if evidence.contract_check != "READY":
        add("CONTRACT_CHECK_FAILED", f"{evidence.repo}: contract-check is {evidence.contract_check}")
    if evidence.stack_preflight == "BLOCKED":
        add("PREFLIGHT_BLOCKED", f"{evidence.repo}: stack preflight is blocked")
    if evidence.main_ci == "FAIL":
        add("CI_FAILED", f"{evidence.repo}: main CI is failing")
    if evidence.unavailable:
        add(
            "EVIDENCE_UNAVAILABLE",
            f"{evidence.repo}: unavailable evidence: {', '.join(sorted(evidence.unavailable))}",
        )

    pr = evidence.pull_request or {}
    merge_commit = pr.get("merge_commit")
    target_tag = f"v{evidence.target_version}" if evidence.target_version else None
    if not evidence.target_version and evidence.latest_tag != f"v{evidence.current_version}":
        add(
            "VERSION_TAG_MISMATCH",
            f"{evidence.repo}: VERSION {evidence.current_version} does not align with latest tag {evidence.latest_tag!r}",
        )
    if (
        evidence.target_version and (pr.get("state") == "MERGED" or evidence.latest_tag == target_tag)
        and evidence.current_version != evidence.target_version
    ):
        add(
            "TARGET_VERSION_MISMATCH",
            f"{evidence.repo}: VERSION {evidence.current_version} does not match target {evidence.target_version}",
        )
    if target_tag and evidence.latest_tag == target_tag and merge_commit:
        if evidence.latest_tag_target != merge_commit:
            add("WRONG_TAG_TARGET", f"{target_tag} does not target verified merge commit {merge_commit}")
    elif target_tag and evidence.latest_tag == target_tag and pr.get("state") != "MERGED":
        add("TAG_BEFORE_MERGE", f"{target_tag} exists before a verified release PR merge")
    return blockers


def _action(state: str, evidence: ReleaseEvidence, blockers: list[dict[str, str]]) -> dict[str, Any]:
    if state == "BLOCKED":
        code = blockers[0]["code"]
        actions = {
            "REPO_MISSING": ("Restore the repository checkout", None, True),
            "DIRTY_TREE": ("Clean the working tree", "git status --short", False),
            "WRONG_BRANCH": ("Switch to main", "git switch main", False),
            "MAIN_NOT_SYNCED": ("Synchronize local main", "git pull --ff-only", False),
            "RELEASE_MODE_BLOCKED": ("Correct the release-mode contract", None, True),
            "RELEASE_CHECK_FAILED": ("Fix the repository release check", "./release-check.sh --dry-run --json", False),
            "CONTRACT_CHECK_FAILED": ("Fix the repository contract", "mq-agent stack contract-check --json", False),
            "PREFLIGHT_BLOCKED": ("Resolve stack preflight blockers", "mq-agent stack release --all --preflight --json", False),
            "CI_FAILED": ("Fix failing main CI", None, True),
            "VERSION_TAG_MISMATCH": ("Align VERSION and the latest release tag", None, True),
            "TARGET_VERSION_MISMATCH": ("Align VERSION with the release target", None, True),
            "EVIDENCE_UNAVAILABLE": ("Restore unavailable release evidence", None, True),
            "WRONG_TAG_TARGET": ("Investigate the incorrect tag target", None, True),
            "TAG_BEFORE_MERGE": ("Investigate the premature release tag", None, True),
        }
        label, command, human = actions[code]
        return {"label": label, "command": command, "requires_human": human}
    if state == "IDLE":
        return {"label": "Choose a target version", "command": None, "requires_human": True}
    if state == "PREFLIGHT_READY":
        command = f"mq-agent stack release --repo {evidence.repo} --version {evidence.target_version}"
        return {"label": "Review the release plan", "command": command, "requires_human": True}
    if state == "PREPARED_PR":
        return {"label": "Wait for review and green CI", "command": None, "requires_human": True}
    if state == "PR_GREEN":
        return {"label": "Review and merge the release PR", "command": None, "requires_human": True}
    if state == "MERGED":
        return {"label": "Finalize the verified merge", "command": None, "requires_human": True}
    if state == "FINALIZED":
        return {"label": "Publish the GitHub Release", "command": None, "requires_human": True}
    if state == "PUBLISHED":
        command = f"mq-agent ship audit --repo {evidence.path} --target {evidence.target_version}"
        return {"label": "Audit the published release", "command": command, "requires_human": False}
    return {"label": "No action needed", "command": None, "requires_human": False}


def resolve_release_state(evidence: ReleaseEvidence, *, audited: bool = False) -> StateResult:
    """Resolve exactly one state using explicit highest-risk-first precedence."""
    blockers = _blockers(evidence)
    if blockers:
        state = "BLOCKED"
    else:
        pr = evidence.pull_request or {}
        target_tag = f"v{evidence.target_version}" if evidence.target_version else None
        tag_matches = bool(target_tag and evidence.latest_tag == target_tag)
        merge_commit = pr.get("merge_commit")
        finalized = bool(
            tag_matches and evidence.latest_tag_type == "tag" and merge_commit
            and evidence.latest_tag_target == merge_commit
        )
        published = finalized and bool(evidence.github_release.get("published"))
        if audited and published:
            state = "AUDITED"
        elif published:
            state = "PUBLISHED"
        elif finalized:
            state = "FINALIZED"
        elif pr.get("state") == "MERGED" and merge_commit:
            state = "MERGED"
        elif (
            pr.get("state") == "OPEN" and pr.get("ci") == "PASS"
            and pr.get("review_decision") in ("APPROVED", "REVIEW_NOT_REQUIRED")
        ):
            state = "PR_GREEN"
        elif pr.get("state") == "OPEN":
            state = "PREPARED_PR"
        elif evidence.target_version and evidence.stack_preflight == "READY":
            state = "PREFLIGHT_READY"
        else:
            state = "IDLE"
    return StateResult(state, blockers, _action(state, evidence, blockers))


def build_release_cockpit(
    evidence: ReleaseEvidence, *, command: str, audited: bool = False,
) -> dict[str, Any]:
    result = resolve_release_state(evidence, audited=audited)
    return {
        "schema": SCHEMA,
        "command": command,
        "checked_at": datetime.now(UTC).isoformat(),
        "state": result.state,
        "safe_to_release": result.state == "PREFLIGHT_READY",
        "repo": {
            "name": evidence.repo, "path": evidence.path, "branch": evidence.branch,
            "path_exists": evidence.path_exists,
            "head_commit": evidence.head_commit,
            "origin_main_commit": evidence.origin_main_commit,
            "clean": evidence.clean, "synced_main": evidence.synced_main,
            "release_mode": evidence.release_mode,
        },
        "release": {
            "current_version": evidence.current_version,
            "target_version": evidence.target_version,
            "latest_tag": evidence.latest_tag,
            "latest_tag_type": evidence.latest_tag_type,
            "latest_tag_target": evidence.latest_tag_target,
        },
        "checks": {
            "release": evidence.release_check,
            "contract": evidence.contract_check,
            "stack_preflight": evidence.stack_preflight,
            "main_ci": evidence.main_ci,
            "unavailable": sorted(set(evidence.unavailable)),
            "evidence": evidence.check_evidence,
        },
        "pull_request": evidence.pull_request,
        "github_release": evidence.github_release,
        "blockers": result.blockers,
        "next_action": result.next_action,
    }


def _run(command: list[str], path: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, cwd=path, text=True, capture_output=True, timeout=60)
    except Exception as exc:  # pragma: no cover - platform failure boundary
        return False, str(exc)
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def _git(path: Path, *args: str) -> tuple[bool, str]:
    return _run(["git", *args], path)


def _gh(path: Path, *args: str) -> tuple[bool, str]:
    return _run(["gh", *args], path)


def _value(path: Path, *args: str) -> str | None:
    ok, output = _git(path, *args)
    return output if ok and output else None


def _release_pr(path: Path, target: str | None) -> tuple[dict[str, Any] | None, str | None]:
    ok, output = _gh(
        path, "pr", "list", "--state", "all", "--limit", "50", "--json",
        "number,url,state,headRefName,baseRefName,reviewDecision,statusCheckRollup,mergeCommit",
    )
    if not ok:
        return None, "github pull request"
    try:
        candidates = json.loads(output)
    except json.JSONDecodeError:
        return None, "github pull request"
    expected = f"mq/release-v{target}" if target else None
    prs = [item for item in candidates if item.get("baseRefName") == "main" and str(item.get("headRefName", "")).startswith("mq/release-v")]
    if expected:
        prs = [item for item in prs if item.get("headRefName") == expected]
    if not prs:
        return None, None
    raw = prs[0]
    checks = raw.get("statusCheckRollup") or []
    conclusions = [str(item.get("conclusion") or item.get("state") or "").upper() for item in checks]
    if any(value in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT") for value in conclusions):
        ci = "FAIL"
    elif conclusions and all(value in ("SUCCESS", "NEUTRAL", "SKIPPED") for value in conclusions):
        ci = "PASS"
    else:
        ci = "PENDING"
    merge = raw.get("mergeCommit") or {}
    return {
        "number": raw.get("number"), "url": raw.get("url"), "state": raw.get("state"),
        "head": raw.get("headRefName"), "base": raw.get("baseRefName"),
        "review_decision": raw.get("reviewDecision") or "REVIEW_NOT_REQUIRED",
        "ci": ci, "merge_commit": merge.get("oid") if isinstance(merge, dict) else None,
    }, None


def _main_ci(path: Path) -> tuple[str, str | None, dict[str, Any]]:
    ok, output = _gh(
        path, "run", "list", "--branch", "main", "--limit", "1", "--json",
        "status,conclusion,url,workflowName",
    )
    if not ok:
        return "UNAVAILABLE", "main CI", {"error": output}
    try:
        runs = json.loads(output)
    except json.JSONDecodeError:
        return "UNAVAILABLE", "main CI", {"error": "invalid GitHub response"}
    if not runs:
        return "UNAVAILABLE", "main CI", {"error": "no main CI run found"}
    run = runs[0]
    conclusion = str(run.get("conclusion") or "").upper()
    status = str(run.get("status") or "").upper()
    if conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED"):
        return "PASS", None, run
    if conclusion in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT"):
        return "FAIL", None, run
    return (
        ("PENDING" if status else "UNAVAILABLE"),
        (None if status else "main CI"),
        run,
    )


def collect_release_evidence(repo_path: str = ".", target: str | None = None) -> ReleaseEvidence:
    """Collect bounded local and GitHub evidence without changing repository state."""
    path = Path(repo_path).resolve()
    unavailable: list[str] = []
    if not path.is_dir():
        return ReleaseEvidence(
            repo=path.name or "unknown", path=str(path), path_exists=False,
            current_version="?", target_version=target, latest_tag=None,
            latest_tag_type=None, latest_tag_target=None, head_commit=None,
            origin_main_commit=None, branch=None, clean=False, synced_main=False,
            release_mode=None, release_check="UNAVAILABLE", contract_check="UNAVAILABLE",
            stack_preflight="UNAVAILABLE", main_ci="UNAVAILABLE", pull_request=None,
            github_release={"published": False, "url": None}, unavailable=[],
            check_evidence={},
        )
    version_path = path / "VERSION"
    current = version_path.read_text().strip() if version_path.exists() else "?"
    branch = _value(path, "branch", "--show-current")
    head = _value(path, "rev-parse", "HEAD")
    origin_main = _value(path, "rev-parse", "origin/main")
    clean = not bool(_value(path, "status", "--short"))
    latest_tag = _value(path, "describe", "--tags", "--abbrev=0")
    tag_type = _value(path, "cat-file", "-t", latest_tag) if latest_tag else None
    tag_target = _value(path, "rev-parse", f"{latest_tag}^{{commit}}") if latest_tag else None

    contract_path = path / ".mq" / "repo-contract.json"
    contract: dict[str, Any] = {}
    try:
        contract = json.loads(contract_path.read_text())
        contract_status = "READY" if contract.get("version") == current else "DRIFT"
    except (OSError, json.JSONDecodeError):
        contract_status = "BLOCKED"

    from mq_agent.tools.stack_release import _run_release_check, plan_stack_release
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _contract_entry, _expand

    release_ok, release_blockers = _run_release_check(path)
    release_status = "READY" if release_ok else "BLOCKED"
    repo_name = str(contract.get("repo") or path.name)
    stack_entry = next((item for item in MQ_STACK_REPOS if item["name"] == repo_name), None)
    if stack_entry and _expand(stack_entry["path"]).resolve() == path:
        contract_result = _contract_entry(stack_entry)
        contract_status = (
            "READY" if contract_result.get("status") == "READY"
            else str(contract_result.get("status") or "BLOCKED")
        )
    else:
        contract_result = {"status": contract_status, "reason": "repo is outside MQ_STACK_REPOS"}
    try:
        if not stack_entry or _expand(stack_entry["path"]).resolve() != path:
            raise ValueError("repo path is outside configured MQ stack")
        plan = plan_stack_release(repo_name, version=target or "")
        plan_blockers = list(plan.get("blockers", []))
        if not target and plan_blockers and all(item.startswith("no unreleased commits") for item in plan_blockers):
            preflight = "UP-TO-DATE"
        else:
            preflight = "READY" if plan.get("go") else "BLOCKED"
    except Exception:
        preflight = "UNAVAILABLE"
        plan_blockers = ["stack release plan could not be collected"]
        unavailable.append("stack preflight")

    pr, pr_error = _release_pr(path, target)
    if pr_error:
        unavailable.append(pr_error)
    main_ci, ci_error, ci_evidence = _main_ci(path)
    if ci_error:
        unavailable.append(ci_error)
    inferred_target = target
    if not inferred_target and pr:
        inferred_target = str(pr.get("head", "")).removeprefix("mq/release-v") or None

    release_tag = f"v{inferred_target}" if inferred_target else latest_tag
    github_release = {"published": False, "url": None}
    if release_tag:
        ok, output = _gh(path, "release", "view", release_tag, "--json", "url,isDraft,tagName")
        if ok:
            try:
                raw_release = json.loads(output)
                github_release = {
                    "published": not bool(raw_release.get("isDraft")),
                    "url": raw_release.get("url"), "tag": raw_release.get("tagName"),
                }
            except json.JSONDecodeError:
                unavailable.append("github release")
        elif "not found" not in output.lower() and "release does not exist" not in output.lower():
            unavailable.append("github release")

    return ReleaseEvidence(
        repo=repo_name, path=str(path), path_exists=True, current_version=current,
        target_version=inferred_target, latest_tag=latest_tag,
        latest_tag_type=tag_type, latest_tag_target=tag_target,
        head_commit=head, origin_main_commit=origin_main, branch=branch,
        clean=clean, synced_main=bool(head and origin_main and head == origin_main),
        release_mode=contract.get("release_mode"), release_check=release_status,
        contract_check=contract_status, stack_preflight=preflight,
        main_ci=main_ci, pull_request=pr, github_release=github_release,
        unavailable=unavailable,
        check_evidence={
            "release": {"blockers": release_blockers},
            "contract": contract_result,
            "stack_preflight": {"blockers": plan_blockers},
            "main_ci": ci_evidence,
        },
    )


def release_cockpit(
    *, command: str, repo_path: str = ".", target: str | None = None,
) -> dict[str, Any]:
    evidence = collect_release_evidence(repo_path, target)
    return build_release_cockpit(evidence, command=command, audited=command == "audit")
