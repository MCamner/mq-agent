#!/usr/bin/env python3
"""Static full-stack workflow governance gate.

The live protection checker also detects WORKFLOW_MUTATION_RISK, but reading
GitHub branch-protection settings requires administration access that the
ordinary Actions token does not have. The full-stack CI job already checks out
all MQ repositories, so this gate reuses the canonical workflow parser against
those local files without making any GitHub API call.
"""
from __future__ import annotations

import sys
from pathlib import Path

from mq_agent.tools.branch_protection_contract import workflow_direct_branch_mutations

WORKFLOW_DIR = Path(".github") / "workflows"
STACK_REPOS = (
    "mq-agent",
    "macos-scripts",
    "mq-mcp",
    "repo-signal",
    "mq-hal",
    "mq-image-analyze",
    "mq-ums",
    "mqobsidian",
)


def workflow_files(repo: Path) -> list[Path]:
    root = repo / WORKFLOW_DIR
    if not root.is_dir():
        return []
    return sorted([*root.glob("*.yml"), *root.glob("*.yaml")])


def violations(repo: Path, *, branch: str = "main") -> list[str]:
    found: list[str] = []
    for path in workflow_files(repo):
        text = path.read_text(encoding="utf-8")
        for problem in workflow_direct_branch_mutations(text, branch=branch):
            found.append(f"{path.relative_to(repo)}: {problem}")
    return found


def discover_stack(root: Path) -> list[Path]:
    parent = root.parent
    repos = [parent / name for name in STACK_REPOS if (parent / name).is_dir()]
    return repos or [root]


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
            "A push-to-main workflow may not commit or push back to protected main. "
            "Regenerate on a branch and update through a pull request instead.",
            file=sys.stderr,
        )
        return 1

    print("workflow governance checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
