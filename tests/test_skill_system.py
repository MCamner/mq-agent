"""Tests for MQ Skill System v2.0 discovery."""
from __future__ import annotations

import json
from dataclasses import fields

from typer.testing import CliRunner

from mq_agent.core.skills import (
    ECOSYSTEM_SKILLS_SCHEMA_VERSION,
    SKILL_EXECUTION_SCHEMA_VERSION,
    SKILL_INDEX_SCHEMA_VERSION,
    SKILL_RECORD_SCHEMA_VERSION,
    SKILL_ROUTE_SCHEMA_VERSION,
    EcosystemSkillSummary,
    SkillExecutionPlan,
    SkillIndex,
    SkillRecord,
    SkillRoute,
    default_mq_repo_paths,
    discover_skill_index,
    discover_skill_indexes,
    is_existing_mq_agent_command,
    normalize_skill_records,
    plan_skill_execution,
    route_skill_request,
    summarize_ecosystem_skills,
)
from mq_agent.main import app

runner = CliRunner()


def test_skill_index_fields_are_stable():
    field_names = {f.name for f in fields(SkillIndex)}
    assert field_names == {
        "schema_version",
        "repo",
        "path",
        "exists",
        "source_type",
        "size_bytes",
        "line_count",
        "skills",
    }


def test_skill_record_fields_are_stable():
    field_names = {f.name for f in fields(SkillRecord)}
    assert field_names == {
        "schema_version",
        "id",
        "name",
        "summary",
        "owner",
        "triggers",
        "safety_class",
        "requires_approval",
        "inputs",
        "outputs",
        "command",
        "source_path",
    }


def test_skill_route_fields_are_stable():
    field_names = {f.name for f in fields(SkillRoute)}
    assert field_names == {
        "schema_version",
        "request",
        "selected_skill",
        "owner",
        "confidence",
        "safety_class",
        "requires_approval",
        "reason",
        "next_action",
        "command",
    }


def test_ecosystem_skill_summary_fields_are_stable():
    field_names = {f.name for f in fields(EcosystemSkillSummary)}
    assert field_names == {
        "schema_version",
        "root",
        "repo_count",
        "repos_with_skills",
        "total_skills",
        "missing_repos",
        "indexes",
    }


def test_skill_execution_plan_fields_are_stable():
    field_names = {f.name for f in fields(SkillExecutionPlan)}
    assert field_names == {
        "schema_version",
        "request",
        "selected_skill",
        "command",
        "approved",
        "executable",
        "status",
        "reason",
    }


def test_discover_skill_index_finds_repo_local_skills_file(tmp_path):
    skills = tmp_path / "SKILLS.md"
    skills.write_text("# Skills\n\n## release-readiness\n", encoding="utf-8")

    index = discover_skill_index(tmp_path)

    assert index.schema_version == SKILL_INDEX_SCHEMA_VERSION
    assert index.repo == tmp_path.name
    assert index.path == str(skills)
    assert index.exists is True
    assert index.source_type == "markdown"
    assert index.line_count == 3
    assert index.size_bytes > 0
    assert [skill.id for skill in index.skills or []] == ["release-readiness"]


def test_discover_skill_index_missing_file_is_graceful(tmp_path):
    index = discover_skill_index(tmp_path)

    assert index.schema_version == SKILL_INDEX_SCHEMA_VERSION
    assert index.exists is False
    assert index.source_type is None
    assert index.size_bytes == 0
    assert index.line_count == 0
    assert index.skills is None


def test_discover_skill_indexes_accepts_multiple_repos(tmp_path):
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "SKILLS.md").write_text("# Skills\n", encoding="utf-8")

    indexes = discover_skill_indexes(repo_a, repo_b)

    assert [index.repo for index in indexes] == ["repo-a", "repo-b"]
    assert [index.exists for index in indexes] == [True, False]


