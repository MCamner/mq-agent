#!/usr/bin/env python3
"""Render the canonical command reference from the live Typer app.

The repository is the authoritative source for the command surface. This
generator introspects the real Click tree behind `mq_agent.main.app` — there is
no hand-maintained command list anywhere in the pipeline.

Usage:
    python tools/generate_command_reference.py            # write the page
    python tools/generate_command_reference.py --check    # fail if stale

Output: docs/generated/Command-Reference.md

The render is deterministic: children are sorted by name and nothing derived
from the clock, the environment, or the release version enters the page. Two
runs on the same code produce byte-identical Markdown.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import click
import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "generated" / "Command-Reference.md"
PROG_NAME = "mq-agent"

sys.path.insert(0, str(REPO_ROOT))

# Help strings contain shell placeholders like `<name>` and bare URLs. Both are
# valid prose but trip markdownlint (MD033 inline HTML, MD034 bare URL) once
# rendered into a table cell, so they are wrapped in code spans.
_PLACEHOLDER = re.compile(r"<([A-Za-z][\w./-]*)>")
_BARE_URL = re.compile(r"(?<![`(\[])(https?://[^\s`)\]]+)")


@dataclass
class Param:
    """A documented argument or option."""

    names: list[str]
    required: bool
    default: str
    description: str


@dataclass
class Node:
    """A command or group in the CLI tree."""

    name: str
    path: str
    description: str
    is_group: bool
    arguments: list[Param] = field(default_factory=list)
    options: list[Param] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)


def _clean(text: str | None) -> str:
    """Collapse help text into a single Markdown-table-safe line."""
    if not text:
        return ""
    collapsed = " ".join(text.split()).replace("|", r"\|")

    # Escape only outside existing code spans — wrapping a placeholder that is
    # already inside one would split the span and emit literal backticks.
    parts = re.split(r"(`[^`]*`)", collapsed)
    for index, part in enumerate(parts):
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            continue
        part = _PLACEHOLDER.sub(r"`<\1>`", part)
        parts[index] = _BARE_URL.sub(r"`\1`", part)
    return "".join(parts)


def _format_default(param: click.Parameter) -> str:
    value = param.default
    if param.required or value is None:
        return "—"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if value == "":
        return '`""`'
    if isinstance(value, (list, tuple)):
        if not value:
            return "—"
        return ", ".join(f"`{item}`" for item in value)
    return f"`{value}`"


def _argument_name(param: click.Parameter) -> str:
    if param.metavar:
        return param.metavar
    return param.name.upper() if param.name else "ARG"


def _collect_params(command: click.Command) -> tuple[list[Param], list[Param]]:
    arguments: list[Param] = []
    options: list[Param] = []

    for param in command.params:
        if isinstance(param, click.Argument):
            arguments.append(
                Param(
                    names=[_argument_name(param)],
                    required=bool(param.required),
                    default=_format_default(param),
                    description=_clean(getattr(param, "help", None)),
                )
            )
            continue

        if not isinstance(param, click.Option):
            continue
        # Click injects --help into every command; it is not part of the
        # surface this page documents.
        if param.name == "help" and param.opts == ["--help"]:
            continue

        names = list(param.opts) + list(param.secondary_opts)
        options.append(
            Param(
                names=names,
                required=bool(param.required),
                default=_format_default(param),
                description=_clean(param.help),
            )
        )

    return arguments, options


def _build(command: click.Command, name: str, parents: list[str]) -> Node:
    path = " ".join([PROG_NAME, *parents, name]) if name else PROG_NAME
    arguments, options = _collect_params(command)
    is_group = isinstance(command, click.Group)

    node = Node(
        name=name,
        path=path,
        description=_clean(command.help or command.short_help),
        is_group=is_group,
        arguments=arguments,
        options=options,
    )

    if isinstance(command, click.Group):
        for child_name in sorted(command.commands):
            node.children.append(
                _build(
                    command.commands[child_name],
                    child_name,
                    [*parents, name] if name else parents,
                )
            )

    return node


def build_tree() -> Node:
    """Introspect the live Typer app into a deterministic tree."""
    from mq_agent.main import app

    root = typer.main.get_command(app)
    if not isinstance(root, click.Group):  # pragma: no cover - defensive
        raise TypeError("mq_agent.main.app did not resolve to a Click group")
    return _build(root, "", [])


def walk(node: Node) -> Iterator[Node]:
    """Yield every descendant of `node`, depth-first, excluding the root."""
    for child in node.children:
        yield child
        yield from walk(child)


def _anchor(path: str) -> str:
    """GitHub heading anchor for a ``## `path` `` heading."""
    return path.replace(" ", "-").replace("`", "").lower()


def _param_table(header: str, params: list[Param]) -> list[str]:
    lines = [
        f"| {header} | Required | Default | Description |",
        "|---|---:|---|---|",
    ]
    for param in params:
        names = ", ".join(f"`{n}`" for n in param.names)
        required = "Yes" if param.required else "No"
        description = param.description or "—"
        lines.append(
            f"| {names} | {required} | {param.default} | {description} |"
        )
    return lines


def _render_node(node: Node) -> list[str]:
    lines = [f"## `{node.path}`", ""]
    lines.append(node.description or "_No description._")
    lines.append("")

    if node.is_group and node.children:
        lines.append("### Subcommands")
        lines.append("")
        lines.append("| Subcommand | Description |")
        lines.append("|---|---|")
        for child in node.children:
            lines.append(
                f"| [`{child.path}`](#{_anchor(child.path)}) "
                f"| {child.description or '—'} |"
            )
        lines.append("")

    if node.arguments:
        lines.append("### Arguments")
        lines.append("")
        lines.extend(_param_table("Argument", node.arguments))
        lines.append("")

    if node.options:
        lines.append("### Options")
        lines.append("")
        lines.extend(_param_table("Option", node.options))
        lines.append("")

    return lines


def render() -> str:
    """Render the full reference as Markdown."""
    tree = build_tree()
    nodes = list(walk(tree))

    lines = [
        "# Command Reference",
        "",
        "Auto-generated from the live Typer application by",
        "`tools/generate_command_reference.py`. Do not edit by hand — run the",
        "generator and commit the result.",
        "",
        "The repository is the authoritative source for the command surface.",
        "This page is a projection of it.",
        "",
        "## Overview",
        "",
        "| Command | Type | Description |",
        "|---|---|---|",
    ]

    for child in tree.children:
        kind = "group" if child.is_group else "command"
        lines.append(
            f"| [`{child.path}`](#{_anchor(child.path)}) | {kind} "
            f"| {child.description or '—'} |"
        )

    lines.append("")

    for node in nodes:
        lines.extend(_render_node(node))

    # Normalise: no trailing blank lines, exactly one terminating newline.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the mq-agent command reference."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the file on disk differs from a fresh render.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Target path (defaults to docs/generated/Command-Reference.md).",
    )
    args = parser.parse_args(argv)

    content = render()
    output: Path = args.output

    if args.check:
        if not output.is_file():
            print(f"[error] {output} is missing — run the generator.")
            return 1
        if output.read_text(encoding="utf-8") != content:
            print(
                f"[error] {output} is stale — run "
                "`python tools/generate_command_reference.py` and commit."
            )
            return 1
        print(f"[ok] {output} is up to date.")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    total = len(list(walk(build_tree())))
    print(f"[ok] Wrote {output} ({total} documented command paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
