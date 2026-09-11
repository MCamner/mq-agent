"""Tests for mq_agent.memory.semantic — no OpenAI calls, no repo-signal required."""

from mq_agent.memory.semantic import SemanticMemoryStatus, status

# Resolution itself is covered in tests/test_vector_store_identity.py, which
# owns the canonical-versus-override contract. These tests cover status().


def test_memory_status_reports_the_repo_it_was_asked_about(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    state = status(tmp_path)
    assert state.repo_path == str(tmp_path.resolve())


def test_memory_status_returns_semantic_memory_status(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    state = status(tmp_path)
    assert isinstance(state, SemanticMemoryStatus)


def test_memory_status_with_vector_store_no_repo_signal(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_abc")
    # repo-signal is unlikely to be missing but we mock it
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: False)
    state = status(tmp_path)
    assert state.status == "missing-repo-signal"
    assert state.enabled is False
    assert state.vector_store_id == "vs_abc"


def test_memory_status_ready(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_abc")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    state = status(tmp_path)
    assert state.status == "ready"
    assert state.enabled is True
