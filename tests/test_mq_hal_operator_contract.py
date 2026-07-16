"""Stable JSON contracts consumed by mq-hal."""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.main import app


CONTRACTS = {
    "mq_stack_cockpit.schema.json": ("mq_agent.tools.stack_cockpit", "COCKPIT_SCHEMA", "mq_stack_cockpit.v1"),
    "mq_brain_gate.schema.json": ("mq_agent.tools.brain_gate", "BRAIN_GATE_SCHEMA", "mq_brain_gate.v1"),
    "mq_stack_runtime.schema.json": ("mq_agent.tools.stack_runtime", "STACK_RUNTIME_SCHEMA", "mq_stack_runtime.v1"),
    "mq_stack_release_check.schema.json": ("mq_agent.tools.stack_tools", "STACK_RELEASE_CHECK_SCHEMA", "mq_stack_release_check.v1"),
    "mq_operator_dashboard.schema.json": ("mq_agent.tools.operator_dashboard", "OPERATOR_DASHBOARD_SCHEMA", "mq_operator_dashboard.v1"),
}


def _schema(filename: str) -> dict:
    schema = json.loads((Path("schemas") / filename).read_text())
    Draft202012Validator.check_schema(schema)
    return schema


@pytest.mark.parametrize(("filename", "module_name", "constant", "expected"), [
    (filename, *values) for filename, values in CONTRACTS.items()
])
def test_schema_files_and_producer_constants_match(filename, module_name, constant, expected):
    module = import_module(module_name)
    schema = _schema(filename)

    assert schema["properties"]["schema"]["const"] == expected
    assert "schema" in schema["required"]
    assert schema["additionalProperties"] is True
    assert getattr(module, constant) == expected


def _cockpit_payload(monkeypatch) -> dict:
    cockpit = import_module("mq_agent.tools.stack_cockpit")
    stack_tools = import_module("mq_agent.tools.stack_tools")
    monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", [{"name": "mq-agent", "role": "orchestrator"}])
    monkeypatch.setattr(cockpit, "_cockpit_entry", lambda _entry: {
        "repo": "mq-agent", "role": "orchestrator", "exists": True,
        "version": "1.18.0", "branch": "main", "dirty": False,
        "contract": "READY", "gate": "GO", "unreleased": 0,
        "next_action": "up to date", "next_action_contract": {
            "text": "up to date", "source_command": "mq-agent stack cockpit",
            "severity": "info", "suggested_route": "none",
            "requires_approval": False, "repo": "mq-agent",
        },
    })
    monkeypatch.setattr(cockpit, "_truth_note_freshness", lambda: {
        "path": None, "date": "2026-07-16", "age_days": 0, "status": "fresh",
    })
    return json.loads(cockpit.stack_cockpit())


def _brain_payload(monkeypatch) -> dict:
    brain = import_module("mq_agent.tools.brain_gate")
    for name in ("_contract_check", "_release_check", "_truth_export_dry_run", "_vault_structure_check", "_brain_review_path"):
        monkeypatch.setattr(brain, name, lambda name=name: brain._check(name.removeprefix("_").replace("_", "-"), True, "ok"))
    return json.loads(brain.brain_release_gate())


def _runtime_payload(monkeypatch) -> dict:
    runtime = import_module("mq_agent.tools.stack_runtime")
    bridge = import_module("mq_agent.tools.mcp_bridge")
    monkeypatch.setattr(bridge, "MultiMCPBridge", lambda: object())
    monkeypatch.setattr(runtime, "_repo_signal_step", lambda: runtime._step("repo-signal", True, "ok"))
    monkeypatch.setattr(runtime, "_mcp_step", lambda _bridge: runtime._step("mq-mcp", True, "ok"))
    monkeypatch.setattr(runtime, "_ollama_step", lambda _bridge: runtime._step("ollama", True, "ok"))
    monkeypatch.setattr(runtime, "_brain_export_step", lambda write: runtime._step("brain export", True, "ok", written=write))
    monkeypatch.setattr(runtime, "_release_step", lambda ci: runtime._step("release", True, "ok", mode="ci" if ci else "local"))
    return json.loads(runtime.stack_run(dry_run=True))


