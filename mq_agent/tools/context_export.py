"""Per-repo .mq/context export helpers.

mq-agent owns orchestration; mqobsidian owns durable memory and context-card
content. This module reads public-safe context cards from the vault and writes
small repo-local context snapshots.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_VAULT_DIR = Path.home() / "mqobsidian"
DEFAULT_REPOS_ROOT = Path.home()

CORE_MQ_REPOS = [
    "mq-agent",
    "mq-mcp",
    "mqobsidian",
    "mq-hal",
    "macos-scripts",
    "repo-signal",
    "mq-ums",
    "mq-image-analyze",
    "mcamner-journal",
]

CONTEXT_FILES = [
    "repo-card.md",
    "active-contract.md",
    "current-blockers.md",
    "integration-map.md",
    "token-budget.md",
]

# Budget contract owned by mqobsidian (.mq/context-budgets.json). mq-agent is a
# consumer: it reads the contract from the vault when rendering token-budget.md
# and falls back to these defaults when the vault predates the contract.
_DEFAULT_BUDGETS = {
    "repo-card.md": 60,
    "active-contract.md": 80,
    "current-blockers.md": 80,
    "integration-map.md": 120,
    "token-budget.md": 80,
    "task-pack.md": 200,
}
_DEFAULT_RENDERED_ORDER = [
    "repo-card.md",
    "active-contract.md",
    "current-blockers.md",
    "integration-map.md",
    "task-pack.md",
]


def _load_budget_contract(vault: Path) -> tuple[dict[str, int], list[str]]:
    """Read budgets from the vault's published contract, else use defaults."""
    path = vault / ".mq" / "context-budgets.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["budgets"], data["rendered_order"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return _DEFAULT_BUDGETS, _DEFAULT_RENDERED_ORDER


