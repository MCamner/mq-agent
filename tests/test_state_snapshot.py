from __future__ import annotations

import json
from pathlib import Path

from mq_agent.tools.state_snapshot import restore, snapshot, verify


def _state_env(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    feedback = tmp_path / "feedback"
    outcomes = tmp_path / "execution" / "outcomes.jsonl"
    receipts = tmp_path / "receipts"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(feedback))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    monkeypatch.setenv("MQ_AGENT_REVIEW_RECEIPTS_DIR", str(receipts))
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg))
    return {
        "feedback": feedback,
        "outcomes": outcomes,
        "receipts": receipts,
        "workflows": xdg / "mq-agent" / "workflows",
    }


def test_snapshot_verify_restore_round_trip(tmp_path: Path, monkeypatch) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    paths["feedback"].mkdir(parents=True)
    (paths["feedback"] / "experiments.jsonl").write_text('{"safe":true}\n')
    paths["outcomes"].parent.mkdir(parents=True)
    paths["outcomes"].write_text('{"run":"one"}\n')
    paths["receipts"].mkdir(parents=True)
    (paths["receipts"] / "abc.json").write_text('{"receipt":"ok"}\n')
    paths["workflows"].mkdir(parents=True)
    (paths["workflows"] / "run_1.json").write_text('{"status":"done"}\n')

    target = tmp_path / "snapshot"
    manifest = snapshot(target)

    assert manifest["schema"] == "mq.state-snapshot.v1"
    assert verify(target)["status"] == "PASS"
    manifest_text = (target / "manifest.json").read_text()
    assert str(tmp_path) not in manifest_text

    (paths["feedback"] / "experiments.jsonl").write_text("corrupt\n")
    result = restore(target)

    assert result["status"] == "RESTORED"
    assert result["deleted_files"] == 0
    assert (paths["feedback"] / "experiments.jsonl").read_text() == '{"safe":true}\n'


def test_verify_fails_on_tamper_or_unexpected_file(tmp_path: Path, monkeypatch) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    paths["feedback"].mkdir(parents=True)
    (paths["feedback"] / "experiments.jsonl").write_text('{"safe":true}\n')
    target = tmp_path / "snapshot"
    snapshot(target)

    copied = target / "components" / "feedback" / "experiments.jsonl"
    copied.write_text("tampered\n")

    report = verify(target)
    assert report["status"] == "FAIL"
    assert any("sha256 mismatch" in item or "size mismatch" in item for item in report["errors"])

    # An undeclared file must not be smuggled into a verified restore.
    copied.write_text('{"safe":true}\n')
    extra = target / "components" / "feedback" / "extra.json"
    extra.write_text("{}\n")
    report = verify(target)
    assert report["status"] == "FAIL"
    assert any("unexpected file" in item for item in report["errors"])
