from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.feedback import append_experiment, build_feedback_experiment
from mq_agent.main import app

runner = CliRunner()


@pytest.fixture()
def isolated_feedback_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "feedback"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(root))
    return root


def _experiment(run_id: str, *, recorded_at: str) -> dict:
    record = build_feedback_experiment(
        task_class="repo-review",
        repository="MCamner/mq-agent",
        active_strategy="context-pack-v1",
        shadow_strategy="hybrid-context-v1",
        snapshot_ref="main",
        snapshot_commit="b" * 40,
        evidence_sources=["repo"],
        state="completed",
        feedback_run_id=run_id,
    )
    record["recorded_at"] = recorded_at
    return record


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def test_feedback_status_human_and_json_share_the_same_facts(
    isolated_feedback_root,
) -> None:
    append_experiment(
        _experiment("fb-cli", recorded_at=_now()),
        isolated_feedback_root,
    )

    json_result = runner.invoke(app, ["feedback", "status", "--json"])
    human_result = runner.invoke(app, ["feedback", "status"])

    assert json_result.exit_code == 0
    assert human_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["health"] == "HEALTHY"
    assert payload["valid_records"] == 1
    assert "HEALTHY" in human_result.output
    assert "1" in human_result.output
    assert "repo-review=1" in human_result.output


def test_feedback_inspect_human_and_json_show_the_same_experiment(
    isolated_feedback_root,
) -> None:
    append_experiment(
        _experiment("fb-inspect", recorded_at=_now()),
        isolated_feedback_root,
    )

    json_result = runner.invoke(
        app, ["feedback", "inspect", "fb-inspect", "--json"]
    )
    human_result = runner.invoke(app, ["feedback", "inspect", "fb-inspect"])

    assert json_result.exit_code == 0
    assert human_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["experiment"]["record"]["feedback_run_id"] == "fb-inspect"
    assert "fb-inspect" in human_result.output
    assert "context-pack-v1" in human_result.output
    assert "hybrid-context-v1" in human_result.output


def test_feedback_recent_is_bounded_and_newest_first(
    isolated_feedback_root,
) -> None:
    append_experiment(
        _experiment("fb-old", recorded_at="2026-10-01T00:00:00Z"),
        isolated_feedback_root,
    )
    append_experiment(
        _experiment("fb-new", recorded_at="2026-10-01T00:02:00Z"),
        isolated_feedback_root,
    )

    result = runner.invoke(
        app, ["feedback", "recent", "--limit", "1", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["returned"] == 1
    assert payload["matched"] == 2
    assert payload["entries"][0]["record"]["feedback_run_id"] == "fb-new"


def test_feedback_report_json_and_human_preserve_unavailable_metrics(
    isolated_feedback_root,
) -> None:
    append_experiment(
        _experiment("fb-report", recorded_at=_now()),
        isolated_feedback_root,
    )

    json_result = runner.invoke(
        app,
        [
            "feedback",
            "report",
            "--task-class",
            "repo-review",
            "--since",
            "30d",
            "--json",
        ],
    )
    human_result = runner.invoke(
        app,
        [
            "feedback",
            "report",
            "--task-class",
            "repo-review",
            "--since",
            "30d",
        ],
    )

    assert json_result.exit_code == 0
    assert human_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["schema"] == "mq.feedback-report.v1"
    assert payload["matched_records"] == 1
    assert payload["metrics"]["retrieval_latency_ms"] == {
        "status": "unavailable",
        "value": None,
    }
    assert "unavailable" in human_result.output
    assert "repo-review" in human_result.output
    assert "30d" in human_result.output


def test_all_f1_commands_are_read_only_when_store_is_absent(
    tmp_path, monkeypatch
) -> None:
    missing = tmp_path / "never-created"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(missing))

    for argv in (
        ["feedback", "status", "--json"],
        ["feedback", "recent", "--json"],
        ["feedback", "report", "--json"],
    ):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
        assert not missing.exists()


def test_feedback_inspect_missing_run_is_nonzero_without_creating_store(
    tmp_path, monkeypatch
) -> None:
    missing = tmp_path / "never-created"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(missing))

    result = runner.invoke(app, ["feedback", "inspect", "missing-id", "--json"])

    assert result.exit_code != 0
    assert not missing.exists()
