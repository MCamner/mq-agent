from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import model_routing


ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_inspect_is_deterministic_read_only_and_schema_valid(monkeypatch) -> None:
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model called")),
        raising=False,
    )

    first = model_routing.inspect_route("Summarize this git diff")
    second = model_routing.inspect_route("Summarize this git diff")

    assert first == second
    assert first["task_class"] == "diff-summary"
    assert first["risk"] == "low"
    assert first["recommended_route"] == "local-shadow"
    assert first["authoritative_agent"] == "codex"
    Draft202012Validator(_schema("model_route_decision.schema.json")).validate(first)


def test_inspect_requires_cloud_for_high_risk_tasks() -> None:
    result = model_routing.inspect_route("Approve this security release architecture")

    assert result["recommended_route"] == "cloud-required"
    assert result["risk"] in {"high", "critical"}
    assert result["local_model"] is None
    assert "policy-requires-cloud" in result["escalation_conditions"]


def test_shadow_does_not_call_model_for_cloud_required(monkeypatch) -> None:
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model called")),
        raising=False,
    )

    result = model_routing.shadow_route("Make a cross-repository architecture decision")

    assert result["candidate"] is None
    assert result["outcome"]["attempted"] is False
    assert result["outcome"]["verification"]["status"] == "SKIPPED"
    assert result["outcome"]["escalation_reason"] == "policy-requires-cloud"


def test_shadow_missing_ollama_returns_structured_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: None)

    result = model_routing.shadow_route("Review README documentation")
    outcome = result["outcome"]

    assert result["candidate"] is None
    assert outcome["attempted"] is False
    assert outcome["model_output_received"] is False
    assert outcome["verification"] == {"status": "UNAVAILABLE", "checks": []}
    assert outcome["escalated"] is True
    assert outcome["escalation_reason"] == "model-unavailable"
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(outcome)


def test_shadow_validates_structured_candidate_without_accepting_it(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: {
            "response": json.dumps(
                {
                    "task_class": "docs-review",
                    "summary": "The README matches the command surface.",
                    "evidence": ["README documents mq-agent route."],
                    "suggestions": [],
                }
            )
        },
    )

    result = model_routing.shadow_route("Review README documentation")
    outcome = result["outcome"]

    assert result["candidate"]["summary"].startswith("The README")
    assert "raw_model_output" not in result
    assert outcome["attempted"] is True
    assert outcome["model_output_received"] is True
    assert outcome["schema_valid"] is True
    assert outcome["verification"]["status"] == "PASS"
    assert outcome["accepted_by_agent"] is False
    assert outcome["accepted_by_operator"] is False
    assert outcome["escalated"] is False
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(outcome)


def test_shadow_malformed_output_escalates_without_returning_raw_text(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: {"response": "not json and potentially unsafe"},
    )

    result = model_routing.shadow_route("Summarize this diff")
    outcome = result["outcome"]

    assert result["candidate"] is None
    assert "not json" not in json.dumps(result)
    assert outcome["attempted"] is True
    assert outcome["model_output_received"] is True
    assert outcome["schema_valid"] is False
    assert outcome["verification"]["status"] == "FAIL"
    assert outcome["escalation_reason"] == "malformed-output"


def test_report_distinguishes_attempted_verified_and_accepted(tmp_path) -> None:
    valid = model_routing._outcome(
        model_routing.inspect_route("Summarize this diff"),
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        verification_checks=["candidate-schema", "task-class-match"],
        accepted_by_agent=True,
    )
    unavailable = model_routing._outcome(
        model_routing.inspect_route("Review README documentation"),
        attempted=False,
        verification_status="UNAVAILABLE",
        escalated=True,
        escalation_reason="model-unavailable",
    )
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        "\n".join((json.dumps(valid), "not-json", json.dumps(unavailable))) + "\n",
        encoding="utf-8",
    )

    report = model_routing.route_report(source)

    assert report["total_records"] == 3
    assert report["valid_outcomes"] == 2
    assert report["invalid_records"] == 1
    assert report["attempted"] == 1
    assert report["verified"] == 1
    assert report["accepted_by_agent"] == 1
    assert report["accepted_by_operator"] == 0
    assert report["escalated"] == 1
    assert report["by_task_class"]["diff-summary"] == {
        "outcomes": 1,
        "attempted": 1,
        "verified": 1,
        "accepted_by_agent": 1,
        "accepted_by_operator": 0,
        "escalated": 0,
        "verification_rate": 1.0,
        "agent_acceptance_rate": 1.0,
    }


def test_route_cli_json_surfaces_are_machine_readable(monkeypatch, tmp_path) -> None:
    inspect_result = runner.invoke(app, ["route", "inspect", "Summarize this diff", "--json"])
    assert inspect_result.exit_code == 0
    assert json.loads(inspect_result.output)["schema"] == "mq.model-route-decision.v1"

    monkeypatch.setattr(model_routing.shutil, "which", lambda _: None)
    shadow_result = runner.invoke(app, ["route", "shadow", "Review README", "--json"])
    assert shadow_result.exit_code == 0
    assert json.loads(shadow_result.output)["outcome"]["verification"]["status"] == "UNAVAILABLE"

    report_result = runner.invoke(
        app,
        ["route", "report", "--source", str(tmp_path / "missing.jsonl"), "--json"],
    )
    assert report_result.exit_code == 0
    assert json.loads(report_result.output)["valid_outcomes"] == 0
