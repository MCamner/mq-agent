"""A quality comparison must not silently include a superseded runtime.

Five applied observations exist in the real store, all written on 2026-09-01,
all before both `d34e1dd` (context integrity) and `7fe49bf` (material
selection). Their grounding numbers measure truncation, not route behaviour.
Nothing stops an aggregate from averaging them together with today's route
except this module — so these tests are the enforcement, not documentation.
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mq_agent.tools import analysis_cohort, model_routing
from mq_agent.tools.analysis_cohort import (
    ERAS,
    Era,
    current_era,
    era_named,
    select_cohort,
)

ERA_C1 = "material-selection"
ERA_C2 = "plan-validation"
ERA_C3 = "plan-composition"
ERA_C4 = "secret-safe-discovery"


def _observation(recorded_at: str, **changes) -> dict:
    record = {
        "schema": "mq.model-route-outcome.v1",
        "task_class": "docs-review",
        "selected_route": "local-shadow",
        "application": "applied",
        "recorded_at": recorded_at,
    }
    record.update(changes)
    return record


#: The five real applied observations, by timestamp. All era A.
HISTORICAL = [
    _observation("2026-09-01T00:38:28.638976Z", selected_route="local-shadow"),
    _observation("2026-09-01T00:39:12.344062Z", selected_route="local-shadow"),
    _observation("2026-09-01T00:39:20.467992Z", selected_route="deterministic-local"),
    _observation("2026-09-01T00:39:28.048877Z", selected_route="deterministic-local"),
    _observation("2026-09-01T00:40:03.214758Z", selected_route="deterministic-local"),
]
CURRENT = _observation("2026-09-03T08:00:00Z")


def test_the_five_historical_observations_are_not_comparable() -> None:
    cohort = select_cohort(HISTORICAL)

    assert cohort.included == []
    assert cohort.excluded_earlier_era == 5


def test_exclusions_are_counted_rather_than_dropped() -> None:
    # A cohort of one that does not say it discarded five is indistinguishable
    # from a store that only ever held one.
    cohort = select_cohort([*HISTORICAL, CURRENT])

    assert len(cohort.included) == 1
    assert cohort.excluded == 5
    assert cohort.excluded_earlier_era == 5


def test_only_applied_observations_enter_a_quality_cohort() -> None:
    advisory = _observation("2026-09-03T08:00:00Z", application="advisory")
    shadow = _observation("2026-09-03T08:00:00Z", application="shadow")
    absent = _observation("2026-09-03T08:00:00Z")
    del absent["application"]

    cohort = select_cohort([CURRENT, advisory, shadow, absent])

    assert cohort.included == [CURRENT]
    assert cohort.excluded_not_applied == 3


def test_a_task_class_filter_reports_what_it_removed() -> None:
    other = _observation("2026-09-03T08:00:00Z", task_class="diff-summary")

    cohort = select_cohort([CURRENT, other], task_class="docs-review")

    assert cohort.included == [CURRENT]
    assert cohort.excluded_other_task_class == 1


def test_an_undated_record_is_excluded_not_assumed() -> None:
    # None is not a date. An observation that cannot be placed in an era must
    # not be guessed into a population that claims to be comparable.
    undated = _observation("2026-09-03T08:00:00Z")
    del undated["recorded_at"]
    malformed = _observation("last tuesday")

    cohort = select_cohort([CURRENT, undated, malformed, "not a record"])

    assert cohort.included == [CURRENT]
    assert cohort.excluded_undated == 3


def test_an_observation_at_the_boundary_belongs_to_the_new_era() -> None:
    # The merge is the moment the runtime changed.
    era = era_named(ERA_C4)
    at_boundary = _observation(era.starts_at.isoformat().replace("+00:00", "Z"))

    assert select_cohort([at_boundary]).included == [at_boundary]


def test_one_second_before_the_boundary_is_the_previous_era() -> None:
    era = era_named(ERA_C4)
    just_before = era.starts_at.timestamp() - 1
    record = _observation(
        datetime.fromtimestamp(just_before, tz=UTC).isoformat().replace("+00:00", "Z")
    )

    assert select_cohort([record]).included == []


def test_eras_are_ordered_and_each_names_the_merge_that_opened_it() -> None:
    for earlier, later in zip(ERAS, ERAS[1:]):
        assert earlier.starts_at < later.starts_at
        assert later.commit
        assert later.why


def test_the_current_era_is_the_last_one() -> None:
    assert current_era() is ERAS[-1]
    assert current_era().name == ERA_C4


def test_an_earlier_era_can_still_be_selected_deliberately() -> None:
    # History is not deleted. Asking for era A is legitimate — silently getting
    # it is not.
    cohort = select_cohort(HISTORICAL, era=ERAS[0])

    assert len(cohort.included) == 5


def test_an_unknown_era_is_refused() -> None:
    with pytest.raises(ValueError):
        era_named("whatever-we-ship-next")


def _names(module) -> tuple[set[str], set[str]]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return imported, called


def test_readiness_cannot_reach_the_cohort() -> None:
    """The separation, asserted in the direction that matters most.

    Readiness answers a question about execution history, where superseded
    records legitimately count. A cutoff leaking into it would quietly narrow
    the gate that is supposed to be hard to pass.
    """
    imported, called = _names(model_routing)

    assert "select_cohort" not in imported
    assert "select_cohort" not in called
    assert "analysis_cohort" not in {name.split(".")[0] for name in imported}


def test_the_cohort_cannot_reach_readiness() -> None:
    # And the other way: a cohort that consulted readiness would reintroduce
    # exactly the shared population definition it exists to prevent.
    imported, called = _names(analysis_cohort)

    assert "route_readiness" not in imported
    assert "route_readiness" not in called


def test_readiness_still_counts_the_historical_observations(tmp_path) -> None:
    """Unchanged, and proven unchanged.

    These five are valid execution history. Readiness may count them; only
    quality comparison may not.
    """
    import json

    store = tmp_path / "route-outcomes.jsonl"
    validator = model_routing._validator("model_route_outcome.schema.json")
    written = 0
    for record in HISTORICAL:
        outcome = model_routing._outcome(
            model_routing.inspect_route("Review the repository documentation for gaps"),
            attempted=True,
            model_output_received=True,
            schema_valid=True,
            verification_status="PASS",
            application="applied",
            execution_run_id="exec-1",
            selected_route=record["selected_route"],
            local_model=None if record["selected_route"] == "deterministic-local" else "m",
        )
        outcome["recorded_at"] = record["recorded_at"]
        validator.validate(outcome)
        store.write_text(
            store.read_text() + json.dumps(outcome) + "\n" if store.exists()
            else json.dumps(outcome) + "\n",
            encoding="utf-8",
        )
        written += 1

    readiness = model_routing.route_readiness(store)

    assert written == 5
    assert readiness["observations_considered"] == 5
    assert readiness["task_classes"]["docs-review"]["actual"]["candidate_routes"] == 2


#: The two real observations from the first Era C runs, before #233.
FIRST_REAL_RUNS = [
    _observation("2026-09-02T13:16:52.839031Z", selected_route="local-shadow"),
    _observation("2026-09-02T13:17:05.000000Z", selected_route="deterministic-local"),
]


def test_the_first_real_runs_are_material_selection_not_plan_validation() -> None:
    """The boundary that was discovered hours after the model was built.

    Both runs verified the executable subset of a plan whose calls were never
    valid — four of seven steps could not run at all. They are real applied
    executions and they are not a baseline for a runtime that rejects such a
    plan up front.
    """
    assert select_cohort(FIRST_REAL_RUNS).included == []
    assert select_cohort(FIRST_REAL_RUNS).excluded_earlier_era == 2
    assert len(select_cohort(FIRST_REAL_RUNS, era=era_named(ERA_C1)).included) == 2


#: The two real observations from the first plan-composition runs.
PLAN_COMPOSITION_RUNS = [
    _observation("2026-09-02T21:51:10.637600Z", selected_route="local-shadow"),
    _observation("2026-09-02T21:51:41.649793Z", selected_route="deterministic-local"),
]


def test_the_two_plan_composition_runs_are_not_the_new_baseline() -> None:
    """They stay countable history and stop being a baseline.

    Both were measured on material that included a local secrets file. Nothing
    about their quality is in question — the material was not admissible.
    """
    assert select_cohort(PLAN_COMPOSITION_RUNS).included == []
    assert select_cohort(PLAN_COMPOSITION_RUNS).excluded_earlier_era == 2
    assert len(select_cohort(PLAN_COMPOSITION_RUNS, era=era_named(ERA_C3)).included) == 2


def test_each_boundary_names_the_merge_that_opened_it() -> None:
    assert era_named(ERA_C2).commit == "0a1721b"
    assert era_named(ERA_C2).starts_at == datetime(2026, 9, 2, 14, 37, 5, tzinfo=UTC)
    assert era_named(ERA_C3).commit == "6c67086"
    assert era_named(ERA_C3).starts_at == datetime(2026, 9, 2, 20, 31, 18, tzinfo=UTC)
    assert era_named(ERA_C4).commit == "49e6c67"
    assert era_named(ERA_C4).starts_at == datetime(2026, 9, 2, 22, 30, 36, tzinfo=UTC)


def test_no_observation_predates_a_working_docs_review() -> None:
    """The quality baseline starts empty, and that is the correct state.

    Every observation in the store was produced by a runtime whose docs-review
    read fewer files than its plan described. None of them is a baseline for
    one that does not.
    """
    assert select_cohort([*HISTORICAL, *FIRST_REAL_RUNS]).included == []
