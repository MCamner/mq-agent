"""Credential boundary tests for the mq-mcp child process."""
from __future__ import annotations

from unittest.mock import patch

from mq_agent.core.credentials import OpenAICredential
from mq_agent.mcp import manager


def test_child_env_ignores_openai_key_from_dotenv(tmp_path, monkeypatch):
    server_dir = tmp_path / "mq-mcp"
    server_dir.mkdir()
    (server_dir / ".env").write_text(
        "OPENAI_API_KEY=stale-dotenv-key\nMQ_TEST_SETTING=from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_install(env):
        env["OPENAI_API_KEY"] = "keychain-key"
        return OpenAICredential("keychain-key", "keychain")

    with patch.object(manager, "install_openai_api_key", side_effect=fake_install):
        child_env = manager._child_env(server_dir)

    assert child_env["OPENAI_API_KEY"] == "keychain-key"
    assert child_env["MQ_TEST_SETTING"] == "from-dotenv"


def test_child_env_preserves_explicit_process_key(tmp_path, monkeypatch):
    server_dir = tmp_path / "mq-mcp"
    server_dir.mkdir()
    (server_dir / ".env").write_text(
        "OPENAI_API_KEY=stale-dotenv-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "explicit-process-key")

    def fake_install(env):
        assert env["OPENAI_API_KEY"] == "explicit-process-key"
        return OpenAICredential("explicit-process-key", "env")

    with patch.object(manager, "install_openai_api_key", side_effect=fake_install):
        child_env = manager._child_env(server_dir)

    assert child_env["OPENAI_API_KEY"] == "explicit-process-key"


def test_child_env_does_not_copy_dotenv_secret_when_credential_missing(tmp_path, monkeypatch):
    server_dir = tmp_path / "mq-mcp"
    server_dir.mkdir()
    (server_dir / ".env").write_text(
        "OPENAI_API_KEY=stale-dotenv-key\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch.object(
        manager,
        "install_openai_api_key",
        return_value=OpenAICredential(None, "missing"),
    ):
        child_env = manager._child_env(server_dir)

    assert "OPENAI_API_KEY" not in child_env
