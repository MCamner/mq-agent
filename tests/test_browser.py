"""Tests for browser_tools and mq-agent browser CLI commands."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.browser_tools import (
    _assert_safe_url,
    _HTMLExtractor,
    inspect_url,
    summarize_url,
    verify_release_url,
)

runner = CliRunner()

SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Release v0.7.0</title>
  <meta name="description" content="mq-agent v0.7.0 release notes">
</head>
<body>
  <h1>v0.7.0 — Browser-assisted workflows</h1>
  <h2>What's new</h2>
  <h2>Installation</h2>
  <p>This release adds browser inspection commands.</p>
  <a href="/McAmner/mq-agent/releases">All releases</a>
  <a href="/McAmner/mq-agent">Repo</a>
</body>
</html>"""


# ── _assert_safe_url ───────────────────────────────────────────────────────

def test_assert_safe_url_accepts_https():
    _assert_safe_url("https://example.com")


def test_assert_safe_url_accepts_http():
    _assert_safe_url("http://localhost:8080")


def test_assert_safe_url_blocks_file():
    with pytest.raises(ValueError, match="Blocked URL scheme"):
        _assert_safe_url("file:///etc/passwd")


def test_assert_safe_url_blocks_javascript():
    with pytest.raises(ValueError, match="Blocked URL scheme"):
        _assert_safe_url("javascript:alert(1)")


def test_assert_safe_url_blocks_missing_scheme():
    with pytest.raises(ValueError, match="must include a scheme"):
        _assert_safe_url("example.com/page")


# ── _HTMLExtractor ─────────────────────────────────────────────────────────

def test_html_extractor_parses_title():
    p = _HTMLExtractor()
    p.feed("<html><head><title>Hello World</title></head></html>")
    assert p.title == "Hello World"


def test_html_extractor_parses_description_meta():
    p = _HTMLExtractor()
    p.feed('<meta name="description" content="Test desc">')
    assert p.description == "Test desc"


def test_html_extractor_parses_headings():
    p = _HTMLExtractor()
    p.feed("<h1>Main Heading</h1><h2>Sub One</h2><h2>Sub Two</h2>")
    assert p.h1s == ["Main Heading"]
    assert "Sub One" in p.h2s
    assert "Sub Two" in p.h2s


def test_html_extractor_parses_links():
    p = _HTMLExtractor()
    p.feed('<a href="/about">About</a><a href="https://example.com">External</a>')
    assert "/about" in p.links
    assert "https://example.com" in p.links


def test_html_extractor_ignores_anchor_and_js_links():
    p = _HTMLExtractor()
    p.feed('<a href="#section">Jump</a><a href="javascript:void(0)">Click</a>')
    assert "#section" not in p.links
    assert "javascript:void(0)" not in p.links


def test_html_extractor_text_content():
    p = _HTMLExtractor()
    p.feed("<p>Hello</p><p>World</p>")
    text = p.text_content()
    assert "Hello" in text
    assert "World" in text


# ── inspect_url ────────────────────────────────────────────────────────────

def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.headers = {"content-type": "text/html; charset=utf-8"}
    resp.raise_for_status = MagicMock()
    return resp


def test_inspect_url_returns_structured_metadata():
    with patch("httpx.get", return_value=_mock_response(SAMPLE_HTML)):
        result = inspect_url("https://example.com")
    assert result["ok"] is True
    assert result["title"] == "Release v0.7.0"
    assert result["description"] == "mq-agent v0.7.0 release notes"
    assert "v0.7.0" in result["h1s"][0]
    assert result["word_count"] > 0
    assert len(result["links"]) > 0


def test_inspect_url_handles_http_error():
    error_resp = MagicMock()
    error_resp.status_code = 404
    error_resp.text = "Not Found"
    import httpx
    exc = httpx.HTTPStatusError("404", request=MagicMock(), response=error_resp)
    with patch("httpx.get", side_effect=exc):
        result = inspect_url("https://example.com/missing")
    assert result["ok"] is False
    assert result["status_code"] == 404


def test_inspect_url_handles_connection_error():
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        result = inspect_url("https://unreachable.invalid")
    assert result["ok"] is False
    assert "error" in result


def test_inspect_url_blocks_file_scheme():
    with pytest.raises(ValueError, match="Blocked URL scheme"):
        inspect_url("file:///etc/passwd")


# ── summarize_url ──────────────────────────────────────────────────────────

def test_summarize_url_includes_title_and_description():
    with patch("httpx.get", return_value=_mock_response(SAMPLE_HTML)):
        summary = summarize_url("https://example.com")
    assert "Release v0.7.0" in summary
    assert "mq-agent v0.7.0" in summary


