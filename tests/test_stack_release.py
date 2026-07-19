"""Tests for v1.14.0 stack release orchestration."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import mq_agent.tools.stack_tools as stack_tools
from mq_agent.tools.stack_release import (
    _write_version,
    bump_version,
    execute_stack_release,
    execute_stack_release_all,
    plan_stack_release,
    plan_stack_release_all,
    preflight_stack_release_all,
    stack_release,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True)


def _make_repo(
    tmp_path: Path, name: str = "mq-agent", with_remote: bool = False,
    with_unreleased: bool = True,
) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgSign", "false"], repo)
    _git(["config", "tag.gpgSign", "false"], repo)

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

    if with_unreleased:
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


def _tags(repo: Path) -> list[str]:
    out = subprocess.run(["git", "tag", "--list"], cwd=repo,
                         capture_output=True, text=True, check=True)
    return sorted(out.stdout.split())


def _porcelain(repo: Path) -> str:
    out = subprocess.run(["git", "status", "--short"], cwd=repo,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


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

    def test_already_tagged_target_version_is_no_go(self, stack_repo):
        # The target tag already exists locally — the drift failure mode: a
        # release for this version was already cut. Target v1.0.0 explicitly so
        # unreleased commits remain present and this is the new blocker.
        plan = plan_stack_release("mq-agent", version="1.0.0")
        assert plan["go"] is False
        assert any("already tagged" in b.lower() for b in plan["blockers"])

    def test_target_tagged_only_on_remote_is_no_go(self, stack_repo):
        # A tag pushed to origin but pruned locally must still block, so a
        # re-release cannot collide with an already-published tag.
        _git(["push", "origin", "v1.0.0"], stack_repo)
        _git(["tag", "-d", "v1.0.0"], stack_repo)
        plan = plan_stack_release("mq-agent", version="1.0.0")
        assert plan["go"] is False
        assert any("already tagged" in b.lower() for b in plan["blockers"])

    def test_new_tag_not_blocked_by_tag_check(self, stack_repo):
        # A target version with no existing tag stays GO — the check must not
        # over-block.
        plan = plan_stack_release("mq-agent", version="9.9.9")
        assert plan["go"] is True
        assert not any("already tagged" in b.lower() for b in plan["blockers"])

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

    def test_refuses_when_switched_off_main_after_plan(self, stack_repo):
        # A GO plan built on main must not execute if the checkout moved to a
        # feature branch between plan and execute — the shape that cut the
        # drifted tags. Nothing may be created.
        plan = plan_stack_release("mq-agent")
        assert plan["go"] is True
        _git(["switch", "-c", "feature"], stack_repo)
        result = execute_stack_release(plan)
        assert result["ok"] is False
        assert result["released"] is False
        assert "main" in result["error"].lower()
        assert result["steps"] == []
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.0"
        tags = subprocess.run(["git", "tag"], cwd=stack_repo,
                              capture_output=True, text=True, check=True).stdout
        assert "v1.0.1" not in tags

    def test_refuses_when_tree_dirtied_after_plan(self, stack_repo):
        # A tree dirtied after planning must abort before any mutation, so a
        # release is never cut from an unclean tree.
        plan = plan_stack_release("mq-agent")
        (stack_repo / "sneaky.txt").write_text("x\n")
        result = execute_stack_release(plan)
        assert result["ok"] is False
        assert result["released"] is False
        assert "clean" in result["error"].lower() or "dirty" in result["error"].lower()
        assert result["steps"] == []
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.0"

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


# ── multi-repo plan (v1.23.0) ────────────────────────────────────────────────

def _multi_stack(tmp_path, monkeypatch):
    """A three-repo stack: one ready, one blocked (dirty), one up-to-date."""
    ready = _make_repo(tmp_path, name="mq-agent")
    blocked = _make_repo(tmp_path, name="mq-mcp")
    (blocked / "dirty.txt").write_text("x\n")  # uncommitted → blocked
    uptodate = _make_repo(tmp_path, name="repo-signal", with_unreleased=False)
    entries = [
        {"name": "mq-agent", "path": str(ready), "role": "test"},
        {"name": "mq-mcp", "path": str(blocked), "role": "test"},
        {"name": "repo-signal", "path": str(uptodate), "role": "test"},
    ]
    monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", entries)
    return ready, blocked, uptodate


@pytest.fixture
def multi_stack(tmp_path, monkeypatch):
    return _multi_stack(tmp_path, monkeypatch)


class TestPlanStackReleaseAll:
    def test_categorizes_every_repo(self, multi_stack):
        data = plan_stack_release_all()
        states = {r["repo"]: r["state"] for r in data["repos"]}
        assert states == {
            "mq-agent": "ready",
            "mq-mcp": "blocked",
            "repo-signal": "up-to-date",
        }

    def test_counts_and_overall_go(self, multi_stack):
        data = plan_stack_release_all()
        assert data["go_count"] == 1
        assert data["blocked_count"] == 1
        assert data["uptodate_count"] == 1
        assert data["overall_go"] is True
        assert data["schema"] == "mq_stack_release_all.v1"

    def test_ready_repo_carries_target_version(self, multi_stack):
        data = plan_stack_release_all(bump="minor")
        ready = next(r for r in data["repos"] if r["repo"] == "mq-agent")
        assert ready["new_version"] == "1.1.0"
        assert ready["tag"] == "v1.1.0"

    def test_up_to_date_is_not_blocked(self, multi_stack):
        data = plan_stack_release_all()
        uptodate = next(r for r in data["repos"] if r["repo"] == "repo-signal")
        assert uptodate["state"] == "up-to-date"
        assert uptodate["blockers"] == []
        assert uptodate["new_version"] is None

    def test_blocked_repo_reports_reason(self, multi_stack):
        data = plan_stack_release_all()
        blocked = next(r for r in data["repos"] if r["repo"] == "mq-mcp")
        assert any("uncommitted" in b for b in blocked["blockers"])

    def test_overall_go_false_when_nothing_ready(self, tmp_path, monkeypatch):
        only_uptodate = _make_repo(tmp_path, name="repo-signal", with_unreleased=False)
        monkeypatch.setattr(
            stack_tools, "MQ_STACK_REPOS",
            [{"name": "repo-signal", "path": str(only_uptodate), "role": "test"}],
        )
        data = plan_stack_release_all()
        assert data["go_count"] == 0
        assert data["overall_go"] is False


class TestStackReleaseAllCli:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from mq_agent.main import app
        return CliRunner().invoke(app, args)

    def test_all_prints_table_and_exits_1_when_blocked(self, multi_stack):
        result = self._invoke(["stack", "release", "--all"])
        assert "mq-agent" in result.output
        assert "ready" in result.output
        assert "blocked" in result.output
        assert result.exit_code == 1  # mq-mcp is blocked

    def test_all_json(self, multi_stack):
        result = self._invoke(["stack", "release", "--all", "--json"])
        data = json.loads(result.output)
        assert data["schema"] == "mq_stack_release_all.v1"
        assert data["go_count"] == 1

    def test_all_and_repo_are_mutually_exclusive(self, multi_stack):
        result = self._invoke(["stack", "release", "--all", "--repo", "mq-agent"])
        assert result.exit_code == 1
        assert "either" in result.output.lower()

    def test_neither_repo_nor_all_errors(self, stack_repo):
        result = self._invoke(["stack", "release"])
        assert result.exit_code == 1

    def test_all_execute_without_approve_is_rejected(self, multi_stack):
        # Until the execute slice shipped this pointed at --repo. Multi-repo
        # execute now exists, so the refusal is the missing --approve instead.
        result = self._invoke(["stack", "release", "--all", "--execute"])
        assert result.exit_code == 1
        assert "--approve" in result.output
        # nothing was released
        for repo in multi_stack:
            assert (repo / "VERSION").read_text().strip() == "1.0.0"

    def test_all_exits_0_when_nothing_blocked(self, tmp_path, monkeypatch):
        ready = _make_repo(tmp_path, name="mq-agent")
        uptodate = _make_repo(tmp_path, name="repo-signal", with_unreleased=False)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", [
            {"name": "mq-agent", "path": str(ready), "role": "test"},
            {"name": "repo-signal", "path": str(uptodate), "role": "test"},
        ])
        result = self._invoke(["stack", "release", "--all"])
        assert result.exit_code == 0


# ── multi-repo preflight hook (v1.23.0) ──────────────────────────────────────

def _release_check_body(status: str = "READY", exit_code: int = 0,
                        valid_json: bool = True) -> str:
    if not valid_json:
        return "#!/bin/sh\necho 'not json at all'\nexit 0\n"
    return (
        "#!/bin/sh\n"
        "cat <<'JSON'\n"
        '{"schema":"repo_release_check.v1","repo":"r","status":"' + status + '",'
        '"blockers":[],"warnings":[],"evidence":{}}\n'
        "JSON\n"
        f"exit {exit_code}\n"
    )


def _add_release_check(repo: Path, *, status: str = "READY", exit_code: int = 0,
                       valid_json: bool = True, executable: bool = True) -> None:
    """Drop a root release-check.sh, commit it, and push so the tree stays clean."""
    script = repo / "release-check.sh"
    script.write_text(_release_check_body(status, exit_code, valid_json))
    if executable:
        script.chmod(0o755)
    _git(["add", "release-check.sh"], repo)
    _git(["commit", "-m", "chore: release-check"], repo)
    subprocess.run(["git", "push"], cwd=repo, capture_output=True, text=True)


def _ready_repo(tmp_path: Path, name: str = "mq-agent") -> Path:
    """A repo that passes every preflight blocker: clean, on main, unreleased
    commits, pushed, contract == VERSION, release-check READY."""
    repo = _make_repo(tmp_path, name=name, with_remote=True)
    _add_release_check(repo, status="READY")
    return repo


def _unpushed_commit(repo: Path) -> None:
    (repo / "extra.txt").write_text("more\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "feat: more"], repo)  # deliberately not pushed


class TestPreflightStackReleaseAll:
    def test_all_ready_would_execute(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        data = preflight_stack_release_all()
        assert data["schema"] == "mq_stack_release_all_execute.v1"
        assert data["ready_count"] == 1
        assert data["blocked_count"] == 0
        assert data["would_execute"] is True
        assert data["aborted_phase"] == "none"
        assert all(r["execute_state"] is None for r in data["repos"])

    def test_missing_release_check_blocks(self, stack_repo):
        data = preflight_stack_release_all()
        r = data["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("no release-check" in b.lower() for b in r["blockers"])
        assert data["would_execute"] is False
        assert data["aborted_phase"] == "preflight"

    def test_not_executable_blocks(self, stack_repo):
        _add_release_check(stack_repo, executable=False)
        data = preflight_stack_release_all()
        r = data["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("executable" in b.lower() for b in r["blockers"])

    def test_release_check_nonzero_exit_blocks(self, stack_repo):
        _add_release_check(stack_repo, exit_code=1)
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("exit" in b.lower() for b in r["blockers"])

    def test_release_check_status_blocked_surfaces(self, stack_repo):
        _add_release_check(stack_repo, status="BLOCKED")
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("release-check" in b.lower() for b in r["blockers"])

    def test_release_check_invalid_json_blocks(self, stack_repo):
        _add_release_check(stack_repo, valid_json=False)
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("json" in b.lower() for b in r["blockers"])

    def test_unpushed_commits_block(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        _unpushed_commit(repo)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("unpushed" in b.lower() for b in r["blockers"])

    def test_version_mismatch_blocks(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        contract = repo / ".mq" / "repo-contract.json"
        d = json.loads(contract.read_text())
        d["version"] = "9.9.9"
        contract.write_text(json.dumps(d, indent=2) + "\n")
        _git(["commit", "-am", "drift contract"], repo)
        subprocess.run(["git", "push"], cwd=repo, capture_output=True, text=True)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("version mismatch" in b.lower() for b in r["blockers"])

    def test_dirty_tree_blocks(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        (repo / "dirty.txt").write_text("x\n")
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("uncommitted" in b.lower() for b in r["blockers"])

    def test_off_main_blocks(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        _git(["switch", "-c", "feature"], repo)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("not on main" in b.lower() for b in r["blockers"])

    def test_target_tag_exists_blocks(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        _git(["tag", "v1.0.1", "HEAD~1"], repo)  # patch target already tagged
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "BLOCKED"
        assert any("already tagged" in b.lower() for b in r["blockers"])

    def test_up_to_date_repo_skips_hardened_checks(self, tmp_path, monkeypatch):
        # No release-check.sh, but up-to-date → must NOT be blocked on it.
        repo = _make_repo(tmp_path, name="repo-signal",
                          with_unreleased=False, with_remote=True)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        r = preflight_stack_release_all()["repos"][0]
        assert r["preflight_state"] == "UP-TO-DATE"
        assert r["blockers"] == []

    def test_preflight_is_read_only(self, stack_repo):
        preflight_stack_release_all()
        assert (stack_repo / "VERSION").read_text().strip() == "1.0.0"
        status = subprocess.run(["git", "status", "--short"], cwd=stack_repo,
                                capture_output=True, text=True, check=True)
        assert status.stdout.strip() == ""

    def test_mixed_stack_reports_all_in_order(self, tmp_path, monkeypatch):
        ready = _ready_repo(tmp_path, name="mq-agent")
        blocked = _make_repo(tmp_path, name="mq-mcp", with_remote=True)  # no check
        uptodate = _make_repo(tmp_path, name="repo-signal",
                              with_unreleased=False, with_remote=True)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", [
            {"name": "mq-agent", "path": str(ready), "role": "test"},
            {"name": "mq-mcp", "path": str(blocked), "role": "test"},
            {"name": "repo-signal", "path": str(uptodate), "role": "test"},
        ])
        data = preflight_stack_release_all()
        assert [r["repo"] for r in data["repos"]] == ["mq-agent", "mq-mcp", "repo-signal"]
        states = {r["repo"]: r["preflight_state"] for r in data["repos"]}
        assert states == {
            "mq-agent": "READY", "mq-mcp": "BLOCKED", "repo-signal": "UP-TO-DATE",
        }
        assert data["would_execute"] is False
        assert data["aborted_phase"] == "preflight"


class TestPreflightCli:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from mq_agent.main import app
        return CliRunner().invoke(app, args)

    def test_preflight_requires_all(self, stack_repo):
        result = self._invoke(["stack", "release", "--preflight", "--repo", "mq-agent"])
        assert result.exit_code == 1

    def test_preflight_and_execute_mutually_exclusive(self, stack_repo):
        result = self._invoke(["stack", "release", "--all", "--preflight", "--execute"])
        assert result.exit_code == 1

    def test_preflight_reports_and_exits_1_when_blocked(self, stack_repo):
        result = self._invoke(["stack", "release", "--all", "--preflight"])
        assert result.exit_code == 1  # missing release-check → blocked
        assert "blocked" in result.output.lower()

    def test_preflight_json(self, stack_repo):
        result = self._invoke(["stack", "release", "--all", "--preflight", "--json"])
        data = json.loads(result.output)
        assert data["schema"] == "mq_stack_release_all_execute.v1"

    def test_preflight_exits_0_when_all_ready(self, tmp_path, monkeypatch):
        repo = _ready_repo(tmp_path)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        result = self._invoke(["stack", "release", "--all", "--preflight"])
        assert result.exit_code == 0


# ── multi-repo execute (v1.23.0) ─────────────────────────────────────────────

def _ready_stack(tmp_path, monkeypatch, names: list[str],
                 no_remote: tuple[str, ...] = ()) -> list[Path]:
    """N preflight-READY repos registered in the given (dependency) order.

    A repo named in `no_remote` still passes preflight — nothing it is checked
    on requires a remote — but its `git push` fails for real during execute.
    That is the failure injection: a genuine mid-flight push failure, not a
    patched return value.
    """
    repos = [
        _ready_repo(tmp_path, name=n) if n not in no_remote
        else _no_remote_ready_repo(tmp_path, name=n)
        for n in names
    ]
    monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", [
        {"name": r.name, "path": str(r), "role": "test"} for r in repos
    ])
    return repos


def _no_remote_ready_repo(tmp_path: Path, name: str) -> Path:
    repo = _make_repo(tmp_path, name=name, with_remote=False)
    _add_release_check(repo, status="READY")
    return repo


def _truth_export_patch():
    return patch(
        "mq_agent.tools.stack_truth.stack_truth_export",
        return_value={"path": "/tmp/truth.md", "ok": True, "status": "READY"},
    )


class TestExecuteStackReleaseAll:
    def test_requires_approve(self, tmp_path, monkeypatch):
        # --execute alone must not mutate: the stack convention is that write
        # flows need an explicit --approve, and this is the widest write there is.
        repos = _ready_stack(tmp_path, monkeypatch, ["a", "b"])
        data = execute_stack_release_all(approve=False)
        assert data["approved"] is False
        assert data["aborted_phase"] == "preflight"
        assert all(r["execute_state"] is None for r in data["repos"])
        for repo in repos:
            assert (repo / "VERSION").read_text().strip() == "1.0.0"
            assert _tags(repo) == ["v1.0.0"]

    def test_blocked_repo_aborts_before_any_mutation(self, tmp_path, monkeypatch):
        # The fail-fast gate: one blocked repo stops the whole run in the
        # preflight phase, so even the READY repos ahead of it are untouched.
        repos = _ready_stack(tmp_path, monkeypatch, ["a", "b"])
        (repos[1] / "dirty.txt").write_text("x\n")
        data = execute_stack_release_all(approve=True)
        assert data["aborted_phase"] == "preflight"
        assert data["released_count"] == 0
        assert all(r["execute_state"] is None for r in data["repos"])
        for repo in repos:
            assert (repo / "VERSION").read_text().strip() == "1.0.0"
            assert _tags(repo) == ["v1.0.0"]

    def test_releases_every_ready_repo_in_order(self, tmp_path, monkeypatch):
        repos = _ready_stack(tmp_path, monkeypatch, ["a", "b", "c"])
        with _truth_export_patch():
            data = execute_stack_release_all(approve=True)
        assert data["aborted_phase"] == "none"
        assert data["released_count"] == 3
        assert [r["repo"] for r in data["repos"]] == ["a", "b", "c"]
        assert all(r["execute_state"] == "RELEASED" for r in data["repos"])
        assert data["executed_at"] is not None
        for repo in repos:
            assert (repo / "VERSION").read_text().strip() == "1.0.1"
            assert "v1.0.1" in _tags(repo)

    def test_repo_2_of_5_fails_so_3_to_5_are_skipped(self, tmp_path, monkeypatch):
        # The locked partial-failure contract: stop-on-first-failure, and every
        # repo after the failure is reported SKIPPED and left completely untouched.
        repos = _ready_stack(tmp_path, monkeypatch, ["a", "b", "c", "d", "e"],
                             no_remote=("b",))
        with _truth_export_patch():
            data = execute_stack_release_all(approve=True)

        states = {r["repo"]: r["execute_state"] for r in data["repos"]}
        assert states == {
            "a": "RELEASED", "b": "FAILED",
            "c": "SKIPPED", "d": "SKIPPED", "e": "SKIPPED",
        }
        assert data["aborted_phase"] == "execute"
        assert data["released_count"] == 1
        assert data["failed_count"] == 1
        assert data["skipped_count"] == 3

        # c/d/e never started — no bump, no tag, clean tree.
        for repo in repos[2:]:
            assert (repo / "VERSION").read_text().strip() == "1.0.0"
            assert _tags(repo) == ["v1.0.0"]
            assert _porcelain(repo) == ""

    def test_already_released_repo_is_not_rolled_back(self, tmp_path, monkeypatch):
        # Locked decision 5: no destructive rollback across repos. Repo a is
        # released before b fails; its tag and commit must survive untouched.
        repos = _ready_stack(tmp_path, monkeypatch, ["a", "b"], no_remote=("b",))
        with _truth_export_patch():
            data = execute_stack_release_all(approve=True)

        released, failed = repos[0], repos[1]
        assert data["repos"][0]["execute_state"] == "RELEASED"
        assert data["repos"][1]["execute_state"] == "FAILED"

        # a stays released, locally and on its remote.
        assert (released / "VERSION").read_text().strip() == "1.0.1"
        assert "v1.0.1" in _tags(released)
        remote_tags = subprocess.run(
            ["git", "ls-remote", "--tags", "origin"], cwd=released,
            capture_output=True, text=True, check=True,
        ).stdout
        assert "v1.0.1" in remote_tags

        # b failed at push: the release commit stays local, the tag is local,
        # and nothing was force-pushed or deleted anywhere.
        assert (failed / "VERSION").read_text().strip() == "1.0.1"

    def test_up_to_date_repo_is_not_executed(self, tmp_path, monkeypatch):
        ready = _ready_repo(tmp_path, name="a")
        stale = _make_repo(tmp_path, name="b", with_remote=True, with_unreleased=False)
        _add_release_check(stale, status="READY")
        # the release-check commit is itself unreleased — re-point the tag at
        # HEAD so the repo is genuinely up to date
        _git(["tag", "-d", "v1.0.0"], stale)
        _git(["tag", "v1.0.0"], stale)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", [
            {"name": "a", "path": str(ready), "role": "test"},
            {"name": "b", "path": str(stale), "role": "test"},
        ])
        with _truth_export_patch():
            data = execute_stack_release_all(approve=True)
        by_repo = {r["repo"]: r for r in data["repos"]}
        assert by_repo["b"]["preflight_state"] == "UP-TO-DATE"
        assert by_repo["b"]["execute_state"] is None
        assert data["released_count"] == 1


class TestExecuteStackReleaseAllCli:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from mq_agent.main import app
        return CliRunner().invoke(app, args)

    def test_execute_without_approve_is_refused(self, tmp_path, monkeypatch):
        repos = _ready_stack(tmp_path, monkeypatch, ["a"])
        result = self._invoke(["stack", "release", "--all", "--execute"])
        assert result.exit_code == 1
        assert "--approve" in result.output
        # a repo that *would* be released must not render as "—" here — that
        # reads as "nothing happens to this repo"
        assert "READY" in result.output
        assert (repos[0] / "VERSION").read_text().strip() == "1.0.0"

    def test_execute_with_approve_releases(self, tmp_path, monkeypatch):
        repos = _ready_stack(tmp_path, monkeypatch, ["a"])
        with _truth_export_patch():
            result = self._invoke(["stack", "release", "--all", "--execute", "--approve"])
        assert result.exit_code == 0
        assert (repos[0] / "VERSION").read_text().strip() == "1.0.1"

    def test_execute_exits_1_when_preflight_blocks(self, tmp_path, monkeypatch):
        repos = _ready_stack(tmp_path, monkeypatch, ["a"])
        (repos[0] / "dirty.txt").write_text("x\n")
        result = self._invoke(["stack", "release", "--all", "--execute", "--approve"])
        assert result.exit_code == 1
        assert (repos[0] / "VERSION").read_text().strip() == "1.0.0"

    def test_execute_json(self, tmp_path, monkeypatch):
        _ready_stack(tmp_path, monkeypatch, ["a"])
        with _truth_export_patch():
            result = self._invoke(
                ["stack", "release", "--all", "--execute", "--approve", "--json"]
            )
        data = json.loads(result.output)
        assert data["schema"] == "mq_stack_release_all_execute.v1"
        assert data["approved"] is True


# ── uv.lock version surface ──────────────────────────────────────────────────

_UV_LOCK = """version = 1
requires-python = ">=3.11"

