"""Tests for stack sweep history persistence and stack history CLI command."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import app, _sweep_history_append, _stack_history_diff

runner = CliRunner()


@pytest.fixture()
def tmp_history(tmp_path, monkeypatch):
    """Redirect history file to a temp directory."""
    mq_dir = tmp_path / ".mq-agent"
    mq_dir.mkdir()
    history_file = mq_dir / "sweep-history.jsonl"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return history_file


def _make_results(scores: dict[str, int]) -> list[dict]:
    return [
        {"name": name, "overall": score, "publish": 14, "skipped": False}
        for name, score in scores.items()
    ]


def _make_sweep(scores: dict[str, int], ts: str = "2026-06-10T10:00:00") -> dict:
    return {"ts": ts, "results": _make_results(scores)}


class TestSweepHistoryAppend:
    def test_creates_file_on_first_write(self, tmp_history):
        _sweep_history_append(_make_results({"mq-agent": 100}))
        assert tmp_history.exists()

    def test_appends_valid_jsonl(self, tmp_history):
        _sweep_history_append(_make_results({"mq-agent": 100}))
        _sweep_history_append(_make_results({"mq-agent": 95}))
        lines = [ln for ln in tmp_history.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2
        for line in lines:
            record = json.loads(line)
            assert "ts" in record
            assert "results" in record

    def test_includes_timestamp(self, tmp_history):
        _sweep_history_append(_make_results({"mq-agent": 100}))
        record = json.loads(tmp_history.read_text().strip())
        assert record["ts"].startswith("2026") or len(record["ts"]) > 10

    def test_skipped_repos_preserved(self, tmp_history):
        results = [{"name": "mq-hal", "skipped": True}]
        _sweep_history_append(results)
        record = json.loads(tmp_history.read_text().strip())
        assert record["results"][0]["skipped"] is True


class TestStackHistoryCmd:
    def test_no_history_file_shows_hint(self, tmp_history):
        result = runner.invoke(app, ["stack", "history"])
        assert result.exit_code == 0
        assert "No sweep history" in result.output

    def test_shows_table_with_one_sweep(self, tmp_history):
        tmp_history.write_text(
            json.dumps(_make_sweep({"mq-agent": 100, "mq-mcp": 95})) + "\n"
        )
        result = runner.invoke(app, ["stack", "history"])
        assert result.exit_code == 0
        assert "mq-agent" in result.output
        assert "mq-mcp" in result.output

    def test_json_output(self, tmp_history):
        tmp_history.write_text(
            json.dumps(_make_sweep({"mq-agent": 100})) + "\n"
        )
        result = runner.invoke(app, ["stack", "history", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["results"][0]["name"] == "mq-agent"

    def test_limit_flag(self, tmp_history):
        lines = "\n".join(
            json.dumps(_make_sweep({"mq-agent": i}, ts=f"2026-06-10T{i:02d}:00:00"))
            for i in range(1, 6)
        ) + "\n"
        tmp_history.write_text(lines)
        result = runner.invoke(app, ["stack", "history", "--json", "--limit", "2"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2

    def test_diff_requires_two_sweeps(self, tmp_history):
        tmp_history.write_text(
            json.dumps(_make_sweep({"mq-agent": 100})) + "\n"
        )
        result = runner.invoke(app, ["stack", "history", "--diff"])
        assert result.exit_code == 0
        assert "at least 2 sweeps" in result.output

    def test_diff_shows_delta(self, tmp_history):
        lines = (
            json.dumps(_make_sweep({"mq-agent": 80}, ts="2026-06-10T10:00:00")) + "\n"
            + json.dumps(_make_sweep({"mq-agent": 90}, ts="2026-06-10T11:00:00")) + "\n"
        )
        tmp_history.write_text(lines)
        result = runner.invoke(app, ["stack", "history", "--diff"])
        assert result.exit_code == 0
        assert "+10" in result.output


class TestStackHistoryDiff:
    def test_improvement_shows_green_delta(self, capsys):
        a = _make_sweep({"mq-agent": 70}, ts="2026-06-10T10:00:00")
        b = _make_sweep({"mq-agent": 85}, ts="2026-06-10T11:00:00")
        _stack_history_diff(a, b)

    def test_regression_shows_red_delta(self, capsys):
        a = _make_sweep({"mq-agent": 90}, ts="2026-06-10T10:00:00")
        b = _make_sweep({"mq-agent": 80}, ts="2026-06-10T11:00:00")
        _stack_history_diff(a, b)

    def test_new_repo_in_b_shows_dash_for_a(self, capsys):
        a = _make_sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00")
        b = _make_sweep({"mq-agent": 100, "mq-mcp": 95}, ts="2026-06-10T11:00:00")
        _stack_history_diff(a, b)
