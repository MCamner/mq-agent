"""Tests for mq-agent Ollama model runtime commands."""
from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.model_runtime import (
    bench_model,
    current_model,
    load_models_config,
    model_doctor,
    switch_model,
)

runner = CliRunner()


def test_default_models_config(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))

    config = load_models_config()

    assert config["current_profile"] == "fast"
    assert config["profiles"]["fast"] == "qwen3:4b-instruct"
    assert config["profiles"]["review"] == "qwen3:4b-instruct"
    assert config["profiles"]["planner"] == "qwen3:4b-instruct"
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
    assert data["profiles"]["planner"] == "qwen3:4b-instruct"


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
    monkeypatch.setattr("mq_agent.tools.model_runtime.shutil.which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        "mq_agent.tools.model_runtime._ollama_generate",
        lambda *args, **kwargs: {
            "response": "OK",
            "done": True,
            "done_reason": "stop",
            "total_duration": 2_000_000_000,
            "load_duration": 500_000_000,
            "prompt_eval_count": 4,
            "prompt_eval_duration": 200_000_000,
            "eval_count": 10,
            "eval_duration": 1_000_000_000,
        },
    )

    result = runner.invoke(app, ["models", "bench", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["schema"] == "ollama_model_benchmark.v1"
    assert data["model"] == "qwen3:4b-instruct"
    assert data["output"] == "OK"
    assert data["metrics"] == {
        "total_duration_ms": 2000.0,
        "load_duration_ms": 500.0,
        "prompt_eval_count": 4,
        "prompt_eval_duration_ms": 200.0,
        "eval_count": 10,
        "eval_duration_ms": 1000.0,
        "tokens_per_second": 10.0,
    }
    assert data["validation"] == {"json_valid": False, "schema_valid": False}


def test_bench_model_validates_memory_schema(monkeypatch):
    payload = {
        "pattern_name": "release-drift",
        "pattern_type": "release",
        "summary": "Version surfaces differed.",
        "evidence": ["version mismatch"],
        "recommended_action": "Check version surfaces.",
        "confidence": "medium",
        "should_store": False,
    }
    monkeypatch.setattr("mq_agent.tools.model_runtime.shutil.which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        "mq_agent.tools.model_runtime._ollama_generate",
        lambda *args, **kwargs: {
            "response": json.dumps(payload),
            "done": True,
            "total_duration": 1,
            "load_duration": 0,
            "prompt_eval_count": 1,
            "prompt_eval_duration": 1,
            "eval_count": 1,
            "eval_duration": 1,
        },
    )

    data = bench_model("mq-learn", prompt="review", validate_schema=True)

    assert data["ok"] is True
    assert data["validation"] == {"json_valid": True, "schema_valid": True}


def test_model_doctor_passes_with_installed_profiles(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))
    monkeypatch.setattr("mq_agent.tools.model_runtime.shutil.which", lambda _: "/usr/bin/ollama")

    def fake_run(args, **kwargs):
        outputs = {
            ("ollama", "--version"): "ollama version is 0.32.1\n",
            ("ollama", "list"): (
                "NAME ID SIZE MODIFIED\n"
                "qwen3:4b-instruct abc 2.5GB today\n"
                "mq-learn:latest def 2.0GB today\n"
            ),
            ("ollama", "ps"): "NAME ID SIZE PROCESSOR CONTEXT UNTIL\n",
        }
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=outputs[tuple(args)], stderr="")

    monkeypatch.setattr("mq_agent.tools.model_runtime.subprocess.run", fake_run)
    monkeypatch.setattr(
        "mq_agent.tools.model_runtime._ollama_generate_json",
        lambda *args: {"response": json.dumps({
            "pattern_name": "version-mismatch",
            "pattern_type": "release",
            "summary": "A version mismatch was corrected.",
            "evidence": ["version mismatch"],
            "recommended_action": "Check version surfaces.",
            "confidence": "medium",
            "should_store": False,
        })},
    )

    result = model_doctor(check_modelfile=False)

    assert result["ok"] is True
    assert result["schema"] == "ollama_runtime_doctor.v1"
    assert result["profiles"]["missing"] == []
    assert result["smoke"]["json_valid"] is True
    assert result["smoke"]["schema_valid"] is True


def test_models_doctor_json_fails_for_missing_profile_models(monkeypatch, tmp_path):
    config_path = tmp_path / "models.json"
    monkeypatch.setenv("MQ_AGENT_MODELS_CONFIG", str(config_path))
    monkeypatch.setenv("MQ_MCP_DIR", str(tmp_path / "missing-mq-mcp"))
    monkeypatch.setattr("mq_agent.tools.model_runtime.shutil.which", lambda _: "/usr/bin/ollama")

    def fake_run(args, **kwargs):
        outputs = {
            ("ollama", "--version"): "ollama version is 0.32.1\n",
            ("ollama", "list"): "NAME ID SIZE MODIFIED\nmq-learn:latest def 2.0GB today\n",
            ("ollama", "ps"): "NAME ID SIZE PROCESSOR CONTEXT UNTIL\n",
        }
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=outputs[tuple(args)], stderr="")

    monkeypatch.setattr("mq_agent.tools.model_runtime.subprocess.run", fake_run)

    result = runner.invoke(app, ["models", "doctor", "--no-smoke", "--json"])

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["profiles"]["missing"] == ["qwen3:4b-instruct"]
