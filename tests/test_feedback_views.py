from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mq_agent.feedback import (
    append_experiment,
    build_feedback_experiment,
    feedback_inspect,
    feedback_recent,
    feedback_report,
    feedback_status,
    read_experiment_history,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "feedback_report.schema.json"


def _experiment(
    run_id: str,
    *,
    task_class: str = "repo-review",
    recorded_at: str = "2026-10-01T00:00:00Z",
    state: str = "completed",
) -> dict:
    record = build_feedback_experiment(
        task_class=task_class,
        repository="MCamner/mq-agent",
        active_strategy="context-pack-v1",
        shadow_strategy="hybrid-context-v1",
        snapshot_ref="main",
        snapshot_commit="a" * 40,
        evidence_sources=["repo", "codegraph"],
        state=state,
        execution_run_id=f"exec-{run_id}",
        feedback_run_id=run_id,
    )
    record["recorded_at"] = recorded_at
    return record


def test_status_on_missing_store_is_empty_and_does_not_create_it(tmp_path) -> None:
    missing = tmp_path / "missing-feedback"

    payload = feedback_status(missing)

    assert payload["health"] == "EMPTY"
    assert payload["valid_records"] == 0
    assert payload["invalid_records"] == 0
    assert not missing.exists()


def test_status_reports_counts_coverage_and_newest_record(tmp_path) -> None:
    append_experiment(_experiment("fb-1", state="planned"), tmp_path)
    append_experiment(
        _experiment(
            "fb-2",
            task_class="docs-review",
            recorded_at="2026-10-01T00:01:00Z",
        ),
        tmp_path,
    )

    payload = feedback_status(tmp_path)

    assert payload["health"] == "HEALTHY"
    assert payload["valid_records"] == 2
    assert payload["task_classes"] == {"docs-review": 1, "repo-review": 1}
    assert payload["states"] == {"completed": 1, "planned": 1}
    assert payload["newest_recorded_at"] == "2026-10-01T00:01:00Z"
    assert payload["degraded_reasons"] == []


def test_status_reports_corrupt_history_without_hiding_valid_records(tmp_path) -> None:
    destination = append_experiment(_experiment("fb-1"), tmp_path)
    with destination.open("ab") as handle:
        handle.write(b'{"schema":"mq.feedback-experiment.v1"')

    payload = feedback_status(tmp_path)

    assert payload["health"] == "DEGRADED"
    assert payload["valid_records"] == 1
    assert payload["invalid_records"] == 1
    assert "corrupt or invalid" in payload["degraded_reasons"][0]


def test_history_and_recent_span_all_retained_rotation_generations(
    tmp_path, monkeypatch
) -> None:
    destination = append_experiment(_experiment("fb-1"), tmp_path)
    monkeypatch.setenv(
        "MQ_AGENT_FEEDBACK_MAX_BYTES",
        str(destination.stat().st_size + 8),
    )
    for index in range(2, 5):
        append_experiment(
            _experiment(
                f"fb-{index}",
                recorded_at=f"2026-10-01T00:0{index}:00Z",
            ),
            tmp_path,
        )

    history = read_experiment_history(tmp_path)
    recent = feedback_recent(tmp_path, limit=4)

    assert [item.record["feedback_run_id"] for item in history.records] == [
        "fb-1",
        "fb-2",
        "fb-3",
        "fb-4",
    ]
    assert [item["record"]["feedback_run_id"] for item in recent["entries"]] == [
        "fb-4",
        "fb-3",
        "fb-2",
        "fb-1",
    ]
    assert [item.source for item in history.records] == [
        "experiments.jsonl.3",
        "experiments.jsonl.2",
        "experiments.jsonl.1",
        "experiments.jsonl",
    ]


@pytest.mark.parametrize("limit", [0, 201])
def test_recent_is_bounded(tmp_path, limit) -> None:
    with pytest.raises(ValueError, match="limit must be between"):
        feedback_recent(tmp_path, limit=limit)


def test_inspect_returns_exact_store_reference_for_one_immutable_record(tmp_path) -> None:
    append_experiment(_experiment("fb-one"), tmp_path)

    payload = feedback_inspect("fb-one", tmp_path)

    assert payload["health"] == "HEALTHY"
    assert payload["experiment"]["record"]["feedback_run_id"] == "fb-one"
    assert payload["experiment"]["store_ref"] == {
        "file": "experiments.jsonl",
        "line": 1,
    }
    assert payload["comparison"]["status"] == "unavailable"
    assert payload["candidate"]["status"] == "unavailable"


def test_inspect_refuses_to_hide_duplicate_immutable_ids(tmp_path) -> None:
    append_experiment(_experiment("fb-dup"), tmp_path)
    append_experiment(_experiment("fb-dup"), tmp_path)

    payload = feedback_inspect("fb-dup", tmp_path)

    assert payload["health"] == "DEGRADED"
    assert payload["experiment"] is None
    assert len(payload["duplicate_records"]) == 2
    assert any("duplicate feedback_run_id" in reason for reason in payload["degraded_reasons"])


def test_inspect_unknown_run_is_explicit(tmp_path) -> None:
    with pytest.raises(ValueError, match="feedback run not found"):
        feedback_inspect("fb-missing", tmp_path)


def test_report_filters_task_class_and_window_without_inventing_metrics(tmp_path) -> None:
    now = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
    old = (now - timedelta(days=40)).isoformat().replace("+00:00", "Z")
    recent = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    append_experiment(_experiment("fb-old", recorded_at=old), tmp_path)
    append_experiment(_experiment("fb-recent", recorded_at=recent), tmp_path)
    append_experiment(
        _experiment("fb-other", task_class="docs-review", recorded_at=recent),
        tmp_path,
    )

    payload = feedback_report(
        tmp_path,
        task_class="repo-review",
        since="30d",
        now=now,
    )

    assert payload["schema"] == "mq.feedback-report.v1"
    assert payload["total_records"] == 3
    assert payload["matched_records"] == 1
    assert payload["by_task_class"] == {"repo-review": 1}
    assert payload["comparison"]["status"] == "unavailable"
    assert payload["comparison"]["records"] is None
    assert all(
        metric == {"status": "unavailable", "value": None}
        for metric in payload["metrics"].values()
    )


@pytest.mark.parametrize("since", ["0d", "30", "forever", "3651d"])
def test_report_rejects_unbounded_or_invalid_windows(tmp_path, since) -> None:
    with pytest.raises(ValueError):
        feedback_report(tmp_path, since=since)


def test_report_contract_is_valid_and_accepts_the_generated_surface(tmp_path) -> None:
    schema = json.loads((ROOT / "schemas" / REPORT_SCHEMA).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    payload = feedback_report(tmp_path)

    Draft202012Validator(schema).validate(payload)


def test_report_schema_is_packaged_and_registered() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    contract = json.loads(
        (ROOT / ".mq" / "repo-contract.json").read_text(encoding="utf-8")
    )

    assert (
        '"schemas/feedback_report.schema.json" = '
        '"mq_agent/schemas/feedback_report.schema.json"'
    ) in pyproject
    assert "mq.feedback-report.v1" in contract["contracts"]
