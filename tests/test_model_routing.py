from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    "-    def send(self, payload):\n"
    "+    def send(self, payload, *, deadline_s: float = 5.0):\n"
    "+        remaining = self.retry_budget\n"
    "+        while remaining > 0 and not self._expired(deadline_s):\n"
)

#: Five real quotes from CONTEXT — the minimum a grounded candidate must carry.
QUOTED_FROM_CONTEXT = [
    "self.retry_budget = retry_budget",
    "def __init__(self, retry_budget: int = 3) -> None:",
    "RETRY_BUDGET = 3",
    "remaining = self.retry_budget",
    "while remaining > 0 and not self._expired(deadline_s):",
]


def _material(count: int) -> tuple[str, list[str]]:
    """Material plus the exact quotes it grounds, for cardinality tests."""
    quotes = [f"the retry budget moved into the client at step {i:02d}" for i in range(count)]
    return "\n".join(quotes), quotes


def _invented(count: int) -> list[str]:
    return [f"a paraphrase that appears in no material, number {i:02d}" for i in range(count)]


def test_candidate_schema_bounds_evidence_item_length_but_not_item_count() -> None:
    # No maxItems on evidence, and that absence is the finding: Ollama compiles a
    # bounded array into a grammar repetition rule the model fills, so the cap
    # manufactured the fabrication it was meant to bound. Over three series of 20
    # real docs-review runs the last citation was ungrounded in 13/20 at
    # maxItems 5, 19/20 at 4, and 5/20 uncapped. Re-adding a cap here reinstates
    # that pressure, so it is asserted absent rather than merely left out.
    schema = model_routing._candidate_schema("docs-review")
    evidence = schema["properties"]["evidence"]
    suggestions = schema["properties"]["suggestions"]

    assert "maxItems" not in evidence
    assert evidence["items"]["maxLength"] == 200
    assert suggestions["maxItems"] == 3
    assert "maxLength" not in suggestions["items"]


def test_the_grammar_pins_the_task_class_rather_than_asking_for_it() -> None:
    # The measured failure this replaces: with {"type": "string"} a docs-review
    # over 74 KB of CHANGELOG-heavy material answered `task_class: "release"`.
    # The model classified the content instead of obeying the prompt, and the
    # whole candidate was discarded as schema-invalid. Ollama enforces this
    # schema as a decoding grammar, so a const makes the wrong answer unemittable
    # rather than merely discouraged.
    schema = model_routing._candidate_schema("docs-review")

    assert schema["properties"]["task_class"] == {"const": "docs-review"}


def test_the_grammar_is_built_per_task_class() -> None:
    # A module constant cannot carry a const. This is why the schema is a
    # function: re-adding a shared constant silently reopens the failure above.
    assert (
        model_routing._candidate_schema("diff-summary")["properties"]["task_class"]
        != model_routing._candidate_schema("docs-review")["properties"]["task_class"]
    )


def test_the_validator_still_checks_the_task_class_itself() -> None:
    # Defence in depth: the grammar only binds a backend that enforces one, and
    # nothing here guarantees the backend will always be Ollama.
    wrong = {
        "task_class": "release",
        "summary": "s",
        "evidence": [],
        "suggestions": [],
    }

    assert not model_routing._candidate_is_valid(wrong, "docs-review")


def _evidence_item_limit() -> int:
    evidence = model_routing._candidate_schema("docs-review")["properties"]["evidence"]
    return int(evidence["items"]["maxLength"])


def test_grounding_accepts_a_truncated_verbatim_prefix() -> None:
    # Why a per-item maxLength is safe: the grounding check is a substring match,
    # so the prefix left by truncation is still verbatim. Measured on qwen3:4b over
    # docs/architecture.md, bounding items at 200 took the run PASS-rate from 0/15
    # to 8/15 (Fisher one-sided p = 0.001) by cutting the model's habit of running
    # the document's tail into one 930-character "quote".
    limit = _evidence_item_limit()
    material = "It stores durable knowledge that should survive beyond a single run."

    assert model_routing.grounded_evidence([material[:limit]], material) == [material[:limit]]


def test_evidence_item_limit_cannot_truncate_below_the_grounding_floor() -> None:
    # These two constants are only safe as a pair. Lowering maxLength under the
    # minimum quote length truncates every quote below the floor, so grounding
    # fails on every run while the rest of the suite stays green.
    limit = _evidence_item_limit()

    assert limit > model_routing._MIN_QUOTE_LENGTH


