from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from mq_agent.feedback import (
    append_experiment,
    build_feedback_experiment,
    feedback_root,
    purge_feedback_state,
    read_experiments,
    sanitize_feedback_record,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAME = "feedback_experiment.schema.json"


def _schema() -> dict:
    return json.loads((ROOT / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8"))


def _experiment(**overrides) -> dict:
    record = build_feedback_experiment(
        task_class="repo-review",
        repository="MCamner/mq-agent",
        active_strategy="context-pack-v1",
        shadow_strategy="hybrid-context-v1",
        snapshot_ref="main",
        snapshot_commit="a" * 40,
        evidence_sources=["repo", "codegraph"],
        execution_run_id="exec-123",
        feedback_run_id="fb-test",
    )
    record.update(overrides)
    return record


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_feedback_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())


def test_builder_emits_a_schema_valid_correlated_experiment() -> None:
    record = _experiment()

    Draft202012Validator(_schema()).validate(record)
    assert record["schema"] == "mq.feedback-experiment.v1"
    assert record["feedback_run_id"] == "fb-test"
    assert record["execution_run_id"] == "exec-123"
    assert record["snapshot"]["commit"] == "a" * 40


def test_contract_rejects_local_checkout_paths_as_repository_identity() -> None:
    with pytest.raises(ValidationError):
        build_feedback_experiment(
            task_class="repo-review",
            repository="/private/local-checkout",
            active_strategy="active",
            shadow_strategy="shadow",
            snapshot_ref="main",
            snapshot_commit="a" * 40,
            evidence_sources=["repo"],
        )


def test_append_writes_one_json_object_per_line(tmp_path) -> None:
    destination = append_experiment(_experiment(), tmp_path)

    append_experiment(_experiment(feedback_run_id="fb-second"), tmp_path)

    assert destination == tmp_path / "experiments.jsonl"
    assert [row["feedback_run_id"] for row in _records(destination)] == [
        "fb-test",
        "fb-second",
    ]


def test_append_redacts_secret_values_and_private_home_paths(tmp_path) -> None:
    home_source = str(Path.home() / "private-source")
    record = _experiment(
        active_strategy="sk-proj-ABCDEFGHIJKL",
        evidence_sources=[home_source, "github_pat_ABCDEFGHIJKLMNO"],
    )

    destination = append_experiment(record, tmp_path)
    raw = destination.read_text(encoding="utf-8")

    assert "sk-proj-" not in raw
    assert "github_pat_" not in raw
    assert str(Path.home()) not in raw
    assert "[REDACTED]" in raw
    assert "$HOME/private-source" in raw


@pytest.mark.parametrize(
    "field",
    ["prompt", "raw_prompt", "diff", "source_body", "stdout", "api_key"],
)
def test_forbidden_payload_channels_are_rejected_before_write(
    tmp_path, field
) -> None:
    record = _experiment()
    record[field] = "must never be persisted"

    with pytest.raises(ValueError, match="forbidden field"):
        append_experiment(record, tmp_path)

    assert not (tmp_path / "experiments.jsonl").exists()


def test_store_rotates_before_crossing_the_configured_bound(
    tmp_path, monkeypatch
) -> None:
    first = sanitize_feedback_record(_experiment())
    line_size = len(
        (json.dumps(first, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    )
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_MAX_BYTES", str(line_size + 5))

    append_experiment(first, tmp_path)
    append_experiment(_experiment(feedback_run_id="fb-second"), tmp_path)

    current = tmp_path / "experiments.jsonl"
    rotated = Path(f"{current}.1")
    assert [row["feedback_run_id"] for row in _records(current)] == ["fb-second"]
    assert [row["feedback_run_id"] for row in _records(rotated)] == ["fb-test"]


def test_single_record_larger_than_store_bound_is_refused(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_MAX_BYTES", "10")

    with pytest.raises(ValueError, match="exceeds configured store size"):
        append_experiment(_experiment(), tmp_path)

    assert not (tmp_path / "experiments.jsonl").exists()


def test_concurrent_appends_do_not_interleave_records(tmp_path) -> None:
    def write(index: int) -> None:
        append_experiment(
            _experiment(feedback_run_id=f"fb-{index}"),
            tmp_path,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(32)))

    result = read_experiments(tmp_path)
    assert len(result.records) == 32
    assert result.issues == []
    assert len({row["feedback_run_id"] for row in result.records}) == 32


def test_truncated_history_is_reported_without_hiding_valid_records(tmp_path) -> None:
    destination = append_experiment(_experiment(), tmp_path)
    with destination.open("ab") as handle:
        handle.write(b'{"schema":"mq.feedback-experiment.v1"')

    result = read_experiments(tmp_path)

    assert [row["feedback_run_id"] for row in result.records] == ["fb-test"]
    assert len(result.issues) == 1
    assert result.issues[0].line == 2


def test_historical_record_that_needs_redaction_is_not_treated_as_valid(
    tmp_path,
) -> None:
    destination = tmp_path / "experiments.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    unsafe = _experiment(evidence_sources=["sk-proj-ABCDEFGHIJKL"])
    destination.write_text(json.dumps(unsafe) + "\n", encoding="utf-8")

    result = read_experiments(tmp_path)

    assert result.records == []
    assert len(result.issues) == 1
    assert "requires redaction" in result.issues[0].reason


def test_purge_deletes_only_known_feedback_artifacts(tmp_path) -> None:
    append_experiment(_experiment(), tmp_path)
    run_file = tmp_path / "runs" / "fb-test.json"
    run_file.write_text("{}", encoding="utf-8")
    keep = tmp_path / "keep.txt"
    keep.write_text("not feedback state", encoding="utf-8")

    deleted = purge_feedback_state(tmp_path)

    assert deleted == 2
    assert not (tmp_path / "experiments.jsonl").exists()
    assert not run_file.exists()
    assert keep.read_text(encoding="utf-8") == "not feedback state"


def test_test_suite_feedback_root_is_not_the_operator_default() -> None:
    assert feedback_root() != Path.home() / ".mq" / "feedback"


def test_feedback_schema_is_force_included_in_the_wheel() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    expected = (
        '"schemas/feedback_experiment.schema.json" = '
        '"mq_agent/schemas/feedback_experiment.schema.json"'
    )
    assert expected in pyproject


def test_feedback_contract_is_registered_in_repo_contract() -> None:
    contract = json.loads(
        (ROOT / ".mq" / "repo-contract.json").read_text(encoding="utf-8")
    )

    assert "mq.feedback-experiment.v1" in contract["contracts"]
