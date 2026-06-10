"""Tests for CI mode (--ci) on stack contract-check and release-check."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.stack_tools import (
    _ci_repo_path,
    _contract_entry,
    _release_entry,
    stack_contract_check,
    stack_release_check,
)

runner = CliRunner()


# ── fixtures ────────────────────────────────────────────────────────────────

def _init_repo(repo, version="1.0.0"):
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)
    (repo / "VERSION").write_text(f"{version}\n")
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


@pytest.fixture()
def ci_checkout(tmp_path):
    """Git repo named like a stack repo, with a valid version-matched contract."""
    repo = tmp_path / "mq-testrepo"
    repo.mkdir()
    _init_repo(repo)
    mq = repo / ".mq"
    mq.mkdir()
    (mq / "repo-contract.json").write_text(json.dumps({
        "repo": "mq-testrepo",
        "role": "tester",
        "version": "1.0.0",
        "status": "active",
        "contracts": ["test.v1"],
    }))
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add contract"], cwd=repo, capture_output=True)
    return repo


# ── _ci_repo_path ────────────────────────────────────────────────────────────

class TestCiRepoPath:
    def test_cwd_matching_name_resolves(self, ci_checkout, monkeypatch):
        monkeypatch.chdir(ci_checkout)
        assert _ci_repo_path({"name": "mq-testrepo", "path": "~/nope"}) == ci_checkout

    def test_cwd_other_name_returns_none(self, ci_checkout, monkeypatch):
        monkeypatch.chdir(ci_checkout)
        assert _ci_repo_path({"name": "mq-other", "path": "~/nope"}) is None

    def test_cwd_without_git_returns_none(self, tmp_path, monkeypatch):
        plain = tmp_path / "mq-testrepo"
        plain.mkdir()
        monkeypatch.chdir(plain)
        assert _ci_repo_path({"name": "mq-testrepo", "path": "~/nope"}) is None


# ── _contract_entry CI mode ──────────────────────────────────────────────────

class TestContractEntryCiMode:
    def test_missing_repo_local_mode_blocked(self, tmp_path):
        e = _contract_entry({"name": "ghost", "path": str(tmp_path / "nope")})
        assert e["status"] == "BLOCKED"

    def test_missing_repo_ci_mode_skipped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        e = _contract_entry({"name": "ghost", "path": str(tmp_path / "nope")}, ci=True)
        assert e["status"] == "SKIPPED"
        assert "CI workspace" in e["reason"]

    def test_ci_checkout_validated_via_cwd(self, ci_checkout, tmp_path, monkeypatch):
        monkeypatch.chdir(ci_checkout)
        e = _contract_entry({"name": "mq-testrepo", "path": str(tmp_path / "nope")}, ci=True)
        assert e["status"] == "READY"

    def test_ci_checkout_drift_still_detected(self, ci_checkout, tmp_path, monkeypatch):
        (ci_checkout / "VERSION").write_text("2.0.0\n")
        subprocess.run(["git", "add", "."], cwd=ci_checkout, capture_output=True)
        subprocess.run(["git", "commit", "-m", "bump"], cwd=ci_checkout, capture_output=True)
        monkeypatch.chdir(ci_checkout)
        e = _contract_entry({"name": "mq-testrepo", "path": str(tmp_path / "nope")}, ci=True)
        assert e["status"] == "DRIFT"
        assert "version mismatch" in e["reason"]

    def test_existing_repo_unaffected_by_ci_flag(self, ci_checkout):
        e = _contract_entry({"name": "mq-testrepo", "path": str(ci_checkout)}, ci=True)
        assert e["status"] == "READY"


# ── _release_entry CI mode ───────────────────────────────────────────────────

class TestReleaseEntryCiMode:
    def test_missing_repo_local_mode_no_go(self, tmp_path):
        e = _release_entry({"name": "ghost", "path": str(tmp_path / "nope")})
        assert e["go"] is False

    def test_missing_repo_ci_mode_skipped_and_go(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        e = _release_entry({"name": "ghost", "path": str(tmp_path / "nope")}, ci=True)
        assert e["skipped"] is True
        assert e["go"] is True
        assert e["blockers"] == []

    def test_ci_checkout_checked_via_cwd(self, ci_checkout, tmp_path, monkeypatch):
        monkeypatch.chdir(ci_checkout)
        e = _release_entry({"name": "mq-testrepo", "path": str(tmp_path / "nope")}, ci=True)
        assert e["exists"] is True
        assert e["go"] is True

    def test_ci_checkout_blocker_still_detected(self, ci_checkout, tmp_path, monkeypatch):
        (ci_checkout / "README.md").unlink()
        monkeypatch.chdir(ci_checkout)
        e = _release_entry({"name": "mq-testrepo", "path": str(tmp_path / "nope")}, ci=True)
        assert e["go"] is False
        assert "no README.md" in e["blockers"]


# ── module-level checks in CI mode ───────────────────────────────────────────

def _fake_stack(tmp_path):
    return [
        {"name": "mq-ghost-one", "path": str(tmp_path / "nope1"), "role": "r"},
        {"name": "mq-ghost-two", "path": str(tmp_path / "nope2"), "role": "r"},
    ]


class TestStackChecksCiMode:
    def test_contract_check_ci_all_missing_is_ready(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            data = json.loads(stack_contract_check(ci=True))
        assert data["overall"] == "READY"
        assert data["mode"] == "ci"
        assert all(e["status"] == "SKIPPED" for e in data["repos"])

    def test_contract_check_local_all_missing_is_not_ready(self, tmp_path):
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            data = json.loads(stack_contract_check())
        assert data["overall"] == "NOT READY"
        assert data["mode"] == "local"

    def test_release_check_ci_all_missing_is_go(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            data = json.loads(stack_release_check(ci=True))
        assert data["overall"] == "GO"
        assert data["mode"] == "ci"


# ── CLI tests ────────────────────────────────────────────────────────────────

class TestCliCiMode:
    def test_contract_check_ci_json_exit_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            result = runner.invoke(app, ["stack", "contract-check", "--ci", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall"] == "READY"

    def test_contract_check_local_json_exit_1(self, tmp_path):
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            result = runner.invoke(app, ["stack", "contract-check", "--json"])
        assert result.exit_code == 1

    def test_contract_check_ci_text_shows_skipped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            result = runner.invoke(app, ["stack", "contract-check", "--ci"])
        assert result.exit_code == 0
        assert "SKIPPED" in result.output

    def test_release_check_ci_json_exit_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            result = runner.invoke(app, ["stack", "release-check", "--ci", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall"] == "GO"
        assert data["mode"] == "ci"

    def test_release_check_local_json_exit_1(self, tmp_path):
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            result = runner.invoke(app, ["stack", "release-check", "--json"])
        assert result.exit_code == 1

    def test_release_check_ci_table_shows_skipped(self, tmp_path, monkeypatch):
        from mq_agent.main import console
        monkeypatch.setattr(console, "_width", 160, raising=False)
        monkeypatch.chdir(tmp_path)
        with patch("mq_agent.tools.stack_tools.MQ_STACK_REPOS", _fake_stack(tmp_path)):
            result = runner.invoke(app, ["stack", "release-check", "--ci"])
        assert result.exit_code == 0
        assert "skipped" in result.output
