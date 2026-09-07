"""Resolve source profiles separately from observed agent discovery."""

import json
import re
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from jsonschema.exceptions import ValidationError

from mq_agent.tools.context_export import parse_frontmatter
from mq_agent.skills.vocabulary import reason, validate

ROOTS = {"codex": ".agents/skills", "claude": ".claude/skills"}


def repository_name(repo: Path) -> str:
    """Use the repository's declared name, including in named worktrees."""
    try:
        data = json.loads((repo / ".mq/repo-contract.json").read_text())
        name = data.get("repo") if isinstance(data, dict) else None
        if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            return name
    except (OSError, ValueError):
        pass
    return repo.name


def resolve_repo(repo: str | Path, repos_root: Path | None = None) -> Path:
    path = Path(repo).expanduser()
    if repos_root is not None and path.name == str(repo):
        explicit = repos_root.expanduser() / path
        if explicit.is_dir():
            return explicit.resolve()
        raise ValueError("Repository directory does not exist under --repos-root.")
    if path.is_dir():
        return path.resolve()
    if path.name == str(repo):
        if repository_name(Path.cwd()) == str(repo):
            return Path.cwd().resolve()
        sibling = (repos_root or Path.home()) / path
        if sibling.is_dir():
            return sibling.resolve()
    raise ValueError("Repository directory does not exist.")


def load_inventory(repo: Path, vocabulary: dict, schema: dict) -> dict:
    sources: dict[str, list[Path]] = {}
    unprofiled = set()
    for rel in ("skills", *ROOTS.values()):
        root = repo / rel
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir()):
            if (folder / "skill-profile.json").is_file():
                sources.setdefault(folder.name, []).append(folder)
            elif (folder / "SKILL.md").is_file():
                unprofiled.add(folder.name)
    entries, reasons = [], []
    for name, folders in sorted(sources.items()):
        try:
            profiles = [
                json.loads((folder / "skill-profile.json").read_text())
                for folder in folders
            ]
            data = profiles[0]
            for profile in profiles:
                validate(profile, schema)
                if profile != data:
                    raise ValueError("Conflicting profiles")
            if data["skill"] != name:
                raise ValueError("Skill identifier differs from directory")
            canonical = repo / "skills" / name
            source = canonical if canonical.exists() else folders[0]
            skill_text = (source / "SKILL.md").read_text()
            if parse_frontmatter(skill_text).get("name") != name:
                raise ValueError("Skill frontmatter name differs")
            for key in ("intents", "domains", "risks", "required_for"):
                dimension = "risks" if key == "required_for" else key
                if set(data[key]) - set(vocabulary[dimension]):
                    raise ValueError("Unknown vocabulary facet")
            if name in data["supersedes"] or set(data["supersedes"]) - set(sources):
                raise ValueError("Invalid supersedes reference")
            discovered = []
            for target, rel in ROOTS.items():
                observed = repo / rel / name / "SKILL.md"
                if observed.is_file() and observed.read_text() == skill_text:
                    discovered.append(target)
            entries.append({"profile": data, "discoverable_targets": discovered})
        except (OSError, ValueError, UnicodeError, ValidationError):
            reasons.append(
                reason(
                    "SKS003_SKILL_PROFILE_INVALID",
                    "Invalid profile, source skill, facet, or conflicting copy.",
                    name,
                )
            )
    try:
        tuple(
            TopologicalSorter(
                {e["profile"]["skill"]: e["profile"]["supersedes"] for e in entries}
            ).static_order()
        )
    except CycleError:
        reasons.append(
            reason("SKS003_SKILL_PROFILE_INVALID", "Cyclic supersedes references.")
        )
        entries = []
    return {
        "entries": entries,
        "unprofiled": sorted(unprofiled - sources.keys()),
        "reasons": reasons,
        "candidate_count": len(sources),
    }
