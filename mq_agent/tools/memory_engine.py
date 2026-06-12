"""mqobsidian memory engine helpers.

The memory engine is intentionally small and local: it scans the standard
mqobsidian vault layout, extracts lightweight metadata from Markdown notes,
and can search, summarize, and infer links without requiring an AI service.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_VAULT_DIR = Path.home() / "mqobsidian"

MEMORY_SECTIONS: tuple[dict[str, str], ...] = (
    {"name": "truth", "path": "memory/stack-truth"},
    {"name": "reviews", "path": "memory/reviews"},
    {"name": "learn", "path": "memory/learn"},
    {"name": "releases", "path": "releases"},
    {"name": "architecture", "path": "architecture"},
    {"name": "decisions", "path": "decisions"},
    {"name": "stack-runs", "path": "mq-stack/runs"},
)

STOPWORDS = {
    "about", "after", "all", "also", "and", "are", "but", "for", "from",
    "has", "into", "not", "that", "the", "this", "with", "you",
}


@dataclass(frozen=True)
class MemoryNote:
    path: str
    section: str
    title: str
    excerpt: str
    words: int
    modified: str
    tags: list[str]


def _vault(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env = os.getenv("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_VAULT_DIR


def _utc_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


def _title(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem.replace("-", " ")


def _excerpt(text: str, limit: int = 220) -> str:
    body = " ".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return body[:limit]


def _tags(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
    counts = Counter(word for word in words if word not in STOPWORDS)
    return [word for word, _count in counts.most_common(8)]


def _note_from_path(path: Path, vault: Path, section: str) -> MemoryNote:
    text = path.read_text(encoding="utf-8", errors="replace")
    words = len(re.findall(r"\S+", text))
    return MemoryNote(
        path=str(path.relative_to(vault)),
        section=section,
        title=_title(path, text),
        excerpt=_excerpt(text),
        words=words,
        modified=_utc_from_timestamp(path.stat().st_mtime),
        tags=_tags(text),
    )


def _scan(vault: Path) -> list[MemoryNote]:
    notes: list[MemoryNote] = []
    for section in MEMORY_SECTIONS:
        root = vault / section["path"]
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.is_file() and path.name != "README.md":
                notes.append(_note_from_path(path, vault, section["name"]))
    return notes


def _payload(vault: Path, notes: list[MemoryNote]) -> dict[str, Any]:
    section_counts = Counter(note.section for note in notes)
    newest = max((note.modified for note in notes), default=None)
    return {
        "vault": str(vault),
        "vault_exists": vault.is_dir(),
        "checked_at": datetime.now(UTC).isoformat(),
        "notes": [note.__dict__ for note in notes],
        "summary": {
            "total_notes": len(notes),
            "sections": dict(sorted(section_counts.items())),
            "newest": newest,
        },
    }


def memory_ingest(vault_path: str | Path | None = None) -> str:
    """Scan mqobsidian memory notes and return a JSON index."""
    vault = _vault(vault_path)
    if not vault.is_dir():
        return json.dumps({
            "vault": str(vault),
            "vault_exists": False,
            "checked_at": datetime.now(UTC).isoformat(),
            "notes": [],
            "summary": {"total_notes": 0, "sections": {}, "newest": None},
            "status": "NO_VAULT",
        }, indent=2)
    payload = _payload(vault, _scan(vault))
    payload["status"] = "OK"
    return json.dumps(payload, indent=2)


def memory_search(query: str, vault_path: str | Path | None = None, limit: int = 10) -> str:
    """Search mqobsidian memory notes by simple local text matching."""
    data = json.loads(memory_ingest(vault_path))
    terms = [term.lower() for term in re.findall(r"\w+", query)]
    results: list[dict[str, Any]] = []
    for note in data["notes"]:
        haystack = " ".join([
            note["path"], note["section"], note["title"], note["excerpt"],
            " ".join(note["tags"]),
        ]).lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            item = dict(note)
            item["score"] = score
            results.append(item)
    results.sort(key=lambda item: (-item["score"], item["path"]))
    return json.dumps({
        "query": query,
        "vault": data["vault"],
        "status": data["status"],
        "count": len(results[:limit]),
        "results": results[:limit],
    }, indent=2)


def memory_summarize(vault_path: str | Path | None = None) -> str:
    """Return a compact section-level summary of mqobsidian memory."""
    data = json.loads(memory_ingest(vault_path))
    sections: dict[str, dict[str, Any]] = {}
    for note in data["notes"]:
        entry = sections.setdefault(note["section"], {
            "notes": 0,
            "words": 0,
            "newest": None,
            "top_tags": Counter(),
        })
        entry["notes"] += 1
        entry["words"] += note["words"]
        entry["newest"] = max(entry["newest"] or note["modified"], note["modified"])
        entry["top_tags"].update(note["tags"])

    serializable = {
        name: {
            "notes": entry["notes"],
            "words": entry["words"],
            "newest": entry["newest"],
            "top_tags": [tag for tag, _count in entry["top_tags"].most_common(8)],
        }
        for name, entry in sorted(sections.items())
    }
    return json.dumps({
        "vault": data["vault"],
        "status": data["status"],
        "total_notes": data["summary"]["total_notes"],
        "sections": serializable,
    }, indent=2)


def memory_link(vault_path: str | Path | None = None, limit: int = 20) -> str:
    """Infer lightweight links between notes that share tags.

    This is read-only: it reports candidate relationships but does not edit
    notes. Link writes can be a later explicit flow.
    """
    data = json.loads(memory_ingest(vault_path))
    notes = data["notes"]
    links: list[dict[str, Any]] = []
    for index, left in enumerate(notes):
        left_tags = set(left["tags"])
        for right in notes[index + 1:]:
            shared = sorted(left_tags & set(right["tags"]))
            if not shared:
                continue
            links.append({
                "source": left["path"],
                "target": right["path"],
                "shared_tags": shared[:6],
                "score": len(shared),
            })
    links.sort(key=lambda item: (-item["score"], item["source"], item["target"]))
    return json.dumps({
        "vault": data["vault"],
        "status": data["status"],
        "count": len(links[:limit]),
        "links": links[:limit],
    }, indent=2)
