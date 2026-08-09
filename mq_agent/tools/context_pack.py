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
    _section_items,
    default_vault,
    parse_frontmatter,
)

# context-pack.v1 exclusion kinds (mqobsidian owns the contract). `forbidden`
# blocks are never pulled in; `fallback` blocks are read only if the context
# above is insufficient; `irrelevant` blocks are simply not needed.
EXCLUSION_KINDS = ("forbidden", "fallback", "irrelevant")

# Block-level metadata (context-card.v1, Phase 11b). mq-agent is the consumer:
# it bounds and ranks card selection from these values; the values live in the
# vault, the selection logic lives here.
#
# A card must never be pulled into a task pack — which lands as a public-safe
# artifact in a target repo — when its publishability/scope marks it local-only.
# That mirrors the mqobsidian publish boundary, machine-checked at selection.
NON_PUBLISHABLE_PUBLISHABILITY = {"local-rich"}
NON_PUBLISHABLE_SCOPE = {"local-only"}

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


def _bullet_lines(items: list[str], fallback: str) -> str:
    if not items:
        return f"* {fallback}"
    return "\n".join(f"* {item}" for item in items)


# Source extensions CodeGraph can index; a `node` query only makes sense for
# these. Shell/PowerShell are unsupported upstream. Kept in sync with
# mqobsidian/scripts/generate-context-pack.py.
SOURCE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx")

# Hard cap so CodeGraph guidance can never become a token sink in the pack.
MAX_CODEGRAPH_QUERIES = 5


def _sanitize_query(task: str) -> str:
    return " ".join(task.split()).replace('"', "'")[:80]


def _repo_relative(path: str, repo: str) -> str:
    prefix = f"{repo}/"
    while path.startswith(prefix):
        path = path[len(prefix):]
    return path


def build_codegraph_queries(
    task: str,
    repos: list[str],
    relevant_files: list[str],
    symbols: list[str],
    mode: str,
) -> list[str]:
    """Build bounded MCP tool intentions for a source-heavy task.

    The returned strings are agent-facing guidance, not shell commands. The
    existing function/result name remains stable for callers while Codex and
    Claude are routed through CodeGraph's MCP tools.
    """
    if mode == "off":
        return []
    if mode == "auto" and not task_is_source_heavy(task):
        return []
    target = repos[0] if repos else None
    if not target:
        return []

    queries = [
        f"* `codegraph_explore` — map task \"{_sanitize_query(task)}\" in `{target}` first."
    ]
    for symbol in symbols:
        symbol = symbol.strip()
        if not symbol:
            continue
        queries.append(f"* `codegraph_callers` — inspect callers of `{symbol}`.")
        queries.append(f"* `codegraph_impact` — inspect the impact of changing `{symbol}`.")
    for path in relevant_files:
        if path.split("/", 1)[0] == target and path.lower().endswith(SOURCE_EXTS):
            queries.append(
                f"* `codegraph_node` — inspect `{_repo_relative(path, target)}` "
                "only if the context result omitted it."
            )

    bounded: list[str] = []
    for query in queries:
        if query not in bounded:
            bounded.append(query)
        if len(bounded) >= MAX_CODEGRAPH_QUERIES:
            break
    return bounded


def _codegraph_section(queries: list[str]) -> str:
    """Render optional MCP-native CodeGraph guidance, or empty when unused."""
    if not queries:
        return ""
    body = "\n".join(queries)
    return (
        "\n## CodeGraph queries\n\n"
        "Use the installed CodeGraph MCP tools directly; these are tool "
        "intentions, not shell commands. Treat source returned by CodeGraph as "
        "already read and do not repeat it with a broad grep/read loop. Fall "
        "back to targeted source reads only when the index is missing, the "
        "language is unsupported, or the result reports missing/stale detail. "
        "CodeGraph never replaces source tests or CLI verification.\n\n"
        f"{body}\n"
    )

def _coerce_exclusion(raw: Any) -> dict[str, str] | None:
    """Normalize one exclusion into `{item, kind, reason}`; drop unusable input.

    Accepts either a structured `{item, kind, reason?}` mapping or a bare string
    (legacy `do_not_read` / card-avoid item), which maps to kind `irrelevant`.
    Unknown kinds fall back to `irrelevant` so a producer typo degrades to the
    safe-but-soft kind instead of emitting an off-contract value.
    """
    if isinstance(raw, str):
        item = raw.strip()
        return {"item": item, "kind": "irrelevant", "reason": ""} if item else None
    if isinstance(raw, dict):
        item = str(raw.get("item", "")).strip()
        if not item:
            return None
        kind = str(raw.get("kind", "irrelevant")).strip()
        if kind not in EXCLUSION_KINDS:
            kind = "irrelevant"
        return {"item": item, "kind": kind, "reason": str(raw.get("reason", "")).strip()}
    return None


