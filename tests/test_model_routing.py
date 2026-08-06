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


def _candidate(evidence: list[str]) -> dict:
    return {
        "response": json.dumps(
            {
                "task_class": "diff-summary",
                "summary": "The change moves the retry budget into the client.",
                "evidence": evidence,
                "suggestions": [],
            }
        )
    }


CONTEXT = (
    "--- a/client.py\n+++ b/client.py\n"
    "-    RETRY_BUDGET = 3\n"
    "+    def __init__(self, retry_budget: int = 3) -> None:\n"
    "+        self.retry_budget = retry_budget\n"
)


def test_candidate_schema_bounds_list_length_but_never_item_length() -> None:
    evidence = model_routing._CANDIDATE_SCHEMA["properties"]["evidence"]
    suggestions = model_routing._CANDIDATE_SCHEMA["properties"]["suggestions"]

    assert evidence["maxItems"] == 5
    assert suggestions["maxItems"] == 3
    # A per-item maxLength truncates a quote mid-string, which fails the grounding
    # check on every run. Bound how many quotes are returned, never how long one is.
    assert "maxLength" not in evidence["items"]
    assert "maxLength" not in suggestions["items"]


def test_shadow_timeout_default_covers_measured_generation_time() -> None:
    import inspect

    assert inspect.signature(model_routing.shadow_route).parameters["timeout"].default == 180


def test_shadow_verifies_evidence_is_quoted_from_the_supplied_material(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: _candidate(["self.retry_budget = retry_budget"]),
    )

    result = model_routing.shadow_route("Summarize this diff", context=CONTEXT)
    outcome = result["outcome"]

    assert outcome["verification"]["status"] == "PASS"
    assert "evidence-grounded" in outcome["verification"]["checks"]
    assert outcome["escalated"] is False
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(outcome)


def test_shadow_fails_evidence_that_is_not_in_the_material(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: _candidate(["the timeout was raised to 30 seconds"]),
    )

    result = model_routing.shadow_route("Summarize this diff", context=CONTEXT)
    outcome = result["outcome"]

    assert result["candidate"] is None
    assert outcome["model_output_received"] is True
    assert outcome["verification"]["status"] == "FAIL"
    assert outcome["escalation_reason"] == "verification-failed"
    assert outcome["escalated"] is True


def test_shadow_rejects_evidence_too_short_to_be_a_quote(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: _candidate(["self"]),
    )

    result = model_routing.shadow_route("Summarize this diff", context=CONTEXT)

    assert result["outcome"]["verification"]["status"] == "FAIL"
    assert result["outcome"]["escalation_reason"] == "verification-failed"


def test_shadow_requires_evidence_when_material_is_supplied(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(model_routing, "_ollama_generate", lambda *args, **kwargs: _candidate([]))

    result = model_routing.shadow_route("Summarize this diff", context=CONTEXT)

    assert result["outcome"]["verification"]["status"] == "FAIL"
    assert result["outcome"]["escalation_reason"] == "verification-failed"


def test_shadow_without_material_is_verified_but_not_grounded(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: _candidate(["anything at all goes here"]),
    )

    outcome = model_routing.shadow_route("Summarize this diff")["outcome"]

    assert outcome["verification"]["status"] == "PASS"
    assert "evidence-grounded" not in outcome["verification"]["checks"]


def test_each_shadow_run_gets_its_own_run_id(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: _candidate(["self.retry_budget = retry_budget"]),
    )

    first = model_routing.shadow_route("Summarize this diff", context=CONTEXT)["outcome"]
    second = model_routing.shadow_route("Summarize this diff", context=CONTEXT)["outcome"]

    assert first["decision_id"] == second["decision_id"]
    assert first["run_id"] != second["run_id"]
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(first)


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


def test_record_route_outcome_appends_valid_jsonl(tmp_path) -> None:
    destination = tmp_path / "route-outcomes.jsonl"
    outcome = model_routing._outcome(
        model_routing.inspect_route("Summarize this diff"),
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        verification_checks=["candidate-schema", "task-class-match"],
    )

    model_routing.record_route_outcome(outcome, destination)
    model_routing.record_route_outcome(outcome, destination)

    records = [json.loads(line) for line in destination.read_text().splitlines()]
    assert records == [outcome, outcome]


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
        "model_output_received": 1,
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

    outcome_path = tmp_path / "route-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(outcome_path))
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: None)
    shadow_result = runner.invoke(app, ["route", "shadow", "Review README", "--json"])
    assert shadow_result.exit_code == 0
    assert json.loads(shadow_result.output)["outcome"]["verification"]["status"] == "UNAVAILABLE"
    assert model_routing.route_report(outcome_path)["valid_outcomes"] == 1

    report_result = runner.invoke(
        app,
        ["route", "report", "--source", str(tmp_path / "missing.jsonl"), "--json"],
    )
    assert report_result.exit_code == 0
    assert json.loads(report_result.output)["valid_outcomes"] == 0


