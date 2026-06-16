"""Tests for `mq-agent memory regenerate-views` and the agent_views tool."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.agent_views import regenerate_agent_views

runner = CliRunner()


def _make_vault(tmp_path: Path) -> Path:
    """Build a minimal mqobsidian-shaped vault with two systems."""
    vault = tmp_path / "mqobsidian"
    sysd = vault / "systems"
    # System with both hot + index → should build.
    full = sysd / "mq-mcp"
    full.mkdir(parents=True)
    (full / "hot.md").write_text(
        "---\ntype: hot-cache\nsystem: mq-mcp\n---\n\n"
        "## Current mission\nDeliver readiness.\n\n"
        "## Active blockers\n- \n\n"  # placeholder-only → dropped
        "## Most important facts\n- v2.0.0 shipped\n",
        encoding="utf-8",
    )
    (full / "index.md").write_text(
        "---\ntype: index\n---\n\n"
        "## Current state\nMCP server, v2.0.0.\n\n"
        "## Active risks\n- shell_exec is RCE\n",
        encoding="utf-8",
    )
    # System with only overview (no hot/index) → should skip.
    bare = sysd / "mq-hal"
    bare.mkdir(parents=True)
    (bare / "overview.md").write_text("# overview\n", encoding="utf-8")
    return vault


def test_tool_builds_and_skips(tmp_path):
    vault = _make_vault(tmp_path)
    result = regenerate_agent_views(vault=vault)
    assert result["written"] == ["mq-mcp"]
    assert [s["system"] for s in result["skipped"]] == ["mq-hal"]
    assert result["refused"] == []

    view = (vault / "memory" / "learn" / "agent" / "mq-mcp.md").read_text()
    assert "type: agent-view" in view
    assert "Deliver readiness." in view
    assert "shell_exec is RCE" in view
    # Placeholder-only "Active blockers" must not leak in.
    assert "Active blockers" not in view


def test_tool_is_idempotent(tmp_path):
    vault = _make_vault(tmp_path)
    regenerate_agent_views(vault=vault)
    second = regenerate_agent_views(vault=vault)
    assert second["written"] == []
    assert second["unchanged"] == ["mq-mcp"]


def test_tool_never_writes_source(tmp_path):
    vault = _make_vault(tmp_path)
    hot = vault / "systems" / "mq-mcp" / "hot.md"
    before = hot.read_text()
    regenerate_agent_views(vault=vault)
    assert hot.read_text() == before  # curated source untouched


def test_dry_run_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path)
    result = regenerate_agent_views(vault=vault, dry_run=True)
    assert result["written"] == ["mq-mcp"]  # would write
    assert not (vault / "memory" / "learn" / "agent" / "mq-mcp.md").exists()


def test_missing_systems_dir_reports_error(tmp_path):
    result = regenerate_agent_views(vault=tmp_path / "empty")
    assert "error" in result
    assert result["written"] == []


def test_cli_json_output(tmp_path):
    vault = _make_vault(tmp_path)
    res = runner.invoke(
        app, ["memory", "regenerate-views", "--vault", str(vault), "--json"]
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["written"] == ["mq-mcp"]
    assert data["vault"] == str(vault.resolve())


def test_cli_dry_run_human_output(tmp_path):
    vault = _make_vault(tmp_path)
    res = runner.invoke(
        app, ["memory", "regenerate-views", "--vault", str(vault), "--dry-run"]
    )
    assert res.exit_code == 0
    assert "dry-run" in res.output
    assert "mq-mcp" in res.output
    assert "skip mq-hal" in res.output
