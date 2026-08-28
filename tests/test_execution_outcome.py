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
        context={"sources": ["repo-card", "codegraph"], "size": 18200},
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


def test_record_rotates_before_the_store_exceeds_the_configured_bound(
    tmp_path, monkeypatch
) -> None:
    destination = tmp_path / "execution-outcomes.jsonl"
    first = _outcome()
    line_size = len((json.dumps(first, ensure_ascii=False) + "\n").encode("utf-8"))
    monkeypatch.setenv("MQ_AGENT_OUTCOME_MAX_BYTES", str(line_size + 10))

    execution_outcome.record_execution_outcome(first, destination)
    execution_outcome.record_execution_outcome(_outcome(), destination)

    assert len(_records(destination)) == 1
    assert len(_records(destination.with_suffix(".jsonl.1"))) == 1


def test_contract_has_no_prompt_or_arbitrary_event_detail_field(tmp_path) -> None:
    with pytest.raises(ValidationError):
        execution_outcome.record_execution_outcome(
            _outcome(events=[{"kind": "budget", "detail": "raw prompt content"}]),
            tmp_path / "out.jsonl",
        )


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


# --- Phase 2: the remaining entrypoints ------------------------------------
#
# One execution is one operator action, and the outermost level owns the
# record. Agents are instrumented at the CLI, never in the agent classes: the
# same AuditAgent runs standalone and inside a swarm, and a swarm record
# already carries per-agent results. Executor.run_plan is never instrumented —
# it is only ever reached from inside an agent.

from typer.testing import CliRunner

from mq_agent.main import app

cli = CliRunner()


@pytest.fixture()
def store(tmp_path, monkeypatch) -> Path:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    monkeypatch.setattr("mq_agent.main._client", lambda: None)
    return destination


def test_a_standalone_audit_records_one_agent_execution(store, monkeypatch) -> None:
    monkeypatch.setattr(
        "mq_agent.agents.audit_agent.AuditAgent.run",
        lambda *a, **k: {"summary": "s", "steps": [], "passed": True, "verification": {}},
    )

    result = cli.invoke(app, ["audit", ".", "--json"])

    assert result.exit_code == 0
    records = _records(store)
    assert len(records) == 1
    assert records[0]["runtime"] == "agent"
    assert records[0]["task_class"] == "audit"
    assert records[0]["result"] == "PASS"


# The record answers "could the run be carried out", not "is the repo healthy".
# An audit that finds problems ran perfectly well; conflating the two would
# make every future success rate a measure of the repos, not of the runtime.
def test_an_agent_that_finds_problems_still_records_a_passing_execution(
    store, monkeypatch
) -> None:
    monkeypatch.setattr(
        "mq_agent.agents.audit_agent.AuditAgent.run",
        lambda *a, **k: {
            "summary": "s",
            "steps": [],
            "passed": False,
            "verification": {"failures": [{"step": "x", "note": "n"}]},
        },
    )

    cli.invoke(app, ["audit", "."])

    assert _records(store)[0]["result"] == "PASS"


