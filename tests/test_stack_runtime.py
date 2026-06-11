"""Tests for the v1.16.0 stack runtime gate."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import stack_run as stack_run_registered
from mq_agent.tools.stack_runtime import stack_run

runner = CliRunner()


def _release_payload(overall: str = "GO") -> str:
    blockers = [] if overall == "GO" else ["dirty tree"]
    return json.dumps({
        "overall": overall,
        "mode": "local",
        "repos": [{"name": "mq-agent", "blockers": blockers}],
    })


def _bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.is_available.return_value = True
    bridge.list_tool_specs.return_value = [
        SimpleNamespace(name="review_repo"),
        SimpleNamespace(name="brain_record_review"),
    ]
    bridge.ollama_learn_status.return_value = {"ok": True, "model": "mq-learn"}
    return bridge


def _patches(release: str | None = None):
    truth = {"markdown": "# truth", "path": "/tmp/truth.md", "written": False}
    return (
        patch("mq_agent.tools.signal_tools.signal_available", return_value=True),
        patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=_bridge()),
        patch("mq_agent.tools.stack_truth.stack_truth_export", return_value=truth),
        patch("mq_agent.tools.stack_tools.stack_release_check", return_value=release or _release_payload()),
    )


class TestStackRunTool:
    def test_all_green_is_pass(self):
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            data = json.loads(stack_run(dry_run=True))
        assert data["overall"] == "PASS"
        assert [s["name"] for s in data["steps"]] == [
            "repo-signal", "mq-mcp", "ollama", "brain export", "release",
        ]
        assert data["writes_enabled"] is False

    def test_brain_without_approve_does_not_write(self):
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3 as truth_mock, p4:
            data = json.loads(stack_run(brain=True, approve=False))
        truth_mock.assert_called_once_with(write=False)
        assert data["writes_enabled"] is False

    def test_brain_with_approve_writes_truth_export(self):
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3 as truth_mock, p4:
            data = json.loads(stack_run(brain=True, approve=True))
        truth_mock.assert_called_once_with(write=True)
        assert data["writes_enabled"] is True

    def test_release_failure_fails_runtime(self):
        p1, p2, p3, p4 = _patches(release=_release_payload("NO-GO"))
        with p1, p2, p3, p4:
            data = json.loads(stack_run())
        assert data["overall"] == "FAIL"
        assert data["next_action"] == "NO-GO — mq-agent: dirty tree"


class TestStackRunCli:
    def test_json_output_exits_zero_when_pass(self):
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            result = runner.invoke(app, ["stack", "run", "--dry-run", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["overall"] == "PASS"

    def test_table_output_shows_runtime_steps(self):
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            result = runner.invoke(app, ["stack", "run", "--dry-run"])
        assert result.exit_code == 0
        assert "mq-stack Runtime" in result.output
        assert "repo-signal" in result.output
        assert "release" in result.output

    def test_json_output_exits_one_when_failed(self):
        p1, p2, p3, p4 = _patches(release=_release_payload("NO-GO"))
        with p1, p2, p3, p4:
            result = runner.invoke(app, ["stack", "run", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["overall"] == "FAIL"

    def test_root_run_stack_alias_json(self):
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            result = runner.invoke(app, ["run", "--stack", "--dry-run", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall"] == "PASS"
        assert data["dry_run"] is True

    def test_root_run_without_command_explains_stack_alias(self):
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 1
        assert "--stack" in result.output

    def test_root_run_shell_preview_still_works(self):
        result = runner.invoke(app, ["run", "echo hello"])
        assert result.exit_code == 0
        assert "Would run" in result.output
        assert "--approve" in result.output

    def test_registered_in_tool_registry(self):
        from mq_agent.tools import TOOL_REGISTRY

        assert TOOL_REGISTRY["stack_run"] is stack_run
        assert stack_run_registered is stack_run
