"""Tests for mq-agent Ollama model runtime commands."""
from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.model_runtime import current_model, load_models_config, switch_model

runner = CliRunner()


def test_default_models_config(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    config = load_models_config()

    assert config["current_profile"] == "fast"
    assert config["profiles"]["memory"] == "mq-learn"


def test_switch_model_dry_run_does_not_write(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    result = switch_model("qwen3", profile="review", approve=False)

    assert result["changed"] is False
    assert result["profile"] == "review"
    assert result["model"] == "qwen3"
    assert not config_path.exists()


def test_switch_model_with_approve_writes_config(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    result = switch_model("mq-learn", profile="memory", approve=True)

    assert result["changed"] is True
    assert result["profile"] == "memory"
    assert result["model"] == "mq-learn"
    assert current_model()["profile"] == "memory"
    assert config_path.exists()


def test_models_current_json(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    result = runner.invoke(app, ["models", "current", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["profile"] == "fast"
    assert data["profiles"]["planner"] == "qwen3"


def test_models_switch_requires_approve_to_write(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    result = runner.invoke(app, ["models", "switch", "qwen3", "--profile", "review"])

    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert not config_path.exists()


def test_models_switch_approve_json(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    result = runner.invoke(
        app,
        ["models", "switch", "mq-learn", "--profile", "memory", "--approve", "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["changed"] is True
    assert data["profile"] == "memory"
    assert data["model"] == "mq-learn"


def test_models_list_json(monkeypatch):
    fake = subprocess.CompletedProcess(
        args=["ollama", "list"],
        returncode=0,
        stdout="NAME ID SIZE MODIFIED\nqwen3 abc 1GB today\nmq-learn def 1GB today\n",
        stderr="",
    )
    monkeypatch.setattr("mq_agent.tools.model_runtime.shutil.which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr("mq_agent.tools.model_runtime.subprocess.run", lambda *a, **kw: fake)

    result = runner.invoke(app, ["models", "list", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["models"] == ["qwen3", "mq-learn"]


def test_models_bench_json(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))
    fake = subprocess.CompletedProcess(
        args=["ollama", "run", "qwen3", "Reply with OK."],
        returncode=0,
        stdout="OK\n",
        stderr="",
    )
    monkeypatch.setattr("mq_agent.tools.model_runtime.shutil.which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr("mq_agent.tools.model_runtime.subprocess.run", lambda *a, **kw: fake)

    result = runner.invoke(app, ["models", "bench", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["model"] == "qwen3"
    assert data["output"] == "OK"
