"""Stack release orchestration — gated single-repo release pipeline.

Closes the loop: the stack suite observes, gates, remembers, and drafts —
`stack release` makes it act. A release is planned (dry-run) by default and
only applied with execute=True. Any failed step aborts the run; file edits
made before the release commit are rolled back so no repo is half-released.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUMP_PARTS = ("patch", "minor", "major")

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _run_git(args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run git and return (ok, combined output). Never raises."""
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=cwd, text=True, capture_output=True, timeout=60,
        )
        out = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, out
    except Exception as exc:
        return False, str(exc)


def bump_version(version: str, part: str) -> str:
    """Bump a semver X.Y.Z string by patch/minor/major."""
    m = _SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"not a semver version: {version!r}")
    major, minor, patch = (int(x) for x in m.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump part: {part!r} (expected one of {BUMP_PARTS})")


def _version_files(repo_path: Path) -> list[Path]:
    """Files that carry the repo version and must be updated on release."""
    files = [repo_path / name for name in ("VERSION", "version.txt") if (repo_path / name).exists()]
    if (repo_path / "pyproject.toml").exists():
        files.append(repo_path / "pyproject.toml")
    return files


def _write_version(repo_path: Path, new_version: str) -> list[Path]:
    """Write the new version to every version-carrying file. Returns changed files."""
    changed: list[Path] = []
    for f in _version_files(repo_path):
        if f.name == "pyproject.toml":
            text = f.read_text()
            updated = re.sub(
                r'^(version\s*=\s*")[^"]+(")', rf"\g<1>{new_version}\g<2>",
                text, count=1, flags=re.MULTILINE,
            )
            if updated != text:
                f.write_text(updated)
                changed.append(f)
        else:
            f.write_text(new_version + "\n")
            changed.append(f)
    return changed


def _sync_contract(repo_path: Path, new_version: str) -> Path | None:
    """Update version in .mq/repo-contract.json so the contract gate stays READY."""
    contract_path = repo_path / ".mq" / "repo-contract.json"
    if not contract_path.exists():
        return None
    contract = json.loads(contract_path.read_text())
    contract["version"] = new_version
    contract_path.write_text(json.dumps(contract, indent=2) + "\n")
    return contract_path


def _update_changelog(repo_path: Path, new_version: str, commits: list[str]) -> Path | None:
    """Insert a release section drafted from commits since the last tag."""
    cl = repo_path / "CHANGELOG.md"
    if not cl.exists():
        return None
    today = datetime.now(UTC).date().isoformat()
    section_lines = [f"## [v{new_version}] — {today}", ""]
    section_lines.extend(f"* {c}" for c in commits)
    section = "\n".join(section_lines)

    text = cl.read_text()
    if "## [Unreleased]" in text:
        text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n{section}", 1)
    else:
        m = re.search(r"^## \[", text, re.MULTILINE)
        if m:
            text = text[: m.start()] + section + "\n\n" + text[m.start() :]
        else:
            text = text.rstrip("\n") + "\n\n" + section + "\n"
    cl.write_text(text)
    return cl


def plan_stack_release(
    repo: str, bump: str = "patch", version: str = "",
) -> dict[str, Any]:
    """Build a release plan for one stack repo. Read-only — never mutates the repo.

    The plan is GO only when the release gate passes, the repo is clean and on
    main, there are unreleased commits, and the target version is valid.
    """
    from mq_agent.tools.stack_tools import (
        MQ_STACK_REPOS,
        _expand,
        _release_entry,
        _release_notes_entry,
    )

    plan: dict[str, Any] = {
        "repo": repo,
        "go": False,
        "blockers": [],
        "warnings": [],
        "steps": [],
        "planned_at": datetime.now(UTC).isoformat(),
    }

    entry = next((r for r in MQ_STACK_REPOS if r["name"] == repo), None)
    if entry is None:
        plan["blockers"].append(f"unknown stack repo: {repo!r}")
        return plan

    path = _expand(entry["path"])
    if not path.exists():
        plan["blockers"].append("repo not found locally")
        return plan
    plan["path"] = str(path)

    gate = _release_entry(entry)
    notes = _release_notes_entry(entry)
    plan["gate"] = gate
    plan["warnings"] = list(gate.get("warnings", []))

    blockers: list[str] = list(gate.get("blockers", []))
    if not gate.get("on_main"):
        blockers.append(f"not on main/master (branch: {gate.get('branch')})")
    if gate.get("dirty"):
        blockers.append("uncommitted changes — release requires a clean tree")
    if not notes.get("has_changes"):
        blockers.append(f"no unreleased commits since {notes.get('last_tag') or 'repo start'}")

    current = gate.get("version", "?")
    plan["current_version"] = current
    if version:
        if not _SEMVER_RE.match(version):
            blockers.append(f"explicit version is not semver: {version!r}")
        new_version = version
    else:
        try:
            new_version = bump_version(current, bump)
        except ValueError as exc:
            blockers.append(str(exc))
            new_version = "?"
    plan["new_version"] = new_version

    plan["commits"] = notes.get("commits", [])
    plan["last_tag"] = notes.get("last_tag")
    plan["blockers"] = blockers
    plan["go"] = not blockers
    if not plan["go"]:
        return plan

    has_contract = (path / ".mq" / "repo-contract.json").exists()
    has_changelog = (path / "CHANGELOG.md").exists()
    tag = f"v{new_version}"
    plan["tag"] = tag
    plan["steps"] = [
        {"step": "bump-version", "detail": f"{current} → {new_version}"},
        *([{"step": "sync-contract", "detail": ".mq/repo-contract.json"}] if has_contract else []),
        *([{"step": "update-changelog", "detail": f"{len(plan['commits'])} commit(s) since {plan['last_tag'] or 'start'}"}] if has_changelog else []),
        {"step": "commit", "detail": f"release: {tag}"},
        {"step": "tag", "detail": tag},
        {"step": "push", "detail": "git push"},
        {"step": "push-tag", "detail": f"git push origin {tag}"},
        {"step": "truth-export", "detail": "write stack truth note to mqobsidian"},
    ]
    return plan


def plan_stack_release_all(bump: str = "patch") -> dict[str, Any]:
    """Plan a release for every stack repo at once. Read-only — never mutates.

    Wraps `plan_stack_release` per repo and aggregates. A repo with no unreleased
    commits is reported as `up-to-date`, not `blocked`: the batch releases what
    is ready and reports what is not, so a healthy stack does not read as failure.

    Execute is deliberately not offered here — a multi-repo apply needs
    per-repo abort semantics that a single flag cannot express. Release each
    ready repo with `plan_stack_release` + `execute_stack_release`.
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS

    repos: list[dict[str, Any]] = []
    go_count = blocked_count = uptodate_count = 0
    for entry in MQ_STACK_REPOS:
        plan = plan_stack_release(entry["name"], bump=bump)
        blockers = plan.get("blockers", [])
        if plan.get("go"):
            state = "ready"
            go_count += 1
        elif blockers and all(b.startswith("no unreleased commits") for b in blockers):
            state = "up-to-date"
            uptodate_count += 1
        else:
            state = "blocked"
            blocked_count += 1
        repos.append({
            "repo": entry["name"],
            "state": state,
            "current_version": plan.get("current_version", "?"),
            "new_version": plan.get("new_version") if state == "ready" else None,
            "tag": plan.get("tag") if state == "ready" else None,
            "blockers": blockers if state == "blocked" else [],
            "warnings": plan.get("warnings", []),
        })
    return {
        "schema": "mq_stack_release_all.v1",
        "planned_at": datetime.now(UTC).isoformat(),
        "bump": bump,
        "repos": repos,
        "go_count": go_count,
        "blocked_count": blocked_count,
        "uptodate_count": uptodate_count,
        "overall_go": go_count > 0,
    }


def execute_stack_release(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute a GO plan step by step. Aborts on the first failure.

    File edits made before the release commit are restored on failure, so an
    aborted run leaves the repo exactly as it was.
    """
    result: dict[str, Any] = {
        "repo": plan.get("repo"),
        "ok": False,
        "released": False,
        "version": plan.get("new_version"),
        "tag": plan.get("tag"),
        "steps": [],
        "executed_at": datetime.now(UTC).isoformat(),
    }
    if not plan.get("go"):
        result["error"] = "plan is NO-GO; refusing to execute"
        result["blockers"] = plan.get("blockers", [])
        return result

    path = Path(plan["path"])
    new_version: str = plan["new_version"]
    tag: str = plan["tag"]
    changed_files: list[Path] = []
    committed = False

    def record(step: str, status: str, detail: str = "") -> None:
        result["steps"].append({"step": step, "status": status, "detail": detail})

    def rollback() -> None:
        if committed or not changed_files:
            return
        rel = [str(f.relative_to(path)) for f in changed_files]
        ok, _ = _run_git(["restore", "--staged", "--worktree", "--"] + rel, path)
        if not ok:
            _run_git(["checkout", "--"] + rel, path)
        result["rolled_back"] = rel

    planned = [s["step"] for s in plan["steps"]]

    def abort(step: str, detail: str) -> dict[str, Any]:
        record(step, "failed", detail)
        rollback()
        for remaining in planned[planned.index(step) + 1 :]:
            record(remaining, "aborted")
        result["error"] = f"{step}: {detail}"
        return result

    try:
        changed_files.extend(_write_version(path, new_version))
        record("bump-version", "done", f"{plan['current_version']} → {new_version}")
    except Exception as exc:
        return abort("bump-version", str(exc))

    if "sync-contract" in planned:
        try:
            contract = _sync_contract(path, new_version)
            if contract:
                changed_files.append(contract)
            record("sync-contract", "done")
        except Exception as exc:
            return abort("sync-contract", str(exc))

    if "update-changelog" in planned:
        try:
            cl = _update_changelog(path, new_version, plan.get("commits", []))
            if cl:
                changed_files.append(cl)
            record("update-changelog", "done")
        except Exception as exc:
            return abort("update-changelog", str(exc))

    rel_files = [str(f.relative_to(path)) for f in changed_files]
    ok, out = _run_git(["add", "--"] + rel_files, path)
    if ok:
        ok, out = _run_git(["commit", "-m", f"release: {tag}"], path)
    if not ok:
        return abort("commit", out)
    committed = True
    record("commit", "done", f"release: {tag}")

    ok, out = _run_git(["tag", "-a", tag, "-m", f"release: {tag}"], path)
    if not ok:
        return abort("tag", out)
    record("tag", "done", tag)

    ok, out = _run_git(["push"], path)
    if not ok:
        return abort("push", out)
    record("push", "done")

    ok, out = _run_git(["push", "origin", tag], path)
    if not ok:
        return abort("push-tag", out)
    record("push-tag", "done")

    result["released"] = True

    try:
        from mq_agent.tools.stack_truth import stack_truth_export

        export = stack_truth_export(write=True)
        record("truth-export", "done", export["path"])
        result["truth_note"] = export["path"]
    except Exception as exc:
        record("truth-export", "failed", str(exc))
        result["warning"] = f"released, but truth-export failed: {exc}"
        return result

    result["ok"] = True
    return result


def stack_release(
    repo: str, bump: str = "patch", version: str = "", execute: bool = False,
) -> str:
    """Orchestrated single-repo release: gate, bump, changelog, tag, push, truth-export.

    Dry-run by default — returns the plan as JSON. With execute=True the plan
    is applied; any failed step aborts and pre-commit file edits are rolled back.
    """
    plan = plan_stack_release(repo, bump=bump, version=version)
    if not execute:
        plan["mode"] = "dry-run"
        return json.dumps(plan, indent=2, default=str)
    result = execute_stack_release(plan)
    result["mode"] = "execute"
    return json.dumps(result, indent=2, default=str)
