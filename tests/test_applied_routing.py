"""The first path where a routing decision governs work rather than advising.

Two things these tests exist to prevent, both of which this codebase has
already produced once:

1. A gate that cannot be satisfied by construction. Eligibility must not depend
   on readiness, because readiness depends on applied observations, which
   depend on eligibility.
2. Evidence that was never earned. Only a route that actually governed work may
   be recorded as `applied`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq_agent.core.state import SafetyMode
from mq_agent.tools import applied_routing, model_routing

DOCS_TASK = "Review the repository documentation for gaps"


def _decision(task: str = DOCS_TASK) -> dict:
    return model_routing.inspect_route(task)


def test_the_allowlist_is_the_only_source_of_authorization() -> None:
    # Deliberately narrow: #214 proves one chain before widening. A wider list
    # is a human decision, never a consequence of collected telemetry.
    assert applied_routing.APPLIED_ROUTE_ALLOWLIST == frozenset({"docs-review"})


def test_eligibility_does_not_depend_on_readiness() -> None:
    """The bootstrap circle, asserted as absent.

    `eligible -> readiness -> applied observations -> eligible` is unsatisfiable.
    Readiness reports evidence; it must never be consulted for permission.
    """
    import ast

    tree = ast.parse(Path(applied_routing.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "route_readiness" not in imported
    assert "route_readiness" not in called


def test_readiness_says_it_grants_no_eligibility(tmp_path) -> None:
    readiness = model_routing.route_readiness(tmp_path / "none.jsonl")

    assert readiness["grants_eligibility"] is False
    assert readiness["automatic_routing_enabled"] is False


# --- the route-level veto, additive to the per-step gate --------------------


def test_a_cloud_required_class_is_never_applied_locally() -> None:
    decision = _decision("Review this change for security vulnerabilities")

    allowed, reason = applied_routing.route_level_safety(decision, SafetyMode.READ_ONLY)

    assert allowed is False
    assert reason == "policy-requires-cloud"


def test_suggest_mode_vetoes_the_candidate() -> None:
    # SafetyGate refuses every step in suggest mode. A route that ran here would
    # be the one part of the process doing real work in a mode promising none.
    allowed, reason = applied_routing.route_level_safety(_decision(), SafetyMode.SUGGEST)

    assert allowed is False
    assert reason == "operator-required"


def test_read_only_permits_the_candidate() -> None:
    allowed, reason = applied_routing.route_level_safety(
        _decision(), SafetyMode.READ_ONLY
    )

    assert allowed is True
    assert reason is None


def test_the_route_veto_does_not_replace_the_per_step_gate() -> None:
    """The route check is a second, earlier gate — not a substitute.

    Reading B3 as a replacement would weaken safety while appearing to add a
    check, so the per-step gate stays untouched and independently enforced.
    """
    from mq_agent.core.safety import SafetyGate
    from mq_agent.core.state import PlanStep

    gate = SafetyGate(SafetyMode.READ_ONLY)
    allowed, _ = gate.check(PlanStep(index=0, description="d", tool="run_command", args={}))

    assert allowed is False


# --- what gets recorded ----------------------------------------------------


def test_a_class_outside_the_allowlist_is_advisory_not_applied(monkeypatch) -> None:
    monkeypatch.setattr(applied_routing, "APPLIED_ROUTE_ALLOWLIST", frozenset())

    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-1", safety_mode=SafetyMode.READ_ONLY
    )

    assert result["candidate"] is None
    assert result["outcome"]["application"] == "advisory"
    assert result["outcome"]["escalated"] is True
    assert result["outcome"]["execution_run_id"] == "exec-1"


# The escalation reason is evidence, not a label. A missing allowlist entry is
# missing human authorization; it is not the routing policy demanding cloud.
# Conflating the two would fill the store with untrue escalation data from the
# first run — the exact failure #213 through #219 existed to remove.
def test_a_missing_allowlist_entry_is_not_recorded_as_a_policy_decision(
    monkeypatch,
) -> None:
    monkeypatch.setattr(applied_routing, "APPLIED_ROUTE_ALLOWLIST", frozenset())

    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-1", safety_mode=SafetyMode.READ_ONLY
    )

    assert result["outcome"]["escalation_reason"] == "operator-required"
    # The policy did recommend the local route here; only authorization was
    # absent. Recording `policy-requires-cloud` would attribute the refusal to
    # a decision the policy never made.
    assert result["decision"]["recommended_route"] == "local-shadow"


# The policy check runs before the allowlist check: a cloud-required class is
# refused by policy whatever the allowlist says, and recording it as merely
# unauthorized would hide the stronger fact.
def test_policy_requires_cloud_is_reserved_for_actual_policy_refusals() -> None:
    result = applied_routing.apply_route(
        "Review this change for security vulnerabilities",
        execution_run_id="exec-1",
        safety_mode=SafetyMode.READ_ONLY,
    )

    assert result["outcome"]["escalation_reason"] == "policy-requires-cloud"
    assert result["decision"]["recommended_route"] == "cloud-required"


def test_a_vetoed_candidate_is_advisory_not_applied() -> None:
    # It never governed anything, so it is not applied evidence — the boundary
    # case that decides whether readiness can trust the store.
    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-1", safety_mode=SafetyMode.SUGGEST
    )

    assert result["outcome"]["application"] == "advisory"
    assert result["outcome"]["escalation_reason"] == "operator-required"


def test_applied_routing_can_be_turned_off(monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_APPLIED_ROUTING", "off")

    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-1", safety_mode=SafetyMode.READ_ONLY
    )

    assert result["outcome"]["application"] == "advisory"
    assert result["candidate"] is None


def test_a_route_that_ran_is_applied_even_when_it_then_escalated(monkeypatch) -> None:
    # A route that began governing and then failed did govern. Recording it as
    # anything else would hide real applied evidence behind its failure.
    def _ran_then_failed(task, **kwargs):
        decision = model_routing.inspect_route(task)
        return {
            "decision": decision,
            "candidate": None,
            "outcome": model_routing._outcome(
                decision,
                attempted=True,
                model_output_received=True,
                verification_status="FAIL",
                escalated=True,
                escalation_reason="malformed-output",
            ),
        }

    monkeypatch.setattr(applied_routing, "shadow_route", _ran_then_failed)

    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-1", safety_mode=SafetyMode.READ_ONLY
    )

    assert result["outcome"]["application"] == "applied"
    assert result["outcome"]["escalated"] is True


def test_a_route_that_never_started_is_not_applied(monkeypatch) -> None:
    def _never_ran(task, **kwargs):
        decision = model_routing.inspect_route(task)
        return {
            "decision": decision,
            "candidate": None,
            "outcome": model_routing._outcome(
                decision,
                verification_status="UNAVAILABLE",
                escalated=True,
                escalation_reason="model-unavailable",
            ),
        }

    monkeypatch.setattr(applied_routing, "shadow_route", _never_ran)

    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-1", safety_mode=SafetyMode.READ_ONLY
    )

    assert result["outcome"]["application"] == "advisory"


def test_a_governing_route_records_applied_with_its_correlation(monkeypatch) -> None:
    def _governed(task, **kwargs):
        decision = model_routing.inspect_route(task)
        return {
            "decision": decision,
            "candidate": {
                "task_class": decision["task_class"],
                "summary": "docs are thin",
                "evidence": [],
                "suggestions": ["add a README section"],
            },
            "outcome": model_routing._outcome(
                decision,
                attempted=True,
                model_output_received=True,
                schema_valid=True,
                verification_status="PASS",
            ),
        }

    monkeypatch.setattr(applied_routing, "shadow_route", _governed)

    result = applied_routing.apply_route(
        DOCS_TASK, execution_run_id="exec-42", safety_mode=SafetyMode.READ_ONLY
    )
    outcome = result["outcome"]

    assert outcome["application"] == "applied"
    assert outcome["execution_run_id"] == "exec-42"
    assert outcome["task_class"] == "docs-review"
    # D3: the observation's own identity is not the run's.
    assert outcome["run_id"] != outcome["execution_run_id"]
    assert result["candidate"]["summary"] == "docs are thin"


# --- end to end, through the enclosing execution ---------------------------


@pytest.fixture()
def stores(tmp_path, monkeypatch):
    executions = tmp_path / "execution-outcomes.jsonl"
    routes = tmp_path / "route-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(executions))
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(routes))
    monkeypatch.setattr("mq_agent.main._client", lambda: None)
    return executions, routes


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_a_docs_audit_correlates_its_routing_observation(stores, monkeypatch) -> None:
    """The whole chain: one execution, one applied route, one real correlation."""
    from typer.testing import CliRunner

    from mq_agent.main import app

    executions, routes = stores
    captured: dict = {}

    def _governed(task, **kwargs):
        decision = model_routing.inspect_route(task)
        return {
            "decision": decision,
            "candidate": {
                "task_class": decision["task_class"],
                "summary": "docs are thin",
                "evidence": [],
                "suggestions": ["add a README section"],
            },
            "outcome": model_routing._outcome(
                decision,
                attempted=True,
                model_output_received=True,
                schema_valid=True,
                verification_status="PASS",
            ),
        }

    monkeypatch.setattr(applied_routing, "shadow_route", _governed)

    def _audit(self, path=".", execution_run_id=None):
        captured["run_id"] = execution_run_id
        steps = [{"description": "read README", "status": "ok", "result": "README"}]
        result = {"steps": steps, "verification": {"all_passed": True}}
        routed = type(self)._routed_docs_review(
            steps, execution_run_id, SafetyMode.READ_ONLY
        )
        if routed is not None:
            result["docs_review"] = routed
        return result

    monkeypatch.setattr("mq_agent.agents.docs_agent.DocsAgent.audit", _audit)

    CliRunner().invoke(app, ["docs-audit", ".", "--json"])

    execution = _records(executions)[0]
    observation = _records(routes)[0]

    assert captured["run_id"] == execution["run_id"]
    assert observation["execution_run_id"] == execution["run_id"]
    assert observation["application"] == "applied"
    assert observation["task_class"] == "docs-review"
    # D1: the execution class and the routing class are different vocabularies
    # describing different things, and both are true of this run.
    assert execution["task_class"] == "docs"
    # D6: nothing writes routing truth at the execution layer any more.
    assert "route" not in execution


def test_readiness_counts_the_real_applied_route(stores, monkeypatch) -> None:
    """`candidate_routes = 1` from a real run — the first honest count."""
    from typer.testing import CliRunner

    from mq_agent.main import app

    _, routes = stores

    def _governed(task, **kwargs):
        decision = model_routing.inspect_route(task)
        return {
            "decision": decision,
            "candidate": {
                "task_class": decision["task_class"],
                "summary": "s",
                "evidence": [],
                "suggestions": ["x"],
            },
            "outcome": model_routing._outcome(
                decision,
                attempted=True,
                model_output_received=True,
                schema_valid=True,
                verification_status="PASS",
            ),
        }

    monkeypatch.setattr(applied_routing, "shadow_route", _governed)

    def _audit(self, path=".", execution_run_id=None):
        steps = [{"description": "d", "status": "ok", "result": "r"}]
        result = {"steps": steps, "verification": {"all_passed": True}}
        routed = type(self)._routed_docs_review(
            steps, execution_run_id, SafetyMode.READ_ONLY
        )
        if routed is not None:
            result["docs_review"] = routed
        return result

    monkeypatch.setattr("mq_agent.agents.docs_agent.DocsAgent.audit", _audit)

    CliRunner().invoke(app, ["docs-audit", ".", "--json"])

    readiness = model_routing.route_readiness(routes)
    docs = readiness["task_classes"]["docs-review"]

    assert docs["actual"]["candidate_routes"] == 1
    # One route is not two. The gate stays shut, and says so honestly rather
    # than being lowered to make the first run look finished.
    assert docs["eligible"] is False
    assert model_routing.READINESS_THRESHOLDS["minimum_candidate_routes"] == 2
