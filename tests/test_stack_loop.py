"""Tests for the v1.20 controlled stack loop."""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.stack_loop import LOOP_CONTRACT, stack_loop

runner = CliRunner()


def _dashboard(next_action: str = "mq-agent: commit or stash uncommitted changes", overall: str = "ATTENTION") -> str:
    return json.dumps({
        "overall": overall,
        "next_action": next_action,
        "stack": {"gate": "GO", "contract": "READY"},
        "brain": {"status": "fresh"},
        "ollama": {"ok": True},
        "contracts": {"READY": 1},
        "repos": [],
    })


def _patch_dashboard(monkeypatch, payload: str) -> None:
    operator_dashboard = import_module("mq_agent.tools.operator_dashboard")
    monkeypatch.setattr(operator_dashboard, "operator_dashboard", lambda: payload)


def test_stack_loop_manual_when_next_action_needs_operator(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard())

    data = json.loads(stack_loop())

    assert data["overall"] == "PLAN"
    assert data["contract"] == LOOP_CONTRACT
    assert data["decision"] == "manual"
    assert data["writes_enabled"] is False
    assert data["steps"][1]["next_action"] == "mq-agent: commit or stash uncommitted changes"


def test_stack_loop_previews_truth_export(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))

    data = json.loads(stack_loop())

    assert data["decision"] == "preview"
    assert data["steps"][-1]["detail"] == "mq-agent stack truth-export --dry-run"
    assert data["steps"][-1]["writes"] is False


def test_stack_loop_previews_release_command(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("repo-signal: stack release --repo repo-signal"))

    data = json.loads(stack_loop(max_iterations=10))

    assert data["max_iterations"] == 5
    assert data["decision"] == "preview"
    assert data["steps"][-1]["detail"] == "mq-agent stack release --repo repo-signal"


def test_stack_loop_idles_when_dashboard_ready(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("all green", overall="READY"))

    data = json.loads(stack_loop())

    assert data["decision"] == "idle"
    assert data["next_action"] == "all green"


def test_stack_loop_blocks_non_dry_run(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("all green", overall="READY"))

    data = json.loads(stack_loop(dry_run=False, approve=True))

    assert data["blocked"] is False
    assert data["mode"] == "idle"
    assert data["writes_enabled"] is False
    assert data["contract"]["execution"] == "controlled"
    assert data["contract"]["rollback_required"] is True
    assert data["blocker"] is None


def test_stack_loop_blocks_execution_without_approval(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))

    data = json.loads(stack_loop(execute=True))

    assert data["blocked"] is True
    assert data["mode"] == "blocked"
    assert data["writes_enabled"] is False
    assert data["blocker"] == "execution requires --approve"
    assert data["steps"][-1]["status"] == "blocked"


def test_stack_loop_executes_truth_export_with_approval(monkeypatch, tmp_path):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))
    stack_loop_module = import_module("mq_agent.tools.stack_loop")
    stack_truth = import_module("mq_agent.tools.stack_truth")
    dest = tmp_path / "truth.md"

    def fake_export(output_path: str = "", write: bool = True):
        path = output_path or str(dest)
        if write:
            Path(path).write_text("truth\n", encoding="utf-8")
        return {"written": write, "status": "READY", "path": path}

    monkeypatch.setattr(stack_truth, "stack_truth_export", fake_export)

    data = json.loads(stack_loop_module.stack_loop(execute=True, approve=True))

    assert data["blocked"] is False
    assert data["mode"] == "approved-execution"
    assert data["writes_enabled"] is True
    assert data["execution_result"]["ok"] is True
    assert data["execution_result"]["action"] == "truth-export"
    assert data["steps"][-1]["status"] == "done"
    assert dest.read_text(encoding="utf-8") == "truth\n"


def test_stack_loop_failed_truth_export_restores_file(monkeypatch, tmp_path):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))
    stack_truth = import_module("mq_agent.tools.stack_truth")
    dest = tmp_path / "truth.md"
    dest.write_text("before\n", encoding="utf-8")

    def fake_export(output_path: str = "", write: bool = True):
        path = output_path or str(dest)
        if write:
            Path(path).write_text("partial\n", encoding="utf-8")
            return {"written": False, "status": "ERROR", "path": path}
        return {"written": False, "status": "READY", "path": path}

    monkeypatch.setattr(stack_truth, "stack_truth_export", fake_export)

    data = json.loads(stack_loop(execute=True, approve=True))

    assert data["blocked"] is True
    assert data["mode"] == "blocked"
    assert data["execution_result"]["ok"] is False
    assert data["execution_result"]["rollback"]["status"] == "restored"
    assert dest.read_text(encoding="utf-8") == "before\n"


def test_stack_loop_executes_release_with_delegated_rollback(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("repo-signal: stack release --repo repo-signal"))
    stack_release = import_module("mq_agent.tools.stack_release")

    monkeypatch.setattr(
        stack_release,
        "stack_release",
        lambda repo, execute=False: json.dumps({"released": execute, "repo": repo}),
    )

    data = json.loads(stack_loop(execute=True, approve=True))

    assert data["execution_result"]["ok"] is True
    assert data["execution_result"]["action"] == "stack-release"
    assert data["execution_result"]["rollback"]["status"] == "delegated"


def test_stack_loop_cli_json(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is none"))

    result = runner.invoke(app, ["stack", "loop", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["decision"] == "preview"


def test_stack_loop_cli_blocks_execute_without_approve(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is none"))

    result = runner.invoke(app, ["stack", "loop", "--execute", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["blocked"] is True
    assert data["blocker"] == "execution requires --approve"


def test_stack_loop_cli_table(monkeypatch):
    _patch_dashboard(monkeypatch, _dashboard())

    result = runner.invoke(app, ["stack", "loop"])

    assert result.exit_code == 0
    assert "mq-stack Loop Plan" in result.output
    assert "manual" in result.output


def test_stack_loop_registered_in_tool_registry():
    from mq_agent.tools import TOOL_REGISTRY

    assert TOOL_REGISTRY["stack_loop"] is stack_loop


def test_stack_loop_plan_schema_documents_contract():
    schema = json.loads(Path("schemas/mq_stack_loop_plan.schema.json").read_text())

    assert schema["title"] == "MQ Stack Loop Plan"
    assert "contract" in schema["required"]
    contract = schema["properties"]["contract"]["properties"]
    assert contract["schema"]["const"] == "mq_stack_loop_plan.v1"
    assert contract["execution"]["const"] == "controlled"
    assert contract["rollback_required"]["const"] is True
