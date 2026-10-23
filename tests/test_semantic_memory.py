"""Tests for mq_agent.memory.semantic — no OpenAI calls, no repo-signal required."""

from mq_agent.memory.semantic import SemanticMemoryStatus, status

# Resolution itself is covered in tests/test_vector_store_identity.py, which
# owns the canonical-versus-override contract. These tests cover status().


def test_memory_status_reports_the_repo_it_was_asked_about(monkeypatch, tmp_path):
    monkeypatch.setenv("MQ_AGENT_PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    state = status(tmp_path)
    assert state.repo_path == str(tmp_path.resolve())


def test_memory_status_returns_semantic_memory_status(monkeypatch, tmp_path):
    monkeypatch.setenv("MQ_AGENT_PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    state = status(tmp_path)
    assert isinstance(state, SemanticMemoryStatus)


def test_memory_status_without_cloud_probe_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setenv("MQ_AGENT_PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_abc")
    import mq_agent.memory.semantic as sem

    monkeypatch.setattr(sem, "repo_signal_available", lambda: False)
    state = status(tmp_path)

    assert state.status == "skipped"
    assert state.enabled is False
    assert state.configured is True
    assert state.reachable is None
    assert state.freshness == "unknown"
    assert state.vector_store_id == "vs_abc"


def test_memory_status_configured_without_openai_probe_is_skipped(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("MQ_AGENT_PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_abc")
    import mq_agent.memory.semantic as sem

    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    state = status(tmp_path)

    assert state.status == "skipped"
    assert state.enabled is False
    assert state.configured is True
    assert state.reachable is None
    assert state.freshness == "unknown"


def test_selected_cloud_without_client_remains_degraded(monkeypatch, tmp_path):
    import mq_agent.memory.semantic as sem

    monkeypatch.setenv("MQ_AGENT_PROVIDER", "openai")
    monkeypatch.setattr(sem, "_openai_client", lambda: None)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    state = status(tmp_path)
    assert state.status == "degraded"
    assert state.reachable is None
    assert state.enabled is False
