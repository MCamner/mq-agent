"""Tests for repo-signal integration tools."""

from mq_agent.tools.signal_tools import (
    repo_analyze,
    repo_publish_checklist,
    repo_readme_score,
    repo_scan,
    repo_signal_json,
    signal_available,
)


def test_signal_available():
    # repo-signal is installed in the dev environment
    assert signal_available() is True


def test_repo_scan_returns_string():
    result = repo_scan(".")
    assert isinstance(result, str)
    assert "Repo:" in result
    assert "Branch:" in result


def test_repo_scan_contains_project_type():
    result = repo_scan(".")
    assert "Project type:" in result


def test_repo_readme_score_returns_string():
    result = repo_readme_score(".")
    assert isinstance(result, str)
    assert "README score:" in result


def test_repo_readme_score_contains_bar():
    result = repo_readme_score(".")
    # bar uses block characters
    assert "█" in result or "░" in result


def test_repo_publish_checklist_returns_string():
    result = repo_publish_checklist(".")
    assert isinstance(result, str)
    assert "Publish checklist:" in result


def test_repo_analyze_returns_string():
    result = repo_analyze(".")
    assert isinstance(result, str)
    assert len(result) > 100


def test_repo_signal_json_structure():
    result = repo_signal_json(".")
    assert result["available"] is True
    assert "name" in result
    assert "project_type" in result
    assert "readme_score" in result
    assert "publish_checklist" in result
    assert "score" in result["readme_score"]
    assert "score" in result["publish_checklist"]


def test_repo_signal_json_readme_score_range():
    result = repo_signal_json(".")
    score = result["readme_score"]["score"]
    assert 0 <= score <= 100


def test_repo_signal_json_focus_areas_is_list():
    result = repo_signal_json(".")
    assert isinstance(result["focus_areas"], list)


def test_repo_scan_missing_path():
    result = repo_scan("/tmp/definitely_does_not_exist_xyz")
    # Should not raise — repo-signal degrades gracefully on missing repos
    assert isinstance(result, str)
