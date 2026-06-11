"""Vault structure — the standard mqobsidian export layout.

mq-agent and mq-mcp write durable memory (truth notes, reviews, learned
patterns, run logs) into the mqobsidian vault. This module defines the
standard directory layout, checks the vault against it, and can create the
missing directories on request.

Read-only by default; `init=True` creates missing standard directories and
drops a small README.md in each created one so the vault stays
self-documenting. The vault itself is never created — a missing vault is an
error, not something to silently bootstrap.

Vault path: MQ_OBSIDIAN_DIR env var, or ~/mqobsidian (same contract as
mq-mcp's obsidian_writer).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_VAULT_DIR = Path.home() / "mqobsidian"

# The standard export structure (v1.15.0). One entry per directory:
# where it lives, what lands there, and which command writes it.
STANDARD_DIRS: tuple[dict[str, str], ...] = (
    {
        "path": "memory/stack-truth",
        "purpose": "Dated stack truth snapshots (contract + release gates)",
        "writer": "mq-agent stack truth-export",
    },
    {
        "path": "memory/reviews",
        "purpose": "Code review summaries",
        "writer": "mq-mcp brain_record_review (mq-agent review --brain)",
    },
    {
        "path": "memory/learn",
        "purpose": "Learned patterns and verified promotions",
        "writer": "mq-mcp brain_record_learning (mq-agent learn --brain)",
    },
    {
        "path": "mq-stack/runs",
        "purpose": "Stack run logs (sweeps, orchestrated releases)",
        "writer": "mq-agent stack release / stack sweep",
    },
    {
        "path": "mq-stack/roadmaps",
        "purpose": "Exported per-repo roadmaps",
        "writer": "manual export (reserved)",
    },
)

# Vault-root directories that predate the standard layout. mq-mcp's
# obsidian_writer still targets these; they are reported, never touched.
LEGACY_DIRS: tuple[dict[str, str], ...] = (
    {"path": "reviews", "standard": "memory/reviews"},
    {"path": "learn", "standard": "memory/learn"},
)


def _vault() -> Path:
    env = os.getenv("MQ_OBSIDIAN_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_VAULT_DIR


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _note_stats(directory: Path) -> tuple[int, str | None]:
    """Count markdown notes (recursively) and date the newest one."""
    notes = [p for p in directory.rglob("*.md") if p.is_file()]
    if not notes:
        return 0, None
    newest = max(p.stat().st_mtime for p in notes)
    return len(notes), datetime.fromtimestamp(newest, UTC).date().isoformat()


def _dir_entry(vault: Path, spec: dict[str, str]) -> dict[str, Any]:
    full = vault / spec["path"]
    exists = full.is_dir()
    notes, newest = _note_stats(full) if exists else (0, None)
    return {
        "path": spec["path"],
        "purpose": spec["purpose"],
        "writer": spec["writer"],
        "exists": exists,
        "notes": notes,
        "newest": newest,
    }


def _legacy_entry(vault: Path, spec: dict[str, str]) -> dict[str, Any] | None:
    full = vault / spec["path"]
    if not full.is_dir():
        return None
    notes, newest = _note_stats(full)
    if notes == 0:
        return None
    return {
        "path": spec["path"],
        "standard": spec["standard"],
        "notes": notes,
        "newest": newest,
    }


def _readme(spec: dict[str, str]) -> str:
    return (
        f"# {spec['path']}\n"
        f"\n"
        f"{spec['purpose']}.\n"
        f"\n"
        f"Writer: `{spec['writer']}`. Part of the standard mq-stack vault\n"
        f"structure — see `mq-agent brain structure`.\n"
    )


def vault_structure(init: bool = False) -> str:
    """Check the mqobsidian vault against the standard export structure.

    With init=True, create missing standard directories (each with a small
    README.md). Returns a JSON string.
    """
    vault = _vault()
    result: dict[str, Any] = {
        "vault": str(vault),
        "vault_exists": vault.is_dir(),
        "checked_at": _utc_now().isoformat(),
        "dirs": [],
        "legacy": [],
        "created": [],
    }

    if not result["vault_exists"]:
        result["status"] = "NO_VAULT"
        return json.dumps(result, indent=2)

    if init:
        for spec in STANDARD_DIRS:
            full = vault / spec["path"]
            if not full.is_dir():
                full.mkdir(parents=True)
                (full / "README.md").write_text(_readme(spec), encoding="utf-8")
                result["created"].append(spec["path"])

    result["dirs"] = [_dir_entry(vault, spec) for spec in STANDARD_DIRS]
    result["legacy"] = [
        entry for spec in LEGACY_DIRS if (entry := _legacy_entry(vault, spec))
    ]
    result["status"] = "OK" if all(d["exists"] for d in result["dirs"]) else "INCOMPLETE"
    return json.dumps(result, indent=2)
