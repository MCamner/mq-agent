"""Tests for mq-agent review pass-through orchestration."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import _contract_status_ok, app
from mq_agent.tools.mcp_bridge import MultiMCPBridge

runner = CliRunner()


class FakeReviewBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None, dict[str, bool]]] = []
        self.tool_calls: list[tuple[str, dict[str, str]]] = []

    def call_tool(self, tool: str, args: dict[str, str]) -> dict[str, Any]:
        self.tool_calls.append((tool, args))
        return {
            "schema": "visual_architecture_observation.v1",
            "image_path": args["image_path"],
            "nodes": [],
            "connections": [],
        }

    def review_file(self, path: str, flags: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("review_file", path, flags))
        return {
            "ok": True,
            "findings": [
                {"severity": "RISK", "file": path, "line": 7, "message": "from mq-mcp"},
            ],
        }

    def review_diff(self, flags: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("review_diff", None, flags))
        return {
            "ok": True,
            "findings": [
                {"severity": "ARCHITECTURE", "message": "from mq-mcp"},
            ],
        }

    def review_repo(self, path: str, flags: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("review_repo", path, flags))
        return {"ok": True, "findings": []}

    def list_architecture_decisions(self) -> None:
        return None


def test_review_file_json_invokes_mcp_bridge_with_flags():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, [
            "review",
            "file",
            "README.md",
            "--security",
            "--architecture",
            "--json",
        ])

    assert result.exit_code == 0
    assert bridge.calls == [
        ("review_file", "README.md", {"security": True, "architecture": True, "risk": False, "fast": False})
    ]
    data = json.loads(result.output)
    assert data["findings"][0]["severity"] == "RISK"


def test_review_file_architecture_image_passes_visual_context_to_mcp():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, [
            "review",
            "file",
            "README.md",
            "--architecture-image",
            "docs/arch.png",
            "--json",
        ])

    assert result.exit_code == 0
    assert bridge.tool_calls == [
        ("observe_architecture", {"image_path": "docs/arch.png"})
    ]
    flags = bridge.calls[0][2]
    assert flags["architecture"] is True
    assert flags["visual_architecture_observation"]["schema"] == "visual_architecture_observation.v1"
    assert flags["visual_architecture_observation"]["image_path"] == "docs/arch.png"


def test_review_diff_architecture_image_unwraps_json_string_payload():
    class JsonStringBridge(FakeReviewBridge):
        def call_tool(self, tool: str, args: dict[str, str]) -> str:
            self.tool_calls.append((tool, args))
            return json.dumps({
                "schema": "visual_architecture_observation.v1",
                "image_path": args["image_path"],
            })

    bridge = JsonStringBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, [
            "review",
            "diff",
            "--visual",
            "docs/diagram.png",
            "--json",
        ])

    assert result.exit_code == 0
    flags = bridge.calls[0][2]
    assert flags["architecture"] is True
    assert flags["visual_architecture_observation"]["schema"] == "visual_architecture_observation.v1"


def test_review_repo_architecture_image_dry_run_prints_visual_step():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, [
            "review",
            "repo",
            ".",
            "--architecture-image",
            "docs/arch.png",
            "--dry-run",
        ])

    assert result.exit_code == 0
    assert "observe_architecture" in result.output
    assert "docs/arch.png" in result.output
    assert bridge.calls == []
    assert bridge.tool_calls == []


def test_review_diff_passes_severity_label_through_unchanged():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "diff"])

    assert result.exit_code == 0
    assert "ARCHITECTURE" in result.output


def test_review_repo_json_invokes_mcp_bridge():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "repo", ".", "--json"])

    assert result.exit_code == 0
    assert bridge.calls == [
        ("review_repo", ".", {"security": False, "architecture": False, "risk": False, "fast": False})
    ]


def test_review_missing_mq_mcp_tool_returns_clear_error():
    class MissingToolBridge:
        def review_file(self, path: str, flags: dict[str, bool]) -> dict[str, object]:
            return {
                "ok": False,
                "error": "mq-mcp tool 'review_file' is not available.",
                "tool": "review_file",
            }

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=MissingToolBridge()):
        result = runner.invoke(app, ["review", "file", "README.md", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert "review_file" in data["error"]


def test_review_mcp_error_string_exits_nonzero():
    class ErrorBridge:
        def review_diff(self, flags: dict[str, bool]) -> str:
            return "mq-mcp error 500: Internal Server Error"

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=ErrorBridge()):
        result = runner.invoke(app, ["review", "diff", "--json"])

    assert result.exit_code == 1
    assert "mq-mcp error 500" in result.output


def test_mcp_bridge_review_helpers_call_expected_tools():
    bridge = MultiMCPBridge()
    with patch.object(bridge, "_call_required_tool", return_value={"ok": True}) as call:
        bridge.review_file("README.md", {"security": False, "architecture": False, "risk": False})
        bridge.review_diff({"security": True, "architecture": False, "risk": False})
        bridge.review_repo(".", {"security": False, "architecture": True, "risk": False})

    assert call.call_args_list[0].args == (
        "review_file",
        {"path": "README.md", "security": False, "architecture": False, "risk": False},
    )
    assert call.call_args_list[1].args == (
        "review_diff",
        {"security": True, "architecture": False, "risk": False},
    )
    assert call.call_args_list[2].args == (
        "review_repo",
        {"path": ".", "security": False, "architecture": True, "risk": False},
    )


def test_review_file_dry_run_prints_plan_and_does_not_call_bridge():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "file", "src/main.py", "--dry-run"])

    assert result.exit_code == 0
    assert "Would call" in result.output
    assert "review_file" in result.output
    assert "src/main.py" in result.output
    assert bridge.calls == []


def test_review_diff_dry_run_with_flags():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "diff", "--dry-run", "--security"])

    assert result.exit_code == 0
    assert "Would call" in result.output
    assert "review_diff" in result.output
    assert "--security" in result.output
    assert bridge.calls == []


def test_review_repo_dry_run_with_flags():
    bridge = FakeReviewBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(app, ["review", "repo", ".", "--dry-run", "--architecture", "--risk"])

    assert result.exit_code == 0
    assert "Would call" in result.output
    assert "review_repo" in result.output
    assert "--architecture" in result.output
    assert "--risk" in result.output
    assert bridge.calls == []


def test_mcp_bridge_risk_requires_installed_risk_tool():
    bridge = MultiMCPBridge()
    with patch.object(bridge, "bridges", {}):
        result = bridge.review_file("README.md", {"security": False, "architecture": False, "risk": True})

    assert result["ok"] is False
    assert "risk_review_file" in result["error"]


def test_contract_status_accepts_mcp_text_wrappers():
    passing = {
        "result": "## Orchestration contract validation — PASS\n\nChecks: 13 passed, 0 failed, 0 warnings"
    }
    failing = {
        "result": "## Orchestration contract validation — FAIL\n\nChecks: 11 passed, 1 failed, 0 warnings"
    }

    assert _contract_status_ok(passing) is True
    assert _contract_status_ok([[{"type": "text", "text": passing["result"]}]]) is True
    assert _contract_status_ok(failing) is False


_REVIEW_OK = {
    "ok": True,
    "findings": [{"severity": "HIGH", "message": "unused import", "file": "README.md"}],
}


def test_review_file_brain_calls_brain_record_review():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = _REVIEW_OK
        MockBridge.return_value.call_tool.return_value = {"ok": True, "path": "mqobsidian/reviews/2026-06-08-readme-md.md"}
        MockBridge.return_value.list_architecture_decisions.return_value = None
        result = runner.invoke(app, ["review", "file", "README.md", "--brain"])

    assert result.exit_code == 0
    call_args = [c[0][0] for c in MockBridge.return_value.call_tool.call_args_list]
    assert "brain_record_review" in call_args


def test_review_diff_brain_calls_brain_record_review():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_diff.return_value = {
            "ok": True,
            "findings": [{"severity": "ARCHITECTURE", "message": "coupling issue"}],
        }
        MockBridge.return_value.call_tool.return_value = {"ok": True, "path": "mqobsidian/reviews/2026-06-08-diff.md"}
        MockBridge.return_value.list_architecture_decisions.return_value = None
        result = runner.invoke(app, ["review", "diff", "--brain"])

    assert result.exit_code == 0
    call_args = [c[0][0] for c in MockBridge.return_value.call_tool.call_args_list]
    assert "brain_record_review" in call_args


def test_review_repo_brain_calls_brain_record_review():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_repo.return_value = {"ok": True, "findings": []}
        MockBridge.return_value.call_tool.return_value = {"ok": True, "path": "mqobsidian/reviews/2026-06-08-dot.md"}
        MockBridge.return_value.list_architecture_decisions.return_value = None
        result = runner.invoke(app, ["review", "repo", ".", "--brain"])

    assert result.exit_code == 0
    call_args = [c[0][0] for c in MockBridge.return_value.call_tool.call_args_list]
    assert "brain_record_review" in call_args


def test_review_file_brain_skips_on_error():
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge") as MockBridge:
        MockBridge.return_value.review_file.return_value = {
            "ok": False,
            "error": "mq-mcp is not reachable",
        }
        result = runner.invoke(app, ["review", "file", "README.md", "--brain"])

    assert result.exit_code == 1
    MockBridge.return_value.call_tool.assert_not_called()
