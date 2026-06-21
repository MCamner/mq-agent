"""Tests for mq-agent task-specific context pack generation (Phase 5)."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.context_pack import build_task_pack, task_is_source_heavy

runner = CliRunner()

TASK_PACK_BUDGET = 200

CARD = """---
schema: context-card.v1
repo: mq-mcp
role: MQ-stack runtime and brain writer
updated_at: 2026-06-19T00:00:00Z
---

# Context Card: mq-mcp

## Role

MQ-stack runtime and brain writer.

## Owns

* brain writer paths

## Does not own

* durable Obsidian storage format

## Reads from

* mqobsidian durable memory

## Writes to

* `memory/reviews/`
* `memory/learn/`

## Use this card when

* task touches the brain writer

## Avoid reading unless needed

* full repo README files
* old release notes
"""


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "mqobsidian"
    cards = vault / "memory" / "context-cards"
    cards.mkdir(parents=True)
    (cards / "mq-mcp-card.md").write_text(CARD, encoding="utf-8")
    return vault


def test_source_heavy_heuristic():
    assert task_is_source_heavy("fix mq-mcp brain writer paths")
    assert task_is_source_heavy("trace callers of store_learn_record")
    assert not task_is_source_heavy("update README and roadmap")
    assert not task_is_source_heavy("write release notes for v1.4")


def test_pack_selects_card_and_do_not_read(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "fix mq-mcp brain writer paths",
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,  # no .codegraph dirs here
    )
    content = result["content"]

    assert "schema: context-pack.v1" in content
    assert "mqobsidian/memory/context-cards/mq-mcp-card.md" in content
    assert "mq-mcp/.mq/context/repo-card.md" in content
    # do-not-read guidance is pulled from the card
    assert "full repo README files" in content
    assert "old release notes" in content
    # source-heavy task -> CodeGraph hint present, but conditional (no index on disk)
    assert result["codegraph_applied"]
    assert "If `.codegraph/` exists" in content


def test_pack_stays_within_budget(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack("fix mq-mcp brain writer paths", repo="mq-mcp", vault=vault, repos_root=tmp_path)
    assert result["line_count"] <= TASK_PACK_BUDGET


def test_non_source_task_omits_codegraph(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "update mq-mcp README and changelog",
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
    )
    assert not result["codegraph_applied"]
    assert "CodeGraph" not in result["content"]
    assert ".codegraph" not in result["content"]


def test_codegraph_on_names_present_index(tmp_path):
    vault = _vault(tmp_path)
    (tmp_path / "mq-mcp" / ".codegraph").mkdir(parents=True)
    result = build_task_pack(
        "summarize mq-mcp ownership",  # non-source task, but forced on
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
        codegraph="on",
    )
    assert result["codegraph_applied"]
    assert "`.codegraph/` is present in `mq-mcp`" in result["content"]


def test_cli_pack_json_to_stdout(tmp_path):
    vault = _vault(tmp_path)
    result = runner.invoke(
        app,
        [
            "context",
            "pack",
            "fix mq-mcp brain writer paths",
            "--repo",
            "mq-mcp",
            "--vault",
            str(vault),
            "--repos-root",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["relevant_repos"] == ["mq-mcp"]
    assert data["codegraph_applied"] is True
    assert "content" not in data


def test_cli_pack_writes_file(tmp_path):
    vault = _vault(tmp_path)
    out = tmp_path / "out" / "task-pack.md"
    result = runner.invoke(
        app,
        [
            "context",
            "pack",
            "update mq-mcp release notes",
            "--repo",
            "mq-mcp",
            "--vault",
            str(vault),
            "--repos-root",
            str(tmp_path),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "schema: context-pack.v1" in text
    assert "CodeGraph" not in text  # doc task stays clean
