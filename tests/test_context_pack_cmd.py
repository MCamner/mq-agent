"""Tests for mq-agent task-specific context pack generation (Phase 5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.context_pack import (
    build_task_pack,
    load_selection_vocabulary,
    task_is_source_heavy,
)

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


# mqobsidian owns the real vocabulary and tests its values (DEC-005). These
# fixtures carry only the few words each assertion needs, so mq-agent tests the
# mechanism -- read the contract, apply it, bound the queries -- without keeping
# a copy of the vocabulary that could drift from the published one.
VOCABULARY = {
    "schema": "context-selection-vocabulary.v1",
    "source_heavy_hints": ["caller", "trace", "writer path", "fix "],
    "source_heavy_suppress": ["readme", "roadmap", "release note"],
    "max_codegraph_queries": 5,
}


def _write_vocabulary(vault: Path, **overrides: object) -> None:
    contract = vault / ".mq"
    contract.mkdir(parents=True, exist_ok=True)
    (contract / "context-selection-vocabulary.json").write_text(
        json.dumps({**VOCABULARY, **overrides}), encoding="utf-8"
    )


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "mqobsidian"
    cards = vault / "memory" / "context-cards"
    cards.mkdir(parents=True)
    (cards / "mq-mcp-card.md").write_text(CARD, encoding="utf-8")
    _write_vocabulary(vault)
    return vault


def test_source_heavy_heuristic(tmp_path):
    vocabulary = load_selection_vocabulary(_vault(tmp_path))

    assert task_is_source_heavy("fix mq-mcp brain writer paths", vocabulary)
    assert task_is_source_heavy("trace callers of store_learn_record", vocabulary)
    assert not task_is_source_heavy("update README and roadmap", vocabulary)
    assert not task_is_source_heavy("write release notes for v1.4", vocabulary)


def test_missing_vocabulary_contract_is_an_error_not_a_default(tmp_path):
    # No fallback on purpose: a private default would be the second source of
    # truth DEC-005 removes, and it would fail silently rather than loudly.
    bare = tmp_path / "mqobsidian"
    bare.mkdir()

    with pytest.raises(ValueError, match="missing selection vocabulary contract"):
        load_selection_vocabulary(bare)


def test_query_bound_comes_from_the_contract(tmp_path):
    vault = _vault(tmp_path)
    _write_vocabulary(vault, max_codegraph_queries=2)

    assert load_selection_vocabulary(vault).max_codegraph_queries == 2


def _write_card(vault: Path, repo: str, *, frontmatter_extra: str = "") -> None:
    cards = vault / "memory" / "context-cards"
    cards.mkdir(parents=True, exist_ok=True)
    card = CARD.replace("repo: mq-mcp", f"repo: {repo}{frontmatter_extra}")
    card = card.replace("Context Card: mq-mcp", f"Context Card: {repo}")
    (cards / f"{repo}-card.md").write_text(card, encoding="utf-8")


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
    # card "avoid" guidance now renders as structured `irrelevant` exclusions
    assert "## Exclusions" in content
    assert "`irrelevant` — full repo README files" in content
    assert "`irrelevant` — old release notes" in content
    # source-heavy task -> bounded MCP-native CodeGraph guidance
    assert result["codegraph_applied"]
    assert "## CodeGraph queries" in content
    assert "`codegraph_explore`" in content
    assert "codegraph explore" not in content


def test_structured_exclusions_render_with_kinds(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "fix mq-mcp brain writer paths",
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
        exclusions=[
            {"item": "mq-ums", "kind": "forbidden", "reason": "unrelated repo"},
            {"item": "archived notes", "kind": "fallback"},
        ],
    )
    content = result["content"]
    assert "`forbidden` — mq-ums: unrelated repo" in content
    assert "`fallback` — archived notes" in content
    # severity ordering: forbidden before fallback before irrelevant
    kinds = [e["kind"] for e in result["exclusions"]]
    assert kinds == sorted(kinds, key=["forbidden", "fallback", "irrelevant"].index)


def test_do_not_read_is_backward_compatible(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "fix mq-mcp brain writer paths",
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
        do_not_read=["legacy avoid item"],
    )
    assert "`irrelevant` — legacy avoid item" in result["content"]
    assert {"item": "legacy avoid item", "kind": "irrelevant", "reason": ""} in result["exclusions"]


def test_local_card_is_withheld_from_pack(tmp_path):
    vault = _vault(tmp_path)
    _write_card(vault, "mq-local", frontmatter_extra="\npublishability: local-rich")
    result = build_task_pack(
        "fix mq-local internals",
        repo="mq-local",
        vault=vault,
        repos_root=tmp_path,
    )
    # not pulled into the selected cards / files, recorded as a forbidden exclusion
    assert "mq-local-card.md" not in [c for c in result["cards"]]
    forbidden = [e for e in result["exclusions"] if e["kind"] == "forbidden"]
    assert any("local-rich" in e["reason"] for e in forbidden)
    assert "mqobsidian/memory/context-cards/mq-local-card.md" not in result["content"].split("## Exclusions")[0]


def test_archived_card_demoted_to_fallback(tmp_path):
    vault = _vault(tmp_path)
    _write_card(vault, "mq-old", frontmatter_extra="\nfreshness: archived")
    result = build_task_pack("touch mq-old", repo="mq-old", vault=vault, repos_root=tmp_path)
    assert result["cards"] == []  # archived card not selected
    assert any(e["kind"] == "fallback" and "archived" in e["reason"] for e in result["exclusions"])


def test_stale_card_kept_but_flagged(tmp_path):
    vault = _vault(tmp_path)
    _write_card(vault, "mq-stale", frontmatter_extra="\nfreshness: stale")
    result = build_task_pack("touch mq-stale", repo="mq-stale", vault=vault, repos_root=tmp_path)
    assert any("mq-stale-card.md" in c for c in result["cards"])  # still selected
    assert "is stale; verify" in result["content"]
    assert result["card_metadata"]["mq-stale"]["freshness"] == "stale"


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


def test_codegraph_on_forces_queries_on_non_source_task(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "summarize mq-mcp ownership",  # non-source task, but forced on
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
        codegraph="on",
    )
    assert result["codegraph_applied"]
    assert "## CodeGraph queries" in result["content"]
    assert "`codegraph_explore`" in result["content"]
    assert "tool intentions, not shell commands" in result["content"]


def test_codegraph_queries_are_bounded_and_scoped(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "trace callers of store_learn_record",
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
        relevant_files=["mq-mcp/runtime/memory/obsidian_writer.py"],
        codegraph_symbols=["store_learn_record"],
    )
    queries = result["codegraph_queries"]
    assert queries  # source-heavy -> emitted
    assert len(queries) <= 5  # bounded, never a token sink
    assert "`codegraph_explore`" in queries[0]
    assert sum("`codegraph_explore`" in q for q in queries) == 1
    assert any("`codegraph_callers`" in q and "`store_learn_record`" in q for q in queries)
    assert any("`codegraph_impact`" in q and "`store_learn_record`" in q for q in queries)
    assert any("`codegraph_node`" in q and "`runtime/memory/obsidian_writer.py`" in q for q in queries)
    assert all(not q.startswith("codegraph ") for q in queries)


def test_codegraph_off_emits_no_queries(tmp_path):
    vault = _vault(tmp_path)
    result = build_task_pack(
        "trace callers of store_learn_record",  # source-heavy
        repo="mq-mcp",
        vault=vault,
        repos_root=tmp_path,
        codegraph="off",
    )
    assert result["codegraph_queries"] == []
    assert not result["codegraph_applied"]
    assert "## CodeGraph queries" not in result["content"]


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


def test_cli_pack_exclude_option(tmp_path):
    vault = _vault(tmp_path)
    result = runner.invoke(
        app,
        [
            "context", "pack", "fix mq-mcp brain writer paths",
            "--repo", "mq-mcp",
            "--vault", str(vault),
            "--repos-root", str(tmp_path),
            "--exclude", "forbidden:mq-ums:unrelated repo",
            "--exclude", "fallback:old logs",
        ],
    )
    assert result.exit_code == 0
    assert "`forbidden` — mq-ums: unrelated repo" in result.stdout
    assert "`fallback` — old logs" in result.stdout


def test_cli_pack_exclude_rejects_bad_kind(tmp_path):
    vault = _vault(tmp_path)
    result = runner.invoke(
        app,
        [
            "context", "pack", "fix mq-mcp brain writer paths",
            "--repo", "mq-mcp", "--vault", str(vault), "--repos-root", str(tmp_path),
            "--exclude", "bogus:item",
        ],
    )
    assert result.exit_code == 2


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