def test_normalize_skill_records_from_markdown_sections(tmp_path):
    skills = tmp_path / "SKILLS.md"
    skills.write_text(
        """# Skills

## Built-in skills

### release-readiness

Full release validation.

Command: `mq-agent release-check`
Outputs: summary, checks, next_actions

### repo-audit

Read-only repository audit.

Command: `mq-agent audit .`
Output: summary, steps, verification

## Safety modes

This is not a skill.
""",
        encoding="utf-8",
    )

    records = normalize_skill_records(skills, repo="demo-repo")

    assert [record.id for record in records] == ["release-readiness", "repo-audit"]
    assert all(record.schema_version == SKILL_RECORD_SCHEMA_VERSION for record in records)
    assert records[0].owner == "demo-repo"
    assert records[0].summary == "Full release validation."
    assert records[0].command == "mq-agent release-check"
    assert records[0].outputs == ["summary", "checks", "next_actions"]
    assert records[0].safety_class == "unknown"
    assert records[1].safety_class == "read-only"
    assert records[1].outputs == ["summary", "steps", "verification"]


def test_normalize_skill_records_from_skill_table(tmp_path):
    skills = tmp_path / "SKILLS.md"
    skills.write_text(
        """# Skills

## Built-in skills

| Skill | Description | Status |
| ----- | ----------- | ------ |
| [docs-maintainer](skills/docs-maintainer/SKILL.md) | Keep docs aligned | stable |
| [release-readiness](skills/release-readiness/SKILL.md) | Prepare releases | stable |

## Boundaries

This is not a skill.
""",
        encoding="utf-8",
    )

    records = normalize_skill_records(skills, repo="demo-repo")

    assert [record.id for record in records] == ["docs-maintainer", "release-readiness"]
    assert records[0].summary == "Keep docs aligned"
    assert records[0].source_path == str(tmp_path / "skills/docs-maintainer/SKILL.md")


def test_route_skill_request_matches_normalized_skill(tmp_path):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### release-readiness

Full release validation.

Command: `mq-agent release-check`
""",
        encoding="utf-8",
    )

    route = route_skill_request("check release readiness", tmp_path)

    assert route.schema_version == SKILL_ROUTE_SCHEMA_VERSION
    assert route.selected_skill == "release-readiness"
    assert route.owner == tmp_path.name
    assert route.confidence in {"medium", "high"}
    assert route.command == "mq-agent release-check"
    assert "Dry-run only" in route.next_action


def test_route_skill_request_no_match_is_graceful(tmp_path):
    (tmp_path / "SKILLS.md").write_text("# Skills\n", encoding="utf-8")

    route = route_skill_request("something unrelated", tmp_path)

    assert route.schema_version == SKILL_ROUTE_SCHEMA_VERSION
    assert route.selected_skill is None
    assert route.confidence == "none"
    assert route.requires_approval is False


def test_default_mq_repo_paths_discovers_existing_siblings(tmp_path):
    root = tmp_path / "mq-agent"
    sibling = tmp_path / "mq-mcp"
    root.mkdir()
    sibling.mkdir()

    paths = default_mq_repo_paths(root)

    assert sibling in paths


def test_summarize_ecosystem_skills_with_explicit_repos(tmp_path):
    repo_a = tmp_path / "mq-agent"
    repo_b = tmp_path / "mq-mcp"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### repo-audit

Read-only repository audit.
""",
        encoding="utf-8",
    )

    summary = summarize_ecosystem_skills(repo_a, repo_b, base_path=repo_a)

    assert summary.schema_version == ECOSYSTEM_SKILLS_SCHEMA_VERSION
    assert summary.repo_count == 2
    assert summary.repos_with_skills == 1
    assert summary.total_skills == 1
    assert summary.missing_repos == ["mq-mcp"]


def test_existing_mq_agent_command_allows_only_simple_mq_agent_surface():
    assert is_existing_mq_agent_command("mq-agent skill list . --json") is True
    assert is_existing_mq_agent_command("mq-image analyze") is False
    assert is_existing_mq_agent_command("mq-agent skill list .; rm -rf /") is False


