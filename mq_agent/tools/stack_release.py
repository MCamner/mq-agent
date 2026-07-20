"""Stack release orchestration — gated single-repo release pipeline.

Closes the loop: the stack suite observes, gates, remembers, and drafts —
`stack release` makes it act. A release is planned (dry-run) by default and
only applied with execute=True. Any failed step aborts the run; file edits
made before the release commit are rolled back so no repo is half-released.
"""
from __future__ import annotations

import json
import os
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


def _tag_exists(repo_path: Path, tag: str) -> bool:
    """True if the tag exists locally or on the tracked remote 'origin'.

    Local catches the drift case (a tag cut off a feature branch that never
    reached main); the remote check catches a tag already published to origin
    but pruned locally. A failing remote lookup (no origin, offline) is treated
    as 'not found' so the plan never blocks on network flakiness.
    """
    ok, out = _run_git(["tag", "--list", tag], repo_path)
    if ok and out.strip():
        return True
    ok, out = _run_git(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"], repo_path)
    return ok and bool(out.strip())


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
    if (repo_path / "uv.lock").exists():
        files.append(repo_path / "uv.lock")
    return files


def _project_name(repo_path: Path) -> str | None:
    """The distribution name from pyproject.toml, if there is one."""
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return None
    match = re.search(
        r'^name\s*=\s*"([^"]+)"', pyproject.read_text(), flags=re.MULTILINE
    )
    return match.group(1) if match else None


def _write_lockfile_version(lock_path: Path, project: str, new_version: str) -> bool:
    """Bump only this project's own `[[package]]` block in uv.lock.

    uv.lock carries the repo version alongside every dependency's, and a repo
    whose release-check gates on it (mq-agent does) will fail its own check
    right after a release that left the lockfile behind — with the tag already
    pushed. The edit is scoped to the block whose `name` matches the project so
    dependencies that happen to share the version string are never rewritten.
    The project's own entry is an editable source with no hashes, so a targeted
    line edit keeps the lockfile valid without invoking `uv` or the network.
    """
    text = lock_path.read_text()
    pattern = re.compile(
        r'(\[\[package\]\]\nname = "' + re.escape(project) + r'"\nversion = ")[^"]+(")'
    )
    updated, count = pattern.subn(rf"\g<1>{new_version}\g<2>", text, count=1)
    if not count:
        return False
    lock_path.write_text(updated)
    return True


def _write_version(repo_path: Path, new_version: str) -> list[Path]:
    """Write the new version to every version-carrying file. Returns changed files."""
    changed: list[Path] = []
    project = _project_name(repo_path)
    for f in _version_files(repo_path):
        if f.name == "uv.lock":
            if project and _write_lockfile_version(f, project, new_version):
                changed.append(f)
        elif f.name == "pyproject.toml":
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

    # A tag already at the target version is the drift failure mode: a release
    # for this version was already cut (often off a feature branch that never
    # reached main). Executing would build a release commit and then abort at
    # the tag step — after the commit — leaving a dangling commit. Refuse here.
    if new_version != "?" and _tag_exists(path, f"v{new_version}"):
        blockers.append(f"target version v{new_version} is already tagged")

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
        *([{"step": "re-gate", "detail": "release-check.sh after bump"}]
          if (path / "release-check.sh").exists() else []),
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


def _run_release_check(repo_path: Path) -> tuple[bool, list[str]]:
    """Run the repo's canonical read-only releasability check.

    Contract: `./release-check.sh --dry-run --json` at the repo root, emitting a
    `repo_release_check.v1` object {schema, repo, status (READY|BLOCKED),
    blockers[], warnings[], evidence{}}. Returns (ok, blockers). BLOCKED when the
    script is missing, not executable, exits non-zero, emits invalid JSON, or
    reports status != READY. mq-agent runs the entrypoint and reads its verdict;
    it never inspects individual `check-*.sh` scripts — each repo owns its own
    releasability behind the one entrypoint.
    """
    script = repo_path / "release-check.sh"
    if not script.exists():
        return False, ["no release-check.sh at repo root"]
    if not os.access(script, os.X_OK):
        return False, ["release-check.sh is not executable"]
    try:
        proc = subprocess.run(
            ["./release-check.sh", "--dry-run", "--json"],
            # A conforming release-check runs the repo's own suite; repos with
            # heavy dependencies (ML imports, a full test run) legitimately take
            # over a minute on a cold cache. Allow generous headroom so a real
            # check is not reported as a timeout-BLOCKED false positive.
            cwd=repo_path, text=True, capture_output=True, timeout=300,
        )
    except Exception as exc:
        return False, [f"release-check.sh failed to run: {exc}"]
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit {proc.returncode}"
        return False, [f"release-check.sh exit {proc.returncode}: {tail}"]
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return False, ["release-check.sh emitted invalid JSON"]
    status = data.get("status")
    if status == "READY":
        return True, []
    reported = [str(b) for b in data.get("blockers", [])]
    return False, reported or [f"release-check.sh reported {status!r}"]


def _version_mismatch(repo_path: Path, version: str) -> str | None:
    """Return a reason if VERSION disagrees with the repo contract version."""
    contract_path = repo_path / ".mq" / "repo-contract.json"
    if not contract_path.exists():
        return "missing .mq/repo-contract.json"
    try:
        contract = json.loads(contract_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return "unreadable .mq/repo-contract.json"
    cver = contract.get("version")
    if cver and version != "?" and cver != version:
        return f"VERSION {version} != contract {cver}"
    return None


def preflight_stack_release_all(bump: str = "patch") -> dict[str, Any]:
    """Read-only multi-repo release preflight — the fail-fast refusal surface.

    Runs the single-repo plan per repo in explicit `MQ_STACK_REPOS` order, then
    applies the stricter multi-repo blocking states that a partial release makes
    too costly to leave as warnings: unpushed commits, VERSION/contract version
    mismatch, and each repo's own `release-check.sh` verdict. Never mutates and
    never executes — every repo's `execute_state` is `None`. Any `BLOCKED` repo
    means a real `--all --execute` run would abort in this phase, before any
    mutation (schema `mq_stack_release_all_execute.v1`).
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand

    repos: list[dict[str, Any]] = []
    ready_count = blocked_count = uptodate_count = 0
    for entry in MQ_STACK_REPOS:
        plan = plan_stack_release(entry["name"], bump=bump)
        blockers = list(plan.get("blockers", []))
        is_uptodate = bool(blockers) and all(
            b.startswith("no unreleased commits") for b in blockers
        )

        path = _expand(entry["path"])
        if not is_uptodate and path.exists():
            unpushed = plan.get("gate", {}).get("unpushed", 0)
            if unpushed:
                blockers.append(f"{unpushed} unpushed commit(s) — push before releasing")
            mismatch = _version_mismatch(path, plan.get("current_version", "?"))
            if mismatch:
                blockers.append(f"version mismatch: {mismatch}")
            ok, rc_blockers = _run_release_check(path)
            if not ok:
                blockers.extend(f"release-check: {b}" for b in rc_blockers)

        if is_uptodate:
            state = "UP-TO-DATE"
            uptodate_count += 1
        elif blockers:
            state = "BLOCKED"
            blocked_count += 1
        else:
            state = "READY"
            ready_count += 1

        repos.append({
            "repo": entry["name"],
            "preflight_state": state,
            "execute_state": None,
            "current_version": plan.get("current_version", "?"),
            "new_version": plan.get("new_version") if state == "READY" else None,
            "tag": plan.get("tag") if state == "READY" else None,
            "blockers": blockers if state == "BLOCKED" else [],
        })

    return {
        "schema": "mq_stack_release_all_execute.v1",
        "planned_at": datetime.now(UTC).isoformat(),
        "executed_at": None,
        "bump": bump,
        "approved": False,
        "aborted_phase": "preflight" if blocked_count else "none",
        "repos": repos,
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "uptodate_count": uptodate_count,
        "would_execute": ready_count > 0 and blocked_count == 0,
    }


RELEASE_MODES = ("direct", "pull_request", "manual")
"""How a repo's release commit is allowed to reach `main`.

* `direct` — mq-agent may commit, tag and push to `main` itself.
* `pull_request` — `main` is branch-protected; the release must go through a
  release branch and a PR, and the tag is cut from the merged commit.
* `manual` — released by hand on purpose; automation must not touch it.

Only `direct` is executable today. The others are declarations that block, so
the tool refuses knowingly instead of discovering the rule from a push error.
"""


def _release_mode(repo_path: Path | None) -> str | None:
    """The repo's declared release path: one of RELEASE_MODES, or None.

    Read from `.mq/repo-contract.json`. `None` means the repo has not declared
    one — treated as refusal by the execute path, never as permission.
    """
    if repo_path is None:
        return None
    contract_path = repo_path / ".mq" / "repo-contract.json"
    if not contract_path.exists():
        return None
    try:
        contract = json.loads(contract_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    mode = contract.get("release_mode")
    return str(mode) if mode else None


def execute_stack_release_all(bump: str = "patch", approve: bool = False) -> dict[str, Any]:
    """Multi-repo release: read-only preflight → fail-fast gate → execute in order.

    Two phases with one gate between them. The preflight is the same read-only
    aggregate `--all --preflight` runs; if it reports a single BLOCKED repo the
    run ends there, before any mutation, and every `execute_state` stays `None`.
    Only a fully clean preflight plus an explicit `approve` reaches the execute
    phase.

    Execute walks the READY repos in explicit `MQ_STACK_REPOS` order — the
    dependency order — and stops on the first failure. Repos after the failure
    are reported `SKIPPED` and never started. An already-released repo is left
    released: un-releasing it would mean deleting a pushed tag or rewriting
    history, which this stack does not do. Repair is fix-forward, and the
    tag-exists (#143) and release-shape (#144) guards make a re-run safe.
    """
    from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand

    data = preflight_stack_release_all(bump=bump)

    # Branch protection is data, not something to discover from a push error.
    # A repo whose main requires a PR cannot be released by direct push, and
    # finding that out at the push step is too late — the bump, commit and tag
    # already exist locally and have to be unwound by hand. Absent declaration
    # means refusal: assuming "direct" is what produced that cleanup.
    paths = {e["name"]: _expand(e["path"]) for e in MQ_STACK_REPOS}
    for entry in data["repos"]:
        if entry["preflight_state"] != "READY":
            continue
        mode = _release_mode(paths.get(entry["repo"]))
        if mode == "direct":
            continue
        entry["preflight_state"] = "BLOCKED"
        if mode is None:
            reason = (
                "release_mode is not declared in .mq/repo-contract.json — "
                "refusing to assume direct push is allowed"
            )
        elif mode not in RELEASE_MODES:
            reason = (
                f"unknown release_mode {mode!r} — expected one of: "
                f"{', '.join(RELEASE_MODES)}"
            )
        elif mode == "pull_request":
            reason = (
                "release_mode 'pull_request': main requires a PR, so this repo "
                "cannot be released by direct push"
            )
        else:
            reason = (
                "release_mode 'manual': this repo is released by hand on purpose"
            )
        entry["blockers"] = list(entry["blockers"]) + [reason]
        entry["new_version"] = None
        entry["tag"] = None
        data["ready_count"] -= 1
        data["blocked_count"] += 1
    if data["blocked_count"]:
        data["aborted_phase"] = "preflight"
        data["would_execute"] = False

    data["approved"] = approve
    data["released_count"] = 0
    data["failed_count"] = 0
    data["skipped_count"] = 0

    if not approve:
        data["aborted_phase"] = "preflight"
        data["would_execute"] = False
        data["error"] = (
            "multi-repo execute requires --approve; nothing was touched"
        )
        return data

    if data["blocked_count"]:
        # Gate: fail fast, before the first mutation.
        return data

    aborted = False
    for entry in data["repos"]:
        if entry["preflight_state"] != "READY":
            continue
        if aborted:
            entry["execute_state"] = "SKIPPED"
            entry["detail"] = "not attempted — run aborted at an earlier repo"
            data["skipped_count"] += 1
            continue

        plan = plan_stack_release(entry["repo"], bump=bump)
        result = execute_stack_release(plan)
        entry["evidence"] = {"steps": result.get("steps", [])}

        if result.get("released"):
            entry["execute_state"] = "RELEASED"
            entry["detail"] = f"tag {entry['tag']} pushed"
            data["released_count"] += 1
            if result.get("warning"):
                entry["detail"] += f" ({result['warning']})"
        else:
            entry["execute_state"] = "FAILED"
            entry["detail"] = result.get("error", "execute failed")
            data["failed_count"] += 1
            aborted = True

    data["executed_at"] = datetime.now(UTC).isoformat()
    data["aborted_phase"] = "execute" if aborted else "none"
    return data


def _verify_release_shape(repo_path: Path) -> tuple[bool, str]:
    """Re-check the release preconditions at execute time: on main and clean.

    The plan enforces these too, but a plan is a snapshot — the checkout can
    move to a feature branch or gain uncommitted changes between plan and
    execute. Re-checking here, before any mutation, means a release is never
    committed, tagged, or pushed from the wrong shape — the exact shape that
    produced tags off unmerged feature branches. Read-only.
    """
    ok, branch = _run_git(["branch", "--show-current"], repo_path)
    branch = branch.strip()
    if not ok:
        return False, f"could not determine branch: {branch}"
    if branch not in ("main", "master"):
        return False, (
            f"repo is on '{branch or 'a detached HEAD'}', not main — "
            "refusing to release off-main"
        )
    ok, out = _run_git(["status", "--short"], repo_path)
    if not ok:
        return False, f"could not check working tree: {out}"
    if out.strip():
        return False, "working tree is not clean — refusing to release from a dirty tree"
    return True, ""


def execute_stack_release(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute a GO plan step by step. Aborts on the first failure.

    File edits made before the release commit are restored on failure, so an
    aborted run leaves the repo exactly as it was.

    Before any mutation the plan's on-main and clean-tree preconditions are
    re-verified against the live repo: a plan is a snapshot, and the checkout
    may have moved off main or gone dirty since it was built.
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

    shape_ok, shape_reason = _verify_release_shape(path)
    if not shape_ok:
        result["error"] = shape_reason
        result["blockers"] = [shape_reason]
        return result

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

    # Re-gate on the repo's own release-check, now that the version surfaces
    # have moved. The check ran pre-bump during planning, where it cannot see
    # drift the bump itself creates — the shape that shipped mq-mcp v2.0.1 and
    # that left v1.23.0's README a version behind inside the release commit.
    # Nothing is committed yet, so a refusal rolls back cleanly. The repo owns
    # the list of surfaces; mq-agent does not need to enumerate them.
    if (path / "release-check.sh").exists():
        gate_ok, gate_blockers = _run_release_check(path)
        if not gate_ok:
            return abort("re-gate", "; ".join(gate_blockers))
        record("re-gate", "done", "release-check READY after bump")

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
