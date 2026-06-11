"""Tests for v1.13.0 stack truth export."""
from __future__ import annotations

import json
from unittest.mock import patch

from mq_agent.tools.stack_truth import (
    build_stack_truth_snapshot,
    render_stack_truth_markdown,
    stack_truth_export,
)


def _contract_payload(overall: str = "READY") -> dict:
    return {
        "overall": overall,
        "reasons": [] if overall == "READY" else ["mq-hal: missing .mq/repo-contract.json"],
        "repos": [
            {
                "name": "mq-agent",
                "status": "READY",
                "reason": "",
                "contract": {"version": "1.13.0"},
            }
        ],
        "checked_at": "2026-06-11T00:00:00+00:00",
    }


def _release_payload(overall: str = "GO") -> dict:
    return {
        "overall": overall,
        "repos": [
            {
                "name": "mq-agent",
                "version": "1.13.0",
                "go": overall == "GO",
                "blockers": [] if overall == "GO" else ["no README.md"],
                "warnings": [],
            }
        ],
        "checked_at": "2026-06-11T00:00:00+00:00",
    }


class TestBuildStackTruthSnapshot:
    def test_ready_when_contract_and_release_are_ready(self):
        snapshot = build_stack_truth_snapshot(_contract_payload(), _release_payload())
        assert snapshot["status"] == "READY"
        assert snapshot["contract_overall"] == "READY"
        assert snapshot["release_overall"] == "GO"
        assert snapshot["repos"][0]["name"] == "mq-agent"

    def test_not_ready_when_contract_not_ready(self):
        snapshot = build_stack_truth_snapshot(_contract_payload("NOT READY"), _release_payload())
        assert snapshot["status"] == "NOT READY"
        assert snapshot["blockers"] == ["mq-hal: missing .mq/repo-contract.json"]

    def test_not_ready_when_release_not_go(self):
        snapshot = build_stack_truth_snapshot(_contract_payload(), _release_payload("NO-GO"))
        assert snapshot["status"] == "NOT READY"
        assert "mq-agent: no README.md" in snapshot["blockers"]


class TestRenderStackTruthMarkdown:
    def test_markdown_contains_truth_sections(self):
        snapshot = build_stack_truth_snapshot(_contract_payload(), _release_payload())
        markdown = render_stack_truth_markdown(snapshot)
        assert "# MQ Stack Truth" in markdown
        assert "## Result" in markdown
        assert "## Stack summary" in markdown
        assert "## Blockers" in markdown
        assert "mq-agent" in markdown
        assert "READY" in markdown


class TestStackTruthExport:
    def test_write_false_returns_markdown_without_writing(self, tmp_path):
        output = tmp_path / "truth.md"
        with patch("mq_agent.tools.stack_tools.stack_contract_check", return_value=json.dumps(_contract_payload())), \
             patch("mq_agent.tools.stack_tools.stack_release_check", return_value=json.dumps(_release_payload())):
            result = stack_truth_export(output_path=str(output), write=False)
        assert result["ok"] is True
        assert result["written"] is False
        assert "MQ Stack Truth" in result["markdown"]
        assert not output.exists()

    def test_write_true_writes_markdown(self, tmp_path):
        output = tmp_path / "truth.md"
        with patch("mq_agent.tools.stack_tools.stack_contract_check", return_value=json.dumps(_contract_payload())), \
             patch("mq_agent.tools.stack_tools.stack_release_check", return_value=json.dumps(_release_payload())):
            result = stack_truth_export(output_path=str(output), write=True)
        assert result["written"] is True
        assert output.exists()
        assert "MQ Stack Truth" in output.read_text()

# ── CLI: truth-export primary + export alias ────────────────────────────────

class TestTruthExportCli:
    def _patches(self):
        return (
            patch("mq_agent.tools.stack_tools.stack_contract_check", return_value=json.dumps(_contract_payload())),
            patch("mq_agent.tools.stack_tools.stack_release_check", return_value=json.dumps(_release_payload())),
        )

    def test_truth_export_writes_note(self, tmp_path):
        from typer.testing import CliRunner

        from mq_agent.main import app
        output = tmp_path / "truth.md"
        p1, p2 = self._patches()
        with p1, p2:
            result = CliRunner().invoke(app, ["stack", "truth-export", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        assert "MQ Stack Truth" in output.read_text()

    def test_export_alias_writes_same_note(self, tmp_path):
        from typer.testing import CliRunner

        from mq_agent.main import app
        output = tmp_path / "truth.md"
        p1, p2 = self._patches()
        with p1, p2:
            result = CliRunner().invoke(app, ["stack", "export", "--output", str(output)])
        assert result.exit_code == 0
        assert "MQ Stack Truth" in output.read_text()

    def test_dry_run_defaults_to_dated_stack_truth_path(self):
        from typer.testing import CliRunner

        from mq_agent.main import app
        result = CliRunner().invoke(app, ["stack", "truth-export", "--dry-run"])
        assert result.exit_code == 0
        assert "stack-truth" in result.output
        assert "mq-stack-truth.md" in result.output

    def test_truth_export_json_writes_machine_readable_result(self, tmp_path):
        from typer.testing import CliRunner

        from mq_agent.main import app
        output = tmp_path / "truth.md"
        p1, p2 = self._patches()
        with p1, p2:
            result = CliRunner().invoke(
                app,
                ["stack", "truth-export", "--output", str(output), "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["written"] is True
        assert data["path"] == str(output)
        assert "MQ Stack Truth" in data["markdown"]
        assert output.exists()

    def test_truth_export_json_dry_run_does_not_write(self, tmp_path):
        from typer.testing import CliRunner

        from mq_agent.main import app
        output = tmp_path / "truth.md"
        p1, p2 = self._patches()
        with p1, p2:
            result = CliRunner().invoke(
                app,
                ["stack", "truth-export", "--output", str(output), "--dry-run", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["written"] is False
        assert data["path"] == str(output)
        assert not output.exists()

    def test_default_write_goes_to_dated_path_not_release_status(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        import mq_agent.tools.stack_truth as stack_truth
        from mq_agent.main import app
        monkeypatch.setattr(stack_truth, "DEFAULT_STACK_TRUTH_DIR", tmp_path / "stack-truth")
        p1, p2 = self._patches()
        with p1, p2:
            result = CliRunner().invoke(app, ["stack", "truth-export"])
        assert result.exit_code == 0
        written = list((tmp_path / "stack-truth").glob("*-mq-stack-truth.md"))
        assert len(written) == 1
