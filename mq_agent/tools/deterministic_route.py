"""The second applied route: local execution with no model inference.

ADR-010 D8 makes `selected_route` name an execution strategy rather than a
model, which is what lets this exist as a route at all — a second local *model*
would have recorded `local-shadow` like the first one and proved nothing.

This is deliberately the dumbest thing that can be called a route. It quotes
lines the audit already gathered, in the order it found them, and stops. There
is no scoring, no ranking, no attempt to judge which line matters most. The
moment it starts choosing cleverly it becomes a second review engine, and the
comparison it exists to make stops meaning anything:

    deterministic-local   what do we get almost free by restating verified facts?
    local-shadow          what additional judgement do we get from inference?

Its grounding rate is 100% by construction, because its evidence *is* the
material. That is the point, and it is also the trap: `verification.status` is
an execution-integrity gate and MUST NOT be read as comparative route quality.
A route that cannot fabricate wins that gate without being better at the job.
Whatever eventually decides between these two routes has to measure utility —
coverage, precision, whether a suggestion led anywhere, which output an operator
kept — and none of that is decided here.
"""
from __future__ import annotations

from typing import Any

from mq_agent.tools.model_routing import _MIN_GROUNDED_EVIDENCE, _MIN_QUOTE_LENGTH, _normalize

#: How many lines to quote. Matched to the verifier's floor rather than chosen:
#: fewer would fail verification by construction, and more would make the
#: baseline win on volume instead of on being verifiable.
EVIDENCE_ITEMS = _MIN_GROUNDED_EVIDENCE


def _quotable(material: str) -> list[str]:
    """Non-empty, de-duplicated lines long enough to survive grounding.

    The length filter is not cosmetic: `evidence_grounding` discards anything
    under `_MIN_QUOTE_LENGTH`, so a shorter line would be extracted, counted as
    evidence, then thrown away by the verifier — the route would fail on its own
    baseline. Same rule as the model route, applied before rather than after.
    """
    seen: set[str] = set()
    lines = []
    for raw in material.splitlines():
        line = raw.strip()
        if not line or len(_normalize(line)) < _MIN_QUOTE_LENGTH:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def deterministic_candidate(task_class: str, material: str) -> dict[str, Any] | None:
    """Build the same candidate shape a model would, by extraction alone.

    Returns None when the material cannot support the verifier's floor. Failing
    here is honest: the route has nothing to say, and manufacturing filler to
    reach five items would be the fabrication the whole verifier exists to catch,
    committed by the baseline instead of by the model.
    """
    quotes = _quotable(material)[:EVIDENCE_ITEMS]
    if len(quotes) < EVIDENCE_ITEMS:
        return None
    return {
        "task_class": task_class,
        # Deterministic and true: it describes what the route did, and claims
        # nothing about what the material means.
        "summary": (
            f"{len(quotes)} verbatim observations extracted from the material "
            "gathered by this run. No inference was performed."
        ),
        "evidence": quotes,
        # Empty, not invented. Suggesting anything would require judgement, which
        # is the thing this route deliberately does not have.
        "suggestions": [],
    }