def _release_payload(monkeypatch) -> dict:
    stack_tools = import_module("mq_agent.tools.stack_tools")
    entry = {"name": "mq-agent", "path": ".", "role": "orchestrator"}
    monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", [entry])
    monkeypatch.setattr(stack_tools, "_release_entry", lambda _entry, ci=False: {
        "name": "mq-agent", "exists": True, "version": "1.18.0",
        "branch": "main", "on_main": True, "dirty": False, "unpushed": 0,
        "changelog_ok": True, "readme_ok": True, "roadmap_ok": True,
        "blockers": [], "warnings": [], "go": True,
    })
    return json.loads(stack_tools.stack_release_check())


def _dashboard_payload(monkeypatch) -> dict:
    dashboard = import_module("mq_agent.tools.operator_dashboard")
    cockpit = import_module("mq_agent.tools.stack_cockpit")
    models = import_module("mq_agent.tools.model_runtime")
    monkeypatch.setattr(cockpit, "stack_cockpit", lambda: json.dumps({
        "overall_gate": "GO", "overall_contract": "READY",
        "brain_export": {"status": "fresh"}, "next_action": "all green", "repos": [{
            "repo": "mq-agent", "role": "orchestrator", "version": "1.18.0",
            "branch": "main", "dirty": False, "contract": "READY", "gate": "GO",
            "next_action": "up to date", "next_action_contract": {
                "text": "up to date", "source_command": "mq-agent stack cockpit",
                "severity": "info", "suggested_route": "none",
                "requires_approval": False, "repo": "mq-agent",
            },
        }],
    }))
    monkeypatch.setattr(models, "current_model", lambda: {"profile": "review", "model": "qwen3"})
    monkeypatch.setattr(models, "list_ollama_models", lambda: {"ok": True, "models": ["qwen3"]})
    return json.loads(dashboard.operator_dashboard())


@pytest.mark.parametrize(("filename", "factory"), [
    ("mq_stack_cockpit.schema.json", _cockpit_payload),
    ("mq_brain_gate.schema.json", _brain_payload),
    ("mq_stack_runtime.schema.json", _runtime_payload),
    ("mq_stack_release_check.schema.json", _release_payload),
    ("mq_operator_dashboard.schema.json", _dashboard_payload),
])
def test_actual_producer_payload_validates(filename, factory, monkeypatch):
    Draft202012Validator(_schema(filename)).validate(factory(monkeypatch))


def test_release_check_cli_uses_canonical_payload(monkeypatch):
    stack_tools = import_module("mq_agent.tools.stack_tools")
    canonical = {
        "schema": "mq_stack_release_check.v1", "overall": "GO", "mode": "local",
        "blocked": [], "warned": [], "repos": [],
        "checked_at": "2026-07-16T00:00:00+00:00",
    }
    monkeypatch.setattr(stack_tools, "stack_release_check", lambda ci=False: json.dumps(canonical))

    result = CliRunner().invoke(app, ["stack", "release-check", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == canonical


def test_missing_local_release_repo_validates(monkeypatch, tmp_path):
    stack_tools = import_module("mq_agent.tools.stack_tools")
    missing = tmp_path / "missing"
    monkeypatch.setattr(stack_tools, "_expand", lambda _path: missing)
    entry = {"name": "missing-repo", "path": "unused", "role": "test"}
    payload = {
        "schema": stack_tools.STACK_RELEASE_CHECK_SCHEMA,
        "overall": "NO-GO",
        "mode": "local",
        "blocked": ["missing-repo"],
        "warned": [],
        "repos": [stack_tools._release_entry(entry)],
        "checked_at": "2026-07-16T00:00:00+00:00",
    }

    Draft202012Validator(_schema("mq_stack_release_check.schema.json")).validate(payload)
