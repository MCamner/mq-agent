"""`stack compatibility --live`: a running server against its committed surface.

The committed `mq-mcp.tool-surface.v1` is the source of truth; a running
server can lag it (a process started from an old checkout). --live reports
that drift as MQC024 WARN with both commits. It never blocks a release, and a
server that is not running is optional evidence that is absent: reported as
UNAVAILABLE, never folded into the stack status.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from mq_agent.tools import mcp_tool_contracts as mtc
from mq_agent.tools.stack_compatibility import build_report, release_blockers
from tests.test_stack_compatibility import DECLARED_MCP_1X, _make_repo
from tests.test_stack_tool_contracts import _need, _producer, _surface, _tool

ROOT = Path(__file__).resolve().parents[1]
URL = "http://mq-mcp.test"
LIVE_COMMIT = "8d7d70b" + "0" * 33

_LABEL = {"A": "read-only", "B": "read-only", "C": "write-capable", "D": "subprocess"}


def _live_tool(name: str, cls: str = "A", params: tuple[tuple[str, bool], ...] = ()) -> dict[str, Any]:
    return {
        "name": name,
        "safety_class": _LABEL[cls],
        "inputSchema": {
            "type": "object",
            "properties": {n: {"type": "string"} for n, _ in params},
            "required": [n for n, r in params if r],
        },
    }


def _fetch(*tools: dict[str, Any], commit: str = LIVE_COMMIT):
    def fetch(url: str) -> Any:
        if url == f"{URL}/tools":
            return {"tools": list(tools)}
        if url == f"{URL}/runtime-identity":
            return {"schema": "mq.runtime-identity.v1", "component": "mq-mcp", "commit": commit}
        return None

    return fetch


def _down(url: str) -> Any:
    return None


def _live(tmp_path: Path, committed: list[dict[str, Any]], fetch) -> list[dict[str, Any]]:
    root = _producer(tmp_path, _surface(*committed))
    return mtc.live_surface_findings({"mq-mcp": root}, {"mq-mcp": URL}, fetch)


def _codes(findings: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(f["code"], f["severity"]) for f in findings]


def test_identical_live_server_reports_nothing(tmp_path: Path) -> None:
    committed = [_tool("git_status"), _tool("record_learning", "C", (("task", True), ("tags", False)))]
    fetch = _fetch(_live_tool("git_status"), _live_tool("record_learning", "C", (("task", True), ("tags", False))))
    assert _live(tmp_path, committed, fetch) == []


def test_stale_server_missing_a_tool_warns_with_both_commits(tmp_path: Path) -> None:
    committed = [_tool("git_status"), _tool("learn_queue_from_last_review", "C")]
    findings = _live(tmp_path, committed, _fetch(_live_tool("git_status")))

    assert _codes(findings) == [("MQC024_TOOL_SURFACE_LIVE_DRIFT", "WARN")]
    finding = findings[0]
    assert finding["blocks_release"] is False
    assert "learn_queue_from_last_review" in finding["message"]
    assert LIVE_COMMIT[:12] in finding["message"]


def test_extra_live_tool_class_and_parameter_drift_warn_once(tmp_path: Path) -> None:
    committed = [_tool("git_status"), _tool("learn_inbox_draft", "A", (("candidate_id", False),))]
    fetch = _fetch(
        _live_tool("git_status", "D"),
        _live_tool("learn_inbox_draft", "A", (("commit", False),)),
        _live_tool("old_tool"),
    )
    findings = _live(tmp_path, committed, fetch)

    assert _codes(findings) == [("MQC024_TOOL_SURFACE_LIVE_DRIFT", "WARN")]
    message = findings[0]["message"]
    assert "old_tool" in message
    assert "git_status" in message
    assert "learn_inbox_draft" in message


def test_server_not_running_is_unavailable_not_drift(tmp_path: Path) -> None:
    findings = _live(tmp_path, [_tool("git_status")], _down)
    assert _codes(findings) == [("MQC024_TOOL_SURFACE_LIVE_DRIFT", "UNAVAILABLE")]
    assert findings[0]["blocks_release"] is False


def test_producer_without_committed_surface_is_not_compared(tmp_path: Path) -> None:
    root = _producer(tmp_path, None)
    assert mtc.live_surface_findings({"mq-mcp": root}, {"mq-mcp": URL}, _fetch(_live_tool("x"))) == []


def test_producer_without_endpoint_is_not_compared(tmp_path: Path) -> None:
    root = _producer(tmp_path, _surface(_tool("git_status")))
    assert mtc.live_surface_findings({"mq-mcp": root}, {}, _fetch()) == []


# --- build_report: optional evidence, never a gate -----------------------------


def _clean_stack(tmp_path: Path, monkeypatch) -> dict[str, str]:
    entry = _make_repo(tmp_path, "mq-mcp", compat=DECLARED_MCP_1X)
    root = Path(entry["path"])
    (root / "contracts").mkdir(exist_ok=True)
    schema = ROOT / "tests" / "fixtures" / "tool_surface.v1.schema.json"
    (root / "contracts" / "tool_surface.v1.schema.json").write_text(schema.read_text("utf-8"), "utf-8")
    (root / "contracts" / "tool_surface.v1.json").write_text(json.dumps(_surface(_tool("git_status"))), "utf-8")
    monkeypatch.setattr(mtc, "load_requirements", lambda: {"tools": [_need("git_status")]})
    return entry


def test_static_report_does_not_contact_a_server(tmp_path: Path, monkeypatch) -> None:
    entry = _clean_stack(tmp_path, monkeypatch)

    def forbidden(url: str) -> Any:
        raise AssertionError(f"static check fetched {url}")

    report = build_report(repos=[entry], slice_only=False, live_fetch=forbidden, live_endpoints={"mq-mcp": URL})
    assert report["status"] == "PASS"


def test_live_drift_warns_but_never_blocks_a_release(tmp_path: Path, monkeypatch) -> None:
    entry = _clean_stack(tmp_path, monkeypatch)
    report = build_report(
        repos=[entry], slice_only=False, live=True,
        live_fetch=_fetch(), live_endpoints={"mq-mcp": URL},
    )
    assert ("MQC024_TOOL_SURFACE_LIVE_DRIFT", "WARN") in _codes(report["findings"])
    assert report["status"] == "WARN"
    assert release_blockers(report) == {}
    schema = json.loads((ROOT / "schemas" / "mq_stack_compatibility.schema.json").read_text("utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(report)) == []


def test_live_server_down_leaves_a_clean_stack_pass(tmp_path: Path, monkeypatch) -> None:
    entry = _clean_stack(tmp_path, monkeypatch)
    static = build_report(repos=[entry], slice_only=False)
    live = build_report(
        repos=[entry], slice_only=False, live=True, live_fetch=_down, live_endpoints={"mq-mcp": URL},
    )
    assert static["status"] == live["status"] == "PASS"
    assert live["next_action"] == static["next_action"]
    assert ("MQC024_TOOL_SURFACE_LIVE_DRIFT", "UNAVAILABLE") in _codes(live["findings"])
