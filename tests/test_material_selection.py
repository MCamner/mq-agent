"""What a routed decision is allowed to read, and why it is that much.

Measured on one real `docs-audit` of this repo: 69,447 characters, of which
README.md is 30,416 and CHANGELOG.md is 38,463. The two whole files are 99% of
it. Everything else is tiny and carries the actual findings — a 547-character
repo summary, and a 21-character "File not found: /docs" which *is* a
documentation gap.

The budget comes from the route's 180s timeout, not from the token ceiling:
warm, 16k characters finished in 61s, 24k took 728s, 40k did not finish in 900s.
Grounding moved the same way — 0.80 at 3k characters, 0.71 at 8k, 0.33 at 32k —
so the cut is not only a cost saving.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mq_agent.tools import material_selection
from mq_agent.tools.material_selection import (
    DEFAULT_MATERIAL_BUDGET,
    material_budget,
    select_material,
)

REPO_SUMMARY = "Repo:   mq-agent\nBranch: main\nFiles:  331 total, 153 Python"
DOCS_GAP = "File not found: /docs"
README = "\n".join(
    ["# mq-agent", "", "Install it like this.", *[f"readme body line {i}" for i in range(400)],
     "## Configuration", *[f"config line {i}" for i in range(400)]]
)
CHANGELOG = "\n".join(
    ["# Changelog", *[f"## 0.{i}.0" for i in range(200)],
     *[f"changelog entry {i}" for i in range(800)]]
)


def test_the_budget_is_respected() -> None:
    selected = select_material([REPO_SUMMARY, README, CHANGELOG, DOCS_GAP], 16000)

    assert len(selected) <= 16000


def test_a_large_source_cannot_starve_a_small_one() -> None:
    # The failure mode of a single global truncation: the CHANGELOG is 55% of
    # the real material, and a naive head-cut would push the repo summary and
    # the missing-/docs finding out entirely.
    selected = select_material([REPO_SUMMARY, README, CHANGELOG, DOCS_GAP], 16000)

    assert REPO_SUMMARY in selected
    assert DOCS_GAP in selected


def test_small_sources_are_never_cut() -> None:
    selected = select_material([REPO_SUMMARY, DOCS_GAP], 16000)

    assert selected == f"{REPO_SUMMARY}\n{DOCS_GAP}"


def test_no_source_is_dropped_entirely() -> None:
    selected = select_material([REPO_SUMMARY, README, CHANGELOG, DOCS_GAP], 16000)

    assert "# mq-agent" in selected
    assert "# Changelog" in selected


def test_selection_only_ever_removes(monkeypatch) -> None:
    """The invariant grounding depends on.

    The selected material is both what the model reads and what its citations
    are checked against. A line that selection invented would be quotable and
    would verify — the context builder manufacturing its own evidence.
    """
    sources = [REPO_SUMMARY, README, CHANGELOG, DOCS_GAP]
    original = set("\n".join(sources).splitlines())

    for line in select_material(sources, 16000).splitlines():
        assert line in original


def test_nothing_is_inserted_to_mark_the_omission() -> None:
    # An "N lines omitted" marker is itself quotable. A route citing the elision
    # as a documentation finding would be evidence about the context builder.
    selected = select_material([README, CHANGELOG], 8000)

    assert "omitted" not in selected.lower()
    assert "truncat" not in selected.lower()


def test_lines_are_kept_whole() -> None:
    # A part-line is still a verbatim substring and would pass grounding, so the
    # model could be handed a sentence that stops mid-claim and cite it.
    selected = select_material([README, CHANGELOG], 8000)
    whole = set(f"{README}\n{CHANGELOG}".splitlines())

    for line in selected.splitlines():
        assert line in whole


def test_headings_survive_the_cut() -> None:
    # Structural, not semantic: a heading states what a section covers, which is
    # what a documentation review is asked about.
    selected = select_material([README, CHANGELOG], 8000)

    assert "## Configuration" in selected


def test_order_is_preserved() -> None:
    selected = select_material([REPO_SUMMARY, README, CHANGELOG, DOCS_GAP], 16000)

    assert selected.index("Repo:   mq-agent") < selected.index("# mq-agent")
    assert selected.index("# mq-agent") < selected.index("# Changelog")
    assert selected.index("# Changelog") < selected.index(DOCS_GAP)


def test_selection_is_deterministic() -> None:
    sources = [REPO_SUMMARY, README, CHANGELOG, DOCS_GAP]

    assert select_material(sources, 16000) == select_material(sources, 16000)


def test_the_selector_does_not_rank_or_score() -> None:
    """Absence, asserted.

    A relevance heuristic inside the context builder would quietly become the
    thing being measured, and the route comparison would stop meaning anything.
    """
    tree = ast.parse(Path(material_selection.__file__).read_text(encoding="utf-8"))
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

    # `sorted`/`.sort` are the signal: putting content in an order other than
    # the one it arrived in is ranking. `max`/`min` appear here only as numeric
    # budget clamps, which is why they are not forbidden.
    assert "sorted" not in called
    assert "sort" not in attributes


def test_empty_material_stays_empty() -> None:
    assert select_material([]) == ""
    assert select_material(["", "   "]) == ""


def test_material_that_already_fits_is_untouched() -> None:
    assert select_material([REPO_SUMMARY, DOCS_GAP], 16000) == f"{REPO_SUMMARY}\n{DOCS_GAP}"


@pytest.mark.parametrize("value", ["", "nonsense", "0", "-1"])
def test_an_unusable_budget_setting_falls_back(value, monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_ROUTE_MATERIAL_BUDGET", value)

    assert material_budget() == DEFAULT_MATERIAL_BUDGET


def test_the_operator_can_set_the_budget(monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_ROUTE_MATERIAL_BUDGET", "4000")

    assert len(select_material([README, CHANGELOG])) <= 4000


def test_the_budget_comes_from_the_timeout_not_the_token_ceiling() -> None:
    # 32768 tokens is roughly 82,000 characters at the measured ratio, so the
    # integrity ceiling never binds. The route's 180s timeout does.
    from mq_agent.tools.context_window import DEFAULT_MAX_CONTEXT_TOKENS

    assert DEFAULT_MATERIAL_BUDGET < DEFAULT_MAX_CONTEXT_TOKENS * 2.5


def test_the_real_docs_audit_material_fits_after_selection() -> None:
    # The concrete goal: ~69k characters of one real audit down to the budget,
    # with every source still represented.
    selected = select_material([REPO_SUMMARY, README, CHANGELOG, DOCS_GAP])

    assert len(selected) <= DEFAULT_MATERIAL_BUDGET
    for marker in ("Repo:   mq-agent", "# mq-agent", "# Changelog", DOCS_GAP):
        assert marker in selected