def test_plan_skill_execution_requires_approval(tmp_path):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### skill-list

List skills.

Command: `mq-agent skill list . --json`
""",
        encoding="utf-8",
    )

    plan = plan_skill_execution("skill list", tmp_path)

    assert plan.schema_version == SKILL_EXECUTION_SCHEMA_VERSION
    assert plan.selected_skill == "skill-list"
    assert plan.command == "mq-agent skill list . --json"
    assert plan.executable is True
    assert plan.status == "needs-approval"


def test_plan_skill_execution_blocks_non_mq_agent_command(tmp_path):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### visual-analysis

Analyze images.

Command: `mq-image analyze`
""",
        encoding="utf-8",
    )

    plan = plan_skill_execution("visual analysis", tmp_path, approve=True)

    assert plan.command == "mq-image analyze"
    assert plan.executable is False
    assert plan.status == "not-executable"


def test_skill_list_json_outputs_skill_index_contract(tmp_path):
    (tmp_path / "SKILLS.md").write_text("# Skills\n", encoding="utf-8")

    result = runner.invoke(app, ["skill", "list", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "mq.skill_index.v1"
    assert data["repo"] == tmp_path.name
    assert data["exists"] is True
    assert data["source_type"] == "markdown"
    assert data["skills"] == []


def test_skill_route_json_outputs_route_contract(tmp_path):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### repo-audit

Read-only repository audit.

Command: `mq-agent audit .`
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["skill", "route", "audit this repo", "--path", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "mq.skill_route.v1"
    assert data["selected_skill"] == "repo-audit"
    assert data["command"] == "mq-agent audit ."
    assert data["requires_approval"] is False


def test_skill_ecosystem_json_outputs_summary_contract(tmp_path):
    repo = tmp_path / "mq-agent"
    repo.mkdir()
    (repo / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### repo-audit

Read-only repository audit.
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["skill", "ecosystem", str(repo), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "mq.ecosystem_skills.v1"
    assert data["repo_count"] == 1
    assert data["repos_with_skills"] == 1
    assert data["total_skills"] == 1
    assert data["indexes"][0]["repo"] == "mq-agent"


def test_skill_run_json_without_approve_does_not_execute(tmp_path, monkeypatch):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### skill-list

List skills.

Command: `mq-agent skill list . --json`
""",
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr("mq_agent.tools.shell_tools.run_command", lambda command, cwd=".": calls.append(command))

    result = runner.invoke(app, ["skill", "run", "skill list", "--path", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "mq.skill_execution.v1"
    assert data["status"] == "needs-approval"
    assert calls == []


def test_skill_run_with_approve_executes_supported_command(tmp_path, monkeypatch):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### skill-list

List skills.

Command: `mq-agent skill list . --json`
""",
        encoding="utf-8",
    )

    def fake_run(command: str, cwd: str = ".") -> str:
        assert command == "mq-agent skill list . --json"
        assert cwd == str(tmp_path)
        return "ok"

    monkeypatch.setattr("mq_agent.tools.shell_tools.run_command", fake_run)

    result = runner.invoke(app, [
        "skill", "run", "skill list", "--path", str(tmp_path), "--approve", "--json",
    ])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "approved"
    assert data["output"] == "ok"


def test_skill_list_missing_file_is_successful_read_only(tmp_path):
    result = runner.invoke(app, ["skill", "list", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "mq.skill_index.v1"
    assert data["exists"] is False
    assert data["skills"] == []


def test_skill_list_json_includes_output_contracts(tmp_path):
    (tmp_path / "SKILLS.md").write_text(
        """# Skills

## Built-in skills

### release-readiness

Full release validation.

Command: `mq-agent release-check`
Outputs: summary, checks, next_actions
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["skill", "list", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["skills"][0]["outputs"] == ["summary", "checks", "next_actions"]