def test_shadow_timeout_default_covers_measured_generation_time() -> None:
    import inspect

    assert inspect.signature(model_routing.shadow_route).parameters["timeout"].default == 180


def test_shadow_verifies_evidence_is_quoted_from_the_supplied_material(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing,
        "_ollama_generate",
        lambda *args, **kwargs: _candidate(QUOTED_FROM_CONTEXT),
    )

    result = model_routing.shadow_route("Summarize this diff", context=CONTEXT)
    outcome = result["outcome"]

    assert outcome["verification"]["status"] == "PASS"
    assert result["candidate"]["evidence"] == QUOTED_FROM_CONTEXT
    assert "evidence-grounded" in outcome["verification"]["checks"]
    assert outcome["escalated"] is False
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(outcome)


def test_shadow_discards_ungrounded_items_from_a_passing_candidate(monkeypatch) -> None:
    # 5 grounded of 12. The floor is met, so the candidate is usable — but the
    # seven invented citations must not travel with it.
    material, quotes = _material(5)
    evidence = quotes + _invented(7)
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing, "_ollama_generate", lambda *a, **k: _candidate(evidence)
    )

    result = model_routing.shadow_route("Summarize this diff", context=material)

    assert result["outcome"]["verification"]["status"] == "PASS"
    assert result["candidate"]["evidence"] == quotes


def test_shadow_keeps_eleven_of_twelve_rather_than_failing_the_candidate(monkeypatch) -> None:
    # The case the old ALL()-gate got wrong: eleven verified citations were
    # thrown away because a twelfth was invented. Now the twelfth is thrown away
    # instead — and it is the only thing thrown away.
    material, quotes = _material(11)
    evidence = [*quotes[:6], *_invented(1), *quotes[6:]]
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing, "_ollama_generate", lambda *a, **k: _candidate(evidence)
    )

    result = model_routing.shadow_route("Summarize this diff", context=material)

    assert result["outcome"]["verification"]["status"] == "PASS"
    assert result["candidate"]["evidence"] == quotes
    assert result["outcome"]["verification"]["grounding"] == {
        "grounded_items": 11,
        "total_items": 12,
    }


def test_shadow_fails_a_candidate_below_the_grounded_minimum(monkeypatch) -> None:
    # 4 grounded of 12. Not a fabrication problem — a sufficiency one. Discarding
    # the invented items would leave too little verified evidence to act on.
    material, quotes = _material(4)
    evidence = quotes + _invented(8)
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing, "_ollama_generate", lambda *a, **k: _candidate(evidence)
    )

    result = model_routing.shadow_route("Summarize this diff", context=material)
    outcome = result["outcome"]

    assert result["candidate"] is None
    assert outcome["verification"]["status"] == "FAIL"
    assert outcome["escalation_reason"] == "verification-failed"
    assert outcome["verification"]["grounding"] == {"grounded_items": 4, "total_items": 12}


def test_telemetry_counts_what_the_model_produced_not_what_survived(monkeypatch) -> None:
    # The verifier sanitizes; telemetry does not forget. `total_items` stays the
    # number the model generated, so a model degrading into fabrication is still
    # visible in the evidence store after the candidate passes.
    material, quotes = _material(6)
    evidence = quotes + _invented(9)
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        model_routing, "_ollama_generate", lambda *a, **k: _candidate(evidence)
    )

    result = model_routing.shadow_route("Summarize this diff", context=material)
    grounding = result["outcome"]["verification"]["grounding"]

    assert grounding["total_items"] == 15
    assert grounding["grounded_items"] == len(result["candidate"]["evidence"]) == 6


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


