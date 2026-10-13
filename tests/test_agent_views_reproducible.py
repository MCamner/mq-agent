"""A committed agent view must be reproducible from versioned sources alone.

mqobsidian tracks `memory/learn/agent/mqobsidian.md` as a required front door,
but `memory/learn/repos/` is gitignored. A view that quoted those local
lessons, and stamped the rebuild day as `generated`, differed between the
operator's vault and a clean clone, and `agent-views check` called it stale
the day after every rebuild.

A system opts in with `agent_view: versioned` in its own `hot.md` or `index.md`. Its view is
then built from `hot.md` + `index.md` only. Every view dates itself from its
sources' `updated:` frontmatter rather than from the clock.
"""
from __future__ import annotations

import datetime as real_datetime
from pathlib import Path

from mq_agent.tools import agent_views
from mq_agent.tools.agent_views import rebuild_agent_views


def _vault(tmp_path: Path, *, versioned: bool, lessons: bool) -> Path:
    vault = tmp_path / "vault"
    sysd = vault / "systems" / "mqobsidian"
    sysd.mkdir(parents=True)
    marker = "agent_view: versioned\n" if versioned else ""
    (sysd / "hot.md").write_text(
        f"---\ntype: hot-cache\n{marker}updated: 2026-09-17\n---\n\n"
        "## Current mission\nKeep durable memory thin.\n\n"
        "## Active blockers\n- none open\n",
        encoding="utf-8",
    )
    (sysd / "index.md").write_text(
        "---\ntype: index\nupdated: 2026-09-20\n---\n\n"
        "## Current priorities\n1. public-safe exports\n",
        encoding="utf-8",
    )
    if lessons:
        repos = vault / "memory" / "learn" / "repos"
        repos.mkdir(parents=True)
        (repos / "mqobsidian.md").write_text(
            "# Learn — mqobsidian\n\n- [[memory/learn/patterns/a]] — a local-only lesson\n",
            encoding="utf-8",
        )
    return vault


def _view(vault: Path) -> str:
    return (vault / "memory" / "learn" / "agent" / "mqobsidian.md").read_text("utf-8")


def _set_today(monkeypatch, day: real_datetime.date) -> None:
    class _Date(real_datetime.date):
        @classmethod
        def today(cls):
            return day

    class _Datetime:
        date = _Date

    monkeypatch.setattr(agent_views, "datetime", _Datetime)


def test_versioned_view_ignores_local_lessons(tmp_path: Path) -> None:
    vault = _vault(tmp_path, versioned=True, lessons=True)

    rebuild_agent_views(vault=vault)

    view = _view(vault)
    assert "Relevant lessons" not in view
    assert "a local-only lesson" not in view
    assert "memory/learn/repos" not in view


def test_versioned_view_is_identical_with_and_without_local_data(tmp_path: Path) -> None:
    operator = _vault(tmp_path / "operator", versioned=True, lessons=True)
    clean_clone = _vault(tmp_path / "clone", versioned=True, lessons=False)

    rebuild_agent_views(vault=operator)
    rebuild_agent_views(vault=clean_clone)

    assert _view(operator) == _view(clean_clone)


def test_local_view_still_uses_local_lessons(tmp_path: Path) -> None:
    vault = _vault(tmp_path, versioned=False, lessons=True)

    rebuild_agent_views(vault=vault)

    view = _view(vault)
    assert "- a local-only lesson" in view
    assert "memory/learn/repos/mqobsidian.md" in view


def test_generated_is_the_newest_source_date(tmp_path: Path) -> None:
    vault = _vault(tmp_path, versioned=True, lessons=False)

    rebuild_agent_views(vault=vault)

    assert "\ngenerated: 2026-09-20\n" in _view(vault)


def test_view_stays_fresh_on_a_later_day(tmp_path: Path, monkeypatch) -> None:
    vault = _vault(tmp_path, versioned=True, lessons=False)
    _set_today(monkeypatch, real_datetime.date(2026, 10, 1))
    rebuild_agent_views(vault=vault)

    _set_today(monkeypatch, real_datetime.date(2026, 10, 2))
    report = rebuild_agent_views(vault=vault, dry_run=True)

    assert report["views_unchanged"] == ["mqobsidian"]


def test_undated_sources_fall_back_to_today(tmp_path: Path, monkeypatch) -> None:
    vault = _vault(tmp_path, versioned=False, lessons=False)
    for name in ("hot.md", "index.md"):
        path = vault / "systems" / "mqobsidian" / name
        path.write_text(
            "\n".join(ln for ln in path.read_text("utf-8").splitlines() if not ln.startswith("updated:")),
            encoding="utf-8",
        )
    _set_today(monkeypatch, real_datetime.date(2026, 10, 1))

    rebuild_agent_views(vault=vault)

    assert "\ngenerated: 2026-10-01\n" in _view(vault)


def test_the_marker_may_sit_in_index(tmp_path: Path) -> None:
    vault = _vault(tmp_path, versioned=False, lessons=True)
    index = vault / "systems" / "mqobsidian" / "index.md"
    index.write_text(
        index.read_text("utf-8").replace("type: index\n", "type: index\nagent_view: versioned\n", 1),
        encoding="utf-8",
    )

    rebuild_agent_views(vault=vault)

    assert "a local-only lesson" not in _view(vault)
