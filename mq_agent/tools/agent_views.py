"""Agent views — compressed first-stop read cards for mqobsidian systems.

Regenerates ``memory/learn/agent/<system>.md`` for each system in the vault from
that system's curated ``hot.md`` + ``index.md`` (and, for lessons, the generated
``memory/learn/repos/<system>.md``). The view is the low-token "step 0" read an
agent does before opening the full notes (see mqobsidian read order).

Design contract (see docs/AGENT_VIEW_CONTRACT.md):
  * Pure extraction — copies real signals out of existing notes, never invents.
  * ``hot.md`` / ``index.md`` are human-curated source and are NEVER written;
    only ``memory/learn/agent/*.md`` is generated.
  * Empty/placeholder sections collapse; a system with neither hot.md nor
    index.md produces no view (the gate — no source, no card).
  * Cards are short (≈120–180 words) with a stable heading structure.
  * Output is confined to ``<vault>/memory/learn/agent/`` (safety guard).

Vault path follows the standard mq-agent contract: ``MQ_OBSIDIAN_DIR`` env var,
else ``~/mqobsidian`` (same as tools/vault_structure.py).
"""
from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_VAULT_DIR = Path.home() / "mqobsidian"

MAX_PRIORITIES = 4
MAX_BLOCKERS = 4
MAX_LESSONS = 3
MAX_STATE_WORDS = 45
MAX_ITEM_WORDS = 18
WORD_BUDGET = 180  # soft cap on card body