def default_vault() -> Path:
    env = os.environ.get("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_VAULT_DIR


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a simple `key: value` YAML frontmatter block into a flat dict.

    Tolerant by design: missing or malformed frontmatter yields `{}` rather than
    raising, because callers (pack selection) treat block-level metadata as
    optional hints, not hard requirements.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for raw_line in lines[1:]:
        if raw_line.strip() == "---":
            break
        key, separator, value = raw_line.partition(":")
        if not separator:
            continue
        data[key.strip()] = value.strip()
    return data


def _section_body(text: str, heading: str) -> str:
    marker = f"## {heading}"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != marker:
            continue
        body: list[str] = []
        for next_line in lines[index + 1 :]:
            if next_line.startswith("## "):
                break
            body.append(next_line)
        return "\n".join(body).strip()
    return ""


def _section_items(text: str, heading: str) -> list[str]:
    items: list[str] = []
    for raw_line in _section_body(text, heading).splitlines():
        line = raw_line.strip()
        if line.startswith(("* ", "- ")):
            items.append(line[2:].strip())
    return items


def _bullet_lines(items: list[str], fallback: str) -> str:
    if not items:
        return f"* {fallback}"
    return "\n".join(f"* {item}" for item in items)


def _card_path(vault: Path, repo: str) -> Path:
    cards_dir = vault / "memory" / "context-cards"
    candidates = [cards_dir / f"{repo}-card.md", cards_dir / f"{repo}.md"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"missing context card for {repo}: {candidates[0]}")


def _render_active_contract(repo: str, card_text: str) -> str:
    return f"""# Active Contract: {repo}

## Owns

{_bullet_lines(_section_items(card_text, "Owns"), "No ownership items defined.")}

## Does Not Own

{_bullet_lines(_section_items(card_text, "Does not own"), "No boundary items defined.")}

## Rules

* Treat this file as routing context, not runtime truth.
* Verify current code, tests, CLI behavior, and contracts in the target repo.
* Do not duplicate behavior owned by another MQ repo.
"""


def _render_integration_map(repo: str, card_text: str) -> str:
    return f"""# Integration Map: {repo}

## Reads From

{_bullet_lines(_section_items(card_text, "Reads from"), "No read dependencies defined.")}

## Writes To

{_bullet_lines(_section_items(card_text, "Writes to"), "No write surfaces defined.")}

## Use When

{_bullet_lines(_section_items(card_text, "Use this card when"), "Use when repo-local context is insufficient.")}

## Avoid Reading First

{_bullet_lines(_section_items(card_text, "Avoid reading unless needed"), "Broad docs unless the compact export is insufficient.")}
"""


def _render_current_blockers(repo: str, card_text: str) -> str:
    return f"""# Current Blockers: {repo}

## Known Blockers

{_bullet_lines(_section_items(card_text, "Current blockers"), "No blockers are declared in the source context card.")}

## Check Before Acting

* Read `.mq/context/repo-card.md`.
* Read `.mq/context/active-contract.md`.
* Read `.mq/context/integration-map.md`.
* Verify live repo state before making runtime or release claims.
"""


def _render_token_budget(repo: str, budgets: dict[str, int], order: list[str]) -> str:
    rows = "\n".join(f"| `{name}` | {budgets[name]} lines |" for name in order)
    return f"""# Token Budget: {repo}

## Generated Context Budgets

| File | Budget |
| --- | ---: |
{rows}

## Rule

If a generated context file exceeds its budget, tighten the export instead of
copying broad README, changelog, release-note, or vault history into it.
"""


def _repo_output_dir(repo: str, output_root: Path) -> Path:
    return output_root.expanduser().resolve() / repo / ".mq" / "context"


def _render_files(vault: Path, repo: str) -> dict[str, str]:
    card_file = _card_path(vault, repo)
    card_text = card_file.read_text(encoding="utf-8")
    budgets, order = _load_budget_contract(vault)
    return {
        "repo-card.md": card_text,
        "active-contract.md": _render_active_contract(repo, card_text),
        "current-blockers.md": _render_current_blockers(repo, card_text),
        "integration-map.md": _render_integration_map(repo, card_text),
        "token-budget.md": _render_token_budget(repo, budgets, order),
    }


def export_repo_context(
    repo: str,
    *,
    vault: Path | None = None,
    output_root: Path | None = None,
    dry_run: bool = False,
    clean: bool = False,
) -> dict[str, Any]:
    """Export one repository's generated context snapshot.

    When ``clean`` is enabled, remove only names listed in ``CONTEXT_FILES`` from
    the target context directory before writing. ``dry_run`` performs no deletion
    or write and reports changed paths through ``would_write``.
    """
    vault = (vault or default_vault()).expanduser().resolve()
    output_root = (output_root or DEFAULT_REPOS_ROOT).expanduser().resolve()
    context_dir = _repo_output_dir(repo, output_root)
    files = _render_files(vault, repo)

    written: list[str] = []
    unchanged: list[str] = []
    would_write: list[str] = []

    if not dry_run:
        if clean and context_dir.exists():
            for filename in CONTEXT_FILES:
                (context_dir / filename).unlink(missing_ok=True)
        context_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in files.items():
        path = context_dir / filename
        if path.exists() and path.read_text(encoding="utf-8") == content:
            unchanged.append(str(path))
            continue
        if dry_run:
            would_write.append(str(path))
        else:
            path.write_text(content, encoding="utf-8")
            written.append(str(path))

    return {
        "repo": repo,
        "vault": str(vault),
        "context_dir": str(context_dir),
        "dry_run": dry_run,
        "clean": clean,
        "written": written,
        "would_write": would_write,
        "unchanged": unchanged,
        "files": CONTEXT_FILES,
    }


def export_repo_contexts(
    *,
    repos: list[str],
    vault: Path | None = None,
    output_root: Path | None = None,
    dry_run: bool = False,
    clean: bool = False,
) -> dict[str, Any]:
    """Export context for each repository, retaining successes after failures.

    Per-repository exceptions are returned in ``errors`` and do not stop later
    exports, so callers must inspect both ``results`` and ``errors``.
    """
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for repo in repos:
        try:
            results.append(
                export_repo_context(
                    repo=repo,
                    vault=vault,
                    output_root=output_root,
                    dry_run=dry_run,
                    clean=clean,
                )
            )
        except Exception as exc:
            errors.append(f"{repo}: {exc}")

    return {
        "repos": repos,
        "dry_run": dry_run,
        "clean": clean,
        "results": results,
        "errors": errors,
    }
