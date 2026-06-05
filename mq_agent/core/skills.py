"""Read-only MQ Skill System discovery helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILL_INDEX_SCHEMA_VERSION = "mq.skill_index.v1"


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

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "repo": self.repo,
            "path": self.path,
            "exists": self.exists,
            "source_type": self.source_type,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
        }


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
    )


def discover_skill_indexes(*repo_paths: str | Path) -> list[SkillIndex]:
    """Discover skill indexes for one or more repositories."""
    paths = repo_paths or (".",)
    return [discover_skill_index(path) for path in paths]
