"""How two routes differ, reported at two levels and never as one number.

A single "route quality score" would have to decide, silently, how much a
refused execution weighs against a weakly grounded answer. There is no honest
exchange rate between those, so this module never invents one. It reports:

    execution divergence   did the routes finish, refuse, or escalate
                           differently — a question about integrity.

    evidence divergence    did they ground different proportions of what they
                           cited — a question about answer quality.

Both are differences of rates, presented side by side with the counts they came
from. Nothing here ranks the routes, and nothing here promotes one.

**Natural mode.** The routes are compared as they were actually used, not by
forcing both to run on every decision. Paired comparison needs an identity that
proves two observations describe the same decision material, and `decision_id`
currently hashes only agent and task, so every docs-review shares one. That
identity question is real, but it is not needed to report what the routes did,
and changing the contract before a paired consumer exists would be building
ahead of the need.

**Structural differences are described, not judged.** `deterministic-local`
runs no model, so it will always show a `model_output_rate` of 0. That is the
strategy working as designed, and it appears here as divergence because it is
divergence. Reading it as a defect is a reader error this module cannot prevent
— which is another reason it refuses to collapse these numbers into a verdict.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mq_agent.tools.analysis_cohort import Era, era_named, select_cohort

#: Below this, a route's numbers are noise dressed as a rate.
#:
#: Deliberately not imported from `READINESS_THRESHOLDS`, which carries the
#: same number. Readiness asks whether a system has applied two routes often
#: enough to be reviewed; this asks whether a sample is large enough to compare.
#: They agree today by coincidence of calibration, not by derivation, and must
#: be free to move apart without one silently dragging the other.
MINIMUM_SAMPLES_PER_ROUTE = 10

#: A comparison needs two things to compare.
MINIMUM_ROUTES = 2


def _rate(part: int, whole: int) -> float | None:
    """None when there is nothing to divide by. A rate over zero is not zero."""
    return round(part / whole, 3) if whole else None


def _route_summary(records: list[Any]) -> dict[str, Any]:
    verification = {"PASS": 0, "FAIL": 0, "SKIPPED": 0}
    escalation_reasons: dict[str, int] = {}
    attempted = responded = schema_valid = escalated = 0
    measured = grounded_items = total_items = 0

    for record in records:
        attempted += int(bool(record.get("attempted")))
        responded += int(bool(record.get("model_output_received")))
        schema_valid += int(bool(record.get("schema_valid")))
        status = str(record.get("verification", {}).get("status", "SKIPPED"))
        verification[status] = verification.get(status, 0) + 1
        if record.get("escalated"):
            escalated += 1
            reason = record.get("escalation_reason") or "unrecorded"
            escalation_reasons[str(reason)] = escalation_reasons.get(str(reason), 0) + 1
        grounding = record.get("verification", {}).get("grounding")
        if isinstance(grounding, dict):
            measured += 1
            grounded_items += int(grounding.get("grounded_items", 0))
            total_items += int(grounding.get("total_items", 0))

    observations = len(records)
    return {
        "observations": observations,
        "sufficient": observations >= MINIMUM_SAMPLES_PER_ROUTE,
        "execution": {
            "attempted": attempted,
            "model_output_received": responded,
            "schema_valid": schema_valid,
            "verification": verification,
            "escalated": escalated,
            "escalation_reasons": escalation_reasons,
            "verification_pass_rate": _rate(verification["PASS"], observations),
            "escalation_rate": _rate(escalated, observations),
            "model_output_rate": _rate(responded, observations),
        },
        "evidence": {
            # Absent grounding is unmeasured, never zero — an observation that
            # never reached verification did not ground nothing, it grounded
            # nothing measurable, and averaging it in as 0.0 would invent data.
            "measured": measured,
            "unmeasured": observations - measured,
            "grounded_items": grounded_items if measured else None,
            "total_items": total_items if measured else None,
            "grounding_ratio": _rate(grounded_items, total_items),
            "grounded_items_per_observation": (
                round(grounded_items / measured, 3) if measured else None
            ),
        },
    }


def _delta(left: float | None, right: float | None) -> float | None:
    """None when either side was not measured. Unknown minus known is unknown."""
    if left is None or right is None:
        return None
    return round(left - right, 3)


def _pair(name_a: str, summary_a: dict, name_b: str, summary_b: dict) -> dict[str, Any]:
    def compare(level: str, field: str) -> dict[str, Any]:
        left, right = summary_a[level][field], summary_b[level][field]
        return {name_a: left, name_b: right, "delta": _delta(left, right)}

    return {
        "routes": [name_a, name_b],
        # Two levels, never summed. A route that refuses cleanly and a route
        # that answers with weak grounding fail differently.
        "execution": {
            field: compare("execution", field)
            for field in ("verification_pass_rate", "escalation_rate", "model_output_rate")
        },
        "evidence": {
            field: compare("evidence", field)
            for field in ("grounding_ratio", "grounded_items_per_observation")
        },
    }


def route_divergence(
    source: Path | None = None,
    *,
    era: str | None = None,
    task_class: str | None = None,
) -> dict[str, Any]:
    """Compare the applied routes within one era, read-only.

    Returns a report in every case. Too little evidence is a reported state
    with the counts that produced it, not an empty result or an exception —
    "we cannot say yet" is the answer, and it has to be visible.
    """
    from mq_agent.tools.model_routing import _outcome_path, _read_records, _split_contracts

    path = _outcome_path(source)
    records, _ = _read_records(path)
    observations, _, invalid = _split_contracts(records)
    chosen: Era | None = era_named(era) if era else None
    cohort = select_cohort(observations, era=chosen, task_class=task_class)

    by_route: dict[str, list[Any]] = {}
    for record in cohort.included:
        route = record.get("selected_route")
        if route:
            by_route.setdefault(str(route), []).append(record)

    routes = {name: _route_summary(items) for name, items in sorted(by_route.items())}
    comparable = sorted(name for name, item in routes.items() if item["sufficient"])

    reasons: list[str] = []
    if len(routes) < MINIMUM_ROUTES:
        reasons.append(
            f"{len(routes)} route(s) observed in this era; a comparison needs "
            f"{MINIMUM_ROUTES}"
        )
    for name in sorted(set(routes) - set(comparable)):
        reasons.append(
            f"{name} has {routes[name]['observations']} observation(s); "
            f"{MINIMUM_SAMPLES_PER_ROUTE} needed to compare"
        )
    if len(comparable) < MINIMUM_ROUTES and not reasons:
        reasons.append("not enough routes reach the minimum sample size")

    pairs = [
        _pair(comparable[i], routes[comparable[i]], comparable[j], routes[comparable[j]])
        for i in range(len(comparable))
        for j in range(i + 1, len(comparable))
    ]

    return {
        "schema": "mq.route-divergence.v1",
        "source": str(path),
        "mode": "natural",
        "era": {
            "name": cohort.era.name,
            "commit": cohort.era.commit,
            "starts_at": cohort.era.starts_at.isoformat(),
            "why": cohort.era.why,
        },
        "task_class": task_class,
        "invalid_records": invalid,
        "cohort": {
            "included": len(cohort.included),
            "excluded": cohort.excluded,
            "excluded_earlier_era": cohort.excluded_earlier_era,
            "excluded_not_applied": cohort.excluded_not_applied,
            "excluded_other_task_class": cohort.excluded_other_task_class,
            "excluded_undated": cohort.excluded_undated,
        },
        "minimum_samples_per_route": MINIMUM_SAMPLES_PER_ROUTE,
        "status": "OK" if pairs else "INSUFFICIENT_EVIDENCE",
        "insufficient_reasons": reasons,
        "routes": routes,
        "comparable_routes": comparable,
        "divergence": pairs,
        # This report describes what two routes did. It does not rank them,
        # score them, or authorize a change of route.
        "grants_promotion": False,
        "recommends_route": None,
    }
