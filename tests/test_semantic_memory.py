"""Tests for mq_agent.memory.semantic — no OpenAI calls, no repo-signal required."""
import pytest

from mq_agent.memory.semantic import SemanticMemoryStatus, get_vector_store_id, status


def test_get_vector_store_id_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    assert get_vector_store_id() is None


def test_get_vector_store_id_present(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_test123")
    assert get_vector_store_id() == "vs_test123"


def test_get_vector_store_id_strips_whitespace(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "  vs_test  ")
    assert get_vector_store_id() == "vs_test"


def test_get_vector_store_id_empty_string(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "")
    assert get_vector_store_id() is None


def test_get_vector_store_id_whitespace_only(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "   ")
    assert get_vector_store_id() is None


def test_memory_status_missing_vector_store(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    state = status(tmp_path)
    assert state.status == "missing-vector-store"
    assert state.enabled is False
    assert state.vector_store_id is None
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
