"""Task-specific context pack generation (Phase 5).

mq-agent owns the task -> pack *selection*; mqobsidian owns the durable context
cards and the `context-pack.v1` contract. This module reads public-safe context
cards from the vault, selects the relevant repos / cards / do-not-read guidance
for one task, and renders a small `context-pack.v1` Markdown pack.

CodeGraph is an optional *local source-intelligence* hint only — it is never
durable memory and never replaces the mqobsidian cards. The hint is added when
a task is source-structure heavy (callers/impact/refactor/...), mirroring the
mqobsidian-side heuristic so both ends stay consistent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mq_agent.tools.context_export import (
    CORE_MQ_REPOS,
    DEFAULT_REPOS_ROOT,
    _section_items,
    default_vault,
)

# Signals that a task is about source-code structure, where CodeGraph
# (callers/callees, impact, code-flow, symbol search) beats broad grep/read.
# Kept in sync with mqobsidian/scripts/generate-context-pack.py.
CODEGRAPH_TASK_HINTS = (
    "caller",
    "callee",
    "impact",
    "blast radius",
    "call graph",
    "code flow",
    "code-flow",
    "refactor",
    "rename",
    "trace",
    "symbol",
    "where is",
    "implement",
    "writer path",
    "wire ",
    "fix ",
)

# Doc-shaped tasks never need CodeGraph; suppress even if a hint also matches so
# non-source packs stay clean.
CODEGRAPH_TASK_SUPPRESS = (
    "readme",
    "roadmap",
    "release note",
    "changelog",
    "docstring",
    "doc ",
    "docs ",
    "docs/",
)


def task_is_source_heavy(task: str) -> bool:
    key = task.lower()
    if any(token in key for token in CODEGRAPH_TASK_SUPPRESS):
        return False
    return any(token in key for token in CODEGRAPH_TASK_HINTS)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def select_relevant_repos(task: str, repo: str | None, extra: list[str]) -> list[str]:
    """Primary repo first, then any core repo named in the task, then extras."""
    task_key = task.lower()
    repos: list[str] = []
    if repo:
        repos.append(repo)
    for core in CORE_MQ_REPOS:
        if core in task_key:
            repos.append(core)
    repos.extend(extra)
    return _dedupe(repos)


def _card_text(vault: Path, repo: str) -> tuple[Path, str] | None:
    cards_dir = vault / "memory" / "context-cards"
    for candidate in (cards_dir / f"{repo}-card.md", cards_dir / f"{repo}.md"):
        if candidate.exists():
            return candidate, candidate.read_text(encoding="utf-8")
    return None


def _has_codegraph(repo: str, repos_root: Path) -> bool:
    return (repos_root / repo / ".codegraph").is_dir()


def _bullet_lines(items: list[str], fallback: str) -> str:
    if not items:
        return f"* {fallback}"
    return "\n".join(f"* {item}" for item in items)


def _codegraph_notes(
    task: str,
    repos: list[str],
    repos_root: Path,
    mode: str,
) -> list[str]:
    """Optional CodeGraph guidance. mode is auto (heuristic) / on / off."""
    if mode == "off":
        return []
    if mode == "auto" and not task_is_source_heavy(task):
        return []

    target = next((r for r in repos if _has_codegraph(r, repos_root)), None)
    if target:
        where = f"`.codegraph/` is present in `{target}`; ask CodeGraph"
    else:
        primary = repos[0] if repos else None
        scope = f" in `{primary}`" if primary else ""
        where = f"If `.codegraph/` exists{scope}, ask CodeGraph"
    return [
        f"{where} for callers/impact before broad grep.",
        "Use CodeGraph for source structure only; use mqobsidian cards/packs for "
        "durable memory and repo boundaries.",
    ]


def build_task_pack(
    task: str,
    *,
    target: str = "both",
    repo: str | None = None,
    relevant_repos: list[str] | None = None,
    relevant_files: list[str] | None = None,
    relevant_decisions: list[str] | None = None,
    notes: list[str] | None = None,
    do_not_read: list[str] | None = None,
    summary: str | None = None,
    vault: Path | None = None,
    repos_root: Path | None = None,
    codegraph: str = "auto",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Select context for `task` and render a `context-pack.v1` Markdown pack.

    Returns a dict with the rendered `content`, the selection it made, and
    whether a CodeGraph hint was applied. Pure: writing is the caller's job.
    """
    vault = (vault or default_vault()).expanduser().resolve()
    repos_root = (repos_root or DEFAULT_REPOS_ROOT).expanduser().resolve()

    repos = select_relevant_repos(task, repo, list(relevant_repos or []))

    files = list(relevant_files or [])
    avoid = list(do_not_read or [])
    cards: list[str] = []
    for r in repos:
        found = _card_text(vault, r)
        if not found:
            continue
        card_path, card_text = found
        try:
            rel = card_path.relative_to(vault)
            cards.append(f"{vault.name}/{rel}")
        except ValueError:
            cards.append(str(card_path))
        avoid.extend(_section_items(card_text, "Avoid reading unless needed"))
    # Point at the primary repo's exported compact card first.
    if repos:
        files.insert(0, f"{repos[0]}/.mq/context/repo-card.md")
    files.extend(cards)

    decisions = list(relevant_decisions or [])
    decisions.append(
        "Durable memory lives in mqobsidian; runtime truth stays in the source repo."
    )

    note_items = list(notes or [])
    note_items.append("Prefer the mqobsidian cards above before broad repo scans.")
    note_items.extend(_codegraph_notes(task, repos, repos_root, codegraph))

    files = _dedupe(files)
    decisions = _dedupe(decisions)
    note_items = _dedupe(note_items)
    avoid = _dedupe(avoid)

    pack_summary = summary or f"Minimum context needed for: {task}"
    generated = generated_at or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    repo_line = repo or (repos[0] if repos else "")

    content = f"""---
schema: context-pack.v1
target: {target}
task: {task}
generated_at: {generated}
repo: {repo_line}
summary: {pack_summary}
---

# Task Context Pack

## Relevant repos

{_bullet_lines(repos, "None specified")}

## Relevant files

{_bullet_lines(files, "None specified")}

## Relevant decisions

{_bullet_lines(decisions, "None specified")}

## Notes

{_bullet_lines(note_items, "Keep the task pack focused on the current change")}

## Do not read first

{_bullet_lines(avoid, "Broad repo scans unless the pack proves insufficient")}
"""

    return {
        "task": task,
        "target": target,
        "repo": repo_line,
        "relevant_repos": repos,
        "cards": cards,
        "codegraph_applied": bool(_codegraph_notes(task, repos, repos_root, codegraph)),
        "line_count": len(content.splitlines()),
        "content": content,
    }


def write_task_pack(content: str, output: Path) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output
