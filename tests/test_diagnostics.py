"""Tests for mq_agent.core.diagnostics."""
from __future__ import annotations

import pytest

from mq_agent.core import diagnostics
from mq_agent.core.credentials import OpenAICredential
from mq_agent.core.diagnostics import required_checks_pass, run_checks


@pytest.fixture(autouse=True)
def _declared_credential(monkeypatch):
    """Every check in this file runs against a stated credential, never the machine's.

    `run_checks()` resolves `OPENAI_API_KEY`, which on macOS reads the login
    Keychain. The tests below assert the *shape* of the check list — how many
    items, which names, in what order — and none of them are about whether this
    developer happens to hold a key. Without a declared credential they were
    reading one, and on Linux CI they were not, so the same assertions were
    exercising two different code paths.

    The two tests that are about the credential set their own, after this.
    """
    monkeypatch.setattr(
        diagnostics,
        "resolve_openai_api_key",
        lambda: OpenAICredential("declared-by-test", "env"),
    )


def test_run_checks_returns_seven_items():
    checks = run_checks()
    assert len(checks) == 7


def test_run_checks_first_four_are_required():
    checks = run_checks()
    names = [name for name, _, _ in checks[:4]]
    assert "OPENAI_API_KEY" in names
    assert "git" in names
    assert "uv" in names
    assert "Python ≥ 3.11" in names


def test_run_checks_sixth_is_optional_mcp():
    checks = run_checks()
    name, _, _ = checks[5]
    assert "optional" in name.lower() or "mcp" in name.lower()


def test_run_checks_includes_orchestration_contract_check():
    checks = run_checks()
    names = [name for name, _, _ in checks]
    assert "validate_orchestration_contract" in names


def test_required_checks_pass_true_when_first_four_ok():
    checks = [
        ("OPENAI_API_KEY", True, ""),
        ("git", True, ""),
        ("uv", True, ""),
        ("Python ≥ 3.11", True, ""),
        ("repo-signal", False, "install"),
        ("mq-mcp (optional)", False, "start"),
        ("validate_orchestration_contract", False, "upgrade"),
    ]
    assert required_checks_pass(checks) is True


def test_required_checks_pass_false_when_one_required_fails():
    checks = [
        ("OPENAI_API_KEY", False, "configure OpenAI credential"),
        ("git", True, ""),
        ("uv", True, ""),
        ("Python ≥ 3.11", True, ""),
        ("repo-signal", True, ""),
        ("mq-mcp (optional)", False, "start"),
    ]
    assert required_checks_pass(checks) is False


def test_run_checks_python_check_passes_on_current_interpreter():
    checks = run_checks()
    py_checks = [(name, ok, action) for name, ok, action in checks if "Python" in name]
    assert len(py_checks) == 1
    _, ok, _ = py_checks[0]
    assert ok is True


def test_run_checks_git_available():
    checks = run_checks()
    git_checks = [(name, ok, _) for name, ok, _ in checks if name == "git"]
    assert len(git_checks) == 1
    _, ok, _ = git_checks[0]
    assert ok is True


def test_run_checks_with_no_api_key(monkeypatch):
    monkeypatch.setattr(
        "mq_agent.core.diagnostics.resolve_openai_api_key",
        lambda: OpenAICredential(None, "missing"),
    )

    checks = run_checks()

    key_checks = [(name, ok, _) for name, ok, _ in checks if "OPENAI" in name]
    assert len(key_checks) == 1
    _, ok, action = key_checks[0]
    assert ok is False
    assert "Keychain" in action


def test_run_checks_accepts_keychain_credential(monkeypatch):
    monkeypatch.setattr(
        "mq_agent.core.diagnostics.resolve_openai_api_key",
        lambda: OpenAICredential("keychain-secret", "keychain"),
    )

    checks = run_checks()

    key_checks = [(name, ok, _) for name, ok, _ in checks if "OPENAI" in name]
    assert len(key_checks) == 1
    assert key_checks[0][1] is True
