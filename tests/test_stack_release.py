"""Tests for v1.14.0 stack release orchestration."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import mq_agent.tools.stack_tools as stack_tools
from mq_agent.tools.stack_release import (
    bump_version,
    execute_stack_release,
    plan_stack_release,
    stack_release,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True)


def _make_repo(tmp_path: Path, name: str = "mq-agent", with_remote: bool = False) -> Path:
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

    (repo / "feature.txt").write_text("new feature\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "feat: add feature"], repo)

    if with_remote:
        remote = tmp_path / f"{name}-remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        _git(["remote", "add", "origin", str(remote)], repo)
        _git(["push", "-u", "origin", "main"], repo)
    return repo


def _stack_entry(repo: Path) -> list[dict[str, str]]:
    return [{"name": repo.name, "path": str(repo), "role": "test"}]


@pytest.fixture
def stack_repo(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, with_remote=True)
    monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
    return repo


class TestBumpVersion:
    def test_patch(self):
        assert bump_version("1.2.3", "patch") == "1.2.4"

    def test_minor(self):
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_major(self):
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_invalid_version(self):
        with pytest.raises(ValueError):
            bump_version("not-a-version", "patch")

    def test_invalid_part(self):
        with pytest.raises(ValueError):
            bump_version("1.2.3", "huge")


class TestPlanStackRelease:
    def test_unknown_repo_is_no_go(self):
        plan = plan_stack_release("not-a-repo")
        assert plan["go"] is False
        assert any("unknown stack repo" in b for b in plan["blockers"])

    def test_missing_repo_is_no_go(self, tmp_path, monkeypatch):
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS",
                            [{"name": "ghost", "path": str(tmp_path / "ghost"), "role": "test"}])
        plan = plan_stack_release("ghost")
        assert plan["go"] is False
        assert "repo not found locally" in plan["blockers"]

    def test_clean_repo_is_go_with_full_step_plan(self, stack_repo):
        plan = plan_stack_release("mq-agent", bump="minor")
        assert plan["go"] is True
        assert plan["current_version"] == "1.0.0"
        assert plan["new_version"] == "1.1.0"
        assert plan["tag"] == "v1.1.0"
        assert [s["step"] for s in plan["steps"]] == [
            "bump-version", "sync-contract", "update-changelog",
            "commit", "tag", "push", "push-tag", "truth-export",
        ]

    def test_explicit_version_overrides_bump(self, stack_repo):
        plan = plan_stack_release("mq-agent", bump="patch", version="3.0.0")
        assert plan["go"] is True
        assert plan["new_version"] == "3.0.0"

    def test_bad_explicit_version_is_no_go(self, stack_repo):
        plan = plan_stack_release("mq-agent", version="3.0")
        assert plan["go"] is False
        assert any("not semver" in b for b in plan["blockers"])

    def test_dirty_tree_is_no_go(self, stack_repo):
        (stack_repo / "dirty.txt").write_text("uncommitted\n")
        plan = plan_stack_release("mq-agent")
        assert plan["go"] is False
        assert any("uncommitted changes" in b for b in plan["blockers"])

    def test_no_unreleased_commits_is_no_go(self, stack_repo):
        _git(["tag", "v1.0.1"], stack_repo)
        plan = plan_stack_release("mq-agent")
        assert plan["go"] is False
        assert any("no unreleased commits" in b for b in plan["blockers"])

    def test_off_main_branch_is_no_go(self, stack_repo):
        _git(["switch", "-c", "feature"], stack_repo)
        plan = plan_stack_release("mq-agent")
        assert plan["go"] is False
        assert any("not on main" in b for b in plan["blockers"])

    def test_plan_is_read_only(self, stack_repo):
        plan_stack_release("mq-agent")
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.0"
        status = subprocess.run(["git", "status", "--short"], cwd=stack_repo,
                                capture_output=True, text=True, check=True)
        assert status.stdout.strip() == ""


class TestExecuteStackRelease:
    def _truth_patch(self):
        return patch(
            "mq_agent.tools.stack_truth.stack_truth_export",
            return_value={"path": "/tmp/truth.md", "ok": True, "status": "READY"},
        )

    def test_refuses_no_go_plan(self, stack_repo):
        (stack_repo / "dirty.txt").write_text("x\n")
        plan = plan_stack_release("mq-agent")
        result = execute_stack_release(plan)
        assert result["ok"] is False
        assert result["released"] is False
        assert "NO-GO" in result["error"]
        assert result["steps"] == []

    def test_full_release_succeeds(self, stack_repo):
        plan = plan_stack_release("mq-agent", bump="minor")
        with self._truth_patch():
            result = execute_stack_release(plan)
        assert result["ok"] is True
        assert result["released"] is True
        assert all(s["status"] == "done" for s in result["steps"])

        assert (stack_repo / "VERSION").read_text().strip() == "1.1.0"
        contract = json.loads((stack_repo / ".mq" / "repo-contract.json").read_text())
        assert contract["version"] == "1.1.0"
        changelog = (stack_repo / "CHANGELOG.md").read_text()
        assert "## [v1.1.0]" in changelog
        assert "feat: add feature" in changelog

        tags = subprocess.run(["git", "tag"], cwd=stack_repo,
                              capture_output=True, text=True, check=True).stdout
        assert "v1.1.0" in tags
        remote_tags = subprocess.run(
            ["git", "ls-remote", "--tags", "origin"], cwd=stack_repo,
            capture_output=True, text=True, check=True).stdout
        assert "v1.1.0" in remote_tags

    def test_release_rechecks_gates_after_success(self, stack_repo):
        plan = plan_stack_release("mq-agent")
        with self._truth_patch():
            execute_stack_release(plan)
        gate = json.loads(stack_tools.stack_release_check())
        contract_gate = json.loads(stack_tools.stack_contract_check())
        assert gate["overall"] == "GO"
        assert contract_gate["overall"] == "READY"

    def test_push_failure_aborts_remaining_steps(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path, with_remote=False)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        plan = plan_stack_release("mq-agent")
        result = execute_stack_release(plan)
        assert result["ok"] is False
        assert result["released"] is False
        statuses = {s["step"]: s["status"] for s in result["steps"]}
        assert statuses["push"] == "failed"
        assert statuses["push-tag"] == "aborted"
        assert statuses["truth-export"] == "aborted"

    def test_pre_commit_failure_rolls_back_file_edits(self, stack_repo):
        plan = plan_stack_release("mq-agent")
        with patch("mq_agent.tools.stack_release._update_changelog",
                   side_effect=RuntimeError("disk full")):
            result = execute_stack_release(plan)
        assert result["ok"] is False
        assert result["released"] is False
        assert "VERSION" in result.get("rolled_back", [])
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.0"
        contract = json.loads((stack_repo / ".mq" / "repo-contract.json").read_text())
        assert contract["version"] == "1.0.0"
        status = subprocess.run(["git", "status", "--short"], cwd=stack_repo,
                                capture_output=True, text=True, check=True)
        assert status.stdout.strip() == ""

    def test_truth_export_failure_reports_released_with_warning(self, stack_repo):
        plan = plan_stack_release("mq-agent")
        with patch("mq_agent.tools.stack_truth.stack_truth_export",
                   side_effect=RuntimeError("vault offline")):
            result = execute_stack_release(plan)
        assert result["ok"] is False
        assert result["released"] is True
        assert "truth-export failed" in result["warning"]


class TestStackReleaseTool:
    def test_dry_run_returns_plan_json(self, stack_repo):
        raw = stack_release("mq-agent")
        data = json.loads(raw)
        assert data["mode"] == "dry-run"
        assert data["go"] is True
        assert data["new_version"] == "1.0.1"

    def test_execute_returns_result_json(self, stack_repo):
        with patch("mq_agent.tools.stack_truth.stack_truth_export",
                   return_value={"path": "/tmp/truth.md"}):
            raw = stack_release("mq-agent", bump="minor", execute=True)
        data = json.loads(raw)
        assert data["mode"] == "execute"
        assert data["ok"] is True
        assert data["tag"] == "v1.1.0"


# ── CLI ──────────────────────────────────────────────────────────────────────

class TestStackReleaseCli:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from mq_agent.main import app
        return CliRunner().invoke(app, args)

    def test_dry_run_is_default_and_prints_plan(self, stack_repo):
        result = self._invoke(["stack", "release", "--repo", "mq-agent"])
        assert result.exit_code == 0
        assert "dry-run:" in result.output
        assert "1.0.1" in result.output
        assert "--execute" in result.output
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.0"

    def test_no_go_exits_1(self, stack_repo):
        (stack_repo / "dirty.txt").write_text("x\n")
        result = self._invoke(["stack", "release", "--repo", "mq-agent"])
        assert result.exit_code == 1
        assert "NO-GO" in result.output

    def test_invalid_bump_exits_1(self, stack_repo):
        result = self._invoke(["stack", "release", "--repo", "mq-agent", "--bump", "huge"])
        assert result.exit_code == 1

    def test_json_dry_run(self, stack_repo):
        result = self._invoke(["stack", "release", "--repo", "mq-agent", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["go"] is True
        assert data["mode"] == "dry-run"

    def test_execute_releases_and_prints_steps(self, stack_repo):
        with patch("mq_agent.tools.stack_truth.stack_truth_export",
                   return_value={"path": "/tmp/truth.md"}):
            result = self._invoke(["stack", "release", "--repo", "mq-agent", "--execute"])
        assert result.exit_code == 0
        assert "Released mq-agent v1.0.1" in result.output
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.1"
