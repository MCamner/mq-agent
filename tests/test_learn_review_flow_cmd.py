"""Tests for mq-agent learn review-flow command."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()

_REVIEW_RESULT = {
    "findings": [
        {"severity": "HIGH", "message": "unused import", "file": "mq-mcp/server.py"}
    ]
}
_EXTRACT_TEXT = (
    "Learn extract from last review: DRY-RUN PREVIEW\n\n"
    "file:     mq-mcp/server.py\n"
    "stored:   false\n\n"
    "pattern_name: release-gate-contracts\n"
    "next:\n"
    "  use record_learning or approved store path if this should become memory"
)
_EXTRACT_RESULT = [[{"type": "text", "text": _EXTRACT_TEXT}], {"result": _EXTRACT_TEXT}]
_REVIEW_ERROR = {"ok": False, "error": "mq-mcp is not reachable"}


def test_review_flow_renders_both_steps():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_RESULT
        MockBridge.return_value.learn_extract_from_last_review.return_value = _EXTRACT_RESULT
        result = runner.invoke(app, ["learn", "review-flow", "mq-mcp/server.py"])

    assert result.exit_code == 0
    assert "Step 1/2" in result.output
    assert "Step 2/2" in result.output
    assert "DRY-RUN PREVIEW" in result.output


def test_review_flow_shows_next_safe_action():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_RESULT
        MockBridge.return_value.learn_extract_from_last_review.return_value = _EXTRACT_RESULT
        result = runner.invoke(app, ["learn", "review-flow", "mq-mcp/server.py"])

    assert result.exit_code == 0
    assert "learn search" in result.output


def test_review_flow_json_output():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_RESULT
        MockBridge.return_value.learn_extract_from_last_review.return_value = {"stored": False}
        result = runner.invoke(app, ["learn", "review-flow", "mq-mcp/server.py", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["path"] == "mq-mcp/server.py"
    assert "review" in data
    assert "extract" in data


def test_review_flow_review_error_exits_nonzero():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_ERROR
        MockBridge.return_value.learn_extract_from_last_review.return_value = _EXTRACT_RESULT
        result = runner.invoke(app, ["learn", "review-flow", "mq-mcp/server.py"])

    assert result.exit_code == 1


def test_review_flow_review_error_json_exits_nonzero():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_ERROR
        MockBridge.return_value.learn_extract_from_last_review.return_value = _EXTRACT_RESULT
        result = runner.invoke(app, ["learn", "review-flow", "mq-mcp/server.py", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["path"] == "mq-mcp/server.py"


def test_review_flow_extract_unavailable_shows_warning():
    error = {
        "ok": False,
        "error": "mq-mcp tool 'learn_extract_from_last_review' is not available.",
    }
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_RESULT
        MockBridge.return_value.learn_extract_from_last_review.return_value = error
        result = runner.invoke(app, ["learn", "review-flow", "mq-mcp/server.py"])

    assert result.exit_code == 0
    assert "unavailable" in result.output


def test_review_flow_calls_bridge_with_path():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_RESULT
        MockBridge.return_value.learn_extract_from_last_review.return_value = _EXTRACT_RESULT
        runner.invoke(app, ["learn", "review-flow", "some/path.py"])

    MockBridge.return_value.review_file.assert_called_once_with("some/path.py", {})
    MockBridge.return_value.learn_extract_from_last_review.assert_called_once_with("some/path.py")
