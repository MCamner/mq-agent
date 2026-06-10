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
