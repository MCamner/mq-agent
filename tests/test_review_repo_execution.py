"""`review repo` records one `mq.execution-outcome.v1` under task class
`repo-review`, and can hand the exact run id to the operator.

The run id is minted before the review starts, so a feedback experiment can
correlate to it directly. It is never recovered afterwards from the store, and
`repo-review` is never mapped onto `audit`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import model_routing
from mq_agent.tools.execution_outcome import SCHEMA_FILE as EXECUTION_SCHEMA_FILE
from mq_agent.tools.execution_outcome import build_execution_outcome
from tests.test_review_cli import FakeReviewBridge

runner = CliRunner()


@pytest.fixture
def outcomes(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(path))
    return path


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _invoke(args: list[str], bridge: Any) -> Any:
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        return runner.invoke(app, ["review", "repo", ".", *args])


def test_repo_review_is_a_known_task_class() -> None:
    record = build_execution_outcome(
        runtime="agent", task_class="repo-review", result="PASS", exit_status="ok", latency_ms=1
    )

    assert record["task_class"] == "repo-review"


def test_review_repo_records_one_repo_review_outcome(outcomes: Path) -> None:
    result = _invoke(["--json"], FakeReviewBridge())

    assert result.exit_code == 0, result.output
    records = _records(outcomes)
    assert len(records) == 1
    assert records[0]["task_class"] == "repo-review"
    assert records[0]["runtime"] == "agent"
    assert records[0]["result"] == "FAIL"
    assert records[0]["exit_status"] == "error"
    assert records[0]["completeness"] == {
        "status": "partial",
        "steps": [{"step": 1, "status": "unmeasured"}],
    }


def test_review_repo_json_payload_is_unchanged_by_default(outcomes: Path) -> None:
    result = _invoke(["--json"], FakeReviewBridge())

    assert json.loads(result.output) == {"ok": True, "findings": []}


def test_with_execution_reports_the_exact_recorded_run_id(outcomes: Path) -> None:
    result = _invoke(["--json", "--with-execution"], FakeReviewBridge())

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["review"] == {"ok": True, "findings": []}
    records = _records(outcomes)
    assert data["execution"] == {
        "execution_run_id": records[0]["run_id"],
        "task_class": "repo-review",
        "execution_outcome_recorded": True,
    }


def test_unrecorded_outcome_is_not_reported_as_recorded(
    outcomes: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_AGENT_TELEMETRY", "off")

    result = _invoke(["--json", "--with-execution"], FakeReviewBridge())

    assert result.exit_code == 0, result.output
    execution = json.loads(result.output)["execution"]
    assert execution["execution_outcome_recorded"] is False
    assert execution["execution_run_id"]
    assert _records(outcomes) == []


def test_failed_review_records_fail_and_still_correlates(outcomes: Path) -> None:
    class FailingBridge(FakeReviewBridge):
        def review_repo(self, path: str, flags: dict[str, Any]) -> dict[str, Any]:
            return {"ok": False, "error": "mq-mcp tool 'review_repo' is not available."}

    result = _invoke(["--json", "--with-execution"], FailingBridge())

    assert result.exit_code == 1
    data = json.loads(result.output)
    records = _records(outcomes)
    assert records[0]["result"] == "FAIL"
    assert records[0]["exit_status"] == "error"
    assert data["execution"]["execution_run_id"] == records[0]["run_id"]
    assert data["review"]["ok"] is False
    assert records[0]["completeness"] == {
        "status": "partial",
        "steps": [{"step": 1, "status": "failed"}],
    }


def test_dry_run_records_nothing(outcomes: Path) -> None:
    result = _invoke(["--dry-run", "--with-execution"], FakeReviewBridge())

    assert result.exit_code == 0
    assert _records(outcomes) == []


def test_human_output_prints_the_run_id(outcomes: Path) -> None:
    result = _invoke(["--with-execution"], FakeReviewBridge())

    assert result.exit_code == 0, result.output
    assert _records(outcomes)[0]["run_id"] in result.output


def test_an_older_schema_rejects_a_repo_review_record(monkeypatch) -> None:
    """The forward cost DEC-006 names, for the widened task-class enum: an
    older closed-schema reader counts a repo-review record as invalid while
    still reading its own records."""
    schema = json.loads(
        model_routing._schema_path(EXECUTION_SCHEMA_FILE).read_text("utf-8")
    )
    schema["properties"]["task_class"]["enum"].remove("repo-review")
    older = Draft202012Validator(schema)
    real = model_routing._validator
    monkeypatch.setattr(
        model_routing,
        "_validator",
        lambda name: older if name == EXECUTION_SCHEMA_FILE else real(name),
    )
    mine = build_execution_outcome(
        runtime="agent", task_class="audit", result="PASS", exit_status="ok", latency_ms=1
    )
    newer = build_execution_outcome(
        runtime="agent", task_class="repo-review", result="PASS", exit_status="ok", latency_ms=1
    )

    _, execution, invalid = model_routing._split_contracts([mine, newer])

    assert len(execution) == 1
    assert invalid == 1


# --- the review target is resolved before delegation ---------------------
#
# mq-mcp runs in its own working directory, so a relative path sent to it
# names a repo relative to mq-mcp, not to the operator. `review repo .` once
# reviewed mq-mcp itself.


def test_dot_is_resolved_to_the_callers_directory(
    outcomes: Path, tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    bridge = FakeReviewBridge()

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "repo", ".", "--json"])

    assert result.exit_code == 0, result.output
    assert bridge.calls[0][1] == str(repo.resolve())


def test_absolute_path_stays_the_target(outcomes: Path, tmp_path: Path) -> None:
    repo = tmp_path / "other"
    repo.mkdir()
    bridge = FakeReviewBridge()

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "repo", str(repo), "--json"])

    assert result.exit_code == 0, result.output
    assert bridge.calls[0][1] == str(repo.resolve())


def test_missing_path_fails_without_delegating_or_recording(
    outcomes: Path, tmp_path: Path
) -> None:
    bridge = FakeReviewBridge()

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(
            app,
            ["review", "repo", str(tmp_path / "absent"), "--json", "--with-execution"],
        )

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert "not a directory" in data["error"]
    assert bridge.calls == []
    assert _records(outcomes) == []


def test_file_path_is_not_a_repo_target(outcomes: Path, tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    bridge = FakeReviewBridge()

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "repo", str(target)])

    assert result.exit_code == 1
    assert bridge.calls == []


def test_dry_run_shows_the_resolved_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["review", "repo", ".", "--dry-run"])

    assert result.exit_code == 0
    assert str(tmp_path.resolve()) in result.output.replace("\n", "")
