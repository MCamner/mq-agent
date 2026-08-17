"""Regression tests for repo-signal CLI discovery."""

from mq_agent.tools import signal_tools


def test_resolver_skips_stale_project_binary_for_compatible_uv_tool(monkeypatch):
    stale = "/tmp/mq-agent/.venv/bin/repo-signal"
    uv_tool = "/Users/test/.local/bin/repo-signal"

    monkeypatch.setattr(signal_tools, "_candidate_bins", lambda: [stale, uv_tool])
    monkeypatch.setattr(
        signal_tools,
        "_probe_version",
        lambda executable: (1, 0, 0) if executable == stale else (1, 4, 2),
    )

    executable, error = signal_tools._resolve_repo_signal()

    assert executable == uv_tool
    assert error is None


def test_resolver_reports_old_candidates_and_uv_tool_fix(monkeypatch):
    stale = "/tmp/mq-agent/.venv/bin/repo-signal"
    monkeypatch.setattr(signal_tools, "_candidate_bins", lambda: [stale])
    monkeypatch.setattr(signal_tools, "_probe_version", lambda _executable: (1, 0, 0))

    executable, error = signal_tools._resolve_repo_signal()

    assert executable is None
    assert error is not None
    assert "need >= 1.4.2" in error
    assert stale in error
    assert "uv tool install" in error
    assert "[ai,vector]" in error


def test_signal_available_accepts_external_cli(monkeypatch):
    monkeypatch.setattr(
        signal_tools,
        "_resolve_repo_signal",
        lambda: ("/Users/test/.local/bin/repo-signal", None),
    )

    assert signal_tools.signal_available() is True


def test_parse_readme_score_preserves_canonical_keys():
    output = """# README Score Report

README score: 80/100

## Checks

- [OK] title
- [OK] short pitch
- [MISSING] install section
- [OK] usage section
- [OK] examples
- [OK] screenshots/demo
- [OK] badges
- [OK] license
- [OK] roadmap
- [MISSING] contributing

Missing: install section, contributing
"""

    result = signal_tools._parse_readme_score(output)

    assert result["score"] == 80
    assert result["max_score"] == 100
    assert "short_pitch" in result["present"]
    assert result["missing"] == ["install", "contributing"]


def test_focus_areas_parse_analyze_contract():
    output = """# Repo Signal Analyze Report

## Suggested Focus Areas

1. Improve release docs
2. Add contract tests
"""

    assert signal_tools._focus_areas_from_analyze(output) == [
        "Improve release docs",
        "Add contract tests",
    ]
