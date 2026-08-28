"""Pack guidance states CodeGraph intentions, never MCP tool names.

The MCP surface varies by installed CodeGraph version: 1.5.0 exposes a single
tool, `codegraph_explore`, while the CLI keeps `callers`, `callees`, `impact`
and `node` as separate commands, and the CLI's own help still refers to a
`codegraph_node` MCP tool. Naming a tool in generated guidance can therefore
point an agent at a call it cannot make, and which names are "current" depends
on what the reader has installed.

mqobsidian made the same change to its reference generator; both sides now emit
intentions so a pack reads the same whichever produced it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mq_agent.tools.context_pack import (
    build_codegraph_queries,
    load_selection_vocabulary,
)

OWN_SYMBOLS = {"codegraph_queries", "codegraph_section", "codegraph_symbols"}
TOOL_NAME = re.compile(r"codegraph_[a-z_]+")

VOCABULARY = {
    "schema": "context-selection-vocabulary.v1",
    "source_heavy_hints": ["caller", "trace", "impact"],
    "source_heavy_suppress": ["readme"],
    "max_codegraph_queries": 5,
}


def _tool_names(text: str) -> set[str]:
    return {m for m in TOOL_NAME.findall(text) if m not in OWN_SYMBOLS}


def _vocabulary(tmp_path: Path):
    vault = tmp_path / "mqobsidian" / ".mq"
    vault.mkdir(parents=True)
    (vault / "context-selection-vocabulary.json").write_text(
        json.dumps(VOCABULARY), encoding="utf-8"
    )
    return load_selection_vocabulary(tmp_path / "mqobsidian")


def _queries(tmp_path: Path) -> list[str]:
    return build_codegraph_queries(
        "trace callers of build_task_pack",
        ["mq-agent"],
        ["mq-agent/mq_agent/tools/context_pack.py"],
        ["build_task_pack"],
        "on",
        _vocabulary(tmp_path),
    )


def test_guidance_names_no_mcp_tool(tmp_path):
    queries = _queries(tmp_path)

    assert queries, "expected guidance for a source-heavy task"
    found = _tool_names("\n".join(queries))
    assert found == set(), (
        f"guidance names MCP tools {sorted(found)}; the MCP surface varies by "
        "installed CodeGraph version, so state the intention instead"
    )


def test_intentions_stay_distinct(tmp_path):
    # Dropping tool names must not flatten the guidance into one repeated line.
    queries = _queries(tmp_path)

    assert len(queries) > 1
    assert len(queries) == len(set(queries)), "guidance repeated itself"


def test_symbol_and_file_intentions_survive(tmp_path):
    queries = _queries(tmp_path)
    body = "\n".join(queries)

    assert "callers of" in body
    assert "blast radius" in body
    assert "context_pack.py" in body
