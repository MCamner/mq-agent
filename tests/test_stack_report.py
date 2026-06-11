"""Tests for stack report and stack release-check CLI commands."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_history(tmp_path, monkeypatch):
    mq_dir = tmp_path / ".mq-agent"
    mq_dir.mkdir()
    history_file = mq_dir / "sweep-history.jsonl"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return history_file


def _sweep(scores: dict[str, int | None], ts: str = "2026-06-10T10:00:00") -> dict:
    results = []
    for name, score in scores.items():
        if score is None:
            results.append({"name": name, "skipped": True})
        else:
            results.append({"name": name, "overall": score, "publish": 14, "skipped": False})
    return {"ts": ts, "results": results}


def _write_sweeps(path: Path, sweeps: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(s) for s in sweeps) + "\n")


@pytest.fixture()
def fake_repo(tmp_path):
    """Create a minimal fake git repo with VERSION and CHANGELOG."""
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    (repo / "VERSION").write_text("1.0.0\n")
    (repo / "CHANGELOG.md").write_text("## [v1.0.0]\n\n* initial\n")
    (repo / "README.md").write_text("# fake\n")
    (repo / "ROADMAP.md").write_text("# roadmap\n")
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "--allow-empty-message"], cwd=repo, capture_output=True)
    return repo


# ── stack report ────────────────────────────────────────────────────────────

class TestStackReport:
    def test_no_history_shows_hint(self, tmp_history):
        result = runner.invoke(app, ["stack", "report"])
        assert result.exit_code == 0
        assert "No sweep history" in result.output

    def test_shows_table_with_history(self, tmp_history):
        _write_sweeps(tmp_history, [_sweep({"mq-agent": 100, "mq-mcp": 90})])
        result = runner.invoke(app, ["stack", "report"])
        assert result.exit_code == 0
        assert "mq-agent" in result.output

    def test_trend_up(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 85}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 95}, ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "report"])
        assert result.exit_code == 0
        assert "↑" in result.output

    def test_trend_down(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 95}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 80}, ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "report"])
        assert result.exit_code == 0
        assert "↓" in result.output

    def test_alert_shown(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 70},  ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "report"])
        assert result.exit_code == 0
        assert "⚠" in result.output

    def test_json_output(self, tmp_history):
        _write_sweeps(tmp_history, [_sweep({"mq-agent": 100})])
        result = runner.invoke(app, ["stack", "report", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(r["name"] == "mq-agent" for r in data)

    def test_json_includes_trend_and_ready(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 90}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 95}, ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "report", "--json"])
        data = json.loads(result.output)
        mq = next(r for r in data if r["name"] == "mq-agent")
        assert mq["score"] == 95
        assert "↑" in mq["trend"]
        assert mq["ready"] is True

    def test_ready_false_when_below_80(self, tmp_history):
        _write_sweeps(tmp_history, [_sweep({"mq-agent": 75})])
        result = runner.invoke(app, ["stack", "report", "--json"])
        data = json.loads(result.output)
        mq = next(r for r in data if r["name"] == "mq-agent")
        assert mq["ready"] is False

    def test_exit_code_0_always(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 50},  ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "report"])
        assert result.exit_code == 0


# ── stack release-check ─────────────────────────────────────────────────────

class TestStackReleaseCheck:
    def test_dry_run_lists_repos(self):
        result = runner.invoke(app, ["stack", "release-check", "--dry-run"])
        assert result.exit_code == 0
        assert "Would check" in result.output

    def test_json_shape(self, fake_repo):
        from mq_agent.tools.stack_tools import _release_entry
        entry = _release_entry({"name": "fake", "path": str(fake_repo)})
        assert "go" in entry
        assert "blockers" in entry
        assert "warnings" in entry

    def test_release_entry_clean_repo_is_go(self, fake_repo):
        from mq_agent.tools.stack_tools import _release_entry
        entry = _release_entry({"name": "fake", "path": str(fake_repo)})
        assert entry["go"] is True
        assert entry["blockers"] == []

    def test_release_entry_missing_version_is_blocker(self, fake_repo):
        from mq_agent.tools.stack_tools import _release_entry
        (fake_repo / "VERSION").unlink()
        entry = _release_entry({"name": "fake", "path": str(fake_repo)})
        assert entry["go"] is False
        assert any("VERSION" in b for b in entry["blockers"])

    def test_release_entry_missing_readme_is_blocker(self, fake_repo):
        from mq_agent.tools.stack_tools import _release_entry
        (fake_repo / "README.md").unlink()
        entry = _release_entry({"name": "fake", "path": str(fake_repo)})
        assert entry["go"] is False

    def test_release_entry_nonexistent_path(self, tmp_path):
        from mq_agent.tools.stack_tools import _release_entry
        entry = _release_entry({"name": "ghost", "path": str(tmp_path / "nope")})
        assert entry["go"] is False
        assert entry["exists"] is False
