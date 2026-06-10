"""Tests for stack alert logic and CLI command."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import _compute_alerts, app

runner = CliRunner()


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_history(tmp_path, monkeypatch):
    mq_dir = tmp_path / ".mq-agent"
    mq_dir.mkdir()
    history_file = mq_dir / "sweep-history.jsonl"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return history_file


def _sweep(scores: dict[str, int | None], ts: str = "2026-06-10T10:00:00") -> dict:
    results = []
    for name, score in scores.items():
        if score is None:
            results.append({"name": name, "skipped": True})
        else:
            results.append({"name": name, "overall": score, "publish": 14, "skipped": False})
    return {"ts": ts, "results": results}


def _write_sweeps(history_file: Path, sweeps: list[dict]) -> None:
    history_file.write_text("\n".join(json.dumps(s) for s in sweeps) + "\n")


# ── _compute_alerts ─────────────────────────────────────────────────────────

class TestComputeAlerts:
    def test_no_alerts_when_stable(self):
        sweeps = [_sweep({"mq-agent": 100}), _sweep({"mq-agent": 100})]
        assert _compute_alerts(sweeps) == []

    def test_drop_triggers_alert(self):
        sweeps = [_sweep({"mq-agent": 100}), _sweep({"mq-agent": 85})]
        alerts = _compute_alerts(sweeps, threshold=10)
        assert len(alerts) == 1
        assert alerts[0]["name"] == "mq-agent"
        assert "dropped 15 pts" in alerts[0]["reasons"]

    def test_drop_below_threshold_no_alert(self):
        sweeps = [_sweep({"mq-agent": 100}), _sweep({"mq-agent": 93})]
        assert _compute_alerts(sweeps, threshold=10) == []

    def test_below_min_score_alerts_regardless_of_delta(self):
        sweeps = [_sweep({"mq-agent": 75}), _sweep({"mq-agent": 78})]
        alerts = _compute_alerts(sweeps, threshold=10, min_score=80)
        assert len(alerts) == 1
        assert "below 80" in alerts[0]["reasons"]

    def test_double_reason_drop_and_below_min(self):
        sweeps = [_sweep({"mq-agent": 95}), _sweep({"mq-agent": 70})]
        alerts = _compute_alerts(sweeps, threshold=10, min_score=80)
        assert len(alerts) == 1
        assert "dropped 25 pts" in alerts[0]["reasons"]
        assert "below 80" in alerts[0]["reasons"]

    def test_skipped_repo_ignored(self):
        sweeps = [_sweep({"mq-agent": 100}), _sweep({"mq-agent": None})]
        assert _compute_alerts(sweeps) == []

    def test_requires_two_sweeps(self):
        assert _compute_alerts([_sweep({"mq-agent": 100})]) == []

    def test_new_repo_below_min_alerts(self):
        sweeps = [_sweep({"mq-agent": 100}), _sweep({"mq-agent": 100, "mq-mcp": 70})]
        alerts = _compute_alerts(sweeps, threshold=10, min_score=80)
        assert any(a["name"] == "mq-mcp" for a in alerts)

    def test_delta_sign_correct(self):
        sweeps = [_sweep({"mq-agent": 90}), _sweep({"mq-agent": 75})]
        alerts = _compute_alerts(sweeps, threshold=10)
        assert alerts[0]["delta"] == -15

    def test_custom_threshold(self):
        sweeps = [_sweep({"mq-agent": 100}), _sweep({"mq-agent": 95})]
        assert _compute_alerts(sweeps, threshold=3) != []
        assert _compute_alerts(sweeps, threshold=10) == []


# ── stack alert CLI ─────────────────────────────────────────────────────────

class TestStackAlertCmd:
    def test_no_history_shows_hint(self, tmp_history):
        result = runner.invoke(app, ["stack", "alert"])
        assert result.exit_code == 0
        assert "No sweep history" in result.output

    def test_single_sweep_prompts_for_more(self, tmp_history):
        _write_sweeps(tmp_history, [_sweep({"mq-agent": 100})])
        result = runner.invoke(app, ["stack", "alert"])
        assert result.exit_code == 0
        assert "at least 2 sweeps" in result.output

    def test_no_alerts_exit_0(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 100}, ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "alert"])
        assert result.exit_code == 0
        assert "No alerts" in result.output

    def test_alert_exit_1(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 75},  ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "alert"])
        assert result.exit_code == 1
        assert "mq-agent" in result.output

    def test_json_output_no_alerts(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 100}, ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "alert", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_json_output_with_alert(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 75},  ts="2026-06-10T11:00:00"),
        ])
        result = runner.invoke(app, ["stack", "alert", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data[0]["name"] == "mq-agent"

    def test_custom_threshold(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 100}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 95},  ts="2026-06-10T11:00:00"),
        ])
        result_tight = runner.invoke(app, ["stack", "alert", "--threshold", "3"])
        assert result_tight.exit_code == 1
        result_loose = runner.invoke(app, ["stack", "alert", "--threshold", "10"])
        assert result_loose.exit_code == 0

    def test_custom_min_score(self, tmp_history):
        _write_sweeps(tmp_history, [
            _sweep({"mq-agent": 85}, ts="2026-06-10T10:00:00"),
            _sweep({"mq-agent": 85}, ts="2026-06-10T11:00:00"),
        ])
        result_strict = runner.invoke(app, ["stack", "alert", "--min-score", "90"])
        assert result_strict.exit_code == 1
        result_loose = runner.invoke(app, ["stack", "alert", "--min-score", "80"])
        assert result_loose.exit_code == 0
