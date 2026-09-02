"""Which observations may be compared with which.

`route_readiness` and route-quality analysis ask different questions of the same
store, and until now they had no way to disagree about the population:

    readiness   has this system really applied two routes, often enough, over
                long enough? A question about execution history, where a
                superseded runtime's records legitimately count.

    quality     is route A better than route B *as they exist now*? A question
                about the current implementation, where those same records are
                noise.

Sharing one population out of convenience is how a comparison starts averaging
two different systems. Nothing here is reachable from `route_readiness`, and it
reads no readiness code — the separation is enforced by tests in both
directions.

**Why eras are timestamps and not a field the emitter records.**

An emitter can only stamp the era it believes it is in. The defect that created
these era boundaries — Ollama truncating every prompt over 4096 tokens because
`options.num_ctx` was never sent — ran for months and was recognized on
2026-09-01. No emitter could have stamped "produced by a runtime that silently
truncates its context", because nobody knew. Era boundaries are discovered
retroactively, and a value frozen at emit time cannot be corrected when
understanding improves. `recorded_at` already exists, cannot lie about when a
record was written, and lets this list grow as more boundaries are found.

It also costs no contract change, so the 135 stored observations stay exactly as
they are.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Era:
    """A span during which the runtime produced comparable observations."""

    name: str
    starts_at: datetime
    commit: str
    why: str


#: Ordered oldest first. Each boundary is a merge that changed what an
#: observation means, not merely what the code looked like.
ERAS: tuple[Era, ...] = (
    Era(
        name="pre-context-integrity",
        starts_at=datetime.min.replace(tzinfo=UTC),
        commit="",
        why=(
            "No options.num_ctx, so Ollama truncated every prompt over 4096 "
            "tokens. Grounding was checked against material the model never "
            "saw, which makes those numbers a measurement of truncation."
        ),
    ),
    Era(
        name="context-integrity",
        starts_at=datetime(2026, 9, 1, 21, 41, 20, tzinfo=UTC),
        commit="d34e1dd",
        why=(
            "The model gets the material the verifier checks against, or the "
            "run says so. No selector yet, so a full docs-audit was refused "
            "rather than run."
        ),
    ),
    Era(
        name="material-selection",
        starts_at=datetime(2026, 9, 2, 9, 15, 49, tzinfo=UTC),
        commit="7fe49bf",
        why=(
            "Context integrity plus a 16k material budget. The first runtime in "
            "which both applied routes produce usable output on real material."
        ),
    ),
)


@dataclass(frozen=True)
class CohortSelection:
    """The comparable observations, and an account of everything left out.

    Exclusions are counted rather than silently dropped. A cohort of three that
    does not say it discarded five is indistinguishable from a store that only
    ever held three.
    """

    era: Era
    included: list[Any] = field(default_factory=list)
    excluded_earlier_era: int = 0
    excluded_not_applied: int = 0
    excluded_other_task_class: int = 0
    excluded_undated: int = 0

    @property
    def excluded(self) -> int:
        return (
            self.excluded_earlier_era
            + self.excluded_not_applied
            + self.excluded_other_task_class
            + self.excluded_undated
        )


def current_era() -> Era:
    """The era the runtime is producing observations in now."""
    return ERAS[-1]


def era_named(name: str) -> Era:
    for era in ERAS:
        if era.name == name:
            return era
    raise ValueError(f"unknown era: {name!r}")


def _recorded_at(record: Any) -> datetime | None:
    """When this observation was written, or None when that cannot be read.

    None is not a date. An observation whose timestamp is missing or malformed
    cannot be placed in an era, and guessing would put an unknown record into a
    population that claims to be comparable.
    """
    if not isinstance(record, dict):
        return None
    raw = record.get("recorded_at")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def select_cohort(
    records: list[Any],
    *,
    era: Era | None = None,
    task_class: str | None = None,
    application: str = "applied",
) -> CohortSelection:
    """Pick the observations a quality comparison may use.

    The era is the current one unless named, and an observation exactly at a
    boundary belongs to the era that boundary opens — the merge is the moment
    the runtime changed.
    """
    chosen = era or current_era()
    selection = CohortSelection(era=chosen)
    included: list[Any] = []
    earlier = not_applied = other_class = undated = 0

    for record in records:
        if not isinstance(record, dict):
            undated += 1
            continue
        when = _recorded_at(record)
        if when is None:
            undated += 1
            continue
        if when < chosen.starts_at:
            earlier += 1
            continue
        if record.get("application") != application:
            not_applied += 1
            continue
        if task_class is not None and record.get("task_class") != task_class:
            other_class += 1
            continue
        included.append(record)

    return CohortSelection(
        era=selection.era,
        included=included,
        excluded_earlier_era=earlier,
        excluded_not_applied=not_applied,
        excluded_other_task_class=other_class,
        excluded_undated=undated,
    )
