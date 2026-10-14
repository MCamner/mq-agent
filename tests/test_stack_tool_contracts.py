"""MCP tool contract checking: mq-agent's declared tool use against each
producer's committed `mq-mcp.tool-surface.v1`.

The check reads files, never a running server: a server can lag main, and a
stopped one is not evidence of anything. A producer that publishes no surface
yet is SKIPPED (nothing to assess), not UNAVAILABLE and not FAIL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from mq_agent.tools import mcp_tool_contracts as mtc
from mq_agent.tools.stack_compatibility import build_report, release_blockers
from tests.test_stack_compatibility import DECLARED_MCP_1X, _make_repo

ROOT = Path(__file__).resolve().parents[1]


def _surface(*tools: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "mq-mcp.tool-surface.v1",
        "producer": "mq-mcp",
        "tool_count": len(tools),
        "tools": list(tools),
    }


def _tool(name: str, cls: str = "A", params: tuple[tuple[str, bool], ...] = ()) -> dict[str, Any]:
    return {
        "name": name,
        "safety_class": cls,
        "write": cls == "C",
        "subprocess": cls == "D",
        "parameters": [{"name": n, "type": ["string"], "required": r} for n, r in params],
        "signature_sha256": "0" * 64,
    }


def _need(name: str, **kw: Any) -> dict[str, Any]:
    need = {"name": name, "producer": "mq-mcp", "max_safety_class": "A", "arguments": []}
    need.update(kw)
    return need


def _producer(tmp_path: Path, surface: dict[str, Any] | None, name: str = "mq-mcp") -> Path:
    root = tmp_path / name
    (root / "contracts").mkdir(parents=True)
    schema = ROOT / "tests" / "fixtures" / "tool_surface.v1.schema.json"
    (root / "contracts" / "tool_surface.v1.schema.json").write_text(schema.read_text("utf-8"), "utf-8")
    if surface is not None:
        (root / "contracts" / "tool_surface.v1.json").write_text(json.dumps(surface), "utf-8")
    return root


def _check(tmp_path: Path, surface: dict[str, Any] | None, *needs: dict[str, Any]):
    root = _producer(tmp_path, surface)
    return mtc.tool_contract_findings({"mq-mcp": root}, {"tools": list(needs)})


def _codes(findings: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return sorted((f["code"], f["severity"]) for f in findings)


# --- one test per outcome -------------------------------------------------


def test_matching_use_produces_no_findings(tmp_path: Path) -> None:
    _, findings = _check(
        tmp_path,
        _surface(_tool("review_file", "B", (("relative_path", True), ("mode", False)))),
        _need("review_file", max_safety_class="B", arguments=["relative_path", "mode"]),
    )

    assert findings == []


def test_absent_tool_fails(tmp_path: Path) -> None:
    _, findings = _check(tmp_path, _surface(), _need("gone_tool"))

    assert _codes(findings) == [("MQC019_TOOL_NOT_PRODUCED", "FAIL")]
    assert findings[0]["repos"] == ["mq-agent", "mq-mcp"]
    assert findings[0]["blocks_release"] is True


def test_absent_optional_tool_warns(tmp_path: Path) -> None:
    _, findings = _check(tmp_path, _surface(), _need("risk_review_repo", optional_tool=True))

    assert _codes(findings) == [("MQC019_TOOL_NOT_PRODUCED", "WARN")]
    assert findings[0]["blocks_release"] is False


def test_escalated_class_fails(tmp_path: Path) -> None:
    _, findings = _check(tmp_path, _surface(_tool("read_it", "C")), _need("read_it", max_safety_class="B"))

    assert _codes(findings) == [("MQC020_TOOL_SAFETY_ESCALATED", "FAIL")]
    assert "C" in findings[0]["message"] and "B" in findings[0]["message"]


def test_a_lower_class_is_fine(tmp_path: Path) -> None:
    _, findings = _check(tmp_path, _surface(_tool("t", "A")), _need("t", max_safety_class="C"))

    assert findings == []


def test_undeclared_argument_fails(tmp_path: Path) -> None:
    _, findings = _check(
        tmp_path,
        _surface(_tool("get_architecture_decision", "A", (("adr_id", True),))),
        _need("get_architecture_decision", arguments=["id"]),
    )

    assert _codes(findings) == [
        ("MQC021_TOOL_ARGUMENT_UNDECLARED", "FAIL"),
        ("MQC022_TOOL_REQUIRED_ARGUMENT_UNSENT", "FAIL"),
    ]


def test_undeclared_optional_argument_only_warns(tmp_path: Path) -> None:
    _, findings = _check(
        tmp_path,
        _surface(_tool("review_repo", "B", (("mode", False),))),
        _need("review_repo", max_safety_class="B", arguments=["mode"], optional_arguments=["structured"]),
    )

    assert _codes(findings) == [("MQC021_TOOL_ARGUMENT_UNDECLARED", "WARN")]


def test_context_arguments_satisfy_requirements_and_are_never_undeclared(tmp_path: Path) -> None:
    _, findings = _check(
        tmp_path,
        _surface(_tool("run_tests", "D", (("repo_name", True),))),
        _need("run_tests", max_safety_class="D", context_arguments=["repo_path", "repo_name"]),
    )

    assert findings == []


def test_missing_surface_is_skipped_not_failed(tmp_path: Path) -> None:
    relationships, findings = _check(tmp_path, None, _need("anything"))

    assert _codes(findings) == [("MQC023_TOOL_SURFACE_UNAVAILABLE", "SKIPPED")]
    assert findings[0]["blocks_release"] is False
    assert relationships[0]["status"] == "SKIPPED"


def test_invalid_surface_fails_the_producer(tmp_path: Path) -> None:
    broken = _surface(_tool("t"))
    broken["tools"][0]["safety_class"] = "read-only"

    _, findings = _check(tmp_path, broken, _need("t"))

    assert _codes(findings) == [("MQC023_TOOL_SURFACE_UNAVAILABLE", "FAIL")]
    assert findings[0]["repos"] == ["mq-agent", "mq-mcp"]


def test_a_producer_outside_the_inventory_is_not_assessed(tmp_path: Path) -> None:
    relationships, findings = mtc.tool_contract_findings(
        {}, {"tools": [_need("observe_architecture", producer="mq-image-analyze")]}
    )

    assert (relationships, findings) == ([], [])


def test_relationship_summarises_the_pair(tmp_path: Path) -> None:
    relationships, _ = _check(
        tmp_path, _surface(_tool("a"), _tool("b")), _need("a"), _need("b")
    )

    assert relationships == [
        {
            "producer": "mq-mcp",
            "consumer": "mq-agent",
            "subject": "mq-mcp.tool-surface.v1",
            "status": "PASS",
            "overlap": None,
            "detail": "2 tools mq-agent calls checked against mq-mcp's published surface",
        }
    ]


# --- in the report --------------------------------------------------------


def test_report_carries_tool_findings_and_validates(tmp_path: Path, monkeypatch) -> None:
    root = _producer(tmp_path, _surface())
    monkeypatch.setattr(mtc, "load_requirements", lambda: {"tools": [_need("gone_tool")]})

    report = build_report(repos=[{"name": "mq-mcp", "path": str(root)}], tracked=())

    assert ("MQC019_TOOL_NOT_PRODUCED", "FAIL") in _codes(report["findings"])
    assert report["status"] == "FAIL"
    assert "mq-agent" in release_blockers(report)
    schema = json.loads((ROOT / "schemas" / "mq_stack_compatibility.schema.json").read_text("utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(report)) == []


def test_report_status_is_unchanged_when_no_producer_publishes(tmp_path: Path, monkeypatch) -> None:
    """The masking trap: a SKIPPED pair must not lift a clean stack to a
    non-zero exit."""
    entry = _make_repo(tmp_path, "mq-mcp", compat=DECLARED_MCP_1X)
    monkeypatch.setattr(mtc, "load_requirements", lambda: {"tools": [_need("x")]})

    with_check = build_report(repos=[entry], slice_only=False)
    monkeypatch.setattr(mtc, "load_requirements", lambda: {"tools": []})
    without_check = build_report(repos=[entry], slice_only=False)

    assert without_check["status"] == "PASS"
    assert with_check["status"] == without_check["status"]
    assert with_check["next_action"] == without_check["next_action"]
    assert ("MQC023_TOOL_SURFACE_UNAVAILABLE", "SKIPPED") in _codes(with_check["findings"])
