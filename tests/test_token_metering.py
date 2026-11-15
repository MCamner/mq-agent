"""Token usage on execution records: measured per run, absent when incomplete.

A run's token count is written only when every model call it started reported
its usage. A call that raised, timed out or came back without counts makes the
total unknowable, and an undercount would read as a cheaper run than the one
that happened.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import execution_outcome, model_routing
from mq_agent.tools.execution_outcome import (
    meter_tokens,
    model_call_started,
    record_model_tokens,
    token_meter,
    usage_tokens,
)

cli = CliRunner()


def _call(input_tokens: int | None, output_tokens: int | None) -> None:
    model_call_started()
    record_model_tokens(input_tokens, output_tokens)


def test_meter_sums_every_reported_call() -> None:
    with token_meter() as meter:
        _call(100, 20)
        _call(50, 5)
    assert meter_tokens(meter) == {"input": 150, "output": 25}


def test_a_call_without_reported_usage_makes_the_total_unknown() -> None:
    with token_meter() as meter:
        _call(100, 20)
        _call(None, 5)
    assert meter_tokens(meter) is None


def test_a_call_that_never_returned_makes_the_total_unknown() -> None:
    with token_meter() as meter:
        _call(100, 20)
        model_call_started()
    assert meter_tokens(meter) is None


def test_a_run_without_model_calls_has_no_token_count() -> None:
    with token_meter() as meter:
        pass
    assert meter_tokens(meter) is None


def test_recording_outside_a_meter_is_a_no_op() -> None:
    model_call_started()
    record_model_tokens(1, 1)


def test_usage_is_read_from_an_openai_style_response() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3))
    assert usage_tokens(response) == (12, 3)
    assert usage_tokens(SimpleNamespace()) == (None, None)


def _fake_urlopen(body: dict):
    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return lambda *a, **k: _Response(json.dumps(body).encode())


def test_local_chat_client_exposes_ollama_counts_as_usage(monkeypatch) -> None:
    from mq_agent.core import local_llm

    monkeypatch.setattr(local_llm.urllib.request, "urlopen", _fake_urlopen({
        "done": True, "message": {"content": "{}"},
        "prompt_eval_count": 40, "eval_count": 7,
    }))
    response = local_llm.OllamaClient().create(model="m", messages=[])
    assert usage_tokens(response) == (40, 7)


def test_direct_ollama_generate_records_into_the_active_meter(monkeypatch) -> None:
    from mq_agent.tools import model_runtime

    monkeypatch.setattr(model_runtime.urllib.request, "urlopen", _fake_urlopen({
        "done": True, "response": "{}", "prompt_eval_count": 30, "eval_count": 4,
    }))
    with token_meter() as meter:
        model_runtime._ollama_generate("m", "p", 5)
    assert meter_tokens(meter) == {"input": 30, "output": 4}


def test_planner_records_the_usage_of_its_model_call() -> None:
    from mq_agent.core.planner import Planner
    from mq_agent.core.state import AgentState

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"steps": []}'))],
        usage=SimpleNamespace(prompt_tokens=200, completion_tokens=10),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: response))
    )
    with token_meter() as meter:
        Planner(client).create_plan(AgentState(goal="g", working_dir="."), [])
    assert meter_tokens(meter) == {"input": 200, "output": 10}


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _store(tmp_path, monkeypatch) -> Path:
    destination = tmp_path / "execution-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(destination))
    monkeypatch.setattr("mq_agent.main._client", lambda: None)
    return destination


def _audit(calls):
    def run(*args, **kwargs):
        calls()
        return {"summary": "s", "steps": [], "passed": True, "verification": {}}
    return run


def test_a_cli_run_records_the_tokens_its_model_calls_reported(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "mq_agent.agents.audit_agent.AuditAgent.run",
        _audit(lambda: (_call(300, 30), _call(100, 10))),
    )
    assert cli.invoke(app, ["audit", ".", "--json"]).exit_code == 0
    assert _records(store)[0]["tokens"] == {"input": 400, "output": 40}


def test_a_cli_run_with_an_unreported_call_records_no_tokens(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "mq_agent.agents.audit_agent.AuditAgent.run",
        _audit(lambda: (_call(300, 30), model_call_started())),
    )
    assert cli.invoke(app, ["audit", ".", "--json"]).exit_code == 0
    assert "tokens" not in _records(store)[0]


def test_route_report_sums_tokens_over_measured_records_only(tmp_path) -> None:
    source = tmp_path / "executions.jsonl"
    base = {"runtime": "agent", "task_class": "ci", "result": "PASS",
            "exit_status": "ok", "latency_ms": 10,
            "route": {"selected": "codex", "policy": "static", "confidence": None}}
    records = [
        execution_outcome.build_execution_outcome(**base, tokens={"input": 100, "output": 10}),
        execution_outcome.build_execution_outcome(**base, tokens={"input": 50, "output": 5}),
        execution_outcome.build_execution_outcome(**base),
    ]
    source.write_text("\n".join(map(json.dumps, records)) + "\n", encoding="utf-8")

    bucket = model_routing.route_report(source)["execution"]["by_task_class"]["ci"][
        "by_route"
    ]["codex"]
    assert bucket["tokens"] == {"measured_outcomes": 2, "input": 150, "output": 15}


def test_route_report_has_no_token_total_when_nothing_was_measured(tmp_path) -> None:
    source = tmp_path / "executions.jsonl"
    record = execution_outcome.build_execution_outcome(
        runtime="agent", task_class="ci", result="PASS", exit_status="ok", latency_ms=10,
    )
    source.write_text(json.dumps(record) + "\n", encoding="utf-8")

    bucket = model_routing.route_report(source)["execution"]["by_task_class"]["ci"][
        "by_route"
    ]["unreported"]
    assert bucket["tokens"] is None
