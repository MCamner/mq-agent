"""mq-stack status tools — repo inventory, last activity, release readiness."""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MQ_STACK_REPOS: list[dict[str, str]] = [
    {"name": "mqlaunch",        "path": "~/macos-scripts",    "role": "Terminal entrypoint"},
    {"name": "mq-agent",        "path": "~/mq-agent",         "role": "Orchestrator"},
    {"name": "mq-mcp",          "path": "~/mq-mcp",           "role": "Runtime/review truth"},
    {"name": "repo-signal",     "path": "~/repo-signal",      "role": "Repo intelligence"},
    {"name": "mq-hal",          "path": "~/mq-hal",           "role": "Local reasoning shell"},
    {"name": "mq-image-analyze","path": "~/mq-image-analyze", "role": "Visual perception"},
    {"name": "mq-ums",          "path": "~/mq-ums",           "role": "UMS/IGEL tooling"},
    {"name": "mqobsidian",      "path": "~/mqobsidian",       "role": "Second brain"},
]

OBSIDIAN_STATUS = Path.home() / "mqobsidian" / "mq-stack" / "05_RELEASE_STATUS.md"


def _expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(
            ["git"] + args, cwd=cwd, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def _version(repo_path: Path) -> str:
    for name in ("VERSION", "version.txt"):
        f = repo_path / name
        if f.exists():
            return f.read_text().strip()
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text()
        import re
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    return "?"


def _readiness_score(repo_path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["repo-signal", "publish-checklist", str(repo_path), "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "score": data.get("score", "?"),
                "total": data.get("total", "?"),
                "status": data.get("status", "?"),
                "next_action": data.get("next_action") or "",
            }
    except Exception:
        pass
    return {"score": "?", "total": "?", "status": "unknown", "next_action": ""}


def _drift_risk(repo_path: Path) -> str:
    """Heuristic drift risk based on uncommitted changes and branch state."""
    branch = _git(["branch", "--show-current"], repo_path)
    dirty = _git(["status", "--short"], repo_path)
    ahead = _git(["rev-list", "--count", "@{u}..HEAD"], repo_path) if branch else "0"
    score = 0
    if dirty:
        score += 1
    if branch and branch not in ("main", "master"):
        score += 1
    try:
        if int(ahead) > 3:
            score += 1
    except ValueError:
        pass
    return ["Low", "Low", "Medium", "High"][min(score, 3)]


def _last_activity(repo_path: Path) -> str:
    return _git(["log", "-1", "--format=%ar"], repo_path) or "unknown"


def _repo_entry(entry: dict[str, str]) -> dict[str, Any]:
    path = _expand(entry["path"])
    if not path.exists():
        return {
            "name": entry["name"],
            "role": entry["role"],
            "version": "—",
            "branch": "—",
            "last_activity": "—",
            "drift_risk": "—",
            "readiness": "—",
            "next_action": "repo not found locally",
            "exists": False,
        }
    version = _version(path)
    branch = _git(["branch", "--show-current"], path)
    last = _last_activity(path)
    drift = _drift_risk(path)
    readiness = _readiness_score(path)
    return {
        "name": entry["name"],
        "role": entry["role"],
        "version": version,
        "branch": branch or "—",
        "last_activity": last,
        "drift_risk": drift,
        "readiness": f"{readiness['score']}/{readiness['total']}",
        "next_action": readiness["next_action"],
        "exists": True,
    }


def stack_status() -> str:
    """Collect version, branch, last activity, drift risk and readiness for all mq-stack repos.

    Returns JSON array.
    """
    results = [_repo_entry(r) for r in MQ_STACK_REPOS]
    return json.dumps(results, indent=2)


def _changelog_has_version(repo_path: Path, version: str) -> bool:
    """Return True if CHANGELOG.md mentions the current version."""
    cl = repo_path / "CHANGELOG.md"
    if not cl.exists() or version in ("?", "—"):
        return False
    text = cl.read_text()
    return f"[{version}]" in text or f"v{version}" in text or f"## {version}" in text


def _readme_present(repo_path: Path) -> bool:
    return (repo_path / "README.md").exists()


def _roadmap_present(repo_path: Path) -> bool:
    return (repo_path / "ROADMAP.md").exists()


def _unpushed_count(repo_path: Path) -> int:
    raw = _git(["rev-list", "--count", "@{u}..HEAD"], repo_path)
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _release_entry(entry: dict[str, str]) -> dict[str, Any]:
    path = _expand(entry["path"])
    if not path.exists():
        return {"name": entry["name"], "exists": False, "go": False, "blockers": ["repo not found"]}

    version = _version(path)
    branch = _git(["branch", "--show-current"], path)
    dirty = bool(_git(["status", "--short"], path))
    unpushed = _unpushed_count(path)
    cl_ok = _changelog_has_version(path, version)
    readme_ok = _readme_present(path)
    roadmap_ok = _roadmap_present(path)

    blockers: list[str] = []
    warnings: list[str] = []

    if version == "?":
        blockers.append("no VERSION file")
    if not cl_ok:
        warnings.append(f"CHANGELOG missing entry for v{version}")
    if not readme_ok:
        blockers.append("no README.md")
    if dirty:
        warnings.append("uncommitted changes")
    if unpushed > 0:
        warnings.append(f"{unpushed} unpushed commit(s)")
    if not roadmap_ok:
        warnings.append("no ROADMAP.md")

    go = len(blockers) == 0

    return {
        "name": entry["name"],
        "exists": True,
        "version": version,
        "branch": branch or "—",
        "on_main": branch in ("main", "master"),
        "dirty": dirty,
        "unpushed": unpushed,
        "changelog_ok": cl_ok,
        "readme_ok": readme_ok,
        "roadmap_ok": roadmap_ok,
        "blockers": blockers,
        "warnings": warnings,
        "go": go,
    }


def _release_notes_entry(entry: dict[str, str]) -> dict[str, Any]:
    """Return git commits since the last tag for a single repo."""
    path = _expand(entry["path"])
    if not path.exists():
        return {"name": entry["name"], "exists": False, "version": "?", "last_tag": None, "commits": [], "has_changes": False}

    version = _version(path)
    last_tag = _git(["describe", "--tags", "--abbrev=0"], path) or None

    if last_tag:
        raw = _git(["log", f"{last_tag}..HEAD", "--oneline", "--no-merges"], path)
    else:
        raw = _git(["log", "--oneline", "--no-merges", "--max-count=20"], path)

    commits = [line.strip() for line in raw.splitlines() if line.strip()] if raw else []
    return {
        "name": entry["name"],
        "exists": True,
        "version": version,
        "last_tag": last_tag,
        "commits": commits,
        "has_changes": len(commits) > 0,
    }


def stack_release_check() -> str:
    """Cross-repo release readiness check for all mq-stack repos.

    Checks VERSION, CHANGELOG, README, working tree, branch state.
    Returns JSON with per-repo status and overall go/no-go.
    """
    entries = [_release_entry(r) for r in MQ_STACK_REPOS if r["name"] != "mqobsidian"]
    all_go = all(e.get("go", False) for e in entries)
    blocked = [e["name"] for e in entries if not e.get("go", False)]
    warned = [e["name"] for e in entries if e.get("warnings")]
    return json.dumps({
        "overall": "GO" if all_go else "NO-GO",
        "blocked": blocked,
        "warned": warned,
        "repos": entries,
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2)


def stack_github_summary() -> str:
    """Show open PRs and branch state for all mq-stack repos.

    Uses 'gh pr list' — degrades gracefully if gh is not installed.
    Returns JSON array.
    """
    import shutil
    if not shutil.which("gh"):
        return json.dumps({"available": False, "error": "gh CLI not found"})

    results = []
    for repo in MQ_STACK_REPOS:
        if repo["name"] == "mqobsidian":
            continue
        path = _expand(repo["path"])
        if not path.exists():
            continue
        try:
            raw = subprocess.check_output(
                ["gh", "pr", "list", "--json", "number,title,headRefName,state"],
                cwd=path, text=True, stderr=subprocess.DEVNULL, timeout=10,
            )
            prs = json.loads(raw)
        except Exception:
            prs = []
        branch = _git(["branch", "--show-current"], path)
        results.append({
            "name": repo["name"],
            "branch": branch or "—",
            "open_prs": len(prs),
            "prs": prs,
        })
    return json.dumps(results, indent=2)


REQUIRED_CONTRACT_FIELDS: frozenset[str] = frozenset({"repo", "role", "version", "status", "contracts"})


def _contract_entry(entry: dict[str, str]) -> dict[str, Any]:
    """Validate .mq/repo-contract.json for a single repo."""
    path = _expand(entry["path"])
    if not path.exists():
        return {"name": entry["name"], "status": "BLOCKED", "reason": "repo not found locally"}

    version = _version(path)
    if version == "?":
        return {"name": entry["name"], "status": "BLOCKED", "reason": "no VERSION file"}

    if not (path / "README.md").exists():
        return {"name": entry["name"], "status": "BLOCKED", "reason": "no README.md"}

    contract_path = path / ".mq" / "repo-contract.json"
    if not contract_path.exists():
        return {"name": entry["name"], "status": "DRIFT", "reason": "missing .mq/repo-contract.json"}

    try:
        contract = json.loads(contract_path.read_text())
    except Exception as exc:
        return {"name": entry["name"], "status": "BLOCKED", "reason": f"invalid contract JSON: {exc}"}

    missing = REQUIRED_CONTRACT_FIELDS - set(contract.keys())
    if missing:
        return {
            "name": entry["name"],
            "status": "BLOCKED",
            "reason": f"contract missing fields: {', '.join(sorted(missing))}",
        }

    if contract.get("version") != version:
        return {
            "name": entry["name"],
            "status": "DRIFT",
            "reason": f"version mismatch: contract={contract['version']!r}, repo={version!r}",
            "contract": contract,
        }

    warnings: list[str] = []
    if _git(["status", "--short"], path):
        warnings.append("uncommitted changes")
    branch = _git(["branch", "--show-current"], path)
    if branch and branch not in ("main", "master"):
        warnings.append(f"on branch {branch!r}")

    return {
        "name": entry["name"],
        "status": "REVIEW" if warnings else "READY",
        "reason": "; ".join(warnings),
        "contract": contract,
    }


def stack_contract_check() -> str:
    """Cross-repo contract manifest check for all mq-stack repos.

    Reads .mq/repo-contract.json per repo and validates VERSION sync.
    Returns JSON with per-repo status (READY/REVIEW/DRIFT/BLOCKED) and overall verdict.
    """
    entries = [_contract_entry(r) for r in MQ_STACK_REPOS if r["name"] != "mqobsidian"]
    has_failure = any(e["status"] in ("BLOCKED", "DRIFT") for e in entries)
    reasons = [f"{e['name']}: {e['reason']}" for e in entries if e["status"] in ("BLOCKED", "DRIFT")]
    return json.dumps({
        "overall": "READY" if not has_failure else "NOT READY",
        "reasons": reasons,
        "repos": entries,
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2)


def stack_export(output_path: str = "") -> str:
    """Generate and write the mq-stack truth snapshot to mqobsidian.

    v1.13.0 upgrades this command from a simple status table to a durable
    contract-check + release-check truth note under mqobsidian/memory/stack-truth.
    """
    from mq_agent.tools.stack_truth import stack_truth_export

    result = stack_truth_export(output_path=output_path, write=True)
    snapshot = result["snapshot"]
    return (
        f"Written: {result['path']} "
        f"({len(snapshot['repos'])} repos, status {snapshot['status']}, {snapshot['checked_at']})"
    )
