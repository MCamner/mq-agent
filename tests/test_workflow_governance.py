from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "workflow_governance", ROOT / "scripts" / "check-workflow-governance.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_workflow(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".github" / "workflows" / "example.yml"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_auto_commit_to_main_is_rejected(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        """name: examples
on:
  push:
    branches: [main]
jobs:
  examples:
    steps:
      - uses: stefanzweifel/git-auto-commit-action@v5
""",
    )
    failures = MODULE.violations(tmp_path)
    assert any("git-auto-commit-action" in item for item in failures)


def test_create_pull_request_is_allowed(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        """name: examples
on:
  push:
    branches: [main]
jobs:
  examples:
    steps:
      - uses: peter-evans/create-pull-request@v7
        with:
          branch: ci/generated-examples
""",
    )
    assert MODULE.violations(tmp_path) == []


def test_read_only_generation_check_is_allowed(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        """name: examples
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  examples:
    steps:
      - run: git diff --exit-code -- examples/generated/*.json
""",
    )
    assert MODULE.violations(tmp_path) == []


def test_shell_git_push_is_rejected(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        """name: bad
on:
  push:
    branches: [main]
jobs:
  write:
    steps:
      - run: |
          git add generated/
          git commit -m update
          git push
""",
    )
    assert MODULE.violations(tmp_path)
