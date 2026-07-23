"""Regression tests for MQ GitHub Actions configuration."""
from __future__ import annotations

import re
from pathlib import Path

from mq_agent.tools.stack_tools import MQ_STACK_REPOS


WORKFLOW_PATH = (
    Path(__file__).parents[1] / ".github" / "workflows" / "mq-stack-gate.yml"
)
TESTS_WORKFLOW_PATH = (
    Path(__file__).parents[1] / ".github" / "workflows" / "tests.yml"
)


def test_full_stack_gate_provisions_every_configured_repo():
    workflow = WORKFLOW_PATH.read_text()
    expected_paths = {Path(repo["path"]).name for repo in MQ_STACK_REPOS}

    checkout_paths = set(re.findall(r"^\s+path: ([\w-]+)$", workflow, re.MULTILINE))
    linked_paths = {
        home_name
        for workspace_name, home_name in re.findall(
            r'ln -s "\$GITHUB_WORKSPACE/([\w-]+)" "\$HOME/([\w-]+)"',
            workflow,
        )
        if workspace_name == home_name
    }

    assert "mqobsidian" in expected_paths
    assert "mqobsidian" in checkout_paths
    assert "mqobsidian" in linked_paths
    assert checkout_paths == expected_paths
    assert linked_paths == expected_paths


def test_ci_ruff_check_uses_repository_default_rules():
    workflow = TESTS_WORKFLOW_PATH.read_text()

    assert "uv run ruff check --select E4,E7,E9,F mq_agent/" in workflow
