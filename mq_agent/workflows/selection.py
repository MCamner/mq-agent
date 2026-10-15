"""Explicit task vocabulary; no model, free shell or open-ended replanning."""

from __future__ import annotations
from dataclasses import dataclass


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class Selection:
    template: str
    reason: str


_INTENTS = {
    "review-and-test": (
        "Review the working diff and verify it with tests.",
        {
            "granska ändringarna",
            "granska ändringar",
            "review changes",
            "review the changes",
        },
    ),
    "repo-preflight": (
        "Inspect prerequisites and repository gates before diagnosis.",
        {
            "felsök repot",
            "felsök",
            "diagnose repository",
            "check prerequisites",
        },
    ),
    "release-ready": (
        "Check release readiness without publishing a release.",
        {
            "förbered release",
            "kontrollera releaseberedskap",
            "prepare release",
            "check release readiness",
        },
    ),
}


def select_task(task: str) -> Selection:
    normalized = " ".join(task.casefold().split())
    for template, (reason, phrases) in _INTENTS.items():
        if normalized in phrases:
            return Selection(template, reason)
    raise SelectionError(
        "Unknown or ambiguous task. Use: granska ändringarna; felsök repot; förbered release."
    )
