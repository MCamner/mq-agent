"""
repo-signal integration tools.

Gracefully degrades when repo-signal is not installed.
Install: uv pip install /path/to/repo-signal
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

_AVAILABLE = False

_scan: Callable[..., Any] | None = None
_score_readme: Callable[..., dict] | None = None
_checklist: Callable[..., dict] | None = None
_analyze_repo: Callable[..., str] | None = None

try:
    from repo_signal.analyze import analyze_repo as _analyze_repo  # type: ignore[no-redef]
    from repo_signal.core.scanner import scan_repository as _scan  # type: ignore[no-redef]
    from repo_signal.publish_checklist import (  # type: ignore[no-redef]
        build_publish_checklist as _checklist,
    )
    from repo_signal.readme_score import score_readme as _score_readme  # type: ignore[no-redef]

    _AVAILABLE = True
except ImportError:
    pass


def signal_available() -> bool:
    return _AVAILABLE


def _not_available_msg() -> str:
    return (
        "repo-signal not installed. "
        "Run: uv pip install -e /path/to/repo-signal  "
        "or: uv pip install repo-signal"
    )


def repo_scan(path: str = ".") -> str:
    """Full repo-signal scan: project type, languages, tooling, focus areas."""
    if not _AVAILABLE:
        return _not_available_msg()
    assert _scan is not None

    repo = _scan(path)
    tooling = [f"  • {t}" for t in repo.detected_tooling] or ["  (none)"]
    entrypoints = [f"  • {e}" for e in repo.entrypoints] or ["  (none detected)"]
    lines = [
        f"Repo:          {repo.name}",
        f"Project type:  {repo.project_type}",
        f"Files:         {repo.repo_size_files}",
        f"Size:          {repo.repo_size_mb:.2f} MB",
        f"Branch:        {repo.git.branch or 'unknown'}",
        f"Changes:       {repo.git.changed_files} uncommitted",
        "",
        "Languages:",
        *[f"  {lang}: {count} files" for lang, count in repo.languages.items()],
        "",
        "Tooling detected:",
        *tooling,
        "",
        "Entry points:",
        *entrypoints,
        "",
        "Focus areas:",
        *[f"  {i + 1}. {f}" for i, f in enumerate(repo.focus_areas)],
    ]
    return "\n".join(lines)


def repo_readme_score(path: str = ".") -> str:
    """Score the README against 10 quality criteria (0–100)."""
    if not _AVAILABLE:
        return _not_available_msg()
    assert _score_readme is not None

    result = _score_readme(path)
    score = result["score"]
    max_score = result["max_score"]
    bar = "█" * (score // 10) + "░" * ((max_score - score) // 10)

    present = [f"  ✓ {k}" for k in result["present"]] or ["  (none)"]
    missing = [f"  ✗ {k}" for k in result["missing"]] or ["  (none — perfect score!)"]
    lines = [
        f"README score: {score}/{max_score}  [{bar}]",
        "",
        "Present:",
        *present,
        "",
        "Missing:",
        *missing,
    ]
    return "\n".join(lines)


def repo_publish_checklist(path: str = ".") -> str:
    """Run the publish readiness checklist against the repo."""
    if not _AVAILABLE:
        return _not_available_msg()
    assert _checklist is not None

    result = _checklist(path)
    score = result["score"]
    total = result["total"]
    status = result["status"].upper()

    lines = [f"Publish checklist: {score}/{total}  [{status}]", ""]

    for group in result.get("groups", []):
        lines.append(f"[{group['name']}]")
        for check in group["checks"]:
            icon = "✓" if check["status"] == "ok" else "✗"
            line = f"  {icon} {check['name']}"
            if check.get("hint") and check["status"] != "ok":
                line += f"  → {check['hint']}"
            lines.append(line)
        lines.append("")

    if result.get("recommended_next_action"):
        lines.append(f"Next: {result['recommended_next_action']}")

    return "\n".join(lines).rstrip()


def repo_analyze(path: str = ".") -> str:
    """Full repo-signal analysis report (markdown)."""
    if not _AVAILABLE:
        return _not_available_msg()
    assert _analyze_repo is not None

    return _analyze_repo(path)


def repo_signal_json(path: str = ".") -> dict:
    """Return all signal data as a structured dict (used by signal_agent)."""
    if not _AVAILABLE:
        return {"available": False, "error": _not_available_msg()}
    assert _scan is not None and _score_readme is not None and _checklist is not None

    repo = _scan(path)
    readme = _score_readme(path)
    checklist = _checklist(path)

    return {
        "available": True,
        "name": repo.name,
        "project_type": repo.project_type,
        "files": repo.repo_size_files,
        "size_mb": round(repo.repo_size_mb, 2),
        "branch": repo.git.branch,
        "changed_files": repo.git.changed_files,
        "languages": repo.languages,
        "tooling": repo.detected_tooling,
        "entrypoints": repo.entrypoints,
        "focus_areas": repo.focus_areas,
        "readme_score": {
            "score": readme["score"],
            "max_score": readme["max_score"],
            "present": readme["present"],
            "missing": readme["missing"],
        },
        "publish_checklist": {
            "score": checklist["score"],
            "total": checklist["total"],
            "status": checklist["status"],
            "next_action": checklist.get("recommended_next_action", ""),
        },
    }
