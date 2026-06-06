"""Render Release Gate v2 output for terminal operators."""
from __future__ import annotations

from typing import Any


def render_release_status(result: dict[str, Any]) -> str:
    status = str(result.get("status", "unknown")).upper()
    lines = [
        "MQ OPERATOR STATUS",
        "",
        "Current release:",
        f"{result.get('repo', 'unknown')} {result.get('target', 'unknown')}",
        "",
        "Gate:",
        status,
        f"Score: {result.get('score', '?')}",
        "",
        "Top blockers:",
    ]
    lines.extend(_numbered([str(item) for item in result.get("blockers", [])]))
    lines.append("")
    lines.append("Warnings:")
    lines.extend(_numbered([str(item) for item in result.get("warnings", [])]))
    lines.append("")
    lines.append("Recommended next action:")
    next_actions = [str(item) for item in result.get("next_actions", [])]
    lines.append(next_actions[0] if next_actions else "No action required.")
    return "\n".join(lines)


def _numbered(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"{index}. {item}" for index, item in enumerate(items[:5], start=1)]
