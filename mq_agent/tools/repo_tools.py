import subprocess
from pathlib import Path

_EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache", "dist", "build", ".eggs"}


def _excluded(path: Path) -> bool:
    return bool(_EXCLUDE_DIRS & set(path.parts))


def repo_summary(path: str = ".") -> str:
    p = Path(path).resolve()

    branch = _git(["branch", "--show-current"], p)
    recent = _git(["log", "--oneline", "-5"], p)
    status = _git(["status", "--short"], p) or "clean"

    all_files = [f for f in p.rglob("*") if f.is_file() and not _excluded(f)]
    py_files = sum(1 for f in all_files if f.suffix == ".py")

    lines = [
        f"Repo:   {p.name}",
        f"Branch: {branch}",
        f"Files:  {len(all_files)} total, {py_files} Python",
        f"Status: {status}",
        "",
        "Recent commits:",
        recent or "(none)",
    ]
    return "\n".join(lines)


def list_files(path: str = ".", pattern: str = "*") -> str:
    p = Path(path).resolve()
    files = sorted(f for f in p.glob(pattern) if f.is_file() and not _excluded(f))
    return "\n".join(str(f.relative_to(p)) for f in files[:100])


def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    if p.stat().st_size > 200_000:
        return f"File too large to read: {path} ({p.stat().st_size} bytes)"
    return p.read_text(errors="replace")


def write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written: {path} ({len(content)} chars)"


def find_files(path: str = ".", pattern: str = "*.py") -> str:
    p = Path(path).resolve()
    files = sorted(f for f in p.rglob(pattern) if not _excluded(f))
    return "\n".join(str(f.relative_to(p)) for f in files[:200])


def run_task_tool(task_name: str, dry_run: bool = False) -> str:
    """Run a named task from the tasks/ directory in the current working directory."""
    from mq_agent.core.task_runner import find_task_files, load_task, run_task

    _STATUS_ICON = {"ok": "✓", "error": "✗", "dry-run": "~", "unknown-tool": "?"}

    task_files = find_task_files(Path.cwd() / "tasks")
    for tf in task_files:
        candidate = load_task(tf)
        if tf.stem == task_name or candidate.name == task_name:
            results = run_task(candidate, dry_run=dry_run)
            lines = [f"Task: {candidate.name}"]
            for r in results:
                icon = _STATUS_ICON.get(r.status, "?")
                snippet = r.output.replace("\n", " ")[:120]
                lines.append(f"  {icon} {r.step} ({r.tool}): {snippet}")
            all_ok = all(r.status in ("ok", "dry-run") for r in results)
            lines.append("  All steps passed" if all_ok else "  Some steps failed")
            return "\n".join(lines)

    return f"Task not found: {task_name}"


def _git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip()
