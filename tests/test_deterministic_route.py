"""The second applied route: local execution with no model inference.

Two things these tests defend, and they pull in opposite directions:

1. The route stays dumb. The moment it ranks, scores, or judges, it stops being
   a control group and becomes a second review engine, and the comparison it
   exists to make means nothing.
2. The route earns its record anyway. Grounding by construction is not a reason
   to skip verification — it is the reason the verification must be the same
   one, so the two routes' records can be compared at all.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq_agent.core.state import SafetyMode
from mq_agent.tools import applied_routing, deterministic_route, model_routing

DOCS_TASK = "Review the repository documentation for gaps"

MATERIAL = "\n".join(
    [
        "README.md documents installation but not configuration",
        "CHANGELOG.md stops at version 0.4.0",
        "docs/architecture.md was last touched in March",
        "no docstring on the public entry point",
        "the /docs folder holds six files, two of them empty",
        "tests reference a wiki page that no longer exists",
    ]
)


def _candidate(material: str) -> dict:
    """The extracted candidate, asserted present.

    Narrowing here rather than at every call site: a None slipping through would
    otherwise fail as an unrelated TypeError several lines later.
    """
    candidate = deterministic_route.deterministic_candidate("docs-review", material)
    assert candidate is not None
    return candidate


def _apply(context: str | None, route: str = "deterministic-local") -> dict:
    return applied_routing.apply_route(
        DOCS_TASK,
        execution_run_id="exec-1",
        safety_mode=SafetyMode.READ_ONLY,
        route=route,
        context=context,
    )


def test_the_extractor_quotes_the_material_in_the_order_it_found_it() -> None:
    candidate = _candidate(MATERIAL)

    assert candidate["evidence"] == MATERIAL.splitlines()[: deterministic_route.EVIDENCE_ITEMS]


def test_the_extractor_makes_no_judgement() -> None:
    # No ranking, no selection by importance, no invented advice. A suggestion
    # would require judgement, which is the thing this route deliberately lacks.
    candidate = _candidate(MATERIAL)

    assert candidate["suggestions"] == []
    assert "no inference" in candidate["summary"].lower()


def test_short_lines_are_skipped_before_the_verifier_would_drop_them() -> None:
    # A line under the grounding floor would be extracted, counted as evidence,
    # then discarded by the verifier — the route failing on its own baseline.
    # Same rule as the model route, applied before rather than after.
    material = "\n".join(["ok", "x", *MATERIAL.splitlines()])

    candidate = _candidate(material)

    assert "ok" not in candidate["evidence"]
    assert "x" not in candidate["evidence"]


def test_repeated_lines_are_quoted_once() -> None:
    lines = MATERIAL.splitlines()
    material = "\n".join([lines[0], lines[0], *lines[1:]])

    candidate = _candidate(material)

    assert len(candidate["evidence"]) == len(set(candidate["evidence"]))


def test_too_little_material_fails_rather_than_padding() -> None:
    # Reaching five by inventing filler would be exactly the fabrication the
    # verifier exists to catch, committed by the baseline instead of the model.
    thin = "\n".join(MATERIAL.splitlines()[:3])

    assert deterministic_route.deterministic_candidate("docs-review", thin) is None


def test_the_item_count_is_the_verifier_floor_not_a_chosen_number() -> None:
    assert deterministic_route.EVIDENCE_ITEMS == model_routing._MIN_GROUNDED_EVIDENCE


def test_an_applied_deterministic_route_records_a_strategy_and_no_model() -> None:
    result = _apply(MATERIAL)
    outcome = result["outcome"]

    assert outcome["selected_route"] == "deterministic-local"
    # ADR-010 D8: the route is the strategy, `local_model` is the model, and a
    # strategy that runs none has none. Not "deterministic", not "none".
    assert outcome["local_model"] is None
    assert outcome["application"] == "applied"
    assert outcome["execution_run_id"] == "exec-1"
    assert outcome["verification"]["status"] == "PASS"
    assert outcome["model_output_received"] is False
    assert result["candidate"]["evidence"]


def test_the_applied_route_may_differ_from_the_recommended_one() -> None:
    # The first time these two fields can disagree. Both facts stay on the
    # record: the policy advised one strategy, the operator applied another.
    result = _apply(MATERIAL)

    assert result["decision"]["recommended_route"] == "local-shadow"
    assert result["outcome"]["selected_route"] == "deterministic-local"


def test_the_deterministic_route_is_verified_like_any_other() -> None:
    result = _apply(MATERIAL)
    verification = result["outcome"]["verification"]

    assert "evidence-grounded" in verification["checks"]
    assert verification["grounding"] == {
        "grounded_items": deterministic_route.EVIDENCE_ITEMS,
        "total_items": deterministic_route.EVIDENCE_ITEMS,
    }


def test_a_route_with_nothing_to_quote_fails() -> None:
    result = _apply("\n".join(["short", "tiny"]))
    outcome = result["outcome"]

    assert result["candidate"] is None
    assert outcome["verification"]["status"] == "FAIL"
    assert outcome["escalation_reason"] == "verification-failed"
    # It ran and it failed. A route that governed a decision badly still
    # governed it — that is what makes the failure evidence.
    assert outcome["application"] == "applied"


def test_a_route_with_no_material_cannot_be_verified() -> None:
    result = _apply(None)

    assert result["candidate"] is None
    assert result["outcome"]["verification"]["status"] == "FAIL"


def test_an_unauthorized_pair_names_the_route_it_refused() -> None:
    # Recording the refusal against `local-shadow` would blame a route that
    # never asked to run, and would put a false applied-route fact in the store.
    result = _apply(MATERIAL, route="some-future-strategy")
    outcome = result["outcome"]

    assert outcome["application"] == "advisory"
    assert outcome["escalation_reason"] == "operator-required"
    assert outcome["selected_route"] == "local-shadow"


def test_the_record_validates_against_the_canonical_contract() -> None:
    from mq_agent.tools.model_routing import _validator

    result = _apply(MATERIAL, route="deterministic-local")
    _validator("model_route_outcome.schema.json").validate(result["outcome"])


def test_both_routes_read_the_same_material() -> None:
    """A failed step's result is an error string, not something the audit saw.

    Comparing two strategies on different material would not be comparing them.
    """
    from mq_agent.agents.docs_agent import DocsAgent

    steps: list[dict] = [
        {"description": "a", "status": "success", "result": "the README documents install"},
        {"description": "b", "status": "failed", "result": "PermissionError: /etc/shadow"},
        {"description": "c", "status": "skipped", "result": None},
    ]

    material = DocsAgent._evidence_material(steps)

    assert "the README documents install" in material
    assert "PermissionError" not in material


def test_two_applied_routes_make_two_candidate_routes(tmp_path, monkeypatch) -> None:
    """The point of the whole exercise, from records the routes actually wrote."""
    store = tmp_path / "route-outcomes.jsonl"
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(store))

    deterministic = _apply(MATERIAL)["outcome"]
    model_shaped = model_routing._outcome(
        model_routing.inspect_route(DOCS_TASK),
        attempted=True,
        model_output_received=True,
        schema_valid=True,
        verification_status="PASS",
        application="applied",
        execution_run_id="exec-1",
    )
    for outcome in (deterministic, model_shaped):
        model_routing.record_route_outcome(outcome)

    readiness = model_routing.route_readiness(store)
    docs = readiness["task_classes"]["docs-review"]

    assert docs["actual"]["candidate_routes"] == 2
    assert docs["routes"] == {"local-shadow": 1, "deterministic-local": 1}
    # Two routes is not readiness. The other gates stay shut and say so.
    assert docs["eligible"] is False


@pytest.mark.parametrize("route", ["local-shadow", "deterministic-local"])
def test_no_route_is_exempt_from_the_allowlist(route, monkeypatch) -> None:
    monkeypatch.setattr(applied_routing, "APPLIED_ROUTE_ALLOWLIST", frozenset())

    outcome = _apply(MATERIAL, route=route)["outcome"]

    assert outcome["application"] == "advisory"
    assert outcome["escalation_reason"] == "operator-required"


def test_verification_status_is_not_documented_as_a_quality_measure() -> None:
    """The sentence that stops a design error later.

    `deterministic-local` grounds by construction, so it wins the verification
    gate without being better at the job. Whatever eventually chooses between
    the routes has to measure utility instead.
    """
    source = Path(deterministic_route.__file__).read_text(encoding="utf-8")

    assert "MUST NOT be read as comparative route quality" in source


def test_the_extractor_does_not_score_or_rank() -> None:
    """Absence, asserted. The failure mode is someone adding cleverness later."""
    import ast

    tree = ast.parse(Path(deterministic_route.__file__).read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not {"sorted", "max", "min"} & called
    assert "sort" not in attributes


def test_the_candidate_shape_matches_what_a_model_would_produce() -> None:
    candidate = _candidate(MATERIAL)

    assert model_routing._candidate_is_valid(candidate, "docs-review")
    assert json.loads(json.dumps(candidate)) == candidate