def test_evidence_review_fails_closed_without_outcomes(tmp_path) -> None:
    source = tmp_path / "missing.jsonl"

    review = model_routing.review_route_evidence("docs-review", source)

    assert review["schema"] == "mq.model-route-evidence-review.v1"
    assert review["decision"] == "NOT_ELIGIBLE"
    assert review["automatic_routing_enabled"] is False
    assert review["operator_approval_required"] is True
    assert review["verified_outcomes"] == 0
    assert review["failed_gates"]
    Draft202012Validator(_schema("model_route_evidence_review.schema.json")).validate(review)


def test_evidence_review_requires_operator_after_all_technical_gates(tmp_path) -> None:
    outcomes = [
        _verified(model_routing.inspect_route(f"Review README documentation part {index}"))
        for index in range(50)
    ]
    outcomes.append(
        model_routing._outcome(
            model_routing.inspect_route("Review README documentation"),
            verification_status="UNAVAILABLE",
            escalated=True,
            escalation_reason="model-unavailable",
        )
    )
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        "\n".join(json.dumps(outcome) for outcome in outcomes) + "\n",
        encoding="utf-8",
    )

    review = model_routing.review_route_evidence("docs-review", source)

    assert review["decision"] == "AWAITING_OPERATOR_APPROVAL"
    assert review["verification_success_rate"] == 1.0
    assert review["failed_gates"] == []
    assert review["automatic_routing_enabled"] is False


def test_verification_rate_ignores_attempts_the_model_never_answered(tmp_path) -> None:
    decision = model_routing.inspect_route("Summarize this diff")
    answered = model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        verification_checks=["candidate-schema", "task-class-match"],
    )
    server_down = model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=False,
        verification_status="UNAVAILABLE",
        escalated=True,
        escalation_reason="model-unavailable",
    )
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        "\n".join((json.dumps(answered), json.dumps(server_down))) + "\n",
        encoding="utf-8",
    )

    review = model_routing.review_route_evidence("diff-summary", source)
    report = model_routing.route_report(source)

    assert review["responded_outcomes"] == 1
    assert review["attempted_outcomes"] == 2
    assert review["verification_success_rate"] == 1.0
    assert report["by_task_class"]["diff-summary"]["verification_rate"] == 1.0
    Draft202012Validator(_schema("model_route_evidence_review.schema.json")).validate(review)


def test_evidence_review_marks_gates_no_observation_could_fail(tmp_path) -> None:
    decision = model_routing.inspect_route("Summarize this diff")
    outcome = model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        verification_checks=["candidate-schema", "task-class-match"],
    )
    source = tmp_path / "outcomes.jsonl"
    source.write_text(json.dumps(outcome) + "\n", encoding="utf-8")

    review = model_routing.review_route_evidence("diff-summary", source)
    by_id = {gate["id"]: gate for gate in review["gates"]}

    assert by_id["zero-unauthorized-writes"]["vacuous"] is True
    assert by_id["zero-safety-contract-violations"]["vacuous"] is True
    assert by_id["all-malformed-outputs-escalated"]["vacuous"] is True
    assert by_id["minimum-verified-outcomes"]["vacuous"] is False
    assert by_id["verification-success-rate"]["vacuous"] is False
    assert set(review["vacuous_gates"]) == {
        "zero-unauthorized-writes",
        "zero-safety-contract-violations",
        "all-malformed-outputs-escalated",
    }
    Draft202012Validator(_schema("model_route_evidence_review.schema.json")).validate(review)


