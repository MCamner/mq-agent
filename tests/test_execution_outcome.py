from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from mq_agent.core.swarm import AgentManifest, SwarmConfig, SwarmRunner
from mq_agent.tools import execution_outcome


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAME = "execution_outcome.schema.json"


def _schema() -> dict:
    return json.loads((ROOT / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8"))


def _outcome(**overrides) -> dict:
    outcome = execution_outcome.build_execution_outcome(
        runtime="swarm",
        task_class="audit",
        result="PASS",
        exit_status="ok",
        latency_ms=1200,
        route={"selected": "swarm", "policy": "static", "confidence": None},
        agents=[{"name": "audit", "status": "ok", "latency_ms": 1100}],
    )
    outcome.update(overrides)
    return outcome


def _config(agent_name: str = "audit") -> SwarmConfig:
    return SwarmConfig(
        name="audit",
        description="test swarm",
        manifests=[
            AgentManifest(
                name=agent_name,
                purpose="test",
                safety_class="read-only",
                allowed_tools=[],
            )
        ],
    )


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- Phase 0: the contract -------------------------------------------------


def test_schema_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(_schema())


def test_built_outcome_is_schema_valid_and_carries_a_run_id() -> None:
    outcome = _outcome()

    Draft202012Validator(_schema()).validate(outcome)
    assert outcome["schema"] == "mq.execution-outcome.v1"
    assert outcome["run_id"]
    assert outcome["route"]["selected"] == "swarm"


def test_route_is_a_field_not_the_subject() -> None:
    outcome = _outcome()

    assert set(outcome["route"]) == {"selected", "policy", "confidence"}


# Counters the runtime does not measure are absent, never zero: a zero would be
# read as "no retries happened" instead of "nobody counted".
def test_unmeasured_counters_are_absent_rather_than_zero() -> None:
    outcome = _outcome()

    assert "retries" not in outcome
    assert "tool_calls" not in outcome
    assert "tokens" not in outcome
    assert "cost" not in outcome


def test_measured_counters_are_kept() -> None:
    outcome = execution_outcome.build_execution_outcome(
        runtime="swarm",
        task_class="ci",
        result="FAIL",
        exit_status="error",
        latency_ms=10,
        retries=2,
        tool_calls=7,
    )

    assert outcome["retries"] == 2
    assert outcome["tool_calls"] == 7


def test_an_unknown_task_class_is_recorded_as_unclassified() -> None:
    outcome = execution_outcome.build_execution_outcome(
        runtime="swarm",
        task_class="something-an-operator-invented",
        result="PASS",
        exit_status="ok",
        latency_ms=5,
    )

    assert outcome["task_class"] == "unclassified"
    Draft202012Validator(_schema()).validate(outcome)


def test_a_record_that_breaks_the_contract_is_rejected(tmp_path) -> None:
    with pytest.raises(ValidationError):
        execution_outcome.record_execution_outcome(
            {"schema": "mq.execution-outcome.v1"}, tmp_path / "out.jsonl"
        )


def test_the_route_contract_is_not_accepted_as_an_execution_record() -> None:
    route_record = json.loads(
        (ROOT / "schemas" / "model_route_outcome.schema.json").read_text(encoding="utf-8")
    )
    assert route_record["properties"]["schema"]["const"] == "mq.model-route-outcome.v1"

    validator = Draft202012Validator(_schema())
    assert not validator.is_valid({"schema": "mq.model-route-outcome.v1"})


def test_record_appends_one_line_per_outcome(tmp_path) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"

    execution_outcome.record_execution_outcome(_outcome(), destination)
    execution_outcome.record_execution_outcome(_outcome(), destination)

    assert len(_records(destination)) == 2


# --- Phase 1: one emit point ----------------------------------------------


def test_a_real_swarm_run_appends_exactly_one_record(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    runner = SwarmRunner(client=None)
    monkeypatch.setattr(SwarmRunner, "_run_agent", lambda *a, **k: {"ok": True})

    result = runner.run(_config(), path=".")

    records = _records(destination)
    assert result.passed is True
    assert len(records) == 1
    assert records[0]["runtime"] == "swarm"
    assert records[0]["task_class"] == "audit"
    assert records[0]["result"] == "PASS"
    assert records[0]["latency_ms"] >= 0
    assert [a["name"] for a in records[0]["agents"]] == ["audit"]


def test_a_failing_swarm_run_still_records_and_classifies_the_failure(
    tmp_path, monkeypatch
) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    runner = SwarmRunner(client=None)

    # An unknown agent name makes _run_agent raise, which the swarm catches.
    result = runner.run(_config(agent_name="not-a-real-agent"), path=".")

    records = _records(destination)
    assert result.passed is False
    assert len(records) == 1
    assert records[0]["result"] == "FAIL"
    assert records[0]["exit_status"] == "error"
    assert records[0]["agents"][0]["status"] == "error"


def test_a_dry_run_records_nothing(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))

    SwarmRunner(client=None).run(_config(), path=".", dry_run=True)

    assert _records(destination) == []


def test_telemetry_can_be_turned_off(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    monkeypatch.setenv("MQ_AGENT_TELEMETRY", "off")
    monkeypatch.setattr(SwarmRunner, "_run_agent", lambda *a, **k: {"ok": True})

    result = SwarmRunner(client=None).run(_config(), path=".")

    assert result.passed is True
    assert _records(destination) == []


# Telemetry is an observer. A broken evidence store must never take a run with
# it — this is the rule that lets the emit points be added everywhere.
def test_a_failed_write_does_not_fail_the_run(tmp_path, monkeypatch, capsys) -> None:
    unwritable = tmp_path / "not-a-directory"
    unwritable.write_text("blocking file", encoding="utf-8")
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(unwritable / "out.jsonl"))
    monkeypatch.setattr(SwarmRunner, "_run_agent", lambda *a, **k: {"ok": True})

    result = SwarmRunner(client=None).run(_config(), path=".")

    assert result.passed is True
    assert len(result.results) == 1


def test_emit_never_raises_even_on_an_invalid_record(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "out.jsonl"))

    assert execution_outcome.emit_execution_outcome(runtime="swarm", result="NOPE") is None


# --- packaging: the schema must travel with the wheel ----------------------


# The module reads the schema from `mq_agent/schemas/` when installed and falls
# back to the repo root when running from a checkout. Without a force-include
# the installed path does not exist, `emit_execution_outcome` swallows the
# FileNotFoundError, and every installed runtime silently records nothing.
def test_the_schema_is_force_included_in_the_wheel() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert f'"schemas/{SCHEMA_NAME}" = "mq_agent/schemas/{SCHEMA_NAME}"' in pyproject


def test_a_record_missing_a_required_execution_field_is_rejected(tmp_path) -> None:
    complete = _outcome()

    for field in ("runtime", "result", "exit_status", "latency_ms", "run_id"):
        incomplete = {k: v for k, v in complete.items() if k != field}
        with pytest.raises(ValidationError):
            execution_outcome.record_execution_outcome(incomplete, tmp_path / "out.jsonl")


def test_an_agent_that_never_ran_reports_no_latency(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    config = _config()
    config.manifests[0].requires_approve = True

    SwarmRunner(client=None).run(config, path=".", approve=False)

    agent = _records(destination)[0]["agents"][0]
    assert agent["status"] == "skipped"
    assert "latency_ms" not in agent


# Several tests drive a real swarm run. Without isolation each pytest run
# appends records to the operator's real store that are indistinguishable from
# real runs — corrupted evidence, not untidiness.
def test_the_suite_never_writes_to_the_operators_real_store() -> None:
    path = execution_outcome.outcome_path()

    assert Path.home() not in path.parents
