"""Tests for mq_agent.memory.semantic — no OpenAI calls, no repo-signal required."""

import pytest

from mq_agent.memory.semantic import (
    CANONICAL_VECTOR_STORE_ID,
    CANONICAL_VECTOR_STORE_NAME,
    SemanticMemoryStatus,
    get_vector_store_id,
    resolve_vector_store_id,
    status,
)


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


# ── canonical store ────────────────────────────────────────────────────────
#
# mq-agent owns the canonical semantic memory. Before this contract the ID
# existed only in gitignored .env files, so an unconfigured shell left
# mq-agent with no memory at all — and any consumer that hardcoded a
# fallback silently pointed somewhere else.


def test_canonical_id_is_the_store_named_by_the_global_policy():
    # mq-mcp/docs/global/GLOBAL_VECTOR_STORE_POLICY.md, "Store IDs".
    assert CANONICAL_VECTOR_STORE_ID == "vs_69ffa9a4ef5c81919d7d237c3ecdc260"
    assert CANONICAL_VECTOR_STORE_NAME == "semantic repository memory"


def test_resolve_falls_back_to_canonical_when_env_is_unset(monkeypatch):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    assert resolve_vector_store_id() == (CANONICAL_VECTOR_STORE_ID, "canonical")


@pytest.mark.parametrize("blank", ["", "   "])
def test_resolve_falls_back_to_canonical_when_env_is_blank(monkeypatch, blank):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", blank)
    assert resolve_vector_store_id() == (CANONICAL_VECTOR_STORE_ID, "canonical")


def test_resolve_prefers_an_explicit_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_override")
    assert resolve_vector_store_id() == ("vs_override", "env")


def test_status_resolves_canonical_without_env(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    state = status(tmp_path)
    assert state.status == "ready"
    assert state.enabled is True
    assert state.vector_store_id == CANONICAL_VECTOR_STORE_ID
    assert state.vector_store_source == "canonical"
    assert state.repo_path == str(tmp_path.resolve())


def test_status_reports_env_as_the_source_when_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_override")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    state = status(tmp_path)
    assert state.vector_store_id == "vs_override"
    assert state.vector_store_source == "env"


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
