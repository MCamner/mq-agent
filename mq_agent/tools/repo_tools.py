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


def _git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip()