def _verified(decision: dict, *, grounded: bool = True) -> dict:
    checks = ["candidate-schema", "task-class-match"]
    if grounded:
        checks.append("evidence-grounded")
    return model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        verification_checks=checks,
    )


def test_volume_from_one_repeated_task_fails_the_coverage_gate(tmp_path) -> None:
    decision = model_routing.inspect_route("Summarize this diff")
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        "\n".join(json.dumps(_verified(decision)) for _ in range(50)) + "\n",
        encoding="utf-8",
    )

    review = model_routing.review_route_evidence("diff-summary", source)
    by_id = {gate["id"]: gate for gate in review["gates"]}

    assert review["verified_outcomes"] == 50
    assert review["distinct_verified_tasks"] == 1
    assert by_id["minimum-verified-outcomes"]["passed"] is True
    assert by_id["distinct-verified-tasks"]["passed"] is False
    assert review["decision"] == "NOT_ELIGIBLE"
    Draft202012Validator(_schema("model_route_evidence_review.schema.json")).validate(review)


def test_ungrounded_outcomes_fail_the_grounding_gate(tmp_path) -> None:
    outcomes = [
        _verified(model_routing.inspect_route(f"Summarize this diff number {index}"), grounded=False)
        for index in range(50)
    ]
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        "\n".join(json.dumps(outcome) for outcome in outcomes) + "\n", encoding="utf-8"
    )

    review = model_routing.review_route_evidence("diff-summary", source)
    by_id = {gate["id"]: gate for gate in review["gates"]}

    assert by_id["distinct-verified-tasks"]["passed"] is True
    assert by_id["verified-outcomes-are-grounded"]["passed"] is False
    assert by_id["verified-outcomes-are-grounded"]["vacuous"] is False
    assert review["grounded_verified_outcomes"] == 0
    assert review["decision"] == "NOT_ELIGIBLE"


def test_grounding_gate_is_vacuous_without_verified_outcomes(tmp_path) -> None:
    source = tmp_path / "missing.jsonl"

    review = model_routing.review_route_evidence("diff-summary", source)
    by_id = {gate["id"]: gate for gate in review["gates"]}

    assert by_id["verified-outcomes-are-grounded"]["vacuous"] is True
    assert "verified-outcomes-are-grounded" in review["vacuous_gates"]


def test_malformed_evidence_makes_the_escalation_gate_meaningful(tmp_path) -> None:
    decision = model_routing.inspect_route("Summarize this diff")
    malformed = model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=True,
        verification_status="FAIL",
        escalated=True,
        escalation_reason="malformed-output",
    )
    source = tmp_path / "outcomes.jsonl"
    source.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    review = model_routing.review_route_evidence("diff-summary", source)
    by_id = {gate["id"]: gate for gate in review["gates"]}

    assert by_id["all-malformed-outputs-escalated"]["passed"] is True
    assert by_id["all-malformed-outputs-escalated"]["vacuous"] is False
    assert by_id["zero-safety-contract-violations"]["vacuous"] is False
    assert "all-malformed-outputs-escalated" not in review["vacuous_gates"]


def test_evidence_review_detects_unescalated_malformed_output(tmp_path) -> None:
    decision = model_routing.inspect_route("Review README documentation")
    malformed = model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=True,
        verification_status="FAIL",
        escalated=False,
        escalation_reason="malformed-output",
    )
    source = tmp_path / "outcomes.jsonl"
    source.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    review = model_routing.review_route_evidence("docs-review", source)

    assert "all-malformed-outputs-escalated" in review["failed_gates"]
    assert review["safety_contract_violations"] == 1


def test_evidence_review_cli_returns_nonzero_when_not_eligible(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "route",
            "evidence-review",
            "docs-review",
            "--source",
            str(tmp_path / "missing.jsonl"),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["decision"] == "NOT_ELIGIBLE"
