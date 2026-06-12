"""Tests for the mqobsidian memory engine."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import memory_ingest as memory_ingest_registered
from mq_agent.tools.memory_engine import memory_ingest, memory_link, memory_search, memory_summarize

runner = CliRunner()


@pytest.fixture
def vault(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "mqobsidian"
    root.mkdir()
    monkeypatch.delenv("MQ_OBSIDIAN_DIR", raising=False)
    module = importlib.import_module("mq_agent.tools.memory_engine")
    monkeypatch.setattr(module, "DEFAULT_VAULT_DIR", root)
    return root


def _note(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed(vault: Path) -> None:
    _note(
        vault,
        "memory/reviews/mq-agent.md",
        "# mq-agent review\n\nRuntime contract and memory engine review.",
    )
    _note(
        vault,
        "memory/learn/runtime-contract.md",
        "# Runtime contract\n\nMemory engine should reuse runtime contract lessons.",
    )
    _note(
        vault,
        "decisions/memory-engine.md",
        "# Memory engine ADR\n\nUse read-only ingest before write flows.",
    )


def test_ingest_indexes_standard_memory_sections(vault):
    _seed(vault)
    data = json.loads(memory_ingest())
    assert data["status"] == "OK"
    assert data["summary"]["total_notes"] == 3
    assert data["summary"]["sections"] == {
        "decisions": 1,
        "learn": 1,
        "reviews": 1,
    }


def test_ingest_ignores_structure_readmes(vault):
    _seed(vault)
    _note(vault, "memory/reviews/README.md", "# memory/reviews\n\nStructure docs.")
    data = json.loads(memory_ingest())
    assert data["summary"]["sections"]["reviews"] == 1
    assert all(not note["path"].endswith("README.md") for note in data["notes"])


def test_ingest_missing_vault_reports_no_vault(vault):
    vault.rmdir()
    data = json.loads(memory_ingest())
    assert data["status"] == "NO_VAULT"
    assert data["vault_exists"] is False


def test_search_ranks_matching_notes(vault):
    _seed(vault)
    data = json.loads(memory_search("runtime contract"))
    assert data["count"] >= 2
    assert data["results"][0]["score"] >= data["results"][1]["score"]
    assert any(item["section"] == "learn" for item in data["results"])


def test_summarize_groups_by_section(vault):
    _seed(vault)
    data = json.loads(memory_summarize())
    assert data["total_notes"] == 3
    assert data["sections"]["reviews"]["notes"] == 1
    assert "memory" in data["sections"]["decisions"]["top_tags"]


def test_link_finds_shared_tags(vault):
    _seed(vault)
    data = json.loads(memory_link())
    assert data["count"] > 0
    assert any("contract" in item["shared_tags"] for item in data["links"])


def test_memory_ingest_cli_json(vault):
    _seed(vault)
    result = runner.invoke(app, ["memory", "ingest", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["summary"]["total_notes"] == 3


def test_memory_query_cli(vault):
    _seed(vault)
    result = runner.invoke(app, ["memory", "query", "runtime"])
    assert result.exit_code == 0
    assert "mqobsidian memory" in result.output
    assert "Runtime contract" in result.output


def test_memory_search_vault_alias(vault):
    _seed(vault)
    result = runner.invoke(app, ["memory", "search-vault", "adr", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["results"][0]["section"] == "decisions"


def test_memory_summarize_cli_json(vault):
    _seed(vault)
    result = runner.invoke(app, ["memory", "summarize", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sections"]["learn"]["notes"] == 1


def test_memory_link_cli_json(vault):
    _seed(vault)
    result = runner.invoke(app, ["memory", "link", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["count"] > 0


def test_registered_in_tool_registry():
    from mq_agent.tools import TOOL_REGISTRY

    assert TOOL_REGISTRY["memory_ingest"] is memory_ingest
    assert memory_ingest_registered is memory_ingest
