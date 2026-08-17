"""
repo-signal integration tools.

repo-signal is treated as an external CLI contract. This keeps mq-agent's
project environment independent from repo-signal's runtime and lets a
user-level ``uv tool`` installation provide the integration.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_MIN_VERSION = (1, 4, 2)
_INSTALL_HINT = (
    "uv tool install "
    "'repo-signal[ai,vector] @ git+https://github.com/MCamner/repo-signal.git@v1.4.2'"
)

_README_LABEL_TO_KEY = {
    "title": "title",
    "short pitch": "short_pitch",
    "install section": "install",
    "usage section": "usage",
    "examples": "examples",
    "screenshots/demo": "screenshots_demo",
    "badges": "badges",
    "license": "license",
    "roadmap": "roadmap",
    "contributing": "contributing",
}


def _version_tuple(v: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", v)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.groups())


def _candidate_bins() -> list[str]:
    """Return repo-signal executables in PATH order, plus an explicit override."""
    candidates: list[str] = []
    seen: set[str] = set()

    override = os.getenv("REPO_SIGNAL_BIN", "").strip()
    if override:
        resolved = str(Path(override).expanduser())
        candidates.append(resolved)
        seen.add(resolved)

    # shutil.which is the canonical first lookup, but uv can prepend an older
    # project-local executable to PATH. Keep scanning PATH so a compatible
    # user-level uv-tool binary can still win when the first candidate is stale.
    first = shutil.which("repo-signal")
    if first:
        candidates.append(first)
        seen.add(first)

    for entry in os.getenv("PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = str(Path(entry).expanduser() / "repo-signal")
        if candidate in seen:
            continue
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            candidates.append(candidate)
            seen.add(candidate)

    return candidates


def _probe_version(executable: str) -> tuple[int, ...]:
    try:
        result = subprocess.run(
            [executable, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return (0,)

    return _version_tuple(result.stdout or result.stderr)


def _resolve_repo_signal() -> tuple[str | None, str | None]:
    """Resolve the first compatible repo-signal CLI, skipping stale PATH entries."""
    stale: list[str] = []
    for executable in _candidate_bins():
        version = _probe_version(executable)
        if version >= _MIN_VERSION:
            return executable, None
        if version != (0,):
            stale.append(f"{executable} ({'.'.join(str(p) for p in version)})")

    minimum = ".".join(str(part) for part in _MIN_VERSION)
    if stale:
        return None, (
            f"repo-signal is too old; need >= {minimum}. Found: {', '.join(stale)}. "
            f"Run: {_INSTALL_HINT}"
        )
    return None, f"repo-signal not installed or not on PATH. Run: {_INSTALL_HINT}"


def signal_available() -> bool:
    executable, _ = _resolve_repo_signal()
    return executable is not None


def _not_available_msg() -> str:
    _, error = _resolve_repo_signal()
    return error or f"repo-signal unavailable. Run: {_INSTALL_HINT}"


def _run_repo_signal(*args: str) -> tuple[bool, str]:
    executable, error = _resolve_repo_signal()
    if executable is None:
        return False, error or _not_available_msg()

    try:
        result = subprocess.run(
            [executable, *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        return False, f"repo-signal failed to start: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return False, detail or f"repo-signal exited with {result.returncode}"
    return True, result.stdout.rstrip()


def _run_json(*args: str) -> tuple[dict[str, Any] | None, str | None]:
    ok, output = _run_repo_signal(*args)
    if not ok:
        return None, output
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        return None, f"repo-signal returned invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "repo-signal returned a non-object JSON contract"
    return data, None


def _parse_readme_score(output: str) -> dict[str, Any]:
    score_match = re.search(r"README score:\s*(\d+)\s*/\s*(\d+)", output)
    score = int(score_match.group(1)) if score_match else 0
    max_score = int(score_match.group(2)) if score_match else 100

    present: list[str] = []
    missing: list[str] = []
    for line in output.splitlines():
        match = re.match(r"\s*-\s*\[(OK|MISSING)\]\s*(.+?)\s*$", line)
        if not match:
            continue
        state, label = match.groups()
        key = _README_LABEL_TO_KEY.get(label.strip().lower(), label.strip().lower().replace(" ", "_"))
        if state == "OK":
            present.append(key)
        else:
            missing.append(key)

    if not present and not missing and "Missing: README.md" in output:
        missing = list(_README_LABEL_TO_KEY.values())

    return {
        "score": score,
        "max_score": max_score,
        "present": present,
        "missing": missing,
    }


def _focus_areas_from_analyze(output: str) -> list[str]:
    marker = "## Suggested Focus Areas"
    if marker not in output:
        return []

    focus: list[str] = []
    in_section = False
    for line in output.splitlines():
        if line.strip() == marker:
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith("## "):
            break
        match = re.match(r"\s*\d+\.\s+(.+?)\s*$", line)
        if match:
            focus.append(match.group(1))
    return focus


def repo_scan(path: str = ".") -> str:
    """Full repo-signal scan: project type, languages, tooling, focus areas."""
    inspect, error = _run_json("inspect", path, "--json")
    if inspect is None:
        return error or _not_available_msg()

    repo = inspect.get("repo", {})
    git = inspect.get("git", {})
    detected = inspect.get("detected", {})
    analyze_ok, analyze_output = _run_repo_signal("analyze", path)
    focus_areas = _focus_areas_from_analyze(analyze_output) if analyze_ok else []

    tooling = [f"  • {item}" for item in detected.get("tooling", [])] or ["  (none)"]
    entrypoints = [f"  • {item}" for item in detected.get("entrypoints", [])] or ["  (none detected)"]
    lines = [
        f"Repo:          {repo.get('name', Path(path).name)}",
        f"Project type:  {repo.get('type') or 'unknown'}",
        f"Files:         {repo.get('files') if repo.get('files') is not None else 'unknown'}",
        f"Branch:        {git.get('branch') or 'unknown'}",
        f"Changes:       {git.get('change_count') if git.get('change_count') is not None else 'unknown'} uncommitted",
        "",
        "Languages:",
        *[f"  {lang}: {count} files" for lang, count in detected.get("languages", {}).items()],
        "",
        "Tooling detected:",
        *tooling,
        "",
        "Entry points:",
        *entrypoints,
        "",
        "Focus areas:",
        *[f"  {index}. {focus}" for index, focus in enumerate(focus_areas, start=1)],
    ]
    return "\n".join(lines)


def repo_readme_score(path: str = ".") -> str:
    """Score the README against 10 quality criteria (0–100)."""
    ok, output = _run_repo_signal("readme-score", path)
    if not ok:
        return output

    result = _parse_readme_score(output)
    score = result["score"]
    max_score = result["max_score"]
    bar = "█" * (score // 10) + "░" * max(0, (max_score - score) // 10)
    present = [f"  ✓ {key}" for key in result["present"]] or ["  (none)"]
    missing = [f"  ✗ {key}" for key in result["missing"]] or ["  (none — perfect score!)"]
    return "\n".join(
        [
            f"README score: {score}/{max_score}  [{bar}]",
            "",
            "Present:",
            *present,
            "",
            "Missing:",
            *missing,
        ]
    )


def repo_publish_checklist(path: str = ".") -> str:
    """Run the publish readiness checklist against the repo."""
    result, error = _run_json("publish-checklist", path, "--format", "json")
    if result is None:
        return error or _not_available_msg()

    score = result.get("score", 0)
    total = result.get("total", 0)
    status = str(result.get("status", "unknown")).upper()
    lines = [f"Publish checklist: {score}/{total}  [{status}]", ""]

    for group in result.get("groups", []):
        lines.append(f"[{group.get('name', 'checks')}]")
        for check in group.get("checks", []):
            icon = "✓" if check.get("status") == "ok" else "✗"
            line = f"  {icon} {check.get('name', 'check')}"
            if check.get("hint") and check.get("status") != "ok":
                line += f"  → {check['hint']}"
            lines.append(line)
        lines.append("")

    next_action = result.get("recommended_next_action")
    if next_action:
        lines.append(f"Next: {next_action}")
    return "\n".join(lines).rstrip()


def repo_analyze(path: str = ".") -> str:
    """Full repo-signal analysis report (markdown)."""
    ok, output = _run_repo_signal("analyze", path)
    return output if ok else output


def repo_suggest(path: str = ".", output_format: str = "text") -> str:
    """Safe patch suggestions — what to improve, no mutations (text/markdown/json)."""
    ok, output = _run_repo_signal("suggest", path, "--format", output_format)
    return output if ok else output


def repo_signal_json(path: str = ".") -> dict[str, Any]:
    """Return structured signal data using repo-signal's CLI JSON contracts."""
    inspect, error = _run_json("inspect", path, "--json")
    if inspect is None:
        return {"available": False, "error": error or _not_available_msg()}

    checklist, checklist_error = _run_json("publish-checklist", path, "--format", "json")
    if checklist is None:
        return {"available": False, "error": checklist_error or "publish-checklist unavailable"}

    readme_ok, readme_output = _run_repo_signal("readme-score", path)
    if not readme_ok:
        return {"available": False, "error": readme_output}
    readme = _parse_readme_score(readme_output)

    analyze_ok, analyze_output = _run_repo_signal("analyze", path)
    focus_areas = _focus_areas_from_analyze(analyze_output) if analyze_ok else []

    repo = inspect.get("repo", {})
    git = inspect.get("git", {})
    detected = inspect.get("detected", {})

    return {
        "available": True,
        "name": repo.get("name", Path(path).name),
        "project_type": repo.get("type") or "unknown",
        "files": repo.get("files"),
        "size_mb": None,
        "branch": git.get("branch"),
        "changed_files": git.get("change_count"),
        "languages": detected.get("languages", {}),
        "tooling": detected.get("tooling", []),
        "entrypoints": detected.get("entrypoints", []),
        "focus_areas": focus_areas,
        "readme_score": readme,
        "publish_checklist": {
            "score": checklist.get("score", 0),
            "total": checklist.get("total", 0),
            "status": checklist.get("status", "unknown"),
            "next_action": checklist.get("recommended_next_action", ""),
        },
    }
