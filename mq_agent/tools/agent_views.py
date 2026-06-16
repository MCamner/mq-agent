"""Agent views — compressed first-stop read cards for mqobsidian systems.

Regenerates ``memory/learn/agent/<system>.md`` for each system in the vault from
that system's ``hot.md`` + ``index.md``. The view is the low-token "step 0" read
an agent does before opening the full notes (see mqobsidian CLAUDE.md / AGENTS.md
read order).

Design contract:
  * Pure extraction — copies real sections out of existing notes, never invents.
  * Empty/placeholder sections are dropped; a system with neither hot.md nor
    index.md produces no view (the gate — no source, no card).
  * ``hot.md`` and ``index.md`` are human-curated source and are NEVER written.
    Only ``memory/learn/agent/*.md`` is generated.
  * Output is confined to ``<vault>/memory/learn/agent/`` — any path escaping
    that directory is refused (safety guard).

Vault path follows the standard mq-agent contract: ``MQ_OBSIDIAN_DIR`` env var,
else ``~/mqobsidian`` (same as tools/vault_structure.py).

This module is the operational owner of view generation that the vault-local
``tools/build-agent-views.py`` prototyped.
"""
from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_VAULT_DIR = Path.home() / "mqobsidian"

# Source sections to lift, in output order: (source_kind, source_header, out_heading).
_PLAN: list[tuple[str, str, str]] = [
    ("hot", "Current mission", "Mission & status"),
    ("hot", "Current status", "Mission & status"),
    ("index", "Current state", "Mission & status"),
    ("hot", "Active blockers", "Blockers & risks"),
    ("index", "Active risks", "Blockers & risks"),
    ("index", "Current priorities", "Priorities & next actions"),
    ("hot", "Immediate next actions", "Priorities & next actions"),
    ("hot", "Most important facts", "Key facts"),
]


def default_vault() -> Path:
    """Resolve the mqobsidian vault root (MQ_OBSIDIAN_DIR env var, else ~/mqobsidian)."""
    env = os.environ.get("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_VAULT_DIR


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1 :] if nl != -1 else ""
    return text


def _section(text: str, header: str) -> str:
    """Body under ``## <header>`` up to the next ``## ``, trimmed.

    Placeholder-only bodies (blank lines or a lone ``-``) return ""."""
    pat = re.compile(rf"^##\s+{re.escape(header)}\s*$", re.MULTILINE)
    m = pat.search(text)
    if not m:
        return ""
    rest = text[m.end() :]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    body = (rest[: nxt.start()] if nxt else rest).strip()
    meaningful = [ln for ln in body.splitlines() if ln.strip() not in ("", "-", "- ")]
    return body if meaningful else ""


def _build_view(vault: Path, system: str) -> str | None:
    """Render the agent-view markdown for one system, or None if no source."""
    sysdir = vault / "systems" / system
    sources: dict[str, str] = {}
    for kind in ("hot", "index"):
        p = sysdir / f"{kind}.md"
        if p.exists():
            sources[kind] = _strip_frontmatter(p.read_text(encoding="utf-8"))
    if not sources:
        return None  # no current-state source — skip, never fabricate

    multi = {h for _, _, h in _PLAN if sum(1 for p in _PLAN if p[2] == h) > 1}
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for kind, header, out_head in _PLAN:
        body = _section(sources.get(kind, ""), header)
        if not body:
            continue
        if out_head not in grouped:
            grouped[out_head] = []
            order.append(out_head)
        block = f"_{header}:_\n{body}" if out_head in multi else body
        if block not in grouped[out_head]:
            grouped[out_head].append(block)

    if not order:
        return None

    src_list = [f"systems/{system}/{k}.md" for k in sources]
    if (vault / "memory" / "learn" / "repos" / f"{system}.md").exists():
        src_list.append(f"memory/learn/repos/{system}.md")

    today = datetime.date.today().isoformat()
    lines = [
        "---",
        "type: agent-view",
        f"system: {system}",
        f"generated: {today}",
        "generator: mq-agent memory regenerate-views",
        f"sources: [{', '.join(src_list)}]",
        "---",
        "",
        f"# {system} — agent view",
        "",
        "Compressed first-stop for agents (read-order step 0). Generated — do not",
        "edit by hand; re-run `mq-agent memory regenerate-views`. Expand to the",
        "sources below only when this view is insufficient.",
        "",
    ]
    for out_head in order:
        lines += [f"## {out_head}", "", "\n\n".join(grouped[out_head]).strip(), ""]
    lines.append("## Expand when needed")
    lines += [f"- {s}" for s in src_list]
    lines.append("")
    return "\n".join(lines)


def regenerate_agent_views(
    vault: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Regenerate every system's agent view under ``<vault>/memory/learn/agent/``.

    Only writes when the rendered content differs from what's on disk (idempotent).
    Returns a structured result for ``--json`` and pretty rendering.
    """
    vault = (vault or default_vault()).resolve()
    out_dir = (vault / "memory" / "learn" / "agent").resolve()
    systems_dir = vault / "systems"

    result: dict[str, Any] = {
        "vault": str(vault),
        "output_dir": str(out_dir),
        "dry_run": dry_run,
        "written": [],
        "unchanged": [],
        "skipped": [],
        "refused": [],
    }

    if not systems_dir.is_dir():
        result["error"] = f"no systems/ directory under vault: {systems_dir}"
        return result

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    for sysdir in sorted(p for p in systems_dir.iterdir() if p.is_dir()):
        name = sysdir.name
        view = _build_view(vault, name)
        if view is None:
            result["skipped"].append(
                {"system": name, "reason": "no hot.md/index.md to compress"}
            )
            continue

        dest = (out_dir / f"{name}.md").resolve()
        # Safety guard: never write outside the agent-views directory.
        if out_dir != dest.parent:
            result["refused"].append({"system": name, "path": str(dest)})
            continue

        current = dest.read_text(encoding="utf-8") if dest.exists() else None
        if current == view:
            result["unchanged"].append(name)
            continue

        if not dry_run:
            dest.write_text(view, encoding="utf-8")
        result["written"].append(name)

    return result
