"""Tests for `mq-agent agent-views rebuild` and the agent_views tool."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.agent_views import WORD_BUDGET, rebuild_agent_views

runner = CliRunner()


def _make_vault(tmp_path: Path, *, with_lessons: bool = True) -> Path:
    """Build a minimal mqobsidian-shaped vault with several systems."""
    vault = tmp_path / "mqobsidian"
    sysd = vault / "systems"

    # 1) Both hot + index → full card.
    full = sysd / "mq-mcp"
    full.mkdir(parents=True)
    (full / "hot.md").write_text(
        "---\ntype: hot-cache\n---\n\n"
        "## Current mission\nDeliver readiness.\n\n"
        "## Current status\nv2.0.0 shipped, 225 tests green.\n\n"
        "## Active blockers\n- \n\n"  # placeholder-only → dropped
        "## Most important facts\n- shell_exec is double-gated\n",
        encoding="utf-8",
    )
    (full / "index.md").write_text(
        "---\ntype: index\n---\n\n"
        "## Current state\nMCP server, v2.0.0.\n\n"
        "## Current priorities\n1. mq-learn phase 0\n2. repo-snapshot evidence\n\n"
        "## Active risks\n- shell_exec is RCE\n",
        encoding="utf-8",
    )

    # 2) Only index → still builds.
    only_index = sysd / "mq-ums"
    only_index.mkdir(parents=True)
    (only_index / "index.md").write_text(
        "---\ntype: index\n---\n\n"
        "## Current state\nLocal UMS web UI, v0.1.4.\n\n"
        "## Current priorities\n1. operator UI\n\n"
        "## Active risks\n- allowlist only\n",
        encoding="utf-8",
    )

    # 3) No hot/index → skipped.
    bare = sysd / "mq-hal"
    bare.mkdir(parents=True)
    (bare / "overview.md").write_text("# overview\n", encoding="utf-8")

    if with_lessons:
        repos = vault / "memory" / "learn" / "repos"
        repos.mkdir(parents=True)
        (repos / "mq-mcp.md").write_text(
            "# Learn — mq-mcp\n\n"
            "- [[memory/learn/patterns/a]] — Fix env auto-load\n"
            "- [[memory/learn/patterns/b]] — Keep contract in sync\n",
            encoding="utf-8",
        )
    return vault


def test_builds_updates_and_skips(tmp_path):
    vault = _make_vault(tmp_path)
    report = rebuild_agent_views(vault=vault)
    assert sorted(report["views_written"]) == ["mq-mcp", "mq-ums"]
    assert report["views_updated"] == []
    assert report["views_skipped_no_source"] == ["mq-hal"]
    assert report["repos_checked"] == 3
    assert report["errors"] == []


def test_card_shape_and_content(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)
    view = (vault / "memory" / "learn" / "agent" / "mq-mcp.md").read_text()
    assert "type: agent-view" in view
    assert "generator: mq-agent agent-views rebuild" in view
    assert "## Current state" in view
    assert "## Active priorities" in view
    assert "## Current blockers" in view
    assert "## Relevant lessons" in view
    assert "## Read next" in view
    # Wikilinks in Read next.
    assert "[[systems/mq-mcp/hot]]" in view
    assert "[[systems/mq-mcp/index]]" in view
    # Lessons extracted from learn/repos.
    assert "Fix env auto-load" in view
    # Placeholder-only blockers collapse to "none" is NOT the case here (index has a risk).
    assert "shell_exec is RCE" in view


def test_only_index_still_builds_and_blockers_present(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)
    view = (vault / "memory" / "learn" / "agent" / "mq-ums.md").read_text()
    assert "Local UMS web UI" in view
    assert "## Read next" in view
    assert "[[systems/mq-ums/index]]" in view
    assert "[[systems/mq-ums/hot]]" not in view  # no hot.md


def test_card_within_word_budget(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)
    view = (vault / "memory" / "learn" / "agent" / "mq-mcp.md").read_text()
    body = view.split("---", 2)[-1]  # drop frontmatter
    words = [w for w in body.split() if not w.startswith(("#", "-", "["))]
    assert len(words) <= WORD_BUDGET + 60  # body prose, generous headroom


def test_idempotent(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)
    second = rebuild_agent_views(vault=vault)
    assert second["views_written"] == []
    assert second["views_updated"] == []
    assert sorted(second["views_unchanged"]) == ["mq-mcp", "mq-ums"]


def test_never_writes_source(tmp_path):
    vault = _make_vault(tmp_path)
    hot = vault / "systems" / "mq-mcp" / "hot.md"
    before = hot.read_text()
    rebuild_agent_views(vault=vault)
    assert hot.read_text() == before


def test_dry_run_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path)
    report = rebuild_agent_views(vault=vault, dry_run=True)
    assert sorted(report["views_written"]) == ["mq-mcp", "mq-ums"]
    assert not (vault / "memory" / "learn" / "agent" / "mq-mcp.md").exists()


def test_missing_systems_dir_reports_error(tmp_path):
    report = rebuild_agent_views(vault=tmp_path / "empty")
    assert report["errors"]
    assert report["views_written"] == []


def test_cli_json_output(tmp_path):
    vault = _make_vault(tmp_path)
    res = runner.invoke(app, ["agent-views", "rebuild", "--vault", str(vault), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert sorted(data["views_written"]) == ["mq-mcp", "mq-ums"]
    assert data["vault"] == str(vault.resolve())


def test_cli_dry_run_human_output(tmp_path):
    vault = _make_vault(tmp_path)
    res = runner.invoke(app, ["agent-views", "rebuild", "--vault", str(vault), "--dry-run"])
    assert res.exit_code == 0
    assert "dry-run" in res.output
    assert "mq-mcp" in res.output
    assert "skip mq-hal" in res.output


# ── --system: surgical single-system rebuild (phase C trigger) ───────────────

def test_system_rebuilds_only_that_system(tmp_path):
    vault = _make_vault(tmp_path)
    report = rebuild_agent_views(vault=vault, system="mq-mcp")
    assert report["system"] == "mq-mcp"
    assert report["repos_checked"] == 1
    assert report["views_written"] == ["mq-mcp"]
    # only the targeted view is written; siblings are left untouched
    agent_dir = vault / "memory" / "learn" / "agent"
    assert (agent_dir / "mq-mcp.md").exists()
    assert not (agent_dir / "mq-ums.md").exists()


def test_system_unknown_reports_error_and_writes_nothing(tmp_path):
    vault = _make_vault(tmp_path)
    report = rebuild_agent_views(vault=vault, system="does-not-exist")
    assert report["errors"]
    assert report["repos_checked"] == 0
    assert report["views_written"] == []
    assert not (vault / "memory" / "learn" / "agent" / "does-not-exist.md").exists()


def test_system_no_source_is_skipped_not_errored(tmp_path):
    vault = _make_vault(tmp_path)
    report = rebuild_agent_views(vault=vault, system="mq-hal")
    assert report["errors"] == []
    assert report["views_skipped_no_source"] == ["mq-hal"]
    assert report["views_written"] == []


def test_cli_system_option(tmp_path):
    vault = _make_vault(tmp_path)
    res = runner.invoke(
        app, ["agent-views", "rebuild", "--vault", str(vault), "--system", "mq-mcp", "--json"]
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["system"] == "mq-mcp"
    assert data["views_written"] == ["mq-mcp"]


# ── check: drift guard (phase C capstone) ────────────────────────────────────

def test_check_reports_stale_when_views_missing(tmp_path):
    vault = _make_vault(tmp_path)  # nothing built yet → every buildable view is stale
    res = runner.invoke(app, ["agent-views", "check", "--vault", str(vault), "--json"])
    assert res.exit_code == 1  # drift → non-zero
    data = json.loads(res.stdout)
    assert sorted(data["stale"]) == ["mq-mcp", "mq-ums"]
    assert data["fresh"] == []
    # check never writes
    assert not (vault / "memory" / "learn" / "agent" / "mq-mcp.md").exists()


def test_check_passes_after_rebuild(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)  # bring views in sync
    res = runner.invoke(app, ["agent-views", "check", "--vault", str(vault), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["stale"] == []
    assert sorted(data["fresh"]) == ["mq-mcp", "mq-ums"]


def test_check_detects_source_edit_as_drift(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)
    # edit a source after the view was built → that view is now stale
    hot = vault / "systems" / "mq-mcp" / "hot.md"
    hot.write_text(
        "---\ntype: hot-cache\n---\n\n## Current mission\nPivoted to a new target.\n",
        encoding="utf-8",
    )
    res = runner.invoke(app, ["agent-views", "check", "--vault", str(vault), "--system", "mq-mcp", "--json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert data["stale"] == ["mq-mcp"]


def test_check_unknown_system_errors(tmp_path):
    vault = _make_vault(tmp_path)
    res = runner.invoke(app, ["agent-views", "check", "--vault", str(vault), "--system", "nope", "--json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert data["errors"]
    assert data["stale"] == []


def test_check_human_output_in_sync(tmp_path):
    vault = _make_vault(tmp_path)
    rebuild_agent_views(vault=vault)
    res = runner.invoke(app, ["agent-views", "check", "--vault", str(vault)])
    assert res.exit_code == 0
    assert "in sync" in res.output
