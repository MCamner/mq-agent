"""Route evidence is recorded only under the planner the era assumes.

#424 made Ollama the default provider, so a docs-audit run without
MQ_AGENT_PROVIDER=openai planned with qwen3.5:9b. The route comparison is
built on gpt-4o planning: the routes differ only in who writes the review of
the material the planner gathered. A run planned by another model must not
add an observation to that comparison.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from mq_agent.agents.docs_agent import DocsAgent
from mq_agent.core.state import PlanStep
from mq_agent.tools import applied_routing


def _agent(tmp_path, planner_model: str, calls: list) -> DocsAgent:
    (tmp_path / "a.md").write_text("declared material")
    plan = [PlanStep(index=0, description="read", tool="read_file", args={"path": str(tmp_path / "a.md")})]
    agent = DocsAgent.__new__(DocsAgent)
    agent.planner = cast(Any, SimpleNamespace(model=planner_model, create_plan=lambda state, tools: plan))
    agent.verifier = cast(Any, SimpleNamespace(verify_plan=lambda plan: {"all_passed": True}))
    agent._routed_docs_review = lambda *a, **k: calls.append(a) or None  # type: ignore[method-assign]
    return agent


def test_route_is_not_applied_or_recorded_under_another_planner(tmp_path) -> None:
    calls: list = []
    result = _agent(tmp_path, "qwen3.5:9b", calls).audit(str(tmp_path), execution_run_id="run-1")
    assert calls == []
    evidence = result["route_evidence"]
    assert evidence["recorded"] is False
    assert "qwen3.5:9b" in evidence["reason"]
    assert applied_routing.ROUTE_EVIDENCE_PLANNER_MODEL in evidence["reason"]


def test_route_runs_under_the_era_planner(tmp_path) -> None:
    calls: list = []
    model = applied_routing.ROUTE_EVIDENCE_PLANNER_MODEL
    result = _agent(tmp_path, model, calls).audit(str(tmp_path), execution_run_id="run-1")
    assert len(calls) == 1
    assert "route_evidence" not in result


def test_era_planner_is_the_one_every_counted_observation_used() -> None:
    assert applied_routing.ROUTE_EVIDENCE_PLANNER_MODEL == "gpt-4o"


def test_cli_says_route_evidence_was_not_recorded(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from mq_agent.main import app

    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "outcomes.jsonl"))
    monkeypatch.setattr("mq_agent.main._client", lambda: object())
    monkeypatch.setattr("mq_agent.main._require_recordable_runtime", lambda: None)

    class Agent:
        def __init__(self, client):
            self.planner = SimpleNamespace(model="qwen3.5:9b")

        def audit(self, path, execution_run_id, route):
            return {
                "steps": [{"status": "success"}], "verification": {"all_passed": True},
                "route_evidence": {"recorded": False, "reason": "planner qwen3.5:9b is not gpt-4o; set MQ_AGENT_PROVIDER=openai to record route evidence"},
            }

    monkeypatch.setattr("mq_agent.agents.docs_agent.DocsAgent", Agent)
    output = CliRunner().invoke(app, ["docs-audit", "."])
    assert "Route evidence NOT recorded" in output.output
    assert "MQ_AGENT_PROVIDER=openai" in output.output
