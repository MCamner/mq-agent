"""Tests for the feedback-signal.v1 writer.

mqobsidian owns the vocabulary and policy (docs/FEEDBACK_LOOP.md); mq-agent
owns the mechanism. Records are machine-emitted to the vault's gitignored
`feedback/` surface and never hand-authored.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.feedback_signal import record_feedback_signal

runner = CliRunner()

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema", "task", "generated_at", "outcome"],
    "properties": {
        "schema": {"const": "feedback-signal.v1"},
        "task": {"type": "string", "minLength": 1},
        "generated_at": {"type": "string"},
        "repo": {"type": "string"},
        "outcome": {"type": "string", "enum": ["sufficient", "insufficient"]},
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["block", "judgment"],
                "properties": {
                    "block": {"type": "string", "minLength": 1},
                    "judgment": {
                        "type": "string",
                        "enum": ["useful", "noise", "missing", "stale"],
                    },
                    "reason": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "additionalProperties": False,
}


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "mqobsidian"
    (vault / "schemas").mkdir(parents=True)
    (vault / "schemas" / "feedback-signal.v1.json").write_text(
        json.dumps(SCHEMA), encoding="utf-8"
    )
    return vault


def test_record_appends_to_the_gitignored_feedback_surface(tmp_path):
    vault = _vault(tmp_path)
    path = record_feedback_signal(
        "fix mq-mcp brain writer paths", outcome="sufficient", vault=vault
    )

    assert path == vault / "feedback" / "signals.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["schema"] == "feedback-signal.v1"
    assert record["task"] == "fix mq-mcp brain writer paths"
    assert record["outcome"] == "sufficient"
    assert record["generated_at"].endswith("Z")


def test_records_append_rather_than_overwrite(tmp_path):
    vault = _vault(tmp_path)
    record_feedback_signal("first task", outcome="sufficient", vault=vault)
    path = record_feedback_signal("second task", outcome="insufficient", vault=vault)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["task"] for line in lines] == ["first task", "second task"]


def test_judgments_carry_block_verdict_and_reason(tmp_path):
    vault = _vault(tmp_path)
    path = record_feedback_signal(
        "trace a routing bug",
        outcome="insufficient",
        repo="mq-agent",
        judgments=[
            ("memory/context-cards/mq-agent-card.md", "useful", "named the boundary"),
            ("mq-mcp/.mq/context/repo-card.md", "noise", None),
        ],
        vault=vault,
    )

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["repo"] == "mq-agent"
    assert record["judgments"][0] == {
        "block": "memory/context-cards/mq-agent-card.md",
        "judgment": "useful",
        "reason": "named the boundary",
    }
    # An omitted reason must be absent, not an empty string the schema would keep.
    assert record["judgments"][1] == {
        "block": "mq-mcp/.mq/context/repo-card.md",
        "judgment": "noise",
    }


def test_record_is_validated_against_the_vault_schema(tmp_path):
    """mqobsidian owns the contract; a record that violates it must not land."""
    vault = _vault(tmp_path)
    try:
        record_feedback_signal("a task", outcome="maybe", vault=vault)
    except ValueError as exc:
        assert "outcome" in str(exc)
    else:
        raise AssertionError("invalid outcome accepted")
    assert not (vault / "feedback").exists()


def test_unknown_judgment_verdict_is_rejected(tmp_path):
    vault = _vault(tmp_path)
    try:
        record_feedback_signal(
            "a task",
            outcome="sufficient",
            judgments=[("some/block.md", "excellent", None)],
            vault=vault,
        )
    except ValueError as exc:
        assert "judgment" in str(exc)
    else:
        raise AssertionError("invalid judgment accepted")


def test_missing_vault_schema_fails_loudly(tmp_path):
    """Never fall back to a local shape: consumers may validate, not redefine."""
    vault = tmp_path / "empty"
    vault.mkdir()
    try:
        record_feedback_signal("a task", outcome="sufficient", vault=vault)
    except ValueError as exc:
        assert "schema" in str(exc).lower()
    else:
        raise AssertionError("missing schema accepted")


def test_cli_records_a_signal(tmp_path):
    vault = _vault(tmp_path)
    result = runner.invoke(
        app,
        [
            "context", "feedback", "fix the exporter",
            "--outcome", "sufficient",
            "--repo", "mq-agent",
            "--judgment", "cards/mq-agent-card.md:useful:named the owner",
            "--vault", str(vault),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["recorded"] is True
    assert report["signals"] == 1
    record = json.loads((vault / "feedback" / "signals.jsonl").read_text().strip())
    assert record["judgments"][0]["reason"] == "named the owner"


def test_cli_rejects_a_malformed_judgment_spec(tmp_path):
    vault = _vault(tmp_path)
    result = runner.invoke(
        app,
        ["context", "feedback", "a task", "--outcome", "sufficient",
         "--judgment", "just-a-block", "--vault", str(vault)],
    )

    assert result.exit_code == 2
    assert not (vault / "feedback").exists()
