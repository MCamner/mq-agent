"""Tests for MQ Skill System v2.0 discovery."""
from __future__ import annotations

import json
from dataclasses import fields

from typer.testing import CliRunner

from mq_agent.core.skills import (
    SKILL_INDEX_SCHEMA_VERSION,
    SKILL_RECORD_SCHEMA_VERSION,
    SkillIndex,
    SkillRecord,
    discover_skill_index,
    discover_skill_indexes,
    normalize_skill_records,
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

### repo-audit

Read-only repository audit.

Command: `mq-agent audit .`

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
    assert records[0].safety_class == "unknown"
    assert records[1].safety_class == "read-only"


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


def test_skill_list_missing_file_is_successful_read_only(tmp_path):
    result = runner.invoke(app, ["skill", "list", str(tmp_path), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "mq.skill_index.v1"
    assert data["exists"] is False
    assert data["skills"] == []
