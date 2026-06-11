"""Tests for the v1.15.0 stack cockpit view."""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import mq_agent.tools.stack_truth as stack_truth
import mq_agent.tools.stack_tools as stack_tools
from mq_agent.tools.stack_cockpit import _truth_note_freshness, stack_cockpit


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path, name: str = "mq-agent") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    (repo / "VERSION").write_text("1.0.0\n")
    (repo / "README.md").write_text(f"# {name}\n")
    (repo / "ROADMAP.md").write_text("# Roadmap\n")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v1.0.0] — 2026-01-01\n\n* initial\n"
    )
    (repo / ".mq").mkdir()
    (repo / ".mq" / "repo-contract.json").write_text(json.dumps({
        "repo": name, "role": "test", "version": "1.0.0",
        "status": "active", "contracts": [],
    }, indent=2) + "\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "initial"], repo)
    _git(["tag", "v1.0.0"], repo)
    return repo


@pytest.fixture
def stack_repo(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(
        stack_tools, "MQ_STACK_REPOS",
        [{"name": repo.name, "path": str(repo), "role": "test"}],
    )
    truth_dir = tmp_path / "stack-truth"
    truth_dir.mkdir()
    monkeypatch.setattr(stack_truth, "DEFAULT_STACK_TRUTH_DIR", truth_dir)
    return repo


def _cockpit() -> dict:
    return json.loads(stack_cockpit())


class TestTruthFreshness:
    def test_no_notes_is_none(self, stack_repo):
        assert _truth_note_freshness()["status"] == "none"

    def test_todays_note_is_fresh(self, stack_repo, tmp_path):
        today = datetime.now(UTC).date().isoformat()
        (tmp_path / "stack-truth" / f"{today}-mq-stack-truth.md").write_text("# truth\n")
        fresh = _truth_note_freshness()
        assert fresh["status"] == "fresh"
        assert fresh["age_days"] == 0

    def test_old_note_is_stale(self, stack_repo, tmp_path):
        (tmp_path / "stack-truth" / "2026-01-01-mq-stack-truth.md").write_text("# truth\n")
        assert _truth_note_freshness()["status"] == "stale"


class TestCockpitEntries:
    def test_clean_released_repo_is_up_to_date(self, stack_repo):
        data = _cockpit()
        row = data["repos"][0]
        assert row["repo"] == "mq-agent"
        assert row["version"] == "1.0.0"
        assert row["branch"] == "main"
        assert row["dirty"] is False
        assert row["contract"] == "READY"
        assert row["gate"] == "GO"
        assert row["unreleased"] == 0
        assert row["next_action"] == "up to date"

    def test_missing_repo_suggests_clone(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            stack_tools, "MQ_STACK_REPOS",
            [{"name": "ghost", "path": str(tmp_path / "ghost"), "role": "test"}],
        )
        row = _cockpit()["repos"][0]
        assert row["exists"] is False
        assert row["next_action"] == "clone repo locally"

    def test_dirty_repo_suggests_commit(self, stack_repo):
        (stack_repo / "wip.txt").write_text("wip\n")
        row = _cockpit()["repos"][0]
        assert row["dirty"] is True
        assert "commit or stash" in row["next_action"]

    def test_contract_drift_wins_over_dirty(self, stack_repo):
        contract = stack_repo / ".mq" / "repo-contract.json"
        data = json.loads(contract.read_text())
        data["version"] = "9.9.9"
        contract.write_text(json.dumps(data, indent=2) + "\n")
        row = _cockpit()["repos"][0]
        assert row["contract"] == "DRIFT"
        assert row["next_action"].startswith("fix contract:")

    def test_off_main_suggests_switch(self, stack_repo):
        _git(["switch", "-c", "feature"], stack_repo)
        row = _cockpit()["repos"][0]
        assert "switch to main" in row["next_action"]

    def test_unreleased_commits_suggest_release(self, stack_repo):
        (stack_repo / "feature.txt").write_text("new\n")
        _git(["add", "-A"], stack_repo)
        _git(["commit", "-m", "feat: add feature"], stack_repo)
        row = _cockpit()["repos"][0]
        assert row["unreleased"] == 1
        assert row["next_action"] == "stack release --repo mq-agent"

    def test_gate_excluded_repo_shows_dashes(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path, name="mqobsidian")
        monkeypatch.setattr(
            stack_tools, "MQ_STACK_REPOS",
            [{"name": "mqobsidian", "path": str(repo), "role": "memory"}],
        )
        monkeypatch.setattr(stack_truth, "DEFAULT_STACK_TRUTH_DIR", tmp_path / "none")
        row = _cockpit()["repos"][0]
        assert row["contract"] == "—"
        assert row["gate"] == "—"


class TestStackSummary:
    def test_all_green_when_clean_and_fresh(self, stack_repo, tmp_path):
        today = datetime.now(UTC).date().isoformat()
        (tmp_path / "stack-truth" / f"{today}-mq-stack-truth.md").write_text("# truth\n")
        data = _cockpit()
        assert data["overall_gate"] == "GO"
        assert data["overall_contract"] == "READY"
        assert data["next_action"] == "all green"

    def test_missing_truth_note_suggests_export(self, stack_repo):
        data = _cockpit()
        assert data["next_action"] == "run stack truth-export — brain note is none"

    def test_pending_repo_drives_next_action(self, stack_repo):
        (stack_repo / "wip.txt").write_text("wip\n")
        data = _cockpit()
        assert data["next_action"].startswith("mq-agent:")
        assert data["overall_gate"] == "GO"  # dirty is a warning, not a blocker

    def test_cockpit_is_read_only(self, stack_repo):
        stack_cockpit()
        status = subprocess.run(["git", "status", "--short"], cwd=stack_repo,
                                capture_output=True, text=True, check=True)
        assert status.stdout.strip() == ""


class TestStackCockpitCli:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from mq_agent.main import app
        return CliRunner().invoke(app, args)

    def test_table_output(self, stack_repo):
        result = self._invoke(["stack", "cockpit"])
        assert result.exit_code == 0
        assert "mq-stack Cockpit" in result.output
        assert "mq-agent" in result.output
        assert "Next:" in result.output

    def test_json_output(self, stack_repo):
        result = self._invoke(["stack", "cockpit", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall_gate"] == "GO"
        assert data["repos"][0]["repo"] == "mq-agent"

    def test_registered_in_tool_registry(self):
        from mq_agent.tools import TOOL_REGISTRY
        assert TOOL_REGISTRY["stack_cockpit"] is stack_cockpit
