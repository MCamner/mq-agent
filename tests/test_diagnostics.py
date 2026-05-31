"""Tests for mq_agent.core.diagnostics."""
from __future__ import annotations

from mq_agent.core.diagnostics import required_checks_pass, run_checks


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
        ("OPENAI_API_KEY", False, "export OPENAI_API_KEY=sk-..."),
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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    checks = run_checks()
    key_checks = [(name, ok, _) for name, ok, _ in checks if "OPENAI" in name]
    assert len(key_checks) == 1
    _, ok, _ = key_checks[0]
    assert ok is False
