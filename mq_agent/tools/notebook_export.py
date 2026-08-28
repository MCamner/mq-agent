"""Local, provider-neutral NotebookLM source-pack generation.

mqobsidian owns the profile and manifest schema. mq-agent consumes both and
materializes a reviewed source set locally. This module performs no network,
authentication, provider sync, or write-back operation.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

from mq_agent import __version__
from mq_agent.tools.context_export import default_vault

MAX_SOURCE_BYTES = 1_000_000
FORBIDDEN_INCLUDES = {"*", "**", "systems", "systems/**", "memory", "memory/**"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_pattern(pattern: str) -> None:
    parts = PurePosixPath(pattern).parts
    if pattern.startswith("/") or ".." in parts or "\\" in pattern:
        raise ValueError(f"unsafe include path: {pattern}")
    if pattern.rstrip("/") in FORBIDDEN_INCLUDES:
        raise ValueError(f"include is too broad: {pattern}")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _excluded(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def _source_kind(relative: str) -> str:
    if "decision-records/" in relative:
        return "decision"
    if "architecture" in relative or "codegraph" in relative:
        return "architecture"
    if "contract" in relative or relative.endswith("memory-model.md"):
        return "contract"
    if "roadmap" in relative:
        return "roadmap"
    return "overview"


def _git_revision(vault: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(vault), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _dirty_paths(vault: Path) -> set[str]:
    """Vault-relative paths whose content differs from the recorded commit."""
    result = subprocess.run(
        ["git", "-C", str(vault), "status", "--porcelain", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    dirty: set[str] = set()
    fields = result.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        dirty.add(path)
        # Renames and copies carry the original path in the next field.
        if "R" in status or "C" in status:
            if index < len(fields):
                dirty.add(fields[index])
                index += 1
    return dirty


def _select_sources(vault: Path, notebook: dict[str, Any]) -> list[tuple[str, bytes]]:
    includes = notebook.get("include")
    excludes = notebook.get("exclude", [])
    if not isinstance(includes, list) or not includes:
        raise ValueError("notebook include must be a non-empty list")
    if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
        raise ValueError("notebook exclude must be a string list")

    selected: dict[str, bytes] = {}
    for pattern in includes:
        if not isinstance(pattern, str):
            raise ValueError("notebook include entries must be strings")
        _safe_pattern(pattern)
        for candidate in sorted(vault.glob(pattern)):
            resolved = candidate.resolve()
            if not candidate.is_file() or not _inside(resolved, vault):
                continue
            relative = candidate.relative_to(vault).as_posix()
            if _excluded(relative, excludes):
                continue
            if candidate.suffix.lower() != ".md":
                raise ValueError(f"unsupported source type: {relative}")
            if candidate.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError(f"source exceeds {MAX_SOURCE_BYTES} bytes: {relative}")
            selected[relative] = candidate.read_bytes()
    if not selected:
        raise ValueError("notebook allowlist selected no sources")
    return sorted(selected.items())


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def build_notebook_pack(
    notebook_id: str,
    *,
    vault: Path | None = None,
    output_root: Path | None = None,
    write: bool = False,
    replace: bool = False,
) -> dict[str, Any]:
    """Preview or materialize one notebook pack from mqobsidian's profile."""
    vault = (vault or default_vault()).expanduser().resolve()
    profile = _load_json(vault / ".mq" / "notebooks.json", "notebook profile")
    notebooks = profile.get("notebooks")
    if not isinstance(notebooks, dict) or notebook_id not in notebooks:
        raise ValueError(f"unknown notebook: {notebook_id}")
    notebook = notebooks[notebook_id]
    if not isinstance(notebook, dict):
        raise ValueError(f"invalid notebook profile: {notebook_id}")
    if profile.get("role") != "consumer" or profile.get("write_back") is not False:
        raise ValueError("notebook profile must be a read-only consumer")
    reviewed = notebook.get("source_lanes", {}).get("reviewed", {})
    observed = notebook.get("source_lanes", {}).get("observed", {})
    if reviewed != {"provider": "mqobsidian", "status": "active"}:
        raise ValueError("reviewed source lane must be active mqobsidian")
    if observed.get("status") != "deferred":
        raise ValueError("observed source lane is not supported in this exporter")

    sources = _select_sources(vault, notebook)
    classification = notebook.get("classification")
    if classification not in {"public-safe", "approved-external"}:
        raise ValueError(f"unsupported classification: {classification}")
    revision = _git_revision(vault)
    dirty_paths = _dirty_paths(vault) if revision else set()

    manifest_sources: list[dict[str, Any]] = []
    rendered: dict[str, bytes] = {}
    for relative, content in sources:
        digest = _sha256(content)
        entry: dict[str, Any] = {
            "path": relative,
            "kind": _source_kind(relative),
            "classification": classification,
            "sha256": digest,
        }
        if revision:
            entry["revision"] = {
                "repository": vault.name,
                "commit": revision,
                # sha256 describes the working tree; say so when it and the
                # commit can disagree, instead of implying commit-bound content.
                "dirty": relative in dirty_paths,
            }
        manifest_sources.append(entry)
        # Plain text, never markup: a file opening with `<!--` is sniffed as
        # HTML by NotebookLM, yields no body, and is rejected as invalid. Plain
        # lines also let the reading model cite the originating vault path,
        # which a comment cannot.
        header_lines = [f"Source: {relative}", f"SHA-256: {digest}"]
        if revision:
            state = " (uncommitted changes)" if relative in dirty_paths else ""
            header_lines.append(f"Repository: {vault.name} @ {revision}{state}")
        header = ("\n".join(header_lines) + "\n\n").encode("utf-8")
        rendered[f"sources/{relative}"] = header + content

    canonical = json.dumps(manifest_sources, sort_keys=True, separators=(",", ":")).encode()
    content_hash = _sha256(canonical)
    manifest = {
        "schema": "notebook-pack.v1",
        "notebook": {
            "id": notebook_id,
            "purpose": notebook.get("purpose", ""),
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": {"name": "mq-agent", "version": __version__},
        "sources": manifest_sources,
        "content_hash": content_hash,
    }
    schema = _load_json(vault / "schemas" / "notebook-pack.v1.json", "notebook pack schema")
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda err: list(err.path))
    if errors:
        raise ValueError(f"manifest violates notebook-pack.v1: {errors[0].message}")

    root = (output_root or (vault / str(profile.get("output_root", ".notebooklm")))).expanduser().resolve()
    pack_dir = root / notebook_id
    would_write = sorted(["manifest.json", *rendered])
    written: list[str] = []
    if write:
        if pack_dir.exists() and not replace:
            raise ValueError(f"pack already exists; use --replace: {pack_dir}")
        temporary = root / f".{notebook_id}.tmp-{os.getpid()}"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        for relative, content in rendered.items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written.append(str(pack_dir / relative))
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written.append(str(pack_dir / "manifest.json"))
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
        root.mkdir(parents=True, exist_ok=True)
        temporary.replace(pack_dir)

    dirty_sources = [
        source["path"]
        for source in manifest_sources
        if source.get("revision", {}).get("dirty")
    ]
    return {
        "notebook": notebook_id,
        "display_name": notebook.get("display_name", notebook_id),
        "vault": str(vault),
        "pack_dir": str(pack_dir),
        "dry_run": not write,
        "source_count": len(sources),
        "dirty_source_count": len(dirty_sources),
        "dirty_sources": dirty_sources,
        "content_hash": content_hash,
        "would_write": would_write if not write else [],
        "written": sorted(written),
        "manifest": manifest,
    }
