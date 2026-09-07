"""Vocabulary-driven, case-insensitive whole-term task profiling."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskProfile:
    task: str
    repo: str | None
    target: str
    intents: tuple[str, ...]
    domains: tuple[str, ...]
    risks: tuple[str, ...]
    matched_terms: tuple[str, ...]

    def facets(self) -> dict:
        return {
            key: list(getattr(self, key)) for key in ("intents", "domains", "risks")
        }


def profile_task(
    task: str, repo: str | None, target: str, vocabulary: dict
) -> TaskProfile:
    terms = set()
    facets = {}
    for dimension in ("intents", "domains", "risks"):
        found = []
        for facet, aliases in sorted(vocabulary[dimension].items()):
            matches = [
                term
                for term in aliases
                if re.search(
                    r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", task.casefold()
                )
            ]
            if matches:
                found.append(facet)
                terms.update(matches)
        facets[dimension] = tuple(found)
    return TaskProfile(task, repo, target, **facets, matched_terms=tuple(sorted(terms)))
