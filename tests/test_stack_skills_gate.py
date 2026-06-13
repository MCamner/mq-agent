"""Tests for stack skills-check command and _skills_entry helper."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.stack_tools import _skills_entry

runner = CliRunner()


# ── fixtures ────────────────────────────────────────────────────────────────

PASSING_CHECKER = """#!/usr/bin/env bash
echo "PASS: all good"
echo "check-skills: OK"
exit 0
"""

FAILING_CHECKER = """#!/usr/bin/env bash
echo "PASS: frontmatter and Evals sections"
echo "FAIL: skills/foo/SKILL.md references non-existent skill 'ghost'"
echo "check-skills: FAILED"
exit 1
"""


@pytest.fixture()
def repo_with_skills(tmp_path):
    """Repo containing a skills/ dir and a configurable check-skills.sh."""
    repo = tmp_path / "repo"
    (repo / "skills" / "demo").mkdir(parents=True)
    (repo / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
    (repo / "scripts").mkdir()
    return repo


def _write_checker(repo, body):
    checker = repo / "scripts" / "check-skills.sh"
    checker.write_text(body)
    checker.chmod(0o755)


# ── _skills_entry unit tests ─────────────────────────────────────────────────

class TestSkillsEntry:
    def test_nonexistent_repo_is_blocked(self, tmp_path):
        e = _skills_entry({"name": "ghost", "path": str(tmp_path / "nope")})
        assert e["status"] == "BLOCKED"
        assert "not found" in e["reason"]

    def test_no_skills_dir_is_skipped(self, tmp_path):
        (tmp_path / "plain").mkdir()
        e = _skills_entry({"name": "plain", "path": str(tmp_path / "plain")})
        assert e["status"] == "SKIPPED"
        assert "no skills/" in e["reason"]

    def test_skills_without_checker_is_review(self, repo_with_skills):
        e = _skills_entry({"name": "demo", "path": str(repo_with_skills)})
        assert e["status"] == "REVIEW"
        assert "without scripts/check-skills.sh" in e["reason"]

    def test_passing_checker_is_ready(self, repo_with_skills):
        _write_checker(repo_with_skills, PASSING_CHECKER)
        e = _skills_entry({"name": "demo", "path": str(repo_with_skills)})
        assert e["status"] == "READY"

    def test_failing_checker_is_drift_with_fail_reason(self, repo_with_skills):
        _write_checker(repo_with_skills, FAILING_CHECKER)
        e = _skills_entry({"name": "demo", "path": str(repo_with_skills)})
        assert e["status"] == "DRIFT"
        assert "non-existent skill" in e["reason"]

    def test_missing_repo_in_ci_is_skipped(self, tmp_path):
        e = _skills_entry({"name": "ghost", "path": str(tmp_path / "nope")}, ci=True)
        assert e["status"] == "SKIPPED"
        assert "CI workspace" in e["reason"]


# ── command-level tests ───────────────────────────────────────────────────────

class TestSkillsCheckCommand:
    def test_json_output_shape_and_exit(self, monkeypatch):
        fake = json.dumps({
            "overall": "READY", "mode": "local", "reasons": [],
            "repos": [{"name": "mq-agent", "status": "READY", "reason": ""}],
            "checked_at": "now",
        })
        monkeypatch.setattr("mq_agent.tools.stack_tools.stack_skills_check", lambda ci=False: fake)
        result = runner.invoke(app, ["stack", "skills-check", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["overall"] == "READY"

    def test_drift_fails_gate(self, monkeypatch):
        fake = json.dumps({
            "overall": "NOT READY", "mode": "local",
            "reasons": ["mq-agent: FAIL: dead ref"],
            "repos": [{"name": "mq-agent", "status": "DRIFT", "reason": "FAIL: dead ref"}],
            "checked_at": "now",
        })
        monkeypatch.setattr("mq_agent.tools.stack_tools.stack_skills_check", lambda ci=False: fake)
        result = runner.invoke(app, ["stack", "skills-check"])
        assert result.exit_code == 1
        assert "NOT READY" in result.output
