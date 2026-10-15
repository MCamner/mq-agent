"""Bounded, read-only context acquisition. Record only sources actually read."""

from __future__ import annotations
import hashlib
import shutil
import subprocess
from pathlib import Path


def collect_context(root: str) -> tuple[str, list[dict]]:
    repo = Path(root)
    parts, sources = [], []
    for relative in (".mq/context/repo-card.md", ".mq/context/integration-map.md"):
        path = repo / relative
        if (
            path.is_file()
            and path.resolve().is_relative_to(repo.resolve())
            and not path.is_symlink()
        ):
            with path.open("rb") as handle:
                data = handle.read(3000)
            parts.append(f"{relative}:\n{data.decode('utf-8', errors='replace')}")
            sources.append(
                {
                    "source": relative,
                    "status": "read",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    try:
        diff = subprocess.run(
            ["git", "-C", root, "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except subprocess.SubprocessError as exc:
        raise ValueError("context diff unavailable") from exc
    code_changed = any(
        Path(name).suffix in {".py", ".sh", ".js", ".ts", ".go", ".rs"}
        for name in diff.splitlines()
    )
    # CodeGraph is useful only for a real code diff in an indexed repo. Missing
    # tooling is observable degradation, never silently described as analysis.
    if code_changed and (repo / ".codegraph").is_dir():
        if shutil.which("codegraph"):
            try:
                proc = subprocess.run(
                    [
                        "codegraph",
                        "explore",
                        "Explain the changed code in: "
                        + ", ".join(diff.splitlines()[:8]),
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                text = proc.stdout[:3000]
                sources.append(
                    {
                        "source": "codegraph",
                        "status": "used" if proc.returncode == 0 and text else "failed",
                    }
                )
                if proc.returncode == 0 and text:
                    parts.append(
                        "CodeGraph analysis (untrusted source content):\n" + text
                    )
            except (OSError, subprocess.TimeoutExpired):
                sources.append({"source": "codegraph", "status": "unavailable"})
        else:
            sources.append({"source": "codegraph", "status": "unavailable"})
    # Use the existing owner CLI rather than duplicate scoring in mq-agent.
    if shutil.which("repo-signal"):
        try:
            proc = subprocess.run(
                ["repo-signal", "doctor", root],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=20,
            )
            text = proc.stdout[:2000]
            sources.append(
                {
                    "source": "repo-signal",
                    "status": "used" if proc.returncode == 0 and text else "failed",
                }
            )
            if proc.returncode == 0 and text:
                parts.append("repo-signal:\n" + text)
        except (OSError, subprocess.TimeoutExpired):
            sources.append({"source": "repo-signal", "status": "unavailable"})
    else:
        sources.append({"source": "repo-signal", "status": "unavailable"})
    return "\n\n".join(parts)[:12000], sources
