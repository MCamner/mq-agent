from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from mq_agent.config import MqAgentConfig
from mq_agent.main import _client
from mq_agent.tools import model_runtime


def test_all_local_profiles_use_qwen():
    assert set(model_runtime.DEFAULT_PROFILES.values()) == {"qwen3.5:9b"}


def test_native_local_client_needs_no_cloud_key(monkeypatch):
    monkeypatch.setattr("mq_agent.config.load_config", lambda: MqAgentConfig())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MQ_AGENT_PROVIDER", raising=False)
    with patch("openai.OpenAI", side_effect=AssertionError("cloud client constructed")):
        client = _client()
    assert type(client).__name__ == "OllamaClient"


def test_routing_json_does_not_inherit_learning_system(monkeypatch):
    monkeypatch.setattr(model_runtime, "_mq_learn_modelfile_path", lambda: pytest.fail("Learning prompt read by routing"))
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"response":"{}"}'
    with patch.object(model_runtime.urllib.request, "urlopen", return_value=response) as opened:
        model_runtime._ollama_generate("qwen3.5:9b", "route evidence", 30, json_format={"type":"object"})
    payload = json.loads(opened.call_args.args[0].data)
    assert "system" not in payload
    assert payload["think"] is False


def test_invalid_provider_is_not_silently_replaced(monkeypatch):
    monkeypatch.setenv("MQ_AGENT_PROVIDER", "typo")
    with pytest.raises(ValueError, match="provider"):
        MqAgentConfig().effective_provider()


def test_local_failure_has_no_cloud_fallback(monkeypatch):
    import urllib.error
    from mq_agent.core import local_llm
    monkeypatch.setattr(local_llm.urllib.request, "urlopen", MagicMock(side_effect=urllib.error.URLError("offline")))
    with patch("openai.OpenAI", side_effect=AssertionError("cloud called")):
        with pytest.raises(urllib.error.URLError):
            local_llm.OllamaClient().chat.completions.create(model="qwen3.5:9b", messages=[])


def test_cloud_model_requires_explicit_cloud_provider(monkeypatch):
    monkeypatch.delenv("MQ_AGENT_MODEL", raising=False)
    monkeypatch.delenv("MQ_AGENT_PROVIDER", raising=False)
    config = MqAgentConfig(model="gpt-4o")
    assert config.effective_provider() == "ollama"
    assert config.effective_model() == "qwen3.5:9b"
    monkeypatch.setenv("MQ_AGENT_PROVIDER", "openai")
    assert config.effective_provider() == "openai"
    assert config.effective_model() == "gpt-4o"


def test_local_memory_status_does_not_probe_cloud_with_ambient_key(monkeypatch):
    from mq_agent.memory.semantic import _openai_client
    monkeypatch.delenv("MQ_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-ambient-key")
    with patch("openai.OpenAI", side_effect=AssertionError("implicit cloud memory call")):
        assert _openai_client() is None
