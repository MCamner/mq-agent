"""Flag-behaviour contract (v1.15.0).

The rules, from the roadmap:

* --dry-run never writes
* --json is machine-readable
* --brain never writes without an explicit command, and respects --dry-run
* --approve is required for commands whose primary action is a write
"""
from __future__ import annotations

import json
from unittest.mock import patch

import click
import typer
from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


def _walk_commands(cmd: click.Command, prefix: str = "") -> list[tuple[str, click.Command]]:
    name = f"{prefix} {cmd.name}".strip()
    found = [(name, cmd)]
    if isinstance(cmd, click.Group):
        for sub in cmd.commands.values():
            found.extend(_walk_commands(sub, name))
    return found


def _opts(cmd: click.Command) -> set[str]:
    return {opt for p in cmd.params for opt in p.opts}


ALL_COMMANDS = _walk_commands(typer.main.get_command(app))


class TestStructuralRules:
    def test_every_brain_command_has_dry_run(self):
        missing = [
            name for name, cmd in ALL_COMMANDS
            if "--brain" in _opts(cmd) and "--dry-run" not in _opts(cmd)
        ]
        assert missing == [], f"--brain without --dry-run: {missing}"

    def test_every_brain_command_has_json(self):
        missing = [
            name for name, cmd in ALL_COMMANDS
            if "--brain" in _opts(cmd) and "--json" not in _opts(cmd)
        ]
        assert missing == [], f"--brain without --json: {missing}"

    def test_known_write_commands_require_approve(self):
        write_commands = {
            "mq-agent learn store",
            "mq-agent learn promote",
            "mq-agent learn from-review",
            "mq-agent learn from-diff",
            "mq-agent brain record-review",
            "mq-agent decide",
        }
        by_name = dict(ALL_COMMANDS)
        # click roots the tree at the executable name used by Typer
        root = ALL_COMMANDS[0][0]
        for wanted in write_commands:
            name = wanted.replace("mq-agent", root, 1).strip()
            assert name in by_name, f"missing command: {name}"
            assert "--approve" in _opts(by_name[name]), f"{name} lacks --approve"


class TestBrainRespectsDryRun:
    def test_learn_extract_review_dry_run_makes_no_calls(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            result = runner.invoke(
                app, ["learn", "extract-review", "f.py", "--brain", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output
        assert "would write a learn note" in result.output
        MockBridge.assert_not_called()

    def test_learn_review_flow_dry_run_makes_no_calls(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            result = runner.invoke(
                app, ["learn", "review-flow", "f.py", "--brain", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output
        MockBridge.assert_not_called()

    def test_signal_dry_run_skips_brain_write(self):
        fake_result = {
            "repo": "demo",
            "project_type": "python",
            "scores": {"overall": 90, "readme": 90, "readme_max": 100,
                       "publish": 5, "publish_total": 6},
            "readme": {"missing": []},
            "publish": {"status": "ready", "next_action": ""},
            "focus_areas": [],
            "steps": [],
        }
        with (
            patch("mq_agent.tools.signal_tools.signal_available", return_value=True),
            patch("mq_agent.agents.signal_agent.SignalAgent") as MockAgent,
            patch("mq_agent.main._client"),
            patch("mq_agent.main._brain_record_review") as mock_brain,
        ):
            MockAgent.return_value.run.return_value = fake_result
            result = runner.invoke(app, ["signal", ".", "--brain", "--dry-run"])
        assert result.exit_code == 0
        mock_brain.assert_not_called()

    def test_review_file_dry_run_makes_no_calls(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            result = runner.invoke(
                app, ["review", "file", "f.py", "--brain", "--dry-run"])
        assert result.exit_code == 0
        MockBridge.assert_not_called()


class TestApproveGate:
    def test_decide_without_approve_is_blocked(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            result = runner.invoke(app, [
                "decide", "Use X", "--context", "c", "--decision", "d", "--rationale", "r"])
        assert result.exit_code == 1
        assert "--approve" in result.output
        MockBridge.assert_not_called()

    def test_decide_with_approve_writes(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            MockBridge.return_value.call_tool.return_value = {"ok": True, "path": "/tmp/adr.md"}
            result = runner.invoke(app, [
                "decide", "Use X", "--context", "c", "--decision", "d",
                "--rationale", "r", "--approve"])
        assert result.exit_code == 0
        assert "Decision recorded" in result.output

    def test_record_review_without_approve_is_blocked(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            result = runner.invoke(app, ["brain", "record-review", "--source", "test:x"])
        assert result.exit_code == 1
        assert "--approve" in result.output
        MockBridge.return_value.call_tool.assert_not_called()


class TestJsonMachineReadable:
    def test_record_review_json_output(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            MockBridge.return_value.call_tool.return_value = {"ok": True, "path": "/tmp/r.md"}
            result = runner.invoke(app, [
                "brain", "record-review", "--source", "test:x", "--approve", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_decide_json_output(self):
        with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
            MockBridge.return_value.call_tool.return_value = {"ok": True, "path": "/tmp/adr.md"}
            result = runner.invoke(app, [
                "decide", "Use X", "--context", "c", "--decision", "d",
                "--rationale", "r", "--approve", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["ok"] is True
