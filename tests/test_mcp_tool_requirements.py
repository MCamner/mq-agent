"""The MCP tool requirements manifest must say exactly what mq-agent calls.

A hand-written list with nothing holding it to the code drifts, which is the
defect the compatibility check exists to catch one level up. The manifest is
therefore compared with the code: every tool name passed literally to a bridge
call, plus every workflow template step, must be declared, and nothing may be
declared that the code no longer calls.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from jsonschema import Draft202012Validator

from mq_agent.tools import mcp_tool_contracts as mtc
from mq_agent.tools.mcp_bridge import MCPBridge, MultiMCPBridge

ROOT = Path(__file__).resolve().parents[1]

# Calls whose first string argument names an MCP tool. `_tool_supports_input`
# takes the bridge first and the tool second; its third argument is a parameter.
_NAME_FIRST = {"call_tool", "call_tool_if_available", "_call_required_tool", "describe_tool"}
_NAME_FIRST_TWO = {"_select_review_tool"}
_NAME_SECOND = {"_tool_supports_input"}


def _called_tools() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "mq_agent").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in _NAME_FIRST:
                picks = node.args[:1]
            elif name in _NAME_FIRST_TWO:
                picks = node.args[:2]
            elif name in _NAME_SECOND:
                picks = node.args[1:2]
            else:
                continue
            found.update(
                a.value for a in picks if isinstance(a, ast.Constant) and isinstance(a.value, str)
            )
    for template in (ROOT / "mq_agent" / "workflows" / "templates").glob("*.json"):
        steps = json.loads(template.read_text(encoding="utf-8")).get("steps", [])
        found.update(step["tool"] for step in steps if "tool" in step)
    return found


def _declared() -> dict[str, dict[str, Any]]:
    return {tool["name"]: tool for tool in mtc.load_requirements()["tools"]}


def test_manifest_validates() -> None:
    schema = json.loads((ROOT / "schemas" / "mcp_tool_requirements.schema.json").read_text("utf-8"))

    assert list(Draft202012Validator(schema).iter_errors(mtc.load_requirements())) == []


def test_every_called_tool_is_declared() -> None:
    assert sorted(_called_tools() - set(_declared())) == []


def test_nothing_is_declared_that_the_code_no_longer_calls() -> None:
    assert sorted(set(_declared()) - _called_tools()) == []


class _Recorder:
    """Stands in for the HTTP bridge and records what each helper sends."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.sent.append((tool, dict(args)))
        return {"ok": True}


def _sent_by_helpers() -> list[tuple[str, dict[str, Any]]]:
    bridge = MultiMCPBridge()
    recorder = _Recorder()
    with (
        patch.object(MCPBridge, "list_tools", return_value=[]),
        patch.object(MCPBridge, "is_available", return_value=True),
        patch.object(bridge, "_call_required_tool", side_effect=recorder),
    ):
        bridge.review_file("README.md", {"receipt": True}, repo_path="/tmp/x")
        bridge.review_diff({"receipt": True})
        bridge.review_repo("/tmp/x", {"receipt": True})
        bridge.image_perception("a.png", producer="p", source_type="screenshot")
        bridge.review_perception({}, producer="p", repo_path="/tmp/x")
        bridge.search_semantic_memory("q")
        bridge.store_semantic_memory("k", "v")
        bridge.get_architecture_decision("ADR-1")
        bridge.learn_status()
        bridge.search_learned_patterns("q")
        bridge.explain_learned_pattern("p")
        bridge.learn_extract_from_last_review("f.py", repo_path="/tmp/x")
        bridge.learn_record("f.py")
        bridge.learn_from_review("f.py", task="t", repo_path="/tmp/x")
        bridge.learn_from_diff("t", "l")
    return recorder.sent


def test_helpers_send_only_declared_arguments() -> None:
    declared = _declared()
    undeclared = []
    for tool, args in _sent_by_helpers():
        need = declared[tool]
        allowed = set(need.get("arguments", [])) | set(need.get("optional_arguments", []))
        undeclared += [(tool, key) for key in args if key not in allowed]

    assert undeclared == []
