"""Read-only MQ Skill System discovery helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILL_INDEX_SCHEMA_VERSION = "mq.skill_index.v1"
SKILL_RECORD_SCHEMA_VERSION = "mq.skill.v1"

_SKIP_HEADINGS = {
    "skills",
    "built-in-skills",
    "safety-modes",
    "run-a-skill",
}
_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")


@dataclass(frozen=True)
class SkillIndex:
    """Discovered repo-local skill index metadata.

    This is intentionally only discovery metadata. Normalized skill records
    belong to the next MQ Skill System v2.0 implementation step.
    """

    schema_version: str
    repo: str
    path: str
    exists: bool
    source_type: str | None = None
    size_bytes: int = 0
    line_count: int = 0
    skills: list[SkillRecord] | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "repo": self.repo,
            "path": self.path,
            "exists": self.exists,
            "source_type": self.source_type,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "skills": [skill.to_dict() for skill in (self.skills or [])],
        }


@dataclass(frozen=True)
class SkillRecord:
    """Normalized mq.skill.v1 record derived from repo-local skill metadata."""

    schema_version: str
    id: str
    name: str
    summary: str
    owner: str
    triggers: list[str]
    safety_class: str
    requires_approval: bool
    inputs: list[str]
    outputs: list[str]
    command: str | None = None
    source_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "owner": self.owner,
            "triggers": self.triggers,
            "safety_class": self.safety_class,
            "requires_approval": self.requires_approval,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "command": self.command,
            "source_path": self.source_path,
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "skill"


def _display_name(value: str) -> str:
    acronyms = {"ai": "AI", "ci": "CI", "mcp": "MCP", "mq": "MQ", "ocr": "OCR", "ui": "UI"}
    words = []
    for word in value.replace("-", " ").strip().split():
        words.append(acronyms.get(word.lower(), word.title()))
    return " ".join(words)


def _extract_command(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("command:"):
            return stripped.split(":", 1)[1].strip().replace("`", "")
    return None


def _extract_summary(lines: list[str]) -> str:
    summary_lines: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            if summary_lines:
                break
            continue
        if stripped.lower().startswith("command:"):
            continue
        if stripped.startswith("|"):
            continue
        summary_lines.append(stripped)
    return " ".join(summary_lines)


def _infer_safety(lines: list[str]) -> tuple[str, bool]:
    text = "\n".join(lines).lower()
    if "requires --approve" in text or "requires approval" in text:
        return "approval-gated", True
    if "read-only" in text:
        return "read-only", False
    return "unknown", False


def _record_from_section(repo: str, source_path: Path, title: str, lines: list[str]) -> SkillRecord:
    skill_id = _slugify(title)
    command = _extract_command(lines)
    safety_class, requires_approval = _infer_safety(lines)
    return SkillRecord(
        schema_version=SKILL_RECORD_SCHEMA_VERSION,
        id=skill_id,
        name=_display_name(title),
        summary=_extract_summary(lines),
        owner=repo,
        triggers=[skill_id],
        safety_class=safety_class,
        requires_approval=requires_approval,
        inputs=[],
        outputs=[],
        command=command,
        source_path=str(source_path),
    )


def normalize_skill_records(skill_path: str | Path, repo: str | None = None) -> list[SkillRecord]:
    """Normalize markdown skill sections into mq.skill.v1 records."""
    path = Path(skill_path)
    repo_name = repo or path.parent.resolve().name
    if not path.exists():
        return []

    records: list[SkillRecord] = []
    current_title: str | None = None
    current_level = 0
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if current_title is None:
            return
        if _slugify(current_title) not in _SKIP_HEADINGS:
            records.append(_record_from_section(repo_name, path, current_title, current_lines))
        current_title = None
        current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            slug = _slugify(title)
            if current_title is not None and level <= current_level:
                flush()
            if current_title is None and slug in _SKIP_HEADINGS:
                continue
            if current_title is None:
                current_title = title
                current_level = level
                current_lines = []
            elif slug in _SKIP_HEADINGS:
                flush()
            else:
                current_lines.append(line)
            continue
        if current_title is not None:
            current_lines.append(line)

    flush()
    return records


def discover_skill_index(repo_path: str | Path = ".") -> SkillIndex:
    """Discover a repo-local SKILLS.md file without parsing or executing it."""
    root = Path(repo_path).expanduser().resolve()
    skill_path = root / "SKILLS.md"

    if not skill_path.exists():
        return SkillIndex(
            schema_version=SKILL_INDEX_SCHEMA_VERSION,
            repo=root.name,
            path=str(skill_path),
            exists=False,
        )

    text = skill_path.read_text(encoding="utf-8")
    return SkillIndex(
        schema_version=SKILL_INDEX_SCHEMA_VERSION,
        repo=root.name,
        path=str(skill_path),
        exists=True,
        source_type="markdown",
        size_bytes=skill_path.stat().st_size,
        line_count=len(text.splitlines()),
        skills=normalize_skill_records(skill_path, repo=root.name),
    )


def discover_skill_indexes(*repo_paths: str | Path) -> list[SkillIndex]:
    """Discover skill indexes for one or more repositories."""
    paths = repo_paths or (".",)
    return [discover_skill_index(path) for path in paths]
