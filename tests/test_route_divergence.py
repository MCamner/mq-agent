"""A comparison that cannot be made must say so, not return a small number.

The failure this module guards against is a report that looks confident on
three observations, or that folds a clean refusal and a weakly grounded answer
into one figure. Both are ways of manufacturing a verdict out of nothing.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from mq_agent.tools import route_divergence as divergence_module
from mq_agent.tools.analysis_cohort import current_era
from mq_agent.tools.route_divergence import (
    MINIMUM_ROUTES,
    MINIMUM_SAMPLES_PER_ROUTE,
    route_divergence,
)

ERA_C_START = current_era().starts_at


def _observation(
    route: str,
    *,
    day: int = 5,
    status: str = "PASS",
    escalated: bool = False,
    escalation_reason: str | None = None,
    grounding: tuple[int, int] | None = None,
    responded: bool = True,
    task_class: str = "docs-review",
) -> dict:
    verification: dict = {"status": status, "checks": []}
    if grounding is not None:
        verification["grounding"] = {
            "grounded_items": grounding[0],
            "total_items": grounding[1],
        }
    return {
        "schema": "mq.model-route-outcome.v1",
        "decision_id": "d" * 16,
        "run_id": f"{route}-{day}-{status}-{escalated}-{grounding}",
        "task_class": task_class,
        "selected_route": route,
        "local_model": None if route == "deterministic-local" else "qwen",
        "authoritative_agent": "claude",
        "attempted": True,
        "model_output_received": responded,
        "schema_valid": True,
        "verification": verification,
        "accepted_by_agent": False,
        "accepted_by_operator": False,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
        "application": "applied",
        "recorded_at": ERA_C_START.replace(day=ERA_C_START.day)
        .replace(microsecond=day)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _every_key(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for item in value.values() for key in _every_key(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in _every_key(item)}
    return set()


def _store(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "route-outcomes.jsonl"
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    return path


def _enough(route: str, **changes) -> list[dict]:
    return [
        _observation(route, day=index, **changes)
        for index in range(MINIMUM_SAMPLES_PER_ROUTE)
    ]


def test_a_small_population_reports_that_it_cannot_compare(tmp_path) -> None:
    store = _store(tmp_path, [_observation("local-shadow"), _observation("deterministic-local")])

    report = route_divergence(store)

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["divergence"] == []
    assert report["comparable_routes"] == []


def test_insufficiency_names_the_route_and_the_count(tmp_path) -> None:
    # "Not enough data" is useless; "deterministic-local has 3, needs 10" is
    # something an operator can act on.
    store = _store(tmp_path, _enough("local-shadow") + [_observation("deterministic-local")] * 3)

    report = route_divergence(store)

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    reasons = " ".join(report["insufficient_reasons"])
    assert "deterministic-local" in reasons
    assert str(MINIMUM_SAMPLES_PER_ROUTE) in reasons
    assert "local-shadow" not in reasons


def test_one_route_alone_is_not_a_comparison(tmp_path) -> None:
    store = _store(tmp_path, _enough("local-shadow"))

    report = route_divergence(store)

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert str(MINIMUM_ROUTES) in " ".join(report["insufficient_reasons"])


def test_the_counts_are_reported_even_when_no_comparison_is_made(tmp_path) -> None:
    # A refusal to conclude must still show its working, or the report is
    # indistinguishable from an empty store.
    store = _store(tmp_path, [_observation("local-shadow")] * 3)

    report = route_divergence(store)

    assert report["routes"]["local-shadow"]["observations"] == 3
    assert report["cohort"]["included"] == 3


def test_execution_and_evidence_divergence_stay_separate(tmp_path) -> None:
    store = _store(
        tmp_path,
        _enough("local-shadow", grounding=(8, 10))
        + _enough("deterministic-local", responded=False, grounding=(5, 5)),
    )

    report = route_divergence(store)
    pair = report["divergence"][0]

    assert report["status"] == "OK"
    assert set(pair["execution"]) == {
        "verification_pass_rate",
        "escalation_rate",
        "model_output_rate",
    }
    assert set(pair["evidence"]) == {"grounding_ratio", "grounded_items_per_observation"}
    assert pair["evidence"]["grounding_ratio"]["local-shadow"] == 0.8
    assert pair["evidence"]["grounding_ratio"]["deterministic-local"] == 1.0


def test_no_scalar_score_and_no_promotion(tmp_path) -> None:
    """The invariant the whole module exists to hold.

    If a single figure ever appears here, someone has decided in private how a
    refused execution trades against a weak citation.
    """
    store = _store(
        tmp_path,
        _enough("local-shadow", grounding=(8, 10))
        + _enough("deterministic-local", grounding=(5, 5)),
    )

    report = route_divergence(store)

    assert report["grants_promotion"] is False
    assert report["recommends_route"] is None
    keys = _every_key(report)
    for forbidden in ("score", "winner", "better", "rank", "recommended_route"):
        # Substring, not equality: `quality_score` is the exact field this
        # invariant exists to keep out, and it would pass an equality check.
        assert not [key for key in keys if forbidden in key], forbidden


def test_a_structural_difference_is_reported_not_judged(tmp_path) -> None:
    # deterministic-local runs no model, so its model_output_rate is 0 by
    # design. It shows up as divergence because it is divergence.
    store = _store(
        tmp_path,
        _enough("local-shadow", responded=True)
        + _enough("deterministic-local", responded=False),
    )

    pair = route_divergence(store)["divergence"][0]

    assert pair["execution"]["model_output_rate"]["deterministic-local"] == 0.0
    assert pair["execution"]["model_output_rate"]["local-shadow"] == 1.0
    assert pair["execution"]["model_output_rate"]["delta"] is not None


def test_unmeasured_grounding_is_not_counted_as_zero(tmp_path) -> None:
    # Absent means unmeasured. Averaging a missing measurement in as 0.0 would
    # invent a bad result out of a run that never reached verification.
    store = _store(
        tmp_path,
        _enough("local-shadow", status="SKIPPED", grounding=None)
        + _enough("deterministic-local", grounding=(5, 5)),
    )

    report = route_divergence(store)
    shadow = report["routes"]["local-shadow"]["evidence"]

    assert shadow["measured"] == 0
    assert shadow["unmeasured"] == MINIMUM_SAMPLES_PER_ROUTE
    assert shadow["grounding_ratio"] is None
    assert shadow["grounded_items"] is None


def test_a_delta_against_an_unmeasured_side_is_unknown(tmp_path) -> None:
    store = _store(
        tmp_path,
        _enough("local-shadow", status="SKIPPED", grounding=None)
        + _enough("deterministic-local", grounding=(5, 5)),
    )

    pair = route_divergence(store)["divergence"][0]

    assert pair["evidence"]["grounding_ratio"]["delta"] is None
    assert pair["execution"]["verification_pass_rate"]["delta"] is not None


def test_escalation_reasons_are_kept_apart_not_totalled(tmp_path) -> None:
    # context-truncated and verification-failed are different failures.
    store = _store(
        tmp_path,
        [
            _observation(
                "local-shadow",
                day=index,
                status="FAIL",
                escalated=True,
                escalation_reason=reason,
            )
            for index, reason in enumerate(
                ["context-truncated", "context-truncated", "verification-failed"]
            )
        ],
    )

    reasons = route_divergence(store)["routes"]["local-shadow"]["execution"][
        "escalation_reasons"
    ]

    assert reasons == {"context-truncated": 2, "verification-failed": 1}


def test_an_earlier_era_cannot_enter_the_comparison(tmp_path) -> None:
    old = _observation("local-shadow")
    old["recorded_at"] = "2026-09-01T00:38:28.638976Z"
    store = _store(tmp_path, [old])

    report = route_divergence(store)

    assert report["routes"] == {}
    assert report["cohort"]["excluded_earlier_era"] == 1


def test_an_advisory_observation_is_not_applied_behaviour(tmp_path) -> None:
    advisory = _observation("local-shadow")
    advisory["application"] = "advisory"
    store = _store(tmp_path, [advisory])

    report = route_divergence(store)

    assert report["routes"] == {}
    assert report["cohort"]["excluded_not_applied"] == 1


def test_a_task_class_filter_reports_what_it_removed(tmp_path) -> None:
    store = _store(
        tmp_path,
        _enough("local-shadow") + [_observation("local-shadow", task_class="diff-summary")],
    )

    report = route_divergence(store, task_class="docs-review")

    assert report["cohort"]["excluded_other_task_class"] == 1
    assert report["routes"]["local-shadow"]["observations"] == MINIMUM_SAMPLES_PER_ROUTE


def test_an_unknown_era_is_refused(tmp_path) -> None:
    with pytest.raises(ValueError):
        route_divergence(_store(tmp_path, []), era="whatever-we-ship-next")


def test_a_missing_store_still_returns_a_report(tmp_path) -> None:
    report = route_divergence(tmp_path / "absent.jsonl")

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["routes"] == {}


def test_the_minimum_is_not_borrowed_from_readiness() -> None:
    """The two gates answer different questions and must move independently.

    Importing `READINESS_THRESHOLDS` here would make a change to the readiness
    calibration silently redefine what counts as comparable.
    """
    tree = ast.parse(Path(divergence_module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "READINESS_THRESHOLDS" not in imported
    assert "route_readiness" not in imported


def test_readiness_is_unaffected_by_the_divergence_gate() -> None:
    from mq_agent.tools.model_routing import READINESS_THRESHOLDS

    # They agree today by calibration, not derivation.
    assert READINESS_THRESHOLDS["minimum_samples_per_route"] == MINIMUM_SAMPLES_PER_ROUTE
