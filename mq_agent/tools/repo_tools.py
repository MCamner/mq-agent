import subprocess
from pathlib import Path


def repo_summary(path: str = ".") -> str:
    p = Path(path).resolve()

    branch = _git(["branch", "--show-current"], p)
    recent = _git(["log", "--oneline", "-5"], p)
    status = _git(["status", "--short"], p) or "clean"

    py_files = len(list(p.rglob("*.py")))
    total_files = len([f for f in p.rglob("*") if f.is_file() and ".git" not in f.parts])

    lines = [
        f"Repo:   {p.name}",
        f"Branch: {branch}",
        f"Files:  {total_files} total, {py_files} Python",
        f"Status: {status}",
        "",
        "Recent commits:",
        recent or "(none)",
    ]
    return "\n".join(lines)


def list_files(path: str = ".", pattern: str = "*") -> str:
    p = Path(path).resolve()
    files = sorted(f for f in p.glob(pattern) if f.is_file() and ".git" not in f.parts)
    return "\n".join(str(f.relative_to(p)) for f in files[:100])


def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    if p.stat().st_size > 200_000:
        return f"File too large to read: {path} ({p.stat().st_size} bytes)"
    return p.read_text(errors="replace")


def find_files(path: str = ".", suffix: str = ".py") -> str:
    p = Path(path).resolve()
    files = sorted(f for f in p.rglob(f"*{suffix}") if ".git" not in f.parts)
    return "\n".join(str(f.relative_to(p)) for f in files[:200])


def _git(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip()