def test_summarize_url_returns_error_string_on_failure():
    with patch("httpx.get", side_effect=Exception("network error")):
        summary = summarize_url("https://unreachable.invalid")
    assert "Error" in summary or "error" in summary


# ── verify_release_url ─────────────────────────────────────────────────────

def test_verify_release_url_passes_for_valid_page():
    with patch("httpx.get", return_value=_mock_response(SAMPLE_HTML)):
        result = verify_release_url("https://github.com/McAmner/mq-agent/releases/tag/v0.7.0")
    assert result["passed"] is True
    assert all(c["passed"] for c in result["checks"] if c["check"] == "page reachable")


def test_verify_release_url_checks_expected_tag():
    with patch("httpx.get", return_value=_mock_response(SAMPLE_HTML)):
        result = verify_release_url(
            "https://github.com/McAmner/mq-agent/releases/tag/v0.7.0",
            expected_tag="v0.7.0",
        )
    tag_check = next(c for c in result["checks"] if "expected tag" in c["check"])
    assert tag_check["passed"] is True


def test_verify_release_url_fails_for_missing_tag():
    with patch("httpx.get", return_value=_mock_response(SAMPLE_HTML)):
        result = verify_release_url(
            "https://github.com/McAmner/mq-agent/releases/tag/v0.7.0",
            expected_tag="v9.9.9",
        )
    tag_check = next(c for c in result["checks"] if "expected tag" in c["check"])
    assert tag_check["passed"] is False


def test_verify_release_url_fails_on_unreachable():
    with patch("httpx.get", side_effect=Exception("timeout")):
        result = verify_release_url("https://unreachable.invalid/releases/tag/v1.0.0")
    assert result["passed"] is False


# ── CLI: browser inspect ───────────────────────────────────────────────────

def test_cli_browser_inspect_json():
    with patch("mq_agent.tools.browser_tools.inspect_url",
               return_value={"ok": True, "url": "https://example.com", "title": "Test",
                             "description": "", "h1s": [], "h2s": [], "links": [],
                             "word_count": 10, "status_code": 200, "content_type": "text/html"}):
        result = runner.invoke(app, ["browser", "inspect", "https://example.com", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["ok"] is True


def test_cli_browser_inspect_exits_1_on_error():
    with patch("mq_agent.tools.browser_tools.inspect_url",
               return_value={"ok": False, "url": "https://bad.invalid", "error": "timeout"}):
        result = runner.invoke(app, ["browser", "inspect", "https://bad.invalid"])
    assert result.exit_code == 1


# ── CLI: browser summarize ─────────────────────────────────────────────────

def test_cli_browser_summarize_json():
    with patch("mq_agent.tools.browser_tools.summarize_url",
               return_value="Title: Test\nWord count: ~50"):
        result = runner.invoke(app, ["browser", "summarize", "https://example.com", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "summary" in data


# ── CLI: browser verify-release ────────────────────────────────────────────

def test_cli_browser_verify_release_passes():
    with patch("mq_agent.tools.browser_tools.verify_release_url",
               return_value={"url": "https://github.com/x/y/releases/tag/v1.0",
                             "passed": True,
                             "checks": [{"check": "page reachable", "passed": True, "note": "HTTP 200"}]}):
        result = runner.invoke(app, ["browser", "verify-release", "https://github.com/x/y/releases/tag/v1.0"])
    assert result.exit_code == 0


def test_cli_browser_verify_release_fails_exits_1():
    with patch("mq_agent.tools.browser_tools.verify_release_url",
               return_value={"url": "https://github.com/x/y/releases/tag/v1.0",
                             "passed": False,
                             "checks": [{"check": "page reachable", "passed": False, "note": "timeout"}]}):
        result = runner.invoke(app, ["browser", "verify-release", "https://github.com/x/y/releases/tag/v1.0"])
    assert result.exit_code == 1


def test_cli_browser_verify_release_with_tag():
    with patch("mq_agent.tools.browser_tools.verify_release_url",
               return_value={"url": "https://github.com/x/y/releases/tag/v0.7.0",
                             "passed": True,
                             "checks": [
                                 {"check": "page reachable", "passed": True, "note": "HTTP 200"},
                                 {"check": "expected tag 'v0.7.0' present", "passed": True, "note": "found"},
                             ]}) as mock:
        result = runner.invoke(app, [
            "browser", "verify-release",
            "https://github.com/x/y/releases/tag/v0.7.0",
            "--tag", "v0.7.0",
        ])
    assert result.exit_code == 0
    mock.assert_called_once_with(
        "https://github.com/x/y/releases/tag/v0.7.0",
        expected_tag="v0.7.0",
        timeout=10,
    )
