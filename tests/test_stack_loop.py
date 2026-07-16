"""Tests for the v1.20 controlled stack loop."""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.stack_loop import LOOP_CONTRACT, stack_loop

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_state_dir(monkeypatch, tmp_path):
    """Keep audit history out of the real ~/.mq-agent during tests."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("MQ_AGENT_STATE_DIR", str(state_dir))
    return state_dir


def _audit_rows(state_dir: Path) -> list[dict]:
    path = state_dir / "stack-loop-history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


def test_stack_loop_audit_schema_documents_contract():
    schema = json.loads(Path("schemas/mq_stack_loop_audit.schema.json").read_text())

    assert schema["title"] == "MQ Stack Loop Audit"
    props = schema["properties"]
    assert props["schema"]["const"] == "mq_stack_loop_audit.v1"
    assert props["source_schema"]["const"] == "mq_stack_loop_plan.v1"
    assert props["approved"]["const"] is True
    assert props["decision"]["const"] == "preview"
    assert props["outcome"]["enum"] == ["success", "failed"]
    assert "rollback" in schema["required"]


def test_stack_loop_dry_run_writes_no_audit(monkeypatch, isolated_state_dir):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))

    data = json.loads(stack_loop())

    assert data["decision"] == "preview"
    assert data["audit"] is None
    assert _audit_rows(isolated_state_dir) == []


def test_stack_loop_idle_writes_no_audit(monkeypatch, isolated_state_dir):
    _patch_dashboard(monkeypatch, _dashboard("all green", overall="READY"))

    data = json.loads(stack_loop(dry_run=False, approve=True))

    assert data["mode"] == "idle"
    assert data["audit"] is None
    assert _audit_rows(isolated_state_dir) == []


def test_stack_loop_unapproved_execution_writes_no_audit(monkeypatch, isolated_state_dir):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))

    data = json.loads(stack_loop(execute=True))

    assert data["blocked"] is True
    assert data["audit"] is None
    assert _audit_rows(isolated_state_dir) == []


def test_stack_loop_approved_success_appends_one_audit_record(monkeypatch, tmp_path, isolated_state_dir):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))
    stack_truth = import_module("mq_agent.tools.stack_truth")
    dest = tmp_path / "truth.md"

    def fake_export(output_path: str = "", write: bool = True):
        path = output_path or str(dest)
        if write:
            Path(path).write_text("truth\n", encoding="utf-8")
        return {"written": write, "status": "READY", "path": path}

    monkeypatch.setattr(stack_truth, "stack_truth_export", fake_export)

    data = json.loads(stack_loop(execute=True, approve=True))

    assert data["audit"]["recorded"] is True
    rows = _audit_rows(isolated_state_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["schema"] == "mq_stack_loop_audit.v1"
    assert row["source_schema"] == "mq_stack_loop_plan.v1"
    assert row["approved"] is True
    assert row["decision"] == "preview"
    assert row["dashboard_overall"] == "ATTENTION"
    assert row["next_action"] == "run stack truth-export — brain note is stale"
    assert row["action"] == "truth-export"
    assert row["outcome"] == "success"
    assert row["execution_ok"] is True
    assert isinstance(row["rollback"]["status"], str)
    assert isinstance(row["recorded_at"], str)


def test_stack_loop_approved_failure_appends_failed_audit_record(monkeypatch, tmp_path, isolated_state_dir):
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
    rows = _audit_rows(isolated_state_dir)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "failed"
    assert rows[0]["execution_ok"] is False
    assert rows[0]["rollback"]["status"] == "restored"


def test_stack_loop_release_audit_records_repo(monkeypatch, isolated_state_dir):
    _patch_dashboard(monkeypatch, _dashboard("repo-signal: stack release --repo repo-signal"))
    stack_release = import_module("mq_agent.tools.stack_release")

    monkeypatch.setattr(
        stack_release,
        "stack_release",
        lambda repo, execute=False: json.dumps({"released": execute, "repo": repo}),
    )

    json.loads(stack_loop(execute=True, approve=True))

    rows = _audit_rows(isolated_state_dir)
    assert len(rows) == 1
    assert rows[0]["action"] == "stack-release"
    assert rows[0]["repo"] == "repo-signal"
    assert rows[0]["rollback"]["status"] == "delegated"


def test_stack_loop_audit_failure_does_not_hide_execution_result(monkeypatch, tmp_path):
    _patch_dashboard(monkeypatch, _dashboard("run stack truth-export — brain note is stale"))
    stack_truth = import_module("mq_agent.tools.stack_truth")
    dest = tmp_path / "truth.md"

    # A file where the state directory should be: the append must fail, not raise.
    blocker = tmp_path / "blocked-state"
    blocker.write_text("not a directory\n", encoding="utf-8")
    monkeypatch.setenv("MQ_AGENT_STATE_DIR", str(blocker))

    def fake_export(output_path: str = "", write: bool = True):
        path = output_path or str(dest)
        if write:
            Path(path).write_text("truth\n", encoding="utf-8")
        return {"written": write, "status": "READY", "path": path}

    monkeypatch.setattr(stack_truth, "stack_truth_export", fake_export)

    data = json.loads(stack_loop(execute=True, approve=True))

    assert data["execution_result"]["ok"] is True
    assert data["blocked"] is False
    assert data["audit"]["recorded"] is False
    assert data["audit"]["error"]
