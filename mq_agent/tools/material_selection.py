"""Choose what a routed decision reads, under a budget it can finish inside.

Measured on 2026-09-02, one `docs-audit` on this repo:

    repo summary                547 chars
    README.md                30,416
    CHANGELOG.md             38,463
    "File not found: /docs"      21
                             ------
                             69,447

Two whole files are 99% of it, and the CHANGELOG alone is 55%. Everything else
is tiny and carries real signal — a missing `/docs` folder is a documentation
finding, not noise.

Three separate limits bound this, and only the smallest one matters here:

    32768 tokens   integrity ceiling; below it the model and the verifier read
                   the same document (see `context_window`)
    180s           the route's own timeout — the real operational limit
    signal         grounding measured 0.80 at 3k chars, 0.71 at 8k, 0.33 at 32k

The middle one binds first. Warm, 16k chars of material completed in 61s while
24k took 728s and 40k did not finish in 900s; the production path runs cold, so
the budget is set where the route reliably finishes. The third says the cut is
not merely a cost saving: on this route more material made the answer worse.

Selection is deterministic. Nothing here scores relevance or ranks lines by
importance — a heuristic reviewer inside the context builder would quietly
become the thing being measured.
"""
from __future__ import annotations

import os

#: Characters of material a routed decision may read. Chosen from the timeout
#: measurements above, not from the token ceiling, which corresponds to roughly
#: 82,000 characters and never binds in practice.
DEFAULT_MATERIAL_BUDGET = 16000

#: A step's result shorter than this is kept whole. Small results are the
#: high-signal ones — a repo summary, a "File not found" — and rationing them
#: buys nothing while risking the loss of a real finding.
_SMALL_RESULT = 1000


def material_budget() -> int:
    """The operator's budget in characters. Invalid settings fall back."""
    raw = os.environ.get("MQ_AGENT_ROUTE_MATERIAL_BUDGET", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MATERIAL_BUDGET
    return value if value > 0 else DEFAULT_MATERIAL_BUDGET


def _allocate(sizes: list[int], budget: int) -> list[int]:
    """Split `budget` between sources, giving no source more than it needs.

    Equal shares, with whatever a small source leaves over redistributed to the
    ones still asking. That is what stops a 38 KB CHANGELOG from consuming the
    whole budget and pushing a 547-character repo summary out entirely — the
    failure mode a single global head-truncation has.
    """
    shares = [0] * len(sizes)
    remaining = budget
    active = [index for index, size in enumerate(sizes) if size > 0]

    while active and remaining > 0:
        share = remaining // len(active)
        if share == 0:
            break
        for index in list(active):
            take = min(sizes[index] - shares[index], share)
            shares[index] += take
            remaining -= take
            if shares[index] >= sizes[index]:
                active.remove(index)
    return shares


def _reduce(text: str, budget: int) -> str:
    """Cut one source to `budget` characters, on line boundaries.

    Headings first, then the opening lines. Both choices are structural rather
    than semantic: a markdown heading states what a section covers, which is
    what a documentation review asks about, and the opening of a README or a
    CHANGELOG is its most current and most descriptive part.

    Whole lines only. A part-line would still be a verbatim substring and would
    pass grounding, so the model could be handed a sentence that stops mid-claim
    and cite it as evidence.

    Nothing is inserted to mark the omission. An "N lines omitted" marker is
    itself quotable material, and a route citing the elision as a documentation
    finding would be the context builder manufacturing evidence.
    """
    lines = text.splitlines()
    keep: list[bool] = [False] * len(lines)
    used = 0

    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            cost = len(line) + 1
            if used + cost > budget:
                break
            keep[index] = True
            used += cost

    for index, line in enumerate(lines):
        if keep[index]:
            continue
        cost = len(line) + 1
        if used + cost > budget:
            break
        keep[index] = True
        used += cost

    return "\n".join(line for index, line in enumerate(lines) if keep[index])


def select_material(sources: list[str], budget: int | None = None) -> str:
    """Join `sources` into material that fits the budget.

    Order is preserved, and a source under `_SMALL_RESULT` is never cut.
    """
    limit = material_budget() if budget is None else budget
    present = [source for source in sources if source and source.strip()]
    if not present:
        return ""

    large = [index for index, source in enumerate(present) if len(source) > _SMALL_RESULT]

    # Small sources are charged against the budget but never rationed: they are
    # cheap, and they are where a missing folder or a one-line failure shows up.
    spent = sum(
        len(source) + 1
        for index, source in enumerate(present)
        if index not in set(large)
    )
    shares = _allocate([len(present[index]) for index in large], max(0, limit - spent))
    reduced = dict(zip(large, shares))

    kept = []
    for index, source in enumerate(present):
        selected = _reduce(source, reduced[index]) if index in reduced else source
        if selected.strip():
            kept.append(selected)
    return "\n".join(kept)