def default_vault() -> Path:
    """Resolve the mqobsidian vault root (MQ_OBSIDIAN_DIR env var, else ~/mqobsidian)."""
    env = os.environ.get("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_VAULT_DIR


# ── source parsing ───────────────────────────────────────────────────────────

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


def _truncate_words(text: str, n: int) -> str:
    words = text.split()
    return text if len(words) <= n else " ".join(words[:n]).rstrip(".,;:") + "…"


def _list_items(body: str) -> list[str]:
    """Extract list items from a section body, stripping bullet/number markers."""
    items: list[str] = []
    for ln in body.splitlines():
        s = ln.strip()
        s = re.sub(r"^([-*]|\d+\.)\s+", "", s)
        if s and s != "-":
            items.append(_truncate_words(s, MAX_ITEM_WORDS))
    return items


def _first_sentences(body: str, max_words: int) -> str:
    """Flatten a section body to one compact paragraph, word-capped."""
    flat = " ".join(ln.strip() for ln in body.splitlines() if ln.strip())
    flat = re.sub(r"\s+", " ", flat).strip()
    return _truncate_words(flat, max_words)


# ── signal extraction (hot prioritised, index as support) ────────────────────

def _state(hot: str, index: str) -> str:
    parts = [_section(hot, "Current mission"), _section(hot, "Current status")]
    text = " ".join(p for p in parts if p).strip()
    if not text:
        text = _section(index, "Current state")
    return _first_sentences(text, MAX_STATE_WORDS) if text else ""


def _priorities(hot: str, index: str) -> list[str]:
    body = _section(index, "Current priorities") or _section(hot, "Immediate next actions")
    return _list_items(body)[:MAX_PRIORITIES]


def _blockers(hot: str, index: str) -> list[str]:
    items = _list_items(_section(hot, "Active blockers")) + _list_items(
        _section(index, "Active risks")
    )
    # dedup, preserve order
    seen: set[str] = set()
    out = [i for i in items if not (i in seen or seen.add(i))]
    return out[:MAX_BLOCKERS] if out else ["none"]


_LESSON_RE = re.compile(r"^-\s+\[\[[^\]]+\]\]\s+—\s+(.+)$")


def _lessons(vault: Path, system: str) -> list[str]:
    p = vault / "memory" / "learn" / "repos" / f"{system}.md"
    if not p.exists():
        return []
    out: list[str] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        m = _LESSON_RE.match(ln.strip())
        if m:
            out.append(_truncate_words(m.group(1).strip(), MAX_ITEM_WORDS))
        if len(out) >= MAX_LESSONS:
            break
    return out


def _read_next(vault: Path, system: str) -> list[str]:
    links = []
    for kind in ("hot", "index"):
        if (vault / "systems" / system / f"{kind}.md").exists():
            links.append(f"[[systems/{system}/{kind}]]")
    return links


# ── rendering ────────────────────────────────────────────────────────────────

def _body_word_count(sections: dict[str, Any]) -> int:
    chunks: list[str] = [sections["state"]]
    for key in ("priorities", "blockers", "lessons"):
        chunks.extend(sections[key])
    return sum(len(c.split()) for c in chunks)


def _render(vault: Path, system: str, sources: dict[str, str]) -> str | None:
    hot, index = sources.get("hot", ""), sources.get("index", "")
    sections = {
        "state": _state(hot, index),
        "priorities": _priorities(hot, index),
        "blockers": _blockers(hot, index),
        "lessons": _lessons(vault, system),
    }
    if not sections["state"] and not sections["priorities"]:
        return None  # nothing meaningful to compress

    # Soft word budget: shed lowest-value content first (lessons, then priorities tail).
    while _body_word_count(sections) > WORD_BUDGET and sections["lessons"]:
        sections["lessons"].pop()
    while _body_word_count(sections) > WORD_BUDGET and len(sections["priorities"]) > 2:
        sections["priorities"].pop()

    src_list = [f"systems/{system}/{k}.md" for k in sources]
    if (vault / "memory" / "learn" / "repos" / f"{system}.md").exists():
        src_list.append(f"memory/learn/repos/{system}.md")

    today = datetime.date.today().isoformat()
    lines = [
        "---",
        "type: agent-view",
        f"system: {system}",
        f"generated: {today}",
        "generator: mq-agent agent-views rebuild",
        f"sources: [{', '.join(src_list)}]",
        "---",
        "",
        f"# {system} — agent view",
        "",
        "Compressed first-stop for agents (read-order step 0). Generated — do not",
        "edit by hand; re-run `mq-agent agent-views rebuild`.",
        "",
    ]
    if sections["state"]:
        lines += ["## Current state", "", sections["state"], ""]
    if sections["priorities"]:
        lines += ["## Active priorities", ""] + [f"- {p}" for p in sections["priorities"]] + [""]
    lines += ["## Current blockers", ""] + [f"- {b}" for b in sections["blockers"]] + [""]
    if sections["lessons"]:
        lines += ["## Relevant lessons", ""] + [f"- {item}" for item in sections["lessons"]] + [""]
    read_next = _read_next(vault, system)
    if read_next:
        lines += ["## Read next", ""] + [f"- {r}" for r in read_next] + [""]
    return "\n".join(lines)


def _build_view(vault: Path, system: str) -> str | None:
    sysdir = vault / "systems" / system
    sources: dict[str, str] = {}
    for kind in ("hot", "index"):
        p = sysdir / f"{kind}.md"
        if p.exists():
            sources[kind] = _strip_frontmatter(p.read_text(encoding="utf-8"))
    if not sources:
        return None
    return _render(vault, system, sources)


# ── orchestration ────────────────────────────────────────────────────────────

def rebuild_agent_views(vault: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Rebuild every system's agent view under ``<vault>/memory/learn/agent/``.

    Writes only when content differs (idempotent). Returns a structured report.
    """
    vault = (vault or default_vault()).resolve()
    out_dir = (vault / "memory" / "learn" / "agent").resolve()
    systems_dir = vault / "systems"

    report: dict[str, Any] = {
        "vault": str(vault),
        "output_dir": str(out_dir),
        "dry_run": dry_run,
        "repos_checked": 0,
        "views_written": [],
        "views_updated": [],
        "views_unchanged": [],
        "views_skipped_no_source": [],
        "errors": [],
    }

    if not systems_dir.is_dir():
        report["errors"].append(f"no systems/ directory under vault: {systems_dir}")
        return report

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    for sysdir in sorted(p for p in systems_dir.iterdir() if p.is_dir()):
        name = sysdir.name
        report["repos_checked"] += 1
        view = _build_view(vault, name)
        if view is None:
            report["views_skipped_no_source"].append(name)
            continue

        dest = (out_dir / f"{name}.md").resolve()
        if dest.parent != out_dir:  # safety guard: never write outside agent-views/
            report["errors"].append(f"refused unsafe output path for {name}: {dest}")
            continue

        existed = dest.exists()
        current = dest.read_text(encoding="utf-8") if existed else None
        if current == view:
            report["views_unchanged"].append(name)
            continue

        if not dry_run:
            dest.write_text(view, encoding="utf-8")
        (report["views_updated"] if existed else report["views_written"]).append(name)

    return report