def test_a_crashing_agent_records_a_failed_execution(store, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr("mq_agent.agents.audit_agent.AuditAgent.run", boom)

    result = cli.invoke(app, ["audit", "."])

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    records = _records(store)
    assert len(records) == 1
    assert records[0]["result"] == "FAIL"
    assert records[0]["exit_status"] == "error"


# On an agent `--dry-run` means "make no writes", not "run nothing": the agent
# still plans, reads the repo and executes its read-only steps. Skipping the
# record would leave the most common `release-check` and `fix-ci` invocation
# invisible — both default to dry_run=True.
def test_an_agent_dry_run_still_records_because_it_still_runs(store, monkeypatch) -> None:
    monkeypatch.setattr(
        "mq_agent.agents.audit_agent.AuditAgent.run",
        lambda *a, **k: {"summary": "s", "steps": [], "passed": True, "verification": {}},
    )

    cli.invoke(app, ["audit", ".", "--dry-run", "--json"])

    assert len(_records(store)) == 1


# The task runner is the opposite case: a dry run never calls the tool, so
# nothing executed and there is no outcome to record.
def test_a_task_dry_run_records_nothing(store, tmp_path, monkeypatch) -> None:
    task_file = tmp_path / "tasks" / "demo.yaml"
    task_file.parent.mkdir()
    task_file.write_text(
        "name: demo\nsteps:\n  - name: s\n    tool: repo_summary\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    cli.invoke(app, ["task", "run", "demo", "--dry-run", "--json"])

    assert _records(store) == []


# repo-signal missing aborts before the agent is constructed. The execution
# never started, so it has no outcome — a SKIPPED record would claim a run was
# measured and found empty.
def test_an_entrypoint_that_never_starts_records_nothing(store, monkeypatch) -> None:
    monkeypatch.setattr("mq_agent.tools.signal_tools.signal_available", lambda: False)

    result = cli.invoke(app, ["signal", "."])

    assert result.exit_code == 1
    assert _records(store) == []


@pytest.mark.parametrize(
    ("argv", "task_class"),
    [
        (["docs-audit", ".", "--json"], "docs"),
        (["release-check", ".", "--json", "--dry-run"], "release"),
        (["fix-ci", ".", "--json", "--dry-run"], "ci"),
    ],
)
def test_each_entrypoint_names_its_own_task_class(store, monkeypatch, argv, task_class) -> None:
    monkeypatch.setattr(
        "mq_agent.agents.docs_agent.DocsAgent.audit",
        lambda *a, **k: {"steps": [], "verification": {"all_passed": True}},
    )
    monkeypatch.setattr(
        "mq_agent.agents.release_agent.ReleaseAgent.run_check",
        lambda *a, **k: {"steps": [], "ready": True, "verification": {}},
    )
    monkeypatch.setattr(
        "mq_agent.agents.ci_agent.CIAgent.diagnose",
        lambda *a, **k: {"ci_context": {}, "steps": [], "mode": "read-only"},
    )

    cli.invoke(app, argv)

    records = _records(store)
    assert len(records) == 1
    assert records[0]["task_class"] == task_class
    assert records[0]["runtime"] == "agent"


# A swarm runs the same agents. If the agent classes emitted, one `swarm run
# ci` would write five records and every later rate would count a wide swarm
# as more runs than a narrow one.
def test_a_swarm_still_records_exactly_one_execution(store, monkeypatch) -> None:
    monkeypatch.setattr(SwarmRunner, "_run_agent", lambda *a, **k: {"ok": True})
    config = SwarmConfig(
        name="ci",
        description="two agents",
        manifests=[
            AgentManifest(name=n, purpose="p", safety_class="read-only", allowed_tools=[])
            for n in ("ci", "audit")
        ],
    )

    SwarmRunner(client=None).run(config, path=".")

    records = _records(store)
    assert len(records) == 1
    assert records[0]["runtime"] == "swarm"
    assert [a["name"] for a in records[0]["agents"]] == ["ci", "audit"]


def test_a_task_run_records_the_task_runner(store, monkeypatch, tmp_path) -> None:
    from mq_agent.core import task_runner

    monkeypatch.setattr(
        task_runner,
        "run_task",
        lambda task, dry_run=False: [
            task_runner.StepResult(step="s", tool="t", status="ok", output="o")
        ],
    )
    task_file = tmp_path / "tasks" / "demo.yaml"
    task_file.parent.mkdir()
    task_file.write_text(
        "name: demo\nsteps:\n  - name: s\n    tool: repo_summary\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    cli.invoke(app, ["task", "run", "demo", "--json"])

    records = _records(store)
    assert len(records) == 1
    assert records[0]["runtime"] == "task-runner"
    assert records[0]["task_class"] == "task"
    assert records[0]["result"] == "PASS"


# A failing task step is an execution failure, unlike an audit finding: the
# runtime could not carry out what it was asked to do.
def test_a_failing_task_step_records_a_failed_execution(store, monkeypatch, tmp_path) -> None:
    from mq_agent.core import task_runner

    monkeypatch.setattr(
        task_runner,
        "run_task",
        lambda task, dry_run=False: [
            task_runner.StepResult(step="s", tool="t", status="error", output="boom")
        ],
    )
    task_file = tmp_path / "tasks" / "demo.yaml"
    task_file.parent.mkdir()
    task_file.write_text(
        "name: demo\nsteps:\n  - name: s\n    tool: repo_summary\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    cli.invoke(app, ["task", "run", "demo", "--json"])

    records = _records(store)
    assert len(records) == 1
    assert records[0]["result"] == "FAIL"
    assert records[0]["exit_status"] == "error"


# run_task is reachable as a registered tool, so an agent can reach it. Only
# the entrypoint records; instrumenting run_task itself would nest a record
# inside an agent execution.
def test_a_task_reached_through_the_tool_registry_records_nothing(store, tmp_path, monkeypatch) -> None:
    from mq_agent.tools.repo_tools import run_task_tool

    task_file = tmp_path / "tasks" / "demo.yaml"
    task_file.parent.mkdir()
    task_file.write_text(
        "name: demo\nsteps:\n  - name: s\n    tool: repo_summary\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    run_task_tool("demo")

    assert _records(store) == []
