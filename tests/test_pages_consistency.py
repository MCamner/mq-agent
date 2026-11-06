"""The Pages site (docs/index.html) is hand-written, so it drifts.

It said the AI commands "need OPENAI_API_KEY" for weeks after #424 made a
local Ollama model the default. These checks tie its claims to the code: every
command it shows must exist in the CLI, and it may not claim a key is needed
while the default provider is local.
"""
from __future__ import annotations

import re
from pathlib import Path

import typer

from mq_agent.config import MqAgentConfig
from mq_agent.main import app

PAGE = Path(__file__).resolve().parents[1] / "docs" / "index.html"


def _cli_tree() -> dict[str, set[str]]:
    group = typer.main.get_command(app)
    tree: dict[str, set[str]] = {}
    for name, command in group.commands.items():  # type: ignore[attr-defined]
        sub = getattr(command, "commands", None)
        tree[name] = set(sub) if sub else set()
    return tree


def missing_commands(page: str) -> list[str]:
    """Commands written as `mq-agent <cmd> [<sub>]` that the CLI does not have."""
    tree = _cli_tree()
    missing = []
    for cmd, sub in re.findall(r"mq-agent ([a-z][a-z0-9-]*)(?: ([a-z][a-z0-9-]*))?", page):
        if cmd not in tree:
            missing.append(cmd)
        elif tree[cmd] and sub and sub not in tree[cmd]:
            missing.append(f"{cmd} {sub}")
    return sorted(set(missing))


def test_every_command_on_the_page_exists() -> None:
    assert missing_commands(PAGE.read_text(encoding="utf-8")) == []


def test_the_check_catches_a_command_the_cli_lacks() -> None:
    assert missing_commands("<pre>mq-agent no-such-command .</pre>") == ["no-such-command"]
    assert missing_commands("<pre>mq-agent mcp no-such-sub</pre>") == ["mcp no-such-sub"]


def test_page_does_not_claim_a_key_while_the_default_is_local() -> None:
    page = PAGE.read_text(encoding="utf-8")
    if MqAgentConfig().provider == "ollama":
        assert "needs OPENAI_API_KEY" not in page