[[package]]
name = "httpx"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "mq-agent"
version = "1.0.0"
source = { editable = "." }
dependencies = [
    { name = "httpx" },
]

[[package]]
name = "zzz-other"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
"""


def _lock_version(repo: Path, package: str) -> str:
    """Read one package's version out of uv.lock."""
    block = None
    for chunk in repo.joinpath("uv.lock").read_text().split("[[package]]"):
        if f'name = "{package}"' in chunk:
            block = chunk
            break
    assert block is not None, f"{package} not found in uv.lock"
    return re.search(r'^version = "([^"]+)"', block, re.MULTILINE).group(1)


class TestLockfileVersionSurface:
    """uv.lock carries the repo version too, and mq-agent's release-check gates
    on it. A release that bumps VERSION and pyproject but leaves uv.lock behind
    ships a tag whose own release-check fails — the exact drift shape that
    produced mq-mcp v2.0.1."""

    def _repo_with_lock(self, tmp_path: Path) -> Path:
        repo = _make_repo(tmp_path, name="mq-agent", with_remote=True)
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "mq-agent"\nversion = "1.0.0"\n'
        )
        (repo / "uv.lock").write_text(_UV_LOCK)
        _git(["add", "-A"], repo)
        _git(["commit", "-m", "chore: add lockfile"], repo)
        subprocess.run(["git", "push"], cwd=repo, capture_output=True, text=True)
        return repo

    def test_write_version_bumps_own_package_in_lockfile(self, tmp_path):
        repo = self._repo_with_lock(tmp_path)
        changed = _write_version(repo, "1.1.0")
        assert repo / "uv.lock" in changed
        assert _lock_version(repo, "mq-agent") == "1.1.0"

    def test_other_packages_on_the_same_version_are_untouched(self, tmp_path):
        # Every package in the fixture starts at 1.0.0 — a careless global
        # substitution would rewrite the whole dependency tree.
        repo = self._repo_with_lock(tmp_path)
        _write_version(repo, "1.1.0")
        assert _lock_version(repo, "httpx") == "1.0.0"
        assert _lock_version(repo, "zzz-other") == "1.0.0"

    def test_missing_lockfile_is_not_an_error(self, tmp_path):
        repo = _make_repo(tmp_path, name="mq-hal", with_remote=True)
        changed = _write_version(repo, "1.1.0")
        assert all(f.name != "uv.lock" for f in changed)

    def test_release_leaves_every_version_surface_in_sync(self, tmp_path, monkeypatch):
        repo = self._repo_with_lock(tmp_path)
        monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", _stack_entry(repo))
        plan = plan_stack_release("mq-agent", bump="minor")
        with patch("mq_agent.tools.stack_truth.stack_truth_export",
                   return_value={"path": "/tmp/t.md", "ok": True, "status": "READY"}):
            result = execute_stack_release(plan)
        assert result["released"] is True
        assert (repo / "VERSION").read_text().strip() == "1.1.0"
        assert _lock_version(repo, "mq-agent") == "1.1.0"
        assert 'version = "1.1.0"' in (repo / "pyproject.toml").read_text()
        # nothing left uncommitted: the lockfile went into the release commit
        assert _porcelain(repo) == ""
