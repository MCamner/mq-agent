#!/usr/bin/env python3
"""Fail when stack workflows attempt to write directly back to protected main.

The stack uses protected main branches. A workflow triggered by a push to main
must not try to commit and push generated output back to the same branch; that
either bypasses governance or fails with GH006 once protection is enforced.

This gate is deliberately static and narrow. It catches known direct-write
mechanisms and explicit git pushes in workflows that run on main. Writing to a
separate branch for a pull request is allowed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOW_DIR = Path(".github") / "workflows"
KNOWN_DIRECT_WRITE_ACTIONS = (
    "stefanzweifel/git-auto-commit-action",
    "ad-m/github-push-action",
    "EndBug/add-and-commit",
)

MAIN_TRIGGER = re.compile(r"(?m)^\s*branches\s*:\s*\[[^\]]*\bmain\b[^\]]*\]")
EXPLICIT_MAIN_PUSH = re.compile(
    r"(?mi)^\s*(?:run:\s*)?.*\bgit\s+push\b[^\n]*(?:\bmain\b|HEAD:main\b)"
)
BARE_GIT_PUSH = re.compile(r"(?mi)^\s*(?:run:\s*)?.*\bgit\s+push\s*(?:$|[;&|])")


def workflow_files(repo: Path) -> list[Path]:
    root = repo / WORKFLOW_DIR
    if not root.is_dir():
        return []
    return sorted([*root.glob("*.yml"), *root.glob("*.yaml")])


def violations(repo: Path) -> list[str]:
    found: list[str] = []
    for path in workflow_files(repo):
        text = path.read_text(encoding="utf-8")
        if not MAIN_TRIGGER.search(text):
            continue

        rel = path.relative_to(repo)
        for action in KNOWN_DIRECT_WRITE_ACTIONS:
            if action.lower() in text.lower():
                found.append(
                    f"{rel}: direct-write action {action!r} runs on pushes to main"
                )

        for pattern, label in (
            (EXPLICIT_MAIN_PUSH, "explicit git push to main"),
            (BARE_GIT_PUSH, "bare git push from a main-push workflow"),
        ):
            if pattern.search(text):
                found.append(f"{rel}: {label}")
    return found


def discover_stack(root: Path) -> list[Path]:
    names = (
        "mq-agent",
        "macos-scripts",
        "mq-mcp",
        "repo-signal",
        "mq-hal",
        "mq-image-analyze",
        "mq-ums",
        "mqobsidian",
    )
    parent = root.parent
    repos = [parent / name for name in names if (parent / name).is_dir()]
    if repos:
        return repos
    return [root]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    for repo in discover_stack(root):
        for failure in violations(repo):
            failures.append(f"{repo.name}: {failure}")

    if failures:
        print("workflow governance violations:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "Protected main must be updated through a pull request branch, not by a "
            "workflow writing back to main.",
            file=sys.stderr,
        )
        return 1

    print("workflow governance checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
