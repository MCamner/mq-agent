import subprocess


def _run(cmd: list[str], cwd: str = ".") -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip() or result.stderr.strip() or "(no output)"


def git_status(path: str = ".") -> str:
    out = _run(["git", "status", "--short"], cwd=path)
    return out if out != "(no output)" else "Clean working tree"


def git_log(path: str = ".", limit: int = 10) -> str:
    return _run(["git", "log", "--oneline", f"-{limit}"], cwd=path)


def git_diff(path: str = ".") -> str:
    out = _run(["git", "diff", "--stat"], cwd=path)
    return out if out != "(no output)" else "No uncommitted changes"


def git_branch(path: str = ".") -> str:
    return _run(["git", "branch", "--show-current"], cwd=path)


def git_remote(path: str = ".") -> str:
    return _run(["git", "remote", "-v"], cwd=path)