def _merge_exclusions(*groups: list[Any]) -> list[dict[str, str]]:
    """Coerce, dedupe (by kind+item, first reason wins), order by kind severity."""
    seen: set[tuple[str, str]] = set()
    collected: list[dict[str, str]] = []
    for group in groups:
        for raw in group:
            entry = _coerce_exclusion(raw)
            if entry is None:
                continue
            key = (entry["kind"], entry["item"])
            if key in seen:
                continue
            seen.add(key)
            collected.append(entry)
    order = {kind: rank for rank, kind in enumerate(EXCLUSION_KINDS)}
    return sorted(collected, key=lambda e: order[e["kind"]])


def _exclusion_lines(exclusions: list[dict[str, str]]) -> str:
    if not exclusions:
        return "* Broad repo scans unless the pack proves insufficient"
    lines: list[str] = []
    for entry in exclusions:
        reason = f": {entry['reason']}" if entry["reason"] else ""
        lines.append(f"* `{entry['kind']}` — {entry['item']}{reason}")
    return "\n".join(lines)


def build_task_pack(
    task: str,
    *,
    target: str = "both",
    repo: str | None = None,
    relevant_repos: list[str] | None = None,
    relevant_files: list[str] | None = None,
    relevant_decisions: list[str] | None = None,
    notes: list[str] | None = None,
    exclusions: list[Any] | None = None,
    do_not_read: list[str] | None = None,
    summary: str | None = None,
    vault: Path | None = None,
    repos_root: Path | None = None,
    codegraph: str = "auto",
    codegraph_symbols: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Select context for `task` and render a `context-pack.v1` Markdown pack.

    Block-level card metadata (`freshness`/`scope`/`publishability`, Phase 11b)
    bounds and ranks selection: a card marked local-only/local-rich never enters
    the pack (publish boundary), an archived card is demoted to a `fallback`
    exclusion, and a stale card is kept but flagged in Notes.

    Negative context is emitted as structured `exclusions` (Phase 11a). The
    legacy `do_not_read` list is still accepted for backward compatibility and
    is folded in as kind `irrelevant`; prefer passing `exclusions` directly.

    Returns a dict with the rendered `content`, the selection it made, and
    whether a CodeGraph hint was applied. Pure: writing is the caller's job.
    """
    vault = (vault or default_vault()).expanduser().resolve()

    repos = select_relevant_repos(task, repo, list(relevant_repos or []))

    files = list(relevant_files or [])
    avoid: list[str] = list(do_not_read or [])
    auto_exclusions: list[dict[str, str]] = []
    stale_notes: list[str] = []
    cards: list[str] = []
    card_metadata: dict[str, dict[str, str]] = {}
    for r in repos:
        found = _card_text(vault, r)
        if not found:
            continue
        card_path, card_text = found
        try:
            ref = f"{vault.name}/{card_path.relative_to(vault)}"
        except ValueError:
            ref = str(card_path)

        meta = parse_frontmatter(card_text)
        freshness = meta.get("freshness", "")
        scope = meta.get("scope", "")
        publishability = meta.get("publishability", "")
        card_metadata[r] = {
            "freshness": freshness,
            "scope": scope,
            "publishability": publishability,
        }

        # Publish-boundary gate: a local-only/local-rich card must not travel
        # into the pack. Record why it was withheld, then skip it entirely.
        if publishability in NON_PUBLISHABLE_PUBLISHABILITY or scope in NON_PUBLISHABLE_SCOPE:
            mark = publishability or scope
            auto_exclusions.append({
                "item": ref,
                "kind": "forbidden",
                "reason": f"card is {mark}; not publishable into a task pack",
            })
            continue

        # Freshness gate: archived cards drop to a fallback read; stale cards
        # stay selected but are flagged so the reader verifies before relying.
        if freshness == "archived":
            auto_exclusions.append({
                "item": ref,
                "kind": "fallback",
                "reason": "card is archived; read only if the context above is insufficient",
            })
            continue
        if freshness == "stale":
            stale_notes.append(f"Card `{ref}` is stale; verify against the repo before relying on it.")

        cards.append(ref)
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
    note_items.extend(stale_notes)

    codegraph_queries = build_codegraph_queries(
        task, repos, list(relevant_files or []), list(codegraph_symbols or []), codegraph
    )

    pack_exclusions = _merge_exclusions(
        list(exclusions or []),
        auto_exclusions,
        avoid,
    )

    files = _dedupe(files)
    decisions = _dedupe(decisions)
    note_items = _dedupe(note_items)

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
{_codegraph_section(codegraph_queries)}
## Exclusions

{_exclusion_lines(pack_exclusions)}
"""

    return {
        "task": task,
        "target": target,
        "repo": repo_line,
        "relevant_repos": repos,
        "cards": cards,
        "card_metadata": card_metadata,
        "exclusions": pack_exclusions,
        "codegraph_applied": bool(codegraph_queries),
        "codegraph_queries": codegraph_queries,
        "line_count": len(content.splitlines()),
        "content": content,
    }


def write_task_pack(content: str, output: Path) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output
