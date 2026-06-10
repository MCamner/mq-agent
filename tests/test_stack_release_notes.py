"""Tests for stack release-notes command and _release_notes_entry helper."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.stack_tools import _release_notes_entry

runner = CliRunner()


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def tagged_repo(tmp_path):
    """Git repo with one tag and one commit after the tag."""
    repo = tmp_path / "tagged"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)
    (repo / "VERSION").write_text("1.0.0\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, capture_output=True)
    (repo / "NEW.md").write_text("new\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat: add new feature"], cwd=repo, capture_output=True)
    return repo


@pytest.fixture()
def untagged_repo(tmp_path):
    """Git repo with commits but no tags."""
    repo = tmp_path / "untagged"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)
    (repo / "VERSION").write_text("0.1.0\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, capture_output=True)
    return repo


@pytest.fixture()
def up_to_date_repo(tmp_path):
    """Git repo where HEAD is the tag — no unreleased commits."""
    repo = tmp_path / "uptodate"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)
    (repo / "VERSION").write_text("2.0.0\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "release v2.0.0"], cwd=repo, capture_output=True)
    subprocess.run(["git", "tag", "v2.0.0"], cwd=repo, capture_output=True)
    return repo


# ── _release_notes_entry ────────────────────────────────────────────────────

class TestReleaseNotesEntry:
    def test_nonexistent_path_returns_not_found(self, tmp_path):
        entry = _release_notes_entry({"name": "ghost", "path": str(tmp_path / "nope")})
        assert entry["exists"] is False
        assert entry["commits"] == []
        assert entry["has_changes"] is False

    def test_tagged_repo_shows_commits_after_tag(self, tagged_repo):
        entry = _release_notes_entry({"name": "test", "path": str(tagged_repo)})
        assert entry["exists"] is True
        assert entry["last_tag"] == "v1.0.0"
        assert entry["has_changes"] is True
        assert len(entry["commits"]) == 1
        assert "feat: add new feature" in entry["commits"][0]

    def test_up_to_date_repo_has_no_commits(self, up_to_date_repo):
        entry = _release_notes_entry({"name": "test", "path": str(up_to_date_repo)})
        assert entry["exists"] is True
        assert entry["has_changes"] is False
        assert entry["commits"] == []

    def test_untagged_repo_falls_back_to_all_commits(self, untagged_repo):
        entry = _release_notes_entry({"name": "test", "path": str(untagged_repo)})
        assert entry["exists"] is True
        assert entry["last_tag"] is None
        assert entry["has_changes"] is True
        assert len(entry["commits"]) >= 1

    def test_version_read_correctly(self, tagged_repo):
        entry = _release_notes_entry({"name": "test", "path": str(tagged_repo)})
        assert entry["version"] == "1.0.0"

    def test_schema_keys_present(self, tagged_repo):
        entry = _release_notes_entry({"name": "test", "path": str(tagged_repo)})
        for key in ("name", "exists", "version", "last_tag", "commits", "has_changes"):
            assert key in entry


# ── CLI command ──────────────────────────────────────────────────────────────

class TestStackReleaseNotesCmd:
    def test_unknown_repo_filter_exits_1(self):
        result = runner.invoke(app, ["stack", "release-notes", "--repo", "nonexistent"])
        assert result.exit_code == 1

    def test_json_output_is_list(self):
        with patch("mq_agent.tools.stack_tools._release_notes_entry") as mock:
            mock.return_value = {
                "name": "fake", "exists": True, "version": "1.0.0",
                "last_tag": "v1.0.0", "commits": [], "has_changes": False,
            }
            result = runner.invoke(app, ["stack", "release-notes", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_json_includes_commits_key(self):
        with patch("mq_agent.tools.stack_tools._release_notes_entry") as mock:
            mock.return_value = {
                "name": "fake", "exists": True, "version": "1.2.0",
                "last_tag": "v1.1.0", "commits": ["abc1234 feat: something"], "has_changes": True,
            }
            result = runner.invoke(app, ["stack", "release-notes", "--json"])
        data = json.loads(result.output)
        assert any("commits" in r for r in data)

    def test_text_output_contains_repo_name(self):
        with patch("mq_agent.tools.stack_tools._release_notes_entry") as mock:
            mock.return_value = {
                "name": "mq-agent", "exists": True, "version": "1.9.0",
                "last_tag": "v1.9.0", "commits": ["abc feat: new"], "has_changes": True,
            }
            result = runner.invoke(app, ["stack", "release-notes"])
        assert result.exit_code == 0
        assert "mq-agent" in result.output

    def test_no_unreleased_shows_up_to_date_message(self):
        with patch("mq_agent.tools.stack_tools._release_notes_entry") as mock:
            mock.return_value = {
                "name": "mq-agent", "exists": True, "version": "1.9.0",
                "last_tag": "v1.9.0", "commits": [], "has_changes": False,
            }
            result = runner.invoke(app, ["stack", "release-notes"])
        assert result.exit_code == 0
        assert "no unreleased commits" in result.output or "up to date" in result.output

    def test_exit_code_always_0(self):
        with patch("mq_agent.tools.stack_tools._release_notes_entry") as mock:
            mock.return_value = {
                "name": "mq-agent", "exists": True, "version": "1.9.0",
                "last_tag": "v1.9.0", "commits": ["abc fix: something"], "has_changes": True,
            }
            result = runner.invoke(app, ["stack", "release-notes"])
        assert result.exit_code == 0

    def test_repo_filter_limits_output(self):
        captured = []

        def fake_entry(repo):
            captured.append(repo["name"])
            return {
                "name": repo["name"], "exists": True, "version": "1.0.0",
                "last_tag": "v1.0.0", "commits": [], "has_changes": False,
            }

        with patch("mq_agent.tools.stack_tools._release_notes_entry", side_effect=fake_entry):
            runner.invoke(app, ["stack", "release-notes", "--repo", "mq-agent"])

        assert captured == ["mq-agent"]
