from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.operator.render_release_status import render_release_status
from mq_agent.perception.contract import validate_perception_payload
from mq_agent.tools.mcp_bridge import MultiMCPBridge

runner = CliRunner()


def sample_gate(status: str = "blocked") -> dict[str, object]:
    return {
        "repo": "mq-agent",
        "target": "v1.4.0",
        "status": status,
        "score": 78,
        "blockers": ["CHANGELOG missing v1.4.0 entry"] if status == "blocked" else [],
        "warnings": ["README mentions old roadmap"] if status == "warning" else [],
        "next_actions": ["Update CHANGELOG"],
        "checks": [],
    }


def test_release_status_json_asks_mq_mcp_gate():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("warning")) as mock:
        result = runner.invoke(app, ["release", "status", "--repo", ".", "--target", "v1.4.0", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with(repo=str(Path(".").expanduser().resolve()), target="v1.4.0")
    payload = json.loads(result.output)
    assert payload["status"] == "warning"


def test_release_status_blocked_exits_nonzero_and_renders_operator_output():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("blocked")):
        result = runner.invoke(app, ["release", "status"])

    assert result.exit_code == 1
    assert "MQ OPERATOR STATUS" in result.output
    assert "BLOCKED" in result.output
    assert "CHANGELOG" in result.output


def test_release_status_missing_gate_tool_is_blocked():
    missing = {
        "ok": False,
        "error": "mq-mcp tool 'release_gate_run' is not available.",
        "hint": "Start or upgrade mq-mcp.",
    }
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=missing):
        result = runner.invoke(app, ["release", "status", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert "release_gate_run" in payload["blockers"][0]


def test_release_renderer_does_not_need_gate_rules():
    output = render_release_status(sample_gate("pass"))

    assert "MQ OPERATOR STATUS" in output
    assert "PASS" in output
    assert "No action required." not in output


def test_perception_contract_validates_minimal_payload():
    payload = {
        "source_type": "screenshot",
        "source_path": "docs/screenshot.png",
        "ocr_text": "",
        "visual_summary": "",
        "risk_signals": [],
        "confidence": "medium",
    }

    assert validate_perception_payload(payload)["ok"] is True


def test_review_perception_json_normalizes_image_ocr_output():
    raw = {"full_text": "Release notes", "confidence": "high", "risk_signals": ["low contrast"]}
    with patch.object(MultiMCPBridge, "call_tool", return_value=raw) as mock:
        result = runner.invoke(app, ["review", "perception", "docs/screenshot.png", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with("image_ocr", {"image_path": "docs/screenshot.png"})
    payload = json.loads(result.output)
    assert payload["source_type"] == "screenshot"
    assert payload["ocr_text"] == "Release notes"
    assert payload["contract"]["ok"] is True
