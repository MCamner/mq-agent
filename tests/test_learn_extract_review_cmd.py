"""Tests for mq-agent learn extract-review command."""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()

_DRY_RUN_TEXT = (
    "Learn extract from last review: DRY-RUN PREVIEW\n\n"
    "file:     mq-mcp/server.py\n"
    "provider: ollama / mq-learn\n"
    "stored:   false\n\n"
    "pattern_name: release-gate-contracts\n"
    "pattern_type: release\n"
    "confidence:   high\n\n"
    "summary: mq-agent needs schema file.\n\n"
    "evidence:\n"
    "  - check_contracts_valid raised BLOCKED/68\n\n"
    "recommended_action: copy schema from mq-mcp\n\n"
    "next:\n"
    "  use record_learning or approved store path if this should become memory"
)

_MCP_TEXT_RESULT = [
    [{"type": "text", "text": _DRY_RUN_TEXT}],
    {"result": _DRY_RUN_TEXT},
]


def test_learn_extract_review_renders_preview():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = _MCP_TEXT_RESULT
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py"])

    assert result.exit_code == 0
    assert "DRY-RUN PREVIEW" in result.output


def test_learn_extract_review_json_output():
    payload = {"status": "dry_run", "stored": False, "file": "mq-mcp/server.py"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = payload
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "dry_run"
    assert data["stored"] is False


def test_learn_extract_review_unavailable_exits_nonzero():
    error = {
        "ok": False,
        "error": "mq-mcp tool 'learn_extract_from_last_review' is not available.",
        "tool": "learn_extract_from_last_review",
    }
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = error
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py"])

    assert result.exit_code == 1
    assert "learn_extract_from_last_review" in result.output


def test_learn_extract_review_no_review_text():
    no_review = [
        [{"type": "text", "text": "Learn extract from last review: NO REVIEW FOUND\n\nfile: mq-mcp/server.py\n\nRun review_file or risk_review_file on this path first."}],
        {"result": "Learn extract from last review: NO REVIEW FOUND"},
    ]
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = no_review
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py"])

    assert result.exit_code == 0
    assert "NO REVIEW FOUND" in result.output


def test_learn_extract_review_calls_bridge_with_path():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = _MCP_TEXT_RESULT
        runner.invoke(app, ["learn", "extract-review", "some/path.py"])

    MockBridge.return_value.learn_extract_from_last_review.assert_called_once_with("some/path.py", repo_path=None)


def test_learn_extract_review_brain_calls_brain_record_learning():
    brain_ok = {"ok": True, "path": "mqobsidian/learn/release-gate-contracts.md"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = _MCP_TEXT_RESULT
        MockBridge.return_value.call_tool.return_value = brain_ok
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py", "--brain"])

    assert result.exit_code == 0
    MockBridge.return_value.call_tool.assert_called_once()
    assert MockBridge.return_value.call_tool.call_args[0][0] == "brain_record_learning"


def test_learn_extract_review_brain_evidence_is_list_not_string():
    """Regression: evidence must be list[str], not a bare string (chars become bullets)."""
    single_line_evidence = (
        "pattern_name: release-gate-contracts\n"
        "pattern_type: release\n"
        "confidence: high\n"
        "summary: test summary\n"
        "evidence: git tag v1.1.0 && gh release create\n"
        "recommended_action: verify tags match releases\n"
    )
    brain_ok = {"ok": True, "path": "mqobsidian/learn/release-gate-contracts.md"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = [
            [{"type": "text", "text": single_line_evidence}],
            {"result": single_line_evidence},
        ]
        MockBridge.return_value.call_tool.return_value = brain_ok
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py", "--brain"])

    assert result.exit_code == 0
    call_kwargs = MockBridge.return_value.call_tool.call_args[0][1]
    evidence = call_kwargs["evidence"]
    assert isinstance(evidence, list), f"evidence must be list, got {type(evidence)}"
    for item in evidence:
        assert isinstance(item, str), f"each evidence item must be str, got {type(item)}"
        assert len(item) > 1, "evidence items must not be single characters (string was iterated)"


def test_learn_extract_review_brain_skips_when_no_review():
    no_review = [
        [{"type": "text", "text": "Learn extract from last review: NO REVIEW FOUND\n\nfile: mq-mcp/server.py"}],
        {"result": "NO REVIEW FOUND"},
    ]
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.learn_extract_from_last_review.return_value = no_review
        result = runner.invoke(app, ["learn", "extract-review", "mq-mcp/server.py", "--brain"])

    assert result.exit_code == 0
    MockBridge.return_value.call_tool.assert_not_called()
