"""Operator-triggered co-change inbox pipeline — orchestration tests.

No real Bridget, no real mqobsidian CLI: both seams are injected. We assert the
stack boundary holds (mq-agent orchestrates, delegates scoring/writeback to
mqobsidian), that --dry-run/--no-writeback behave, and that the emitted record keeps
producer=mq-agent + evidence.source=bridget/cg-2.
"""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.memory import inbox_pipeline as ip

runner = CliRunner()

_STRONG = {
    "repo": "macos-scripts",
    "run_id": "cochange-run-20260629T000000Z-abc12345",
    "target": "terminal/mqlaunch.sh",
    "window": 300,
    "rows": [
        {"path": "terminal/foo.sh", "confidence": 0.6, "count": 6, "base": 10},
        {"path": "terminal/bar.sh", "confidence": 0.3, "count": 3, "base": 10},
    ],
}
_WEAK = {"repo": "macos-scripts", "run_id": "r", "target": "x", "window": 300,
         "rows": [{"path": "y", "confidence": 0.6, "count": 1, "base": 10}]}  # count < min_support


def _runner(data):
    def fake(repo, target, *, window=300, mq_mcp_dir=None):
        return data
    return fake


class _RecordingCLI:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, vault: Path, args: list[str]):
        self.calls.append(args)
        return 0, f"{args[0]} summary", ""


# --- happy path ------------------------------------------------------------

def test_emit_happy_path_writes_inbox_and_delegates(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline(
        "repo", "terminal/mqlaunch.sh", vault=tmp_path,
        runner=_runner(_STRONG), cli_runner=cli,
    )
    assert res["evidence"]["found"] and res["evidence"]["run_id"] == "cochange-run-20260629T000000Z-abc12345"
    assert res["emit"]["status"] == "emitted"
    inbox = tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl"
    assert inbox.exists()
    rec = json.loads(inbox.read_text().strip())
    assert rec["producer"] == "mq-agent"
    assert rec["evidence"][0]["source"] == "bridget/cg-2"
    # mq-agent delegated scoring/writeback/status to mqobsidian's CLI — in order.
    assert cli.calls == [["score", "--apply"], ["learn-writeback", "--apply"], ["status"]]
    assert res["ok"] is True


def test_dry_run_writes_nothing(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline(
        "repo", "terminal/mqlaunch.sh", vault=tmp_path, dry_run=True,
        runner=_runner(_STRONG), cli_runner=cli,
    )
    assert res["emit"]["status"] == "would-emit"
    assert not (tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl").exists()
    assert cli.calls == [["score", "--dry-run"], ["learn-writeback", "--dry-run"], ["status"]]


def test_no_writeback_scores_but_skips_writeback(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline(
        "repo", "terminal/mqlaunch.sh", vault=tmp_path, no_writeback=True,
        runner=_runner(_STRONG), cli_runner=cli,
    )
    assert res["writeback"].get("skipped") == "--no-writeback"
    assert ["learn-writeback", "--apply"] not in cli.calls
    assert cli.calls == [["score", "--apply"], ["status"]]


def test_no_cluster_skips_emit_but_still_scores(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline("repo", "x", vault=tmp_path, runner=_runner(_WEAK), cli_runner=cli)
    assert res["emit"]["status"] == "skipped"
    assert not (tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl").exists()
    assert cli.calls[0] == ["score", "--apply"]  # scoring still runs after emission


def test_unavailable_evidence_is_graceful(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline("repo", "x", vault=tmp_path, runner=_runner(None), cli_runner=cli)
    assert res["evidence"]["found"] is False
    assert res["emit"]["status"] == "skipped" and "unavailable" in res["emit"]["detail"]


# --- vault resolution ------------------------------------------------------

def test_vault_resolution_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(tmp_path / "fromenv"))
    assert ip.resolve_vault("/explicit") == Path("/explicit")          # flag wins
    assert ip.resolve_vault(None) == tmp_path / "fromenv"              # then env
    monkeypatch.delenv("MQ_OBSIDIAN_DIR")
    assert ip.resolve_vault(None).name == "mqobsidian"                 # then default


def test_missing_mqobsidian_cli_is_reported_not_raised(tmp_path):
    rc, out, err = ip.run_mqobsidian_cli(tmp_path, ["status"])
    assert rc == 127 and "not found" in err


# --- CLI wiring (graceful with no real deps) -------------------------------

def test_cli_command_wires_and_degrades_gracefully(tmp_path):
    # No Bridget + tmp vault has no memory_cli.py → every stage degrades, no crash.
    result = runner.invoke(app, ["memory", "inbox-cochange", str(tmp_path), "f.py", "--vault", str(tmp_path)])
    assert "MQ memory co-change intake" in result.output
    assert "Bridget/CG-2 evidence" in result.output
    assert "mqobsidian scoring" in result.output
