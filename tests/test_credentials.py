"""Tests for process-scoped OpenAI credential resolution."""
from __future__ import annotations

import subprocess

from mq_agent.core import credentials


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["security"], returncode=returncode, stdout=stdout, stderr="")


def test_explicit_environment_key_wins_without_keychain(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Keychain must not be read when OPENAI_API_KEY is set")

    monkeypatch.setattr(credentials.subprocess, "run", fail_if_called)
    result = credentials.resolve_openai_api_key(
        {"OPENAI_API_KEY": "env-secret"},
        platform="darwin",
    )

    assert result.key == "env-secret"
    assert result.source == "env"


def test_keychain_is_fallback_on_macos(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return _completed("keychain-secret\n")

    monkeypatch.setattr(credentials.subprocess, "run", fake_run)
    result = credentials.resolve_openai_api_key(
        {"USER": "operator"},
        platform="darwin",
    )

    assert result.key == "keychain-secret"
    assert result.source == "keychain"
    args, kwargs = calls[0]
    assert args == [
        "/usr/bin/security",
        "find-generic-password",
        "-a",
        "operator",
        "-s",
        "mq-openai-api-key",
        "-w",
    ]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False


def test_keychain_service_and_account_can_be_overridden(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return _completed("keychain-secret")

    monkeypatch.setattr(credentials.subprocess, "run", fake_run)
    result = credentials.resolve_openai_api_key(
        {
            "USER": "ignored-user",
            "MQ_OPENAI_KEYCHAIN_SERVICE": "custom-service",
            "MQ_OPENAI_KEYCHAIN_ACCOUNT": "custom-account",
        },
        platform="darwin",
    )

    assert result.source == "keychain"
    assert seen["args"][3] == "custom-account"
    assert seen["args"][5] == "custom-service"


def test_non_macos_does_not_probe_keychain(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("security must not be called off macOS")

    monkeypatch.setattr(credentials.subprocess, "run", fail_if_called)
    result = credentials.resolve_openai_api_key({}, platform="linux")

    assert result.key is None
    assert result.source == "missing"


def test_failed_keychain_lookup_is_missing(monkeypatch):
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["security"],
            returncode=44,
            stdout="",
            stderr="sensitive diagnostic",
        ),
    )

    result = credentials.resolve_openai_api_key(
        {"USER": "operator"},
        platform="darwin",
    )

    assert result.key is None
    assert result.source == "missing"
    assert "sensitive diagnostic" not in repr(result)


def test_credential_repr_never_contains_secret():
    result = credentials.OpenAICredential("super-secret", "keychain")

    assert "super-secret" not in repr(result)
    assert "keychain" in repr(result)


def test_install_places_keychain_key_in_process_env(monkeypatch):
    env = {"USER": "operator"}
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *args, **kwargs: _completed("new-key"),
    )

    result = credentials.install_openai_api_key(env, platform="darwin")

    assert result.source == "keychain"
    assert env["OPENAI_API_KEY"] == "new-key"


def test_install_never_overwrites_explicit_process_key(monkeypatch):
    env = {"OPENAI_API_KEY": "explicit-key"}

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Keychain must not be read")

    monkeypatch.setattr(credentials.subprocess, "run", fail_if_called)
    result = credentials.install_openai_api_key(env, platform="darwin")

    assert result.source == "env"
    assert env["OPENAI_API_KEY"] == "explicit-key"
