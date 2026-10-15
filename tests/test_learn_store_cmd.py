"""Tests for mq-agent learn extract / list / store (explicit candidate IDs).

`learn store` stores one explicitly chosen inbox candidate. It never stores
"the latest" candidate and never guesses record_learning arguments: the fields
come from mq-mcp's learn_inbox_draft, and validation comes from the operator.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()

CID = "cand-0123456789ab"
_DRAFT = {
    "candidate_id": CID,
    "candidate": "schema-force-include",
    "draft": {
        "task": "Force-include every runtime schema in pyproject.toml",
        "lesson": "Schemas read at runtime must be force-included in the wheel.",
        "validation": "MANUAL VALIDATION REQUIRED: verify against evidence — pyproject.toml",
        "risk": "low",
        "repo": "mq-agent",
        "source": "manual",
        "tags": ["release", "packaging"],
    },
    "write_performed": False,
}


def _text(value: str):
    return [[{"type": "text", "text": value}], {"result": value}]


def _wire(mock, *, draft=None, record="Saved lesson L-0042.", drop="Removed 1 candidate from the learn inbox, 0 remaining:"):
    bridge = mock.return_value
    bridge.learn_inbox_draft.return_value = _text(json.dumps(draft or _DRAFT))
    bridge.record_learning.return_value = _text(record)
    bridge.learn_inbox_drop.return_value = _text(drop)
    return bridge


# --- learn store: the explicit-ID contract -------------------------------------


def test_store_without_candidate_id_aborts():
    result = runner.invoke(app, ["learn", "store", "--approve"])
    assert result.exit_code != 0
    assert "CANDIDATE_ID" in result.output


def test_store_rejects_a_path_instead_of_an_id():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        result = runner.invoke(app, ["learn", "store", "mq-mcp/server.py", "--validation", "v", "--approve"])
    assert result.exit_code == 1
    assert "candidate ID" in result.output
    assert "learn list" in result.output
    mock.assert_not_called()


def test_store_without_approve_exits_nonzero():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        result = runner.invoke(app, ["learn", "store", CID, "--validation", "v"])
    assert result.exit_code == 1
    assert "--approve" in result.output
    mock.assert_not_called()


def test_store_without_validation_exits_nonzero():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        result = runner.invoke(app, ["learn", "store", CID, "--approve"])
    assert result.exit_code == 1
    assert "--validation" in result.output
    mock.assert_not_called()


def test_store_dry_run_names_the_candidate_and_calls_nothing():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        result = runner.invoke(app, ["learn", "store", CID, "--dry-run"])
    assert result.exit_code == 0
    assert CID in result.output
    assert "record_learning" in result.output
    mock.assert_not_called()


def test_store_sends_draft_fields_and_operator_validation():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        bridge = _wire(mock)
        result = runner.invoke(app, ["learn", "store", CID, "--validation", "CI green after #405", "--approve"])

    assert result.exit_code == 0, result.output
    bridge.learn_inbox_draft.assert_called_once_with(CID)
    bridge.record_learning.assert_called_once_with(
        task="Force-include every runtime schema in pyproject.toml",
        lesson="Schemas read at runtime must be force-included in the wheel.",
        validation="CI green after #405",
        source="manual",
        repo="mq-agent",
        risk="low",
        tags="release,packaging",
    )
    bridge.learn_inbox_drop.assert_called_once_with(CID, apply=True)
    assert "L-0042" in result.output


def test_store_never_forwards_the_manual_validation_placeholder():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        bridge = _wire(mock)
        runner.invoke(app, ["learn", "store", CID, "--validation", "checked by hand", "--approve"])
    sent = bridge.record_learning.call_args.kwargs["validation"]
    assert "MANUAL VALIDATION REQUIRED" not in sent


def test_store_unknown_candidate_aborts_before_writing():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        bridge = mock.return_value
        bridge.learn_inbox_draft.return_value = _text("No pending candidate matches.")
        result = runner.invoke(app, ["learn", "store", CID, "--validation", "v", "--approve"])

    assert result.exit_code == 1
    assert "No pending candidate matches" in result.output
    bridge.record_learning.assert_not_called()
    bridge.learn_inbox_drop.assert_not_called()


def test_store_failure_keeps_the_candidate_in_the_inbox():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        bridge = _wire(mock)
        bridge.record_learning.return_value = {"ok": False, "error": "mq-mcp tool 'record_learning' is not available."}
        result = runner.invoke(app, ["learn", "store", CID, "--validation", "v", "--approve"])

    assert result.exit_code == 1
    bridge.learn_inbox_drop.assert_not_called()


def test_store_reports_a_failed_drop_after_a_successful_store():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        _wire(mock, drop="Learn inbox is empty — nothing to drop.")
        result = runner.invoke(app, ["learn", "store", CID, "--validation", "v", "--approve"])

    assert result.exit_code == 1
    assert "L-0042" in result.output
    assert "learn_inbox_drop" in result.output


def test_store_json_output():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        _wire(mock)
        result = runner.invoke(app, ["learn", "store", CID, "--validation", "v", "--approve", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["candidate_id"] == CID
    assert data["stored"].startswith("Saved lesson")
    assert data["dropped"] is True


# --- learn extract / learn list ------------------------------------------------


def test_extract_requires_approve():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        result = runner.invoke(app, ["learn", "extract", "mq_agent/main.py"])
    assert result.exit_code == 1
    assert "--approve" in result.output
    mock.assert_not_called()


def test_extract_queues_and_prints_the_candidate_id():
    queued = {"status": "queued", "candidate_id": CID, "candidate": {"pattern_name": "schema-force-include"}}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        bridge = mock.return_value
        bridge.learn_queue_from_last_review.return_value = _text(json.dumps(queued))
        result = runner.invoke(app, ["learn", "extract", "mq_agent/main.py", "--repo", "/tmp/r", "--approve"])

    assert result.exit_code == 0, result.output
    bridge.learn_queue_from_last_review.assert_called_once_with("mq_agent/main.py", repo_path="/tmp/r")
    assert CID in result.output
    assert f"learn store {CID}" in result.output


def test_extract_not_queued_exits_nonzero():
    refused = {"status": "not-queued", "reason": "confidence 'low' is below the inbox bar (medium/high)"}
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        mock.return_value.learn_queue_from_last_review.return_value = _text(json.dumps(refused))
        result = runner.invoke(app, ["learn", "extract", "mq_agent/main.py", "--approve"])

    assert result.exit_code == 1
    assert "below the inbox bar" in result.output


def test_list_shows_the_inbox():
    listing = f"Learn inbox: 1 pending candidate(s), showing 1\n\n- {CID}  schema-force-include"
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as mock:
        mock.return_value.learn_inbox.return_value = _text(listing)
        result = runner.invoke(app, ["learn", "list"])

    assert result.exit_code == 0, result.output
    assert CID in result.output
    mock.return_value.learn_inbox.assert_called_once_with(limit=20)