def _history_source(tmp_path) -> Path:
    """Three outcomes recorded oldest first, with one unparsable line between them."""
    first = {
        **model_routing._outcome(
            model_routing.inspect_route("Summarize this diff"),
            attempted=True,
            model_output_received=True,
            schema_valid=True,
            verification_status="PASS",
            verification_checks=["candidate-schema", "task-class-match"],
        ),
        "recorded_at": "2026-08-07T10:00:00Z",
    }
    second = {
        **model_routing._outcome(
            model_routing.inspect_route("Review README documentation"),
            attempted=False,
            verification_status="UNAVAILABLE",
            escalated=True,
            escalation_reason="model-unavailable",
        ),
        "recorded_at": "2026-08-07T11:00:00Z",
    }
    third = {
        **model_routing._outcome(
            model_routing.inspect_route("Summarize this diff"),
            attempted=True,
            model_output_received=True,
            verification_status="FAIL",
            escalated=True,
            escalation_reason="verification-failed",
        ),
        "recorded_at": "2026-08-07T12:00:00Z",
    }
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        "\n".join(
            (json.dumps(first), "not-json", json.dumps(second), json.dumps(third))
        )
        + "\n",
        encoding="utf-8",
    )
    return source


def test_history_returns_validated_outcomes_newest_first(tmp_path) -> None:
    history = model_routing.route_history(_history_source(tmp_path))

    assert history["schema"] == "mq.model-route-history.v1"
    assert history["total_records"] == 4
    assert history["valid_outcomes"] == 3
    assert history["invalid_records"] == 1
    assert [entry["recorded_at"] for entry in history["entries"]] == [
        "2026-08-07T12:00:00Z",
        "2026-08-07T11:00:00Z",
        "2026-08-07T10:00:00Z",
    ]
    assert history["entries"][0]["escalation_reason"] == "verification-failed"
    assert history["entries"][1]["verification"]["status"] == "UNAVAILABLE"


def test_history_entries_keep_the_stages_the_report_must_not_conflate(tmp_path) -> None:
    """attempted, answered, schema-valid and verified stay separable per decision."""
    history = model_routing.route_history(_history_source(tmp_path))

    failed = history["entries"][0]
    assert failed["attempted"] is True
    assert failed["model_output_received"] is True
    assert failed["schema_valid"] is False
    assert failed["verification"]["status"] == "FAIL"
    assert failed["accepted_by_agent"] is False


def test_history_filters_one_decision_for_explain(tmp_path) -> None:
    source = _history_source(tmp_path)
    target = model_routing.route_history(source)["entries"][1]["decision_id"]

    history = model_routing.route_history(source, decision_id=target)

    assert history["filters"] == {"decision_id": target, "task_class": None}
    assert history["matched"] == 1
    assert [entry["decision_id"] for entry in history["entries"]] == [target]


def test_history_filters_by_task_class(tmp_path) -> None:
    history = model_routing.route_history(_history_source(tmp_path), task_class="diff-summary")

    assert history["matched"] == 2
    assert {entry["task_class"] for entry in history["entries"]} == {"diff-summary"}


def test_history_limit_caps_entries_without_hiding_the_match_count(tmp_path) -> None:
    history = model_routing.route_history(_history_source(tmp_path), limit=1)

    assert history["matched"] == 3
    assert history["returned"] == 1
    assert len(history["entries"]) == 1


def test_history_of_a_missing_source_is_empty_not_an_error(tmp_path) -> None:
    history = model_routing.route_history(tmp_path / "missing.jsonl")

    assert history["total_records"] == 0
    assert history["matched"] == 0
    assert history["entries"] == []


def test_history_never_writes_to_its_source(tmp_path) -> None:
    source = _history_source(tmp_path)
    before = source.read_bytes()

    model_routing.route_history(source)

    assert source.read_bytes() == before


