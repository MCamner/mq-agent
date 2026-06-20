"""Tests for mq-agent context export."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.context_export import CORE_MQ_REPOS, export_repo_context

runner = CliRunner()


CARD = """---
schema: context-card.v1
repo: mq-agent
role: MQ-stack workflow orchestrator
updated_at: 2026-06-19T00:00:00Z
---

# Context Card: mq-agent

## Role

MQ-stack workflow orchestrator.

## Owns

* stack gates
* context export commands

## Does not own

* durable Obsidian storage format
* repo-signal scoring internals

## Reads from

* mqobsidian durable memory
* repo-signal repo assessments

## Writes to

* `.mq/context/`
* stack truth exports

## Use this card when

* task involves context export

## Avoid reading unless needed

* full repo README files
"""


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "mqobsidian"
    cards = vault / "memory" / "context-cards"
    cards.mkdir(parents=True)
    (cards / "mq-agent-card.md").write_text(CARD, encoding="utf-8")
    return vault


def test_export_repo_context_writes_expected_files(tmp_path):
    vault = _vault(tmp_path)
    report = export_repo_context("mq-agent", vault=vault, output_root=tmp_path)
    context_dir = tmp_path / "mq-agent" / ".mq" / "context"

    assert report["written"]
    assert (context_dir / "repo-card.md").read_text(encoding="utf-8") == CARD
    assert "# Active Contract: mq-agent" in (context_dir / "active-contract.md").read_text()
    assert "# Integration Map: mq-agent" in (context_dir / "integration-map.md").read_text()
    assert "# Current Blockers: mq-agent" in (context_dir / "current-blockers.md").read_text()
    assert "# Token Budget: mq-agent" in (context_dir / "token-budget.md").read_text()


def test_export_repo_context_is_idempotent(tmp_path):
    vault = _vault(tmp_path)
    export_repo_context("mq-agent", vault=vault, output_root=tmp_path)
    second = export_repo_context("mq-agent", vault=vault, output_root=tmp_path)

    assert second["written"] == []
    assert len(second["unchanged"]) == 5


def test_clean_replaces_owned_files_but_preserves_task_pack(tmp_path):
    vault = _vault(tmp_path)
    context_dir = tmp_path / "mq-agent" / ".mq" / "context"
    context_dir.mkdir(parents=True)
    task_pack = context_dir / "task-pack.md"
    task_pack.write_text("keep me\n", encoding="utf-8")
    (context_dir / "repo-card.md").write_text("stale\n", encoding="utf-8")

    report = export_repo_context(
        "mq-agent",
        vault=vault,
        output_root=tmp_path,
        clean=True,
    )

    assert task_pack.read_text(encoding="utf-8") == "keep me\n"
    assert (context_dir / "repo-card.md").read_text(encoding="utf-8") == CARD
    assert len(report["written"]) == 5


def test_cli_dry_run_json_writes_nothing(tmp_path):
    vault = _vault(tmp_path)
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "context",
            "export",
            "--repo",
            "mq-agent",
            "--vault",
            str(vault),
            "--output-root",
            str(out),
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["results"][0]["repo"] == "mq-agent"
    assert len(data["results"][0]["would_write"]) == 5
    assert not (out / "mq-agent" / ".mq" / "context").exists()


def test_cli_export_all_uses_core_repo_cards(tmp_path):
    vault = tmp_path / "mqobsidian"
    cards = vault / "memory" / "context-cards"
    cards.mkdir(parents=True)
    for repo in CORE_MQ_REPOS:
        cards.joinpath(f"{repo}-card.md").write_text(CARD.replace("mq-agent", repo), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "context",
            "export",
            "--all",
            "--vault",
            str(vault),
            "--output-root",
            str(tmp_path / "repos"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    for repo in CORE_MQ_REPOS:
        assert (tmp_path / "repos" / repo / ".mq" / "context" / "repo-card.md").exists()


def test_token_budget_reads_vault_contract(tmp_path):
    vault = _vault(tmp_path)
    contract = vault / ".mq" / "context-budgets.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(
        json.dumps(
            {
                "budgets": {
                    "repo-card.md": 60,
                    "active-contract.md": 80,
                    "current-blockers.md": 80,
                    "integration-map.md": 120,
                    "task-pack.md": 150,
                },
                "rendered_order": [
                    "repo-card.md",
                    "active-contract.md",
                    "current-blockers.md",
                    "integration-map.md",
                    "task-pack.md",
                ],
            }
        ),
        encoding="utf-8",
    )

    export_repo_context("mq-agent", vault=vault, output_root=tmp_path)
    budget = (tmp_path / "mq-agent" / ".mq" / "context" / "token-budget.md").read_text()

    assert "| `task-pack.md` | 150 lines |" in budget


def test_token_budget_falls_back_without_contract(tmp_path):
    vault = _vault(tmp_path)

    export_repo_context("mq-agent", vault=vault, output_root=tmp_path)
    budget = (tmp_path / "mq-agent" / ".mq" / "context" / "token-budget.md").read_text()

    assert "| `task-pack.md` | 200 lines |" in budget
