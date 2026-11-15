"""Scoped runtime measurements from real dispatch boundaries and provider usage."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mq_agent.core.execution_metrics import (
    collect_execution_metrics,
    create_chat_completion,
    mark_tool_scope,
    record_tool_call,
)
from mq_agent.core.executor import Executor
from mq_agent.core.safety import SafetyGate
from mq_agent.core.state import AgentState, PlanStep, SafetyMode
from mq_agent.core.task_runner import Task, TaskStep, run_task


def response(input_tokens=3, output_tokens=2):
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=input_tokens, completion_tokens=output_tokens))


def client(*responses):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=list(responses)))))


def test_usage_requires_every_observed_call_per_field():
    c = client(response(4, 1), response(None, 2))
    with collect_execution_metrics() as metrics:
        create_chat_completion(c, model="fixture")
        create_chat_completion(c, model="fixture")
    assert metrics.fields() == {"tokens": {"output": 3}}


def test_failed_model_call_keeps_original_exception_and_omits_partial_totals():
    failure = RuntimeError("provider failed")
    c = client(response(), failure)
    with collect_execution_metrics() as metrics:
        create_chat_completion(c)
        with pytest.raises(RuntimeError) as caught:
            create_chat_completion(c)
    assert caught.value is failure
    assert metrics.fields() == {}


def test_unobserved_and_invalid_counts_do_not_become_zero():
    with collect_execution_metrics() as metrics:
        assert metrics.fields() == {}
        create_chat_completion(client(response(True, -1)))
    assert metrics.fields() == {}


def test_scope_resets_after_failure_and_nested_scopes_do_not_leak():
    with collect_execution_metrics() as outer:
        mark_tool_scope()
        record_tool_call()
        with pytest.raises(ValueError):
            with collect_execution_metrics() as inner:
                mark_tool_scope()
                record_tool_call()
                record_tool_call()
                raise ValueError("fixture")
        record_tool_call()
    assert outer.fields() == {"tool_calls": 2}
    assert inner.fields() == {"tool_calls": 2}
    with collect_execution_metrics() as after:
        assert after.fields() == {}


def test_executor_counts_actual_failed_dispatch_not_denied_or_dry_run():
    fail = Mock(side_effect=ValueError("fixture"))
    step = PlanStep(index=0, description="Call fixture", tool="read_file", args={})
    state = AgentState(goal="fixture", safety_mode=SafetyMode.READ_ONLY, plan=[step])
    with collect_execution_metrics() as metrics:
        Executor(SafetyGate(SafetyMode.READ_ONLY), {"read_file": fail}).run_plan(state)
    assert metrics.fields() == {"tool_calls": 1}
    assert fail.call_count == 1
    dry = AgentState(goal="fixture", safety_mode=SafetyMode.READ_ONLY,
                     plan=[PlanStep(index=0, description="Dry", tool="read_file", args={})])
    with collect_execution_metrics() as metrics:
        Executor(SafetyGate(SafetyMode.READ_ONLY), {"read_file": fail}, dry_run=True).run_plan(dry)
    assert metrics.fields() == {}  # dry-run means no measured execution
    assert fail.call_count == 1


def test_yaml_counts_only_registered_dispatch_attempts(monkeypatch):
    from mq_agent.tools import TOOL_REGISTRY
    monkeypatch.setitem(TOOL_REGISTRY, "fixture_fail", Mock(side_effect=ValueError("fixture")))
    task = Task(name="fixture", steps=[TaskStep(name="missing", tool="fixture_absent"),
                                      TaskStep(name="fails", tool="fixture_fail")])
    with collect_execution_metrics() as metrics:
        results = run_task(task)
    assert [r.status for r in results] == ["unknown-tool", "error"]
    assert metrics.fields() == {"tool_calls": 1}


def test_standalone_emits_usage_once_and_no_cost(tmp_path, monkeypatch):
    from mq_agent.main import _execution_outcome
    from mq_agent.tools.execution_outcome import read_execution_outcomes
    path = tmp_path / "outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(path))
    with _execution_outcome("audit"):
        mark_tool_scope()
        record_tool_call()
        create_chat_completion(client(response(11, 7)))
    records, issues = read_execution_outcomes(path)
    assert issues == []
    assert len(records) == 1
    assert records[0]["tool_calls"] == 1
    assert records[0]["tokens"] == {"input": 11, "output": 7}
    assert "cost" not in records[0]
    assert "retries" not in records[0]


def test_ollama_projects_only_actual_nonnegative_integer_counts(monkeypatch):
    from mq_agent.core.local_llm import OllamaClient
    body = {"done": True, "message": {"content": "fixture"},
            "prompt_eval_count": 8, "eval_count": 3}
    mocked = Mock()
    mocked.__enter__ = Mock(return_value=SimpleNamespace(read=lambda: json.dumps(body).encode()))
    mocked.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: mocked)
    with collect_execution_metrics() as metrics:
        create_chat_completion(OllamaClient(), model="fixture", messages=[])
    assert metrics.fields() == {"tokens": {"input": 8, "output": 3}}
    body["prompt_eval_count"] = True
    body.pop("eval_count")
    with collect_execution_metrics() as metrics:
        create_chat_completion(OllamaClient(), model="fixture", messages=[])
    assert metrics.fields() == {}


def test_actual_planner_and_verifier_usage_share_one_scope():
    from mq_agent.core.planner import Planner
    from mq_agent.core.verification import Verifier
    from mq_agent.core.state import StepStatus
    planned = response(10, 4)
    planned.choices = [SimpleNamespace(message=SimpleNamespace(content='{"steps": []}'))]
    checked = response(5, 2)
    checked.choices = [SimpleNamespace(message=SimpleNamespace(content='{"success": true}'))]
    c = client(planned, checked)
    with collect_execution_metrics() as metrics:
        assert Planner(c).create_plan(AgentState(goal="fixture"), []) == []
        assert Verifier(c).verify(PlanStep(index=0, description="fixture", status=StepStatus.SUCCESS, result="ok"))[0]
    assert metrics.fields() == {"tokens": {"input": 15, "output": 6}}


def test_executor_fanout_counts_actual_invocations():
    from mq_agent.core.tool_contract import produces
    @produces("paths")
    def finder() -> str:
        return "one.md\ntwo.md\n"
    def reader(path: str) -> str:
        return path
    state = AgentState(goal="fixture", safety_mode=SafetyMode.DANGEROUS, plan=[
        PlanStep(index=0, description="find", tool="finder"),
        PlanStep(index=1, description="read", tool="reader", for_each={"step": 0, "as": "path"}),
    ])
    with collect_execution_metrics() as metrics:
        Executor(SafetyGate(SafetyMode.DANGEROUS), {"finder": finder, "reader": reader}).run_plan(state)
    assert metrics.fields() == {"tool_calls": 3}


def test_swarm_aggregates_supported_agents_and_omits_mixed_coverage(tmp_path, monkeypatch):
    from mq_agent.core.swarm import AgentManifest, SwarmConfig, SwarmRunner
    from mq_agent.tools.execution_outcome import read_execution_outcomes
    path = tmp_path / "swarm.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(path))
    config = SwarmConfig(name="audit", description="fixture", manifests=[
        AgentManifest(name=n, purpose="fixture", safety_class="read-only", allowed_tools=[])
        for n in ["first", "second"]])
    swarm = SwarmRunner(client())
    def supported(*args, **kwargs):
        mark_tool_scope()
        record_tool_call()
        create_chat_completion(client(response(2, 1)))
        return {}
    monkeypatch.setattr(swarm, "_run_agent", supported)
    swarm.run(config)
    records, issues = read_execution_outcomes(path)
    assert not issues
    assert len(records) == 1
    assert records[0]["tool_calls"] == 2
    assert records[0]["tokens"] == {"input": 4, "output": 2}
    assert records[0]["events"] == [{"kind": "metrics-scope:mq-agent-local"}]
    def mixed(manifest, *args, **kwargs):
        return supported() if manifest.name == "first" else {}
    monkeypatch.setattr(swarm, "_run_agent", mixed)
    swarm.run(config)
    records, _ = read_execution_outcomes(path)
    assert "tool_calls" not in records[1]
    assert "tokens" not in records[1]


def test_workflow_counts_current_dispatches_not_historical_attempts(tmp_path):
    from mq_agent.workflows import PolicyProvider, Runner, new_run, validate_plan
    from mq_agent.workflows.storage import WorkflowStore
    provider = PolicyProvider(fetcher=lambda: [{
        "name": "git_status", "class": "A", "write": False, "subprocess": True,
        "network": False, "side_effects": [], "approval": "plan", "workflow_allowed": True,
        "idempotent": True, "retry_safe": True}])
    seen = []
    runner = Runner(WorkflowStore(tmp_path / "workflows"), lambda *a: {"ok": True},
                    policy_provider=provider, observer=lambda run, meta: seen.append(meta))
    for run_id in ["one", "two"]:
        plan = validate_plan({"schema": "mq-workflow-plan.v1", "run_id": run_id,
              "template": "fixture", "task": "fixture", "repo": str(tmp_path), "steps": [
                  {"id": "first", "name": "fixture", "tool": "git_status", "attempt": 4}]})
        runner.run(new_run(plan))
    assert [meta["tool_calls"] for meta in seen] == [1, 1]


def test_unavailable_usage_property_never_changes_provider_result():
    class Result:
        @property
        def usage(self):
            raise ValueError("unsupported fixture usage")
    result = Result()
    with collect_execution_metrics() as metrics:
        assert create_chat_completion(client(result)) is result
    assert metrics.fields() == {}


def test_known_unmeasured_model_boundary_invalidates_usage(monkeypatch):
    from mq_agent.tools.model_runtime import _ollama_generate
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"done":true,"response":"fixture"}'
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response())
    with collect_execution_metrics() as metrics:
        create_chat_completion(client(response(3, 2)))
        _ollama_generate("fixture", "fixture", timeout=1)
    assert metrics.fields() == {}


def test_workflow_observer_emits_scope_marker_for_measured_dispatch(tmp_path, monkeypatch):
    from mq_agent.workflows.cli import _default_observer
    from mq_agent.tools.execution_outcome import read_execution_outcomes
    path = tmp_path / "workflow.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(path))
    monkeypatch.delenv("MQ_WORKFLOW_OBSERVE", raising=False)
    monkeypatch.setattr("mq_agent.workflows.cli.emit_observation", lambda *a, **k: None)
    observer = _default_observer()
    assert observer is not None
    observer(SimpleNamespace(summary={"ok": True}), {"duration_ms": 12, "tool_calls": 2})
    records, issues = read_execution_outcomes(path)
    assert not issues
    assert records[0]["tool_calls"] == 2
    assert records[0]["events"] == [{"kind": "metrics-scope:mq-agent-local"}]
    assert "tokens" not in records[0]
    assert "cost" not in records[0]


def test_resumed_workflow_emits_current_invocation_count_with_new_execution_id(tmp_path, monkeypatch):
    from mq_agent.workflows import PolicyProvider, Runner, new_run, validate_plan
    from mq_agent.workflows.cli import _default_observer
    from mq_agent.workflows.storage import WorkflowStore
    from mq_agent.tools.execution_outcome import read_execution_outcomes
    monkeypatch.setenv('MQ_OBSIDIAN_DIR',str(tmp_path/'vault'))
    path=tmp_path/'execution.jsonl'
    monkeypatch.setenv('MQ_AGENT_EXECUTION_OUTCOMES',str(path))
    monkeypatch.delenv('MQ_WORKFLOW_OBSERVE',raising=False)
    def policy(name):
        return {'name':name,'class':'A','write':False,'subprocess':True,'network':False,
                'side_effects':[],'approval':'none','workflow_allowed':True,'idempotent':True,'retry_safe':True}
    provider=PolicyProvider(fetcher=lambda:[policy('git_status'),policy('git_diff')])
    plan=validate_plan({'schema':'mq-workflow-plan.v1','run_id':'persistent-workflow',
        'template':'fixture','task':'resume fixture','repo':str(tmp_path),'status':'paused','steps':[
            {'id':'old','name':'Earlier work','tool':'git_status','status':'passed','attempt':3},
            {'id':'new','name':'Current work','tool':'git_diff','status':'pending'}]})
    calls=[]
    def execute(name, *args):
        calls.append(name)
        return {'ok':True}
    runner=Runner(WorkflowStore(tmp_path/'workflows'),execute,
        policy_provider=provider,observer=_default_observer())
    runner.run(new_run(plan))
    records,issues=read_execution_outcomes(path)
    assert issues==[]
    assert calls==['git_diff']
    assert len(records)==1
    assert records[0]['run_id']!='persistent-workflow'
    assert records[0]['tool_calls']==1
    assert records[0]['events']==[{'kind':'metrics-scope:mq-agent-local'}]