def test_history_cli_json_is_machine_readable_and_filterable(tmp_path) -> None:
    source = _history_source(tmp_path)
    result = runner.invoke(app, ["route", "history", "--source", str(source), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema"] == "mq.model-route-history.v1"
    assert payload["returned"] == 3

    target = payload["entries"][1]["decision_id"]
    filtered = runner.invoke(
        app,
        ["route", "history", "--source", str(source), "--decision-id", target, "--json"],
    )
    assert filtered.exit_code == 0
    assert json.loads(filtered.output)["matched"] == 1


def test_history_groups_every_run_of_a_repeated_decision(tmp_path) -> None:
    """decision_id is derived from task and agent, so one decision can hold many runs."""
    source = _history_source(tmp_path)
    repeated = model_routing.route_history(source, task_class="diff-summary")["entries"][0]

    history = model_routing.route_history(source, decision_id=repeated["decision_id"])

    assert history["matched"] == 2
    run_ids = {entry["run_id"] for entry in history["entries"]}
    assert len(run_ids) == 2


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


# --- both contracts, presented separately ---------------------------------


def _execution_record(
    task_class: str = "ci",
    result: str = "PASS",
    recorded_at: str = "2026-08-07T13:00:00Z",
    route: str | None = None,
    **metrics: Any,
) -> dict:
    from mq_agent.tools import execution_outcome

    record = execution_outcome.build_execution_outcome(
        runtime="swarm",
        task_class=task_class,
        result=result,
        exit_status="ok" if result == "PASS" else "error",
        latency_ms=metrics.pop("latency_ms", 1000),
        route=(
            {"selected": route, "policy": "static", "confidence": None}
            if route is not None
            else None
        ),
        context=metrics.pop("context", None),
        **metrics,
    )
    record["recorded_at"] = recorded_at
    return record


def _mixed_source(tmp_path: Path) -> Path:
    """One file holding both contracts plus a line belonging to neither."""
    source = tmp_path / "mixed.jsonl"
    route = model_routing._outcome(
        model_routing.inspect_route("Summarize this diff"),
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        verification_checks=["candidate-schema", "task-class-match"],
        accepted_by_agent=True,
    )
    source.write_text(
        "\n".join(
            (
                json.dumps(route),
                json.dumps(_execution_record()),
                json.dumps(_execution_record(task_class="audit", result="FAIL")),
                "not-json",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return source


# An execution record in the source is a valid record of a different contract,
# not a broken one. Counting it as invalid would make a healthy store look
# corrupt and hide real corruption behind the noise.
def test_report_does_not_call_an_execution_record_invalid(tmp_path) -> None:
    report = model_routing.route_report(_mixed_source(tmp_path))

    assert report["total_records"] == 4
    assert report["valid_outcomes"] == 1
    assert report["invalid_records"] == 1


# The two contracts measure different things: a route verification rate says
# whether a local model could be trusted, an execution result says whether a
# run worked. One number over both would mean neither.
def test_report_keeps_route_rates_free_of_execution_records(tmp_path) -> None:
    mixed = model_routing.route_report(_mixed_source(tmp_path))

    assert mixed["verified"] == 1
    assert mixed["attempted"] == 1
    assert mixed["by_task_class"]["diff-summary"]["verification_rate"] == 1.0
    assert set(mixed["by_task_class"]) == {"diff-summary"}


def test_report_presents_execution_outcomes_as_their_own_contract(tmp_path) -> None:
    report = model_routing.route_report(_mixed_source(tmp_path))
    execution = report["execution"]

    assert execution["schema"] == "mq.execution-outcome.v1"
    assert execution["outcomes"] == 2
    assert execution["by_result"] == {"PASS": 1, "FAIL": 1, "SKIPPED": 0}
    assert execution["by_task_class"]["ci"]["PASS"] == 1
    assert execution["by_task_class"]["audit"]["FAIL"] == 1


def test_report_groups_execution_outcomes_by_task_class_and_route(tmp_path) -> None:
    source = tmp_path / "executions.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                _execution_record(route="codex"),
                _execution_record(result="FAIL", route="claude"),
                _execution_record(task_class="audit"),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    by_task = model_routing.route_report(source)["execution"]["by_task_class"]

    assert by_task["ci"]["by_route"]["codex"]["PASS"] == 1
    assert by_task["ci"]["by_route"]["claude"]["FAIL"] == 1
    assert by_task["audit"]["by_route"]["unreported"]["outcomes"] == 1


def test_report_filters_both_contracts_by_supported_time_window(tmp_path) -> None:
    source = tmp_path / "mixed.jsonl"
    recent = _execution_record(recorded_at="2026-08-27T12:00:00Z")
    old = _execution_record(recorded_at="2026-07-01T12:00:00Z")
    source.write_text("\n".join(map(json.dumps, (recent, old))) + "\n", encoding="utf-8")

    report = model_routing.route_report(
        source, since="30d", now=datetime(2026, 8, 28, tzinfo=UTC)
    )

    assert report["window"] == "30d"
    assert report["execution"]["outcomes"] == 1


def test_execution_report_includes_route_metrics(tmp_path) -> None:
    source = tmp_path / "executions.jsonl"
    records = [
        _execution_record(
            route="codex", latency_ms=100, tool_calls=2, retries=1,
            context={"sources": ["repo-card"], "size": 1000},
        ),
        _execution_record(route="codex", latency_ms=300, tool_calls=4, fallbacks=1),
        _execution_record(route="codex", latency_ms=200, result="FAIL"),
    ]
    source.write_text("\n".join(map(json.dumps, records)) + "\n", encoding="utf-8")

    metrics = model_routing.route_report(source)["execution"]["by_task_class"]["ci"][
        "by_route"
    ]["codex"]

    assert metrics["success_rate"] == 0.667
    assert metrics["median_latency_ms"] == 200
    assert metrics["p90_latency_ms"] == 300
    assert metrics["tool_calls"] == 6
    assert metrics["retries"] == 1
    assert metrics["fallbacks"] == 1
    assert metrics["median_context_size"] == 1000


def _applied_observation(
    task: str = "Review the documentation",
    *,
    route: str = "local-shadow",
    application: str = "applied",
    recorded_at: str | None = None,
) -> dict:
    observation = model_routing._outcome(
        model_routing.inspect_route(task),
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        application=application,
        execution_run_id="exec-1",
    )
    observation["selected_route"] = route
    if recorded_at is not None:
        observation["recorded_at"] = recorded_at
    return observation


# Readiness reads routing observations grouped by the routing task class, not
# execution outcomes grouped by `audit`/`ci`/`docs` (ADR-010 D5). An audit can
# contain several unrelated routing decisions, so "does audit have two routes"
# had no answer; "does docs-review have two applied routes" does.
def test_route_readiness_reports_each_threshold_without_enabling_routing(tmp_path) -> None:
    source = tmp_path / "route-outcomes.jsonl"
    records = []
    for index in range(15):
        records.append(
            _applied_observation(
                route="local-shadow", recorded_at=f"2026-08-{index + 1:02d}T12:00:00Z"
            )
        )
        records.append(
            _applied_observation(
                route="cloud-required", recorded_at=f"2026-08-{index + 1:02d}T13:00:00Z"
            )
        )
    source.write_text("\n".join(map(json.dumps, records)) + "\n", encoding="utf-8")

    readiness = model_routing.route_readiness(source)
    docs = readiness["task_classes"]["docs-review"]

    assert docs["eligible"] is True
    assert docs["recommendation"] == "AWAITING_OPERATOR_APPROVAL"
    assert docs["actual"]["candidate_routes"] == 2
    assert readiness["automatic_routing_enabled"] is False
    # Evidence is not authorization. Applying a route needs an operator
    # allowlist and a safety check; telemetry alone never grants execution.
    assert readiness["grants_eligibility"] is False


def test_readiness_counts_applied_observations_only(tmp_path) -> None:
    source = tmp_path / "route-outcomes.jsonl"
    records = [
        _applied_observation(route="local-shadow", application="applied"),
        _applied_observation(route="cloud-required", application="shadow"),
        _applied_observation(route="cloud-required", application="advisory"),
    ]
    # An observation predating the `application` field: absent is not applied.
    unmarked = _applied_observation(route="cloud-required")
    del unmarked["application"]
    records.append(unmarked)
    source.write_text("\n".join(map(json.dumps, records)) + "\n", encoding="utf-8")

    readiness = model_routing.route_readiness(source)

    assert readiness["observations_considered"] == 1
    assert readiness["observations_ignored_not_applied"] == 3
    assert readiness["task_classes"]["docs-review"]["actual"]["candidate_routes"] == 1


def test_readiness_never_reads_the_execution_store(tmp_path, monkeypatch) -> None:
    # D6: `execution.route` is not routing truth, and readiness must not fall
    # back to it — that is the layer confusion this whole change removes.
    executions = tmp_path / "executions.jsonl"
    executions.write_text(
        json.dumps(_execution_record(route="codex")) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(executions))
    source = tmp_path / "route-outcomes.jsonl"
    source.write_text(json.dumps(_applied_observation()) + "\n", encoding="utf-8")

    readiness = model_routing.route_readiness(source)

    assert set(readiness["task_classes"]) == {"docs-review"}
    assert "ci" not in readiness["task_classes"]


def test_execution_compare_never_recommends_a_winner(tmp_path) -> None:
    source = tmp_path / "executions.jsonl"
    source.write_text(
        "\n".join(
            map(
                json.dumps,
                (_execution_record(route="codex"), _execution_record(route="claude")),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    comparison = model_routing.execution_compare("ci", "codex", "claude", source)

    assert comparison["comparable"] is True
    assert comparison["recommendation"] is None
    assert set(comparison["routes"]) == {"codex", "claude"}


def test_execution_report_and_compare_cli_are_machine_readable(tmp_path) -> None:
    source = tmp_path / "executions.jsonl"
    source.write_text(
        "\n".join(
            map(
                json.dumps,
                (_execution_record(route="codex"), _execution_record(route="claude")),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    report = runner.invoke(app, ["execution", "report", "--source", str(source), "--json"])
    compare = runner.invoke(
        app,
        [
            "execution",
            "compare",
            "--task-class",
            "ci",
            "--left",
            "codex",
            "--right",
            "claude",
            "--source",
            str(source),
            "--json",
        ],
    )

    assert report.exit_code == 0
    assert json.loads(report.output)["schema"] == "mq.execution-report.v1"
    assert compare.exit_code == 0
    assert json.loads(compare.output)["comparable"] is True


# Scoring is a later phase. Counts are evidence; a rate is a judgement, and
# emitting one here would invite exactly the merged number this split avoids.
def test_report_does_not_score_execution_outcomes(tmp_path) -> None:
    execution = model_routing.route_report(_mixed_source(tmp_path))["execution"]

    assert not [key for key in execution if key.endswith("_rate")]


def test_history_keeps_execution_entries_in_their_own_list(tmp_path) -> None:
    history = model_routing.route_history(_mixed_source(tmp_path))

    assert [entry["schema"] for entry in history["entries"]] == [
        "mq.model-route-outcome.v1"
    ]
    assert len(history["execution"]["entries"]) == 2
    assert history["execution"]["matched"] == 2


# A decision id names one routing decision. No execution record carries one, so
# filtering by it must empty the execution list rather than ignore the filter.
def test_history_decision_filter_excludes_execution_entries(tmp_path) -> None:
    source = _mixed_source(tmp_path)
    decision_id = model_routing.route_history(source)["entries"][0]["decision_id"]

    history = model_routing.route_history(source, decision_id=decision_id)

    assert len(history["entries"]) == 1
    assert history["execution"]["entries"] == []


def test_history_task_class_filter_applies_to_each_contract_separately(tmp_path) -> None:
    history = model_routing.route_history(_mixed_source(tmp_path), task_class="ci")

    assert history["entries"] == []
    assert [e["task_class"] for e in history["execution"]["entries"]] == ["ci"]


def test_history_orders_execution_entries_newest_first(tmp_path) -> None:
    source = tmp_path / "execution.jsonl"
    source.write_text(
        "\n".join(
            (
                json.dumps(_execution_record(recorded_at="2026-08-07T10:00:00Z")),
                json.dumps(_execution_record(recorded_at="2026-08-07T12:00:00Z")),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    entries = model_routing.route_history(source)["execution"]["entries"]

    assert [e["recorded_at"] for e in entries] == [
        "2026-08-07T12:00:00Z",
        "2026-08-07T10:00:00Z",
    ]


# Without an explicit source the two stores are separate files, and each
# contract is read from its own.
def test_each_contract_falls_back_to_its_own_default_store(tmp_path, monkeypatch) -> None:
    route_store = tmp_path / "route-outcomes.jsonl"
    execution_store = tmp_path / "execution-outcomes.jsonl"
    route_store.write_text("", encoding="utf-8")
    execution_store.write_text(json.dumps(_execution_record()) + "\n", encoding="utf-8")
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(route_store))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(execution_store))

    report = model_routing.route_report()

    assert report["source"] == str(route_store)
    assert report["valid_outcomes"] == 0
    assert report["execution"]["source"] == str(execution_store)
    assert report["execution"]["outcomes"] == 1


def test_a_missing_execution_store_is_empty_not_an_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(tmp_path / "nope.jsonl"))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "also-nope.jsonl"))

    report = model_routing.route_report()

    assert report["execution"]["outcomes"] == 0
    assert model_routing.route_history()["execution"]["entries"] == []


def test_report_cli_shows_both_contracts_without_merging_them(tmp_path) -> None:
    result = runner.invoke(app, ["route", "report", "--source", str(_mixed_source(tmp_path))])

    assert result.exit_code == 0
    assert "Model Route Report" in result.output
    assert "Execution Outcomes" in result.output


def test_report_cli_shows_execution_route_groups(tmp_path) -> None:
    source = tmp_path / "execution.jsonl"
    source.write_text(json.dumps(_execution_record(route="codex")) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["route", "report", "--source", str(source)])

    assert result.exit_code == 0
    assert "Route" in result.output
    assert "codex" in result.output


def test_history_cli_shows_execution_entries_in_their_own_table(tmp_path) -> None:
    result = runner.invoke(app, ["route", "history", "--source", str(_mixed_source(tmp_path))])

    assert result.exit_code == 0
    assert "Model Route History" in result.output
    assert "Execution Outcomes" in result.output
# ── grounding detail ─────────────────────────────────────────────────────────
#
# A binary verdict made the 0.434 verification rate uninterpretable: it could
# not distinguish a model inventing citations from one paraphrasing a single
# item out of five. Every failure discarded the partial result, so 130 stored
# outcomes could not be diagnosed after the fact.


def _grounded_outcome(task_class: str, status: str, grounded, total) -> dict:
    decision = model_routing.inspect_route("Summarize this git diff")
    decision["task_class"] = task_class
    return model_routing._outcome(
        decision,
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status=status,
        verification_checks=["candidate-schema", "task-class-match"]
        + (["evidence-grounded"] if status == "PASS" else []),
        escalated=status != "PASS",
        escalation_reason=None if status == "PASS" else "verification-failed",
        grounding=(grounded, total) if grounded is not None else None,
    )


def test_evidence_grounding_reports_counts() -> None:
    context = "The producer's validator could not see it. The consumer caught it."
    assert model_routing.evidence_grounding(
        ["The producer's validator could not see it.", "a paraphrase nobody wrote"],
        context,
    ) == (1, 2)


def test_empty_evidence_is_zero_of_zero() -> None:
    assert model_routing.evidence_grounding([], "anything") == (0, 0)


def test_short_quotes_do_not_count_as_grounded() -> None:
    # Below _MIN_QUOTE_LENGTH: matches too much of any material to be a citation.
    assert model_routing.evidence_grounding(["the"], "the quick brown fox") == (0, 1)


def test_outcome_carries_grounding_when_measured() -> None:
    outcome = _grounded_outcome("diff-summary", "FAIL", 3, 5)

    assert outcome["verification"]["grounding"] == {
        "grounded_items": 3,
        "total_items": 5,
    }
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(outcome)


def test_grounding_is_optional_so_stored_outcomes_stay_valid() -> None:
    """The 130 existing records predate this field and must stay valid."""
    outcome = model_routing._outcome(model_routing.inspect_route("Summarize this git diff"))

    assert "grounding" not in outcome["verification"]
    Draft202012Validator(_schema("model_route_outcome.schema.json")).validate(outcome)


def test_review_reports_item_level_rate_beside_the_answer_rate(tmp_path) -> None:
    records = [
        _grounded_outcome("diff-summary", "FAIL", 3, 5),
        _grounded_outcome("diff-summary", "FAIL", 4, 5),
        _grounded_outcome("diff-summary", "PASS", 5, 5),
    ]
    source = tmp_path / "outcomes.jsonl"
    source.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    review = model_routing.review_route_evidence("diff-summary", source)

    # 1 of 3 answers accepted, but 12 of 15 citations were verbatim.
    assert review["verification_success_rate"] == 0.333
    assert review["grounded_items"] == 12
    assert review["grounding_items_measured"] == 15
    assert review["grounding_item_rate"] == 0.8
    Draft202012Validator(_schema("model_route_evidence_review.schema.json")).validate(review)


def test_item_rate_is_null_when_nothing_measured_it(tmp_path) -> None:
    source = tmp_path / "outcomes.jsonl"
    source.write_text(
        json.dumps(_grounded_outcome("diff-summary", "PASS", None, None)), encoding="utf-8"
    )

    review = model_routing.review_route_evidence("diff-summary", source)

    # 0.0 would read as "nothing was grounded" rather than "nothing measured it".
    assert review["grounding_item_rate"] is None
    assert review["grounding_items_measured"] == 0
