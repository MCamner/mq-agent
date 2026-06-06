"""Read-only MQ Skill System discovery helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILL_INDEX_SCHEMA_VERSION = "mq.skill_index.v1"
SKILL_RECORD_SCHEMA_VERSION = "mq.skill.v1"
SKILL_ROUTE_SCHEMA_VERSION = "mq.skill_route.v1"
ECOSYSTEM_SKILLS_SCHEMA_VERSION = "mq.ecosystem_skills.v1"
SKILL_EXECUTION_SCHEMA_VERSION = "mq.skill_execution.v1"

MQ_ECOSYSTEM_REPOS = (
    "macos-scripts",
    "mq-agent",
    "mq-mcp",
    "mq-hal",
    "mq-ums",
    "mq-image-analyze",
    "repo-signal",
)

_SKIP_HEADINGS = {
    "skills",
    "built-in-skills",
    "safety-modes",
    "run-a-skill",
}
_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
_SKILL_TABLE_LINK_RE = re.compile(r"\|\s*\[([^\]]+)\]\((skills/[^)]+/SKILL\.md)\)\s*\|([^|]+)\|")


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


@dataclass(frozen=True)
class SkillRoute:
    """Dry-run routing preview for a request and normalized skill index."""

    schema_version: str
    request: str
    selected_skill: str | None
    owner: str | None
    confidence: str
    safety_class: str | None
    requires_approval: bool
    reason: str
    next_action: str
    command: str | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "request": self.request,
            "selected_skill": self.selected_skill,
            "owner": self.owner,
            "confidence": self.confidence,
            "safety_class": self.safety_class,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "next_action": self.next_action,
            "command": self.command,
        }


@dataclass(frozen=True)
class EcosystemSkillSummary:
    """Cross-repo MQ skill inventory summary."""

    schema_version: str
    root: str
    repo_count: int
    repos_with_skills: int
    total_skills: int
    missing_repos: list[str]
    indexes: list[SkillIndex]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "root": self.root,
            "repo_count": self.repo_count,
            "repos_with_skills": self.repos_with_skills,
            "total_skills": self.total_skills,
            "missing_repos": self.missing_repos,
            "indexes": [index.to_dict() for index in self.indexes],
        }


@dataclass(frozen=True)
class SkillExecutionPlan:
    """Approval-gated execution plan for a routed skill command."""

    schema_version: str
    request: str
    selected_skill: str | None
    command: str | None
    approved: bool
    executable: bool
    status: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "request": self.request,
            "selected_skill": self.selected_skill,
            "command": self.command,
            "approved": self.approved,
            "executable": self.executable,
            "status": self.status,
            "reason": self.reason,
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "skill"


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}


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


def _extract_outputs(lines: list[str]) -> list[str]:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith(("output:", "outputs:")):
            value = stripped.split(":", 1)[1].strip().replace("`", "")
            return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _extract_safety_metadata(lines: list[str]) -> tuple[str, bool] | None:
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not lower.startswith(("safety:", "safety class:")):
            continue
        value = stripped.split(":", 1)[1].strip().lower()
        if "requires --approve" in value or "requires approval" in value or value.startswith("approval"):
            return "approval-gated", True
        if "suggest" in value:
            return "suggest", False
        if "read-only" in value or "readonly" in value:
            return "read-only", False
        if "write" in value:
            return "write-capable", True
        return value or "unknown", "approval" in value
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
        if stripped.lower().startswith(("output:", "outputs:")):
            continue
        if stripped.lower().startswith(("safety:", "safety class:")):
            continue
        if stripped.startswith("|"):
            continue
        summary_lines.append(stripped)
    return " ".join(summary_lines)


def _infer_safety(lines: list[str]) -> tuple[str, bool]:
    metadata = _extract_safety_metadata(lines)
    if metadata:
        return metadata
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
        outputs=_extract_outputs(lines),
        command=command,
        source_path=str(source_path),
    )


def _records_from_skill_table(repo: str, skill_path: Path, text: str) -> list[SkillRecord]:
    records: list[SkillRecord] = []
    for line in text.splitlines():
        match = _SKILL_TABLE_LINK_RE.search(line)
        if not match:
            continue
        title = match.group(1).strip()
        linked_path = match.group(2).strip()
        summary = match.group(3).strip()
        skill_id = _slugify(title)
        records.append(SkillRecord(
            schema_version=SKILL_RECORD_SCHEMA_VERSION,
            id=skill_id,
            name=_display_name(title),
            summary=summary,
            owner=repo,
            triggers=[skill_id],
            safety_class="unknown",
            requires_approval=False,
            inputs=[],
            outputs=[],
            source_path=str(skill_path.parent / linked_path),
        ))
    return records


def normalize_skill_records(skill_path: str | Path, repo: str | None = None) -> list[SkillRecord]:
    """Normalize markdown skill sections into mq.skill.v1 records."""
    path = Path(skill_path)
    repo_name = repo or path.parent.resolve().name
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    table_records = _records_from_skill_table(repo_name, path, text)
    if table_records:
        return table_records

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

    for line in text.splitlines():
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


def default_mq_repo_paths(base_path: str | Path = ".") -> list[Path]:
    """Return existing sibling repo paths for the known MQ ecosystem repos."""
    root = Path(base_path).expanduser().resolve()
    parent = root.parent
    return [parent / name for name in MQ_ECOSYSTEM_REPOS if (parent / name).exists()]


def summarize_ecosystem_skills(
    *repo_paths: str | Path,
    base_path: str | Path = ".",
) -> EcosystemSkillSummary:
    """Summarize skill indexes across MQ ecosystem repositories."""
    paths = [Path(path).expanduser().resolve() for path in repo_paths]
    if not paths:
        paths = default_mq_repo_paths(base_path)
    indexes = discover_skill_indexes(*paths)
    missing = [index.repo for index in indexes if not index.exists]
    return EcosystemSkillSummary(
        schema_version=ECOSYSTEM_SKILLS_SCHEMA_VERSION,
        root=str(Path(base_path).expanduser().resolve().parent),
        repo_count=len(indexes),
        repos_with_skills=sum(1 for index in indexes if index.exists),
        total_skills=sum(len(index.skills or []) for index in indexes),
        missing_repos=missing,
        indexes=indexes,
    )


def route_skill_request(request: str, repo_path: str | Path = ".") -> SkillRoute:
    """Preview which normalized skill should handle a request.

    This function is read-only. It inspects normalized skill metadata and returns
    an explainable routing decision without running any command.
    """
    index = discover_skill_index(repo_path)
    skills = index.skills or []
    normalized_request = request.strip()
    request_slug = _slugify(normalized_request)
    request_tokens = _tokens(normalized_request)

    best: tuple[int, SkillRecord] | None = None
    for skill in skills:
        search_parts = [
            skill.id,
            skill.name,
            skill.summary,
            skill.command or "",
            " ".join(skill.triggers),
        ]
        search_text = " ".join(search_parts).lower()
        skill_tokens = set().union(*(_tokens(part) for part in search_parts))
        score = len(request_tokens & skill_tokens)
        if skill.id in request_slug or any(trigger in request_slug for trigger in skill.triggers):
            score += 5
        if normalized_request.lower() in search_text:
            score += 3
        if best is None or score > best[0]:
            best = (score, skill)

    if best is None or best[0] == 0:
        return SkillRoute(
            schema_version=SKILL_ROUTE_SCHEMA_VERSION,
            request=normalized_request,
            selected_skill=None,
            owner=None,
            confidence="none",
            safety_class=None,
            requires_approval=False,
            reason="No normalized skill matched the request.",
            next_action="Inspect available skills with `mq-agent skill list --json`.",
        )

    score, skill = best
    confidence = "high" if score >= 5 else "medium" if score >= 2 else "low"
    next_action = (
        f"Dry-run only. Candidate command: {skill.command}"
        if skill.command
        else "Dry-run only. Inspect this skill before execution behavior is added."
    )
    return SkillRoute(
        schema_version=SKILL_ROUTE_SCHEMA_VERSION,
        request=normalized_request,
        selected_skill=skill.id,
        owner=skill.owner,
        confidence=confidence,
        safety_class=skill.safety_class,
        requires_approval=skill.requires_approval,
        reason=f"Matched request terms against normalized skill `{skill.id}`.",
        next_action=next_action,
        command=skill.command,
    )


def is_existing_mq_agent_command(command: str | None) -> bool:
    """Return whether a command belongs to mq-agent's existing command surface."""
    if not command:
        return False
    stripped = command.strip()
    if not stripped.startswith("mq-agent "):
        return False
    blocked_chars = {";", "|", "&", ">", "<", "$", "\n"}
    return not any(char in stripped for char in blocked_chars)


def plan_skill_execution(request: str, repo_path: str | Path = ".", approve: bool = False) -> SkillExecutionPlan:
    """Plan approval-gated execution for a routed skill command."""
    route = route_skill_request(request, repo_path)
    executable = is_existing_mq_agent_command(route.command)
    if route.selected_skill is None:
        status = "no-route"
        reason = route.reason
    elif not executable:
        status = "not-executable"
        reason = "Selected skill has no supported mq-agent command surface."
    elif not approve:
        status = "needs-approval"
        reason = "Execution requires --approve."
    else:
        status = "approved"
        reason = "Approved for execution through existing mq-agent command surface."

    return SkillExecutionPlan(
        schema_version=SKILL_EXECUTION_SCHEMA_VERSION,
        request=route.request,
        selected_skill=route.selected_skill,
        command=route.command,
        approved=approve,
        executable=executable,
        status=status,
        reason=reason,
    )
