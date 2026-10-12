"""Tests for `mq-agent context prepare`: agent-views rebuild + context export
as one repeatable, verified step (ROADMAP: Agent context pipeline)."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from tests.test_agent_views_cmd import _make_vault
from tests.test_context_export_cmd import CARD

runner = CliRunner()


def _vault(tmp_path: Path) -> Path:
    vault = _make_vault(tmp_path)
    cards = vault / "memory" / "context-cards"
    cards.mkdir(parents=True)
    (cards / "mq-agent-card.md").write_text(CARD, encoding="utf-8")
    return vault


def _prepare(vault: Path, out: Path, *extra: str):
    return runner.invoke(
        app,
        [
            "context", "prepare", "--repo", "mq-agent",
            "--vault", str(vault), "--output-root", str(out), "--json", *extra,
        ],
    )


def test_prepare_rebuilds_views_then_exports_and_verifies(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    out = tmp_path / "repos"

    result = _prepare(vault, out)

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert sorted(data["agent_views"]["views_written"]) == ["mq-mcp", "mq-ums"]
    assert (vault / "memory" / "learn" / "agent" / "mq-mcp.md").is_file()
    assert data["context_export"]["errors"] == []
    assert (out / "mq-agent" / ".mq" / "context" / "repo-card.md").is_file()
    assert data["views_fresh_after"] is True


def test_prepare_is_repeatable(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    out = tmp_path / "repos"
    _prepare(vault, out)

    second = json.loads(_prepare(vault, out).output)

    assert second["ok"] is True
    assert second["agent_views"]["views_written"] == []
    assert second["agent_views"]["views_updated"] == []
    assert second["context_export"]["results"][0]["written"] == []


def test_prepare_dry_run_writes_nothing(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    out = tmp_path / "repos"

    result = _prepare(vault, out, "--dry-run")

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["views_fresh_after"] is None
    assert not (vault / "memory" / "learn" / "agent").exists()
    assert not (out / "mq-agent").exists()


def test_prepare_stops_before_export_when_rebuild_fails(
    tmp_path: Path, monkeypatch
) -> None:
    vault = _vault(tmp_path)
    out = tmp_path / "repos"

    def failing(**_kwargs):
        return {
            "vault": str(vault), "system": None, "repos_checked": 0,
            "views_written": [], "views_updated": [], "views_unchanged": [],
            "views_skipped_no_source": [], "errors": ["boom"],
        }

    monkeypatch.setattr("mq_agent.tools.agent_views.rebuild_agent_views", failing)

    result = _prepare(vault, out)

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["context_export"] is None
    assert not (out / "mq-agent").exists()


def test_prepare_fails_when_export_fails(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)  # no context cards
    out = tmp_path / "repos"

    result = _prepare(vault, out)

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["context_export"]["errors"]


def test_prepare_requires_repo_or_all(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "prepare", "--vault", str(tmp_path)])

    assert result.exit_code == 2
