"""Executor measurements, rather than verification, establish audit coverage."""
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from mq_agent.tools.execution_outcome import execution_completeness_from_steps
from mq_agent.core.state import PlanStep, StepStatus
from mq_agent.main import app


def _step(status=StepStatus.SUCCESS, **fields):
    return {"status": status.value, **fields}


@pytest.mark.parametrize("status,expected", [
    (StepStatus.FAILED, "failed"), (StepStatus.SKIPPED, "skipped"),
    (StepStatus.PENDING, "not-executed"), (StepStatus.RUNNING, "not-executed"),
])
def test_unfinished_steps_are_partial(status, expected):
    actual = execution_completeness_from_steps([_step(status)])
    assert actual == {"status": "partial", "steps": [{"step": 1, "status": expected}]}


def test_empty_plan_is_partial():
    assert execution_completeness_from_steps([]) == {"status": "partial", "steps": []}


@pytest.mark.parametrize("source,executed,flag,expected", [
    (30, 25, False, "partial"), (2, 2, True, "complete"),
    (2, 1, True, "partial"), (2, 2, False, "partial"),
    (None, None, None, "unmeasured"), (2, None, True, "unmeasured"),
    (0, 0, True, "complete"),
])
def test_fan_out_requires_measured_equal_counts_and_flag(source, executed, flag, expected):
    actual = execution_completeness_from_steps([_step(
        for_each={"step": 0, "as": "path"}, source_item_count=source,
        executed_call_count=executed, fan_out_complete=flag,
    )])
    assert actual["steps"][0]["status"] == expected
    assert actual["status"] == ("complete" if expected == "complete" else "partial")
    assert ("source_item_count" in actual["steps"][0]) == (source is not None and executed is not None)


def test_ordinary_success_is_complete():
    assert execution_completeness_from_steps([_step()])["status"] == "complete"


@pytest.mark.parametrize("complete,verified,expected_exit", [
    (True, True, 0), (False, True, 1), (True, False, 1),
])
def test_docs_cli_records_coverage_and_actual_execution_id(tmp_path, monkeypatch, complete, verified, expected_exit):
    destination = tmp_path / "outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    monkeypatch.setenv("MQ_AGENT_TELEMETRY", "on")
    monkeypatch.setattr("mq_agent.main._client", lambda: object())
    monkeypatch.setattr("mq_agent.main._require_recordable_runtime", lambda: None)
    completeness = {"status": "complete" if complete else "partial", "steps": [
        {"step": 1, "status": "complete" if complete else "partial",
         "source_item_count": 2, "executed_call_count": 2 if complete else 1}
    ]}
    observed = []
    class Agent:
        def __init__(self, client):
            self.planner = SimpleNamespace(model="test-model")
        def audit(self, path, execution_run_id, route):
            observed.append(execution_run_id)
            return {"steps": [{"status": "success", "for_each": {"step": 0, "as": "path"},
                "source_item_count": 2, "executed_call_count": 2 if complete else 1,
                "fan_out_complete": complete}], "verification": {"all_passed": verified}}
    monkeypatch.setattr("mq_agent.agents.docs_agent.DocsAgent", Agent)
    output = CliRunner().invoke(app, ["docs-audit", ".", "--json"])
    assert output.exit_code == expected_exit, output.output
    payload = json.loads(output.output)
    record = json.loads(destination.read_text())
    assert record["completeness"] == completeness
    assert record["result"] == ("PASS" if expected_exit == 0 else "FAIL")
    assert record["exit_status"] == ("ok" if expected_exit == 0 else "error")
    assert payload["execution_run_id"] == record["run_id"] == observed[0]
    assert payload["execution_outcome_recorded"] is True


@pytest.mark.parametrize("count,expected", [(2, "complete"), (30, "partial")])
def test_docs_agent_reports_real_fan_out_measurements(tmp_path, count, expected):
    from typing import Any, cast

    from mq_agent.agents.docs_agent import DocsAgent

    for index in range(count):
        (tmp_path / f"file{index}.md").write_text("declared material")
    plan = [
        PlanStep(index=0, description="discover", tool="find_files", args={"path": str(tmp_path), "pattern": "*.md"}),
        PlanStep(index=1, description="read discovered", tool="read_file", for_each={"step": 0, "as": "path"}),
    ]
    agent = DocsAgent.__new__(DocsAgent)
    agent.planner = cast(Any, SimpleNamespace(create_plan=lambda state, tools: plan))
    agent.verifier = cast(Any, SimpleNamespace(verify_plan=lambda plan: {"all_passed": True}))
    result = agent.audit(str(tmp_path))
    assert result["completeness"]["status"] == expected
    measured = result["completeness"]["steps"][1]
    assert measured["source_item_count"] == count
    assert measured["executed_call_count"] == min(count, 25)


def test_docs_cli_missing_completeness_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "outcomes.jsonl"))
    monkeypatch.setattr("mq_agent.main._client", lambda: object())
    monkeypatch.setattr("mq_agent.main._require_recordable_runtime", lambda: None)
    class Agent:
        def __init__(self, client):
            self.planner = SimpleNamespace(model="test")
        def audit(self, *args, **kwargs):
            return {"steps": [], "verification": {"all_passed": True}}
    monkeypatch.setattr("mq_agent.agents.docs_agent.DocsAgent", Agent)
    result = CliRunner().invoke(app, ["docs-audit", ".", "--json"])
    assert result.exit_code == 1
    assert json.loads((tmp_path / "outcomes.jsonl").read_text())["result"] == "FAIL"


def test_complete_outcome_rejects_unequal_measured_counts():
    from mq_agent.tools.execution_outcome import build_execution_outcome

    with pytest.raises(ValueError, match="equal measured"):
        build_execution_outcome(
            runtime="agent", task_class="docs", result="PASS", exit_status="ok", latency_ms=1,
            completeness={"status": "complete", "steps": [{
                "step": 1, "status": "complete", "source_item_count": 3, "executed_call_count": 2,
            }]},
        )
