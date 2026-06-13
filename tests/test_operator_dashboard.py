"""Tests for the v1.19.0 operator dashboard snapshot."""
from __future__ import annotations

import json
from importlib import import_module


def _fake_cockpit() -> str:
    return json.dumps({
        "overall_gate": "GO",
        "overall_contract": "READY",
        "brain_export": {
            "path": "/tmp/2026-06-12-mq-stack-truth.md",
            "date": "2026-06-12",
            "age_days": 0,
            "status": "fresh",
        },
        "next_action": "all green",
        "repos": [
            {
                "repo": "mq-agent",
                "role": "orchestrator",
                "version": "1.18.0",
                "branch": "main",
                "dirty": False,
                "contract": "READY",
                "gate": "GO",
                "next_action": "up to date",
            },
            {
                "repo": "mq-mcp",
                "role": "tool-runtime",
                "version": "1.0.0",
                "branch": "main",
                "dirty": True,
                "contract": "READY",
                "gate": "GO",
                "next_action": "commit or stash uncommitted changes",
            },
        ],
        "checked_at": "2026-06-12T00:00:00+00:00",
    })


def _patch_dashboard_deps(monkeypatch, cockpit: str | None = None, ollama_ok: bool = True) -> None:
    model_runtime = import_module("mq_agent.tools.model_runtime")
    stack_cockpit = import_module("mq_agent.tools.stack_cockpit")

    monkeypatch.setattr(stack_cockpit, "stack_cockpit", lambda: cockpit or _fake_cockpit())
    monkeypatch.setattr(
        model_runtime,
        "current_model",
        lambda: {
            "profile": "review",
            "model": "qwen3",
            "config_path": "/tmp/models.json",
            "profiles": {"review": "qwen3"},
        },
    )
    monkeypatch.setattr(
        model_runtime,
        "list_ollama_models",
        lambda: {"ok": ollama_ok, "models": ["qwen3"]} if ollama_ok else {
            "ok": False,
            "models": [],
            "detail": "ollama CLI not found",
            "hint": "install or start Ollama",
        },
    )


def test_operator_dashboard_summarizes_stack_brain_ollama_and_contracts(monkeypatch):
    from mq_agent.tools.operator_dashboard import operator_dashboard

    _patch_dashboard_deps(monkeypatch)
    data = json.loads(operator_dashboard())

    assert data["overall"] == "ATTENTION"
    assert data["stack"]["repo_count"] == 2
    assert data["stack"]["actionable_count"] == 1
    assert data["stack"]["dirty_count"] == 1
    assert data["brain"]["status"] == "fresh"
    assert data["ollama"]["profile"] == "review"
    assert data["contracts"]["READY"] == 2
    assert data["next_action"].startswith("mq-mcp:")


def test_operator_dashboard_surfaces_ollama_when_stack_is_clean(monkeypatch):
    from mq_agent.tools.operator_dashboard import operator_dashboard

    clean = json.loads(_fake_cockpit())
    clean["repos"][1]["dirty"] = False
    clean["repos"][1]["next_action"] = "up to date"
    _patch_dashboard_deps(monkeypatch, cockpit=json.dumps(clean), ollama_ok=False)

    data = json.loads(operator_dashboard())

    assert data["overall"] == "ATTENTION"
    assert data["ollama"]["ok"] is False
    assert data["next_action"] == "install or start Ollama"


def test_dashboard_cli_json(monkeypatch):
    from typer.testing import CliRunner

    from mq_agent.main import app

    _patch_dashboard_deps(monkeypatch)
    result = CliRunner().invoke(app, ["dashboard", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["stack"]["repo_count"] == 2


def test_dashboard_cli_table(monkeypatch):
    from typer.testing import CliRunner

    from mq_agent.main import app

    _patch_dashboard_deps(monkeypatch)
    result = CliRunner().invoke(app, ["dashboard"])

    assert result.exit_code == 0
    assert "mq-agent Operator Dashboard" in result.output
    assert "Ollama" in result.output


def test_registered_in_tool_registry():
    from mq_agent.tools import TOOL_REGISTRY
    from mq_agent.tools.operator_dashboard import operator_dashboard

    assert TOOL_REGISTRY["operator_dashboard"] is operator_dashboard


def test_tui_dashboard_panel_text_is_compact():
    from mq_agent.tui.app import dashboard_panel_text

    data = {
        "overall": "ATTENTION",
        "next_action": "mq-agent: commit or stash uncommitted changes",
        "stack": {
            "gate": "GO",
            "contract": "READY",
            "repo_count": 8,
            "actionable_count": 2,
            "dirty_count": 1,
        },
        "brain": {
            "status": "fresh",
            "age_days": 0,
            "path": "/Users/example/mqobsidian/memory/stack-truth/2026-06-12-mq-stack-truth.md",
        },
        "ollama": {
            "ok": True,
            "profile": "fast",
            "model": "qwen3",
            "models": ["qwen3", "mq-learn"],
        },
        "contracts": {"READY": 7, "REVIEW": 1},
    }

    panels = dashboard_panel_text(data)

    assert set(panels) == {"panel-stack", "panel-brain", "panel-ollama", "panel-next"}
    assert "Stack" in panels["panel-stack"]
    assert "Actions: 2" in panels["panel-stack"]
    assert "Profile: fast -> qwen3" in panels["panel-ollama"]
    assert "mq-agent: commit" in panels["panel-next"]
