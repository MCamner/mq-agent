"""b2tui bridge tools — read-only access to the B2 prompt library and history."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

VAULT = Path.home() / "mqobsidian"
PROMPTS_DIR = VAULT / "_prompts" / "saved-prompts-md-export"
HISTORY_FILE = Path.home() / ".b2tui_history.jsonl"

SKIP_FILES = {"INDEX.md", "README.md", "EXPORT_NOTES.md", "PROMPT_EXPORT_INDEX.md"}

ROUTES: dict[str, list[str]] = {
    "architecture": [
        "design", "blueprint", "component", "integration", "structure",
        "arkitektur", "system", "hld", "lld", "requirements", "krav",
    ],
    "implementation": [
        "kod", "code", "config", "flow", "test", "rollback",
        "implementation", "bygga", "bygg", "deploy", "operationer", "raci",
    ],
    "review": [
        "granska", "review", "audit", "kontrakt", "repo-status",
        "inspect", "check", "kritik",
    ],
    "research": [
        "undersök", "tech", "evaluation", "research", "ny teknik",
        "market", "analys", "jämför", "compare",
    ],
    "content": [
        "rapport", "presentation", "tui", "tool", "docs", "interactive",
        "report", "write", "skriva", "content",
    ],
    "learning": [
        "förstå", "lär", "concept", "repetera", "learning",
        "explain", "förklara", "feynman",
    ],
    "decision": [
        "prioritera", "välj", "approach", "roadmap", "decision",
        "decide", "strategi", "strategy",
    ],
}

ROUTE_PRIMARY: dict[str, str] = {
    "architecture": "02.11",
    "implementation": "02.03",
    "review": "02.10",
    "research": "04.02",
    "content": "05.03",
    "learning": "06.01",
    "decision": "03.04",
}


@dataclass
class PromptMeta:
    id: str
    name: str
    category: str
    path: str


def _parse_id(filename: str) -> str:
    m = re.match(r"^(\d+\.\d+)", filename)
    return m.group(1) if m else ""


def _parse_name(filename: str) -> str:
    stem = Path(filename).stem
    m = re.match(r"^\d+\.\d+_?(.*)", stem)
    raw = m.group(1) if m else stem
    return raw.replace("_", " ").strip()


def _parse_category(dir_name: str) -> str:
    m = re.match(r"^\d+_(.*)", dir_name)
    raw = m.group(1) if m else dir_name
    return raw.replace("_", " ")


def _load_prompt_index() -> list[PromptMeta]:
    if not PROMPTS_DIR.exists():
        return []
    prompts: list[PromptMeta] = []
    for cat_dir in sorted(PROMPTS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        category = _parse_category(cat_dir.name)
        for f in sorted(cat_dir.iterdir()):
            if f.name in SKIP_FILES or f.suffix != ".md":
                continue
            pid = _parse_id(f.name)
            if not pid:
                continue
            prompts.append(PromptMeta(
                id=pid,
                name=_parse_name(f.name),
                category=category,
                path=str(f),
            ))
    return prompts


def b2_list_prompts(category: str = "") -> str:
    """List available B2 prompts, optionally filtered by category."""
    prompts = _load_prompt_index()
    if category:
        prompts = [p for p in prompts if category.lower() in p.category.lower()]
    if not prompts:
        return f"No prompts found{f' in category {category!r}' if category else ''}. Vault: {PROMPTS_DIR}"
    lines = [f"{p.id}  [{p.category}]  {p.name}" for p in prompts]
    return "\n".join(lines)


def b2_route(topic: str) -> str:
    """Route a topic string to a B2 route and return the primary prompt ID (e.g. '02.11').

    Returns the prompt_id string directly so it can be piped into b2_get_prompt.
    """
    topic_lower = topic.lower()
    matched_route: str | None = None
    for route, keywords in ROUTES.items():
        if any(kw in topic_lower for kw in keywords):
            matched_route = route
            break
    if matched_route is None:
        matched_route = "implementation"
    return ROUTE_PRIMARY[matched_route]


def b2_route_info(topic: str) -> str:
    """Route a topic and return full JSON: route name, prompt_id, prompt_name."""
    topic_lower = topic.lower()
    matched_route: str | None = None
    for route, keywords in ROUTES.items():
        if any(kw in topic_lower for kw in keywords):
            matched_route = route
            break
    if matched_route is None:
        matched_route = "implementation"

    primary_id = ROUTE_PRIMARY[matched_route]
    prompts = _load_prompt_index()
    prompt_name = next((p.name for p in prompts if p.id == primary_id), primary_id)

    return json.dumps({
        "route": matched_route,
        "prompt_id": primary_id,
        "prompt_name": prompt_name,
    }, ensure_ascii=False)


def b2_get_prompt(prompt_id: str) -> str:
    """Read the markdown content of a B2 prompt by its ID (e.g. '02.11')."""
    prompts = _load_prompt_index()
    meta = next((p for p in prompts if p.id == prompt_id), None)
    if meta is None:
        return f"Prompt not found: {prompt_id}"
    p = Path(meta.path)
    if not p.exists():
        return f"Prompt file missing: {meta.path}"
    return p.read_text(errors="replace")


def b2_history(limit: int = 10) -> str:
    """Read the last N entries from b2tui run history. Returns JSON array."""
    if not HISTORY_FILE.exists():
        return "[]"
    lines = HISTORY_FILE.read_text().splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return json.dumps(entries[-limit:], indent=2)


def b2_log_run(prompt_id: str, context: str = "", result: str = "") -> str:
    """Append a workflow run entry to ~/.b2tui_history.jsonl."""
    prompts = _load_prompt_index()
    meta = next((p for p in prompts if p.id == prompt_id), None)
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "prompt_id": prompt_id,
        "prompt_name": meta.name if meta else prompt_id,
        "category": meta.category if meta else "",
        "context": context,
        "result_preview": result[:200] if result else "",
        "source": "mq-agent",
    }
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return f"Logged run: {prompt_id} at {entry['timestamp']}"
