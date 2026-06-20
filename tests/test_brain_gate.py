"""Tests for the brain release gate (stack brain-gate)."""
from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import brain_release_gate as brain_release_gate_registered
from mq_agent.tools.brain_gate import BRAIN_REVIEW_TOOLS, brain_release_gate

runner = CliRunner()

GREEN_CONTRACT = json.dumps({"overall": "READY", "reasons": []})
GREEN_RELEASE = json.dumps({"overall": "GO", "repos": []})
GREEN_TRUTH = {"markdown": "# truth", "path": "/tmp/truth.md", "written": False}
GREEN_VAULT = json.dumps({"status": "OK", "dirs": []})


def _bridge(available: bool = True, tools: tuple[str, ...] = BRAIN_REVIEW_TOOLS) -> MagicMock:
    bridge = MagicMock()
    bridge.is_available.return_value = available
    bridge.list_tool_specs.return_value = [SimpleNamespace(name=t) for t in tools]
    mock_cls = MagicMock(return_value=bridge)
    return mock_cls


@dataclass
class GateMocks:
    truth_mock: MagicMock


@contextmanager
def _gate(contract=GREEN_CONTRACT, release=GREEN_RELEASE, truth=GREEN_TRUTH,
          vault=GREEN_VAULT, bridge_cls=None) -> Iterator[GateMocks]:
    with ExitStack() as stack:
        stack.enter_context(patch(
            "mq_agent.tools.stack_tools.stack_contract_check", return_value=contract))
        stack.enter_context(patch(
            "mq_agent.tools.stack_tools.stack_release_check", return_value=release))
        truth_mock = stack.enter_context(patch(
            "mq_agent.tools.stack_truth.stack_truth_export", return_value=truth))
        stack.enter_context(patch(
            "mq_agent.tools.vault_structure.vault_structure", return_value=vault))
        stack.enter_context(patch(
            "mq_agent.tools.mcp_bridge.MultiMCPBridge", bridge_cls or _bridge()))
        yield GateMocks(truth_mock=truth_mock)



def _statuses(data: dict) -> dict[str, str]:
    return {c["name"]: c["status"] for c in data["checks"]}


class TestGate:
    def test_all_green_is_go(self):
        with _gate() as g:
            data = json.loads(brain_release_gate())
        assert data["overall"] == "GO"
        assert set(_statuses(data).values()) == {"PASS"}
        assert data["next_action"] == "all green — release away"
        g.truth_mock.assert_called_once_with(write=False)

    def test_contract_drift_fails(self):
        contract = json.dumps({"overall": "DRIFT", "reasons": ["mq-mcp: version mismatch"]})
        with _gate(contract=contract):
            data = json.loads(brain_release_gate())
        assert data["overall"] == "NO-GO"
        assert _statuses(data)["contract-check"] == "FAIL"
        assert data["next_action"] == "mq-agent stack contract-check"

    def test_release_blockers_fail_with_detail(self):
        release = json.dumps({
            "overall": "NO-GO",
            "repos": [{"name": "mq-mcp", "blockers": ["dirty tree"]}],
        })
        with _gate(release=release):
            data = json.loads(brain_release_gate())
        check = next(c for c in data["checks"] if c["name"] == "release-check")
        assert check["status"] == "FAIL"
        assert "mq-mcp: dirty tree" in check["detail"]

    def test_truth_export_must_render(self):
        with _gate(truth={"markdown": "", "path": "", "written": False}):
            data = json.loads(brain_release_gate())
        assert _statuses(data)["truth-export"] == "FAIL"

    def test_incomplete_vault_fails_with_missing_dirs(self):
        vault = json.dumps({
            "status": "INCOMPLETE",
            "dirs": [{"path": "memory/reviews", "exists": False}],
        })
        with _gate(vault=vault):
            data = json.loads(brain_release_gate())
        check = next(c for c in data["checks"] if c["name"] == "vault-structure")
        assert check["status"] == "FAIL"
        assert "memory/reviews" in check["detail"]
        assert check["hint"] == "mq-agent brain structure --init --approve"

    def test_unreachable_mcp_fails(self):
        with _gate(bridge_cls=_bridge(available=False)):
            data = json.loads(brain_release_gate())
        check = next(c for c in data["checks"] if c["name"] == "brain-review")
        assert check["status"] == "FAIL"
        assert check["detail"] == "mq-mcp not reachable"
        assert check["hint"] == "mq-agent mcp start"

    def test_missing_brain_tool_fails(self):
        with _gate(bridge_cls=_bridge(tools=("review_repo",))):
            data = json.loads(brain_release_gate())
        check = next(c for c in data["checks"] if c["name"] == "brain-review")
        assert check["status"] == "FAIL"
        assert "brain_record_review" in check["detail"]


class TestCli:
    def test_go_exits_0(self):
        with _gate():
            result = runner.invoke(app, ["stack", "brain-gate"])
        assert result.exit_code == 0
        assert "GO" in result.output

    def test_no_go_exits_1_with_hint(self):
        with _gate(bridge_cls=_bridge(available=False)):
            result = runner.invoke(app, ["stack", "brain-gate"])
        assert result.exit_code == 1
        assert "NO-GO" in result.output
        assert "mq-agent mcp start" in result.output

    def test_json_output(self):
        with _gate():
            result = runner.invoke(app, ["stack", "brain-gate", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall"] == "GO"
        assert len(data["checks"]) == 5
        assert set(data) >= {"overall", "checks", "next_action", "checked_at"}
        assert {c["name"] for c in data["checks"]} == {
            "contract-check",
            "release-check",
            "truth-export",
            "vault-structure",
            "brain-review",
        }
        assert all(set(c) >= {"name", "status", "detail"} for c in data["checks"])

    def test_json_no_go_exits_1(self):
        with _gate(contract=json.dumps({"overall": "BLOCKED", "reasons": []})):
            result = runner.invoke(app, ["stack", "brain-gate", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["overall"] == "NO-GO"

    def test_registered_in_tool_registry(self):
        from mq_agent.tools import TOOL_REGISTRY
        assert TOOL_REGISTRY["brain_release_gate"] is brain_release_gate
        assert brain_release_gate_registered is brain_release_gate
