from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.state_snapshot import inventory, restore, snapshot, verify

runner = CliRunner()


def _state_env(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    feedback = tmp_path / "feedback"
    outcomes = tmp_path / "execution" / "outcomes.jsonl"
    receipts = tmp_path / "receipts"
    xdg = tmp_path / "xdg"
    notebook = tmp_path / "notebook"
    monkeypatch.setenv("MQ_AGENT_FEEDBACK_DIR", str(feedback))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(outcomes))
    monkeypatch.setenv("MQ_AGENT_REVIEW_RECEIPTS_DIR", str(receipts))
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg))
    monkeypatch.setenv("MQ_AGENT_NOTEBOOK_STATE_DIR", str(notebook))
    return {
        "feedback": feedback,
        "outcomes": outcomes,
        "receipts": receipts,
        "workflows": xdg / "mq-agent" / "workflows",
        "notebook": notebook,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _seed_notebook_state(root: Path) -> None:
    _write_json(
        root / "inventory.json",
        {"schema": "notebook-drive-inventory-checkpoint.v1", "status": "current"},
    )
    _write_json(
        root / "catalog.json",
        {
            "schema": "notebook-corpus-index.v1",
            "corpus": {"key": "demo", "provider": "google-drive"},
            "snapshot_at": "2026-10-07T18:00:00Z",
            "notebooks": [],
            "items": [],
        },
    )
    _write_json(
        root / "catalog.checkpoint.json",
        {
            "schema": "notebook-corpus-build-checkpoint.v1",
            "source_snapshot_at": "2026-10-07T18:00:00Z",
        },
    )
    _write_json(
        root / "sync-state.json",
        {
            "schema": "notebook-knowledge-sync-state.v1",
            "snapshot_at": "2026-10-07T18:00:00Z",
            "catalog_sha256": "0" * 64,
            "items": {},
        },
    )
    _write_json(
        root / "semantic-index.json",
        {
            "schema": "notebook-semantic-index-experiment.v1",
            "canonical": False,
            "disposable": True,
            "snapshot_at": "2026-10-07T18:00:00Z",
            "corpus": {"key": "demo", "provider": "google-drive"},
            "chunks": [
                {
                    "chunk_id": "item-1:0",
                    "drive_item_id": "drive-1",
                    "vector": [0.1, 0.2],
                }
            ],
            "trace": {"embedding_dimension": 2},
        },
    )


def test_snapshot_v2_verify_restore_round_trip(tmp_path: Path, monkeypatch) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    paths["feedback"].mkdir(parents=True)
    (paths["feedback"] / "experiments.jsonl").write_text('{"safe":true}\n')
    paths["outcomes"].parent.mkdir(parents=True)
    paths["outcomes"].write_text('{"run":"one"}\n')
    paths["receipts"].mkdir(parents=True)
    (paths["receipts"] / "abc.json").write_text('{"receipt":"ok"}\n')
    paths["workflows"].mkdir(parents=True)
    (paths["workflows"] / "run_1.json").write_text('{"status":"done"}\n')
    _seed_notebook_state(paths["notebook"])

    target = tmp_path / "snapshot"
    manifest = snapshot(target)

    assert manifest["schema"] == "mq.state-snapshot.v2"
    assert manifest["snapshot_id"].startswith("sha256:")
    assert verify(target)["status"] == "PASS"
    manifest_text = (target / "manifest.json").read_text()
    assert str(tmp_path) not in manifest_text

    by_name = {row["name"]: row for row in manifest["components"]}
    assert by_name["notebook-drive-inventory"]["state_schema"] == (
        "notebook-drive-inventory-checkpoint.v1"
    )
    assert by_name["notebook-corpus-catalog"]["state_schema"] == (
        "notebook-corpus-index.v1"
    )
    assert by_name["notebook-semantic-index"]["state_schema"] == (
        "notebook-semantic-index-experiment.v1"
    )
    for component in manifest["components"]:
        for row in component["files"]:
            assert row["fingerprint"] == f"sha256:{row['sha256']}"

    (paths["feedback"] / "experiments.jsonl").write_text("corrupt\n")
    (paths["notebook"] / "inventory.json").write_text('{"schema":"broken.v1"}\n')
    unrelated = paths["notebook"] / "operator-note.txt"
    unrelated.write_text("keep me\n")

    result = restore(target)

    assert result["status"] == "RESTORED"
    assert result["deleted_files"] == 0
    assert (paths["feedback"] / "experiments.jsonl").read_text() == '{"safe":true}\n'
    restored_inventory = json.loads(
        (paths["notebook"] / "inventory.json").read_text(encoding="utf-8")
    )
    assert restored_inventory["schema"] == "notebook-drive-inventory-checkpoint.v1"
    assert unrelated.read_text() == "keep me\n"


def test_inventory_lists_portable_notebook_components(tmp_path: Path, monkeypatch) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    _seed_notebook_state(paths["notebook"])

    report = inventory()
    components = {row["name"]: row for row in report["components"]}

    assert report["schema"] == "mq.state-snapshot.v2"
    assert components["notebook-drive-inventory"]["file_count"] == 1
    assert components["notebook-corpus-checkpoint"]["file_count"] == 1
    assert components["notebook-sync-state"]["file_count"] == 1
    assert components["notebook-semantic-index"]["file_count"] == 1
    assert "credentials-and-env" in report["excluded"]
    assert "remote-vector-store-contents" in report["excluded"]
    assert "notebook-source-bodies" in report["excluded"]


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
    assert any(
        "sha256 mismatch" in item
        or "size mismatch" in item
        or "fingerprint mismatch" in item
        for item in report["errors"]
    )

    copied.write_text('{"safe":true}\n')
    extra = target / "components" / "feedback" / "extra.json"
    extra.write_text("{}\n")
    report = verify(target)
    assert report["status"] == "FAIL"
    assert any("unexpected file" in item for item in report["errors"])


def test_v2_manifest_fingerprint_detects_metadata_tamper(
    tmp_path: Path, monkeypatch
) -> None:
    _state_env(tmp_path, monkeypatch)
    target = tmp_path / "snapshot"
    snapshot(target)

    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["excluded"].append("invented-state")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        verify(target)
    except ValueError as exc:
        assert "manifest fingerprint mismatch" in str(exc)
    else:
        raise AssertionError("tampered v2 manifest must fail closed")


def test_notebook_schema_mismatch_is_refused_before_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    _write_json(
        paths["notebook"] / "inventory.json",
        {"schema": "notebook-drive-inventory-checkpoint.v2"},
    )

    try:
        snapshot(tmp_path / "snapshot")
    except ValueError as exc:
        assert "schema mismatch" in str(exc)
    else:
        raise AssertionError("version drift must fail closed")


def test_notebook_credential_like_keys_are_refused(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    credential_key = "access" + "_token"
    _write_json(
        paths["notebook"] / "inventory.json",
        {
            "schema": "notebook-drive-inventory-checkpoint.v1",
            credential_key: "<redacted>",
        },
    )

    try:
        snapshot(tmp_path / "snapshot")
    except ValueError as exc:
        assert "credential-like keys" in str(exc)
    else:
        raise AssertionError("credential-like notebook state must be refused")


def test_semantic_index_raw_text_payload_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    raw_key = "raw" + "_text"
    _write_json(
        paths["notebook"] / "semantic-index.json",
        {
            "schema": "notebook-semantic-index-experiment.v1",
            "canonical": False,
            "disposable": True,
            "chunks": [{"chunk_id": "1", raw_key: "payload", "vector": [0.1]}],
        },
    )

    try:
        snapshot(tmp_path / "snapshot")
    except ValueError as exc:
        assert "raw source payload fields" in str(exc)
    else:
        raise AssertionError("raw Notebook source payload must remain excluded")


def test_restore_dry_run_verifies_targets_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    _seed_notebook_state(paths["notebook"])
    target = tmp_path / "snapshot"
    snapshot(target)

    (paths["notebook"] / "inventory.json").unlink()
    result = restore(target, dry_run=True)

    assert result["status"] == "WOULD_RESTORE"
    assert result["restored_files"] == 0
    assert result["planned_files"] > 0
    assert not (paths["notebook"] / "inventory.json").exists()


def test_cli_restore_dry_run_needs_no_write_approval(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    _seed_notebook_state(paths["notebook"])
    target = tmp_path / "snapshot"
    snapshot(target)

    result = runner.invoke(app, ["state", "restore", str(target), "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "WOULD_RESTORE"
    assert payload["restored_files"] == 0


def test_cli_restore_write_still_requires_approval(
    tmp_path: Path, monkeypatch
) -> None:
    _state_env(tmp_path, monkeypatch)
    target = tmp_path / "snapshot"
    snapshot(target)

    result = runner.invoke(app, ["state", "restore", str(target), "--json"])

    assert result.exit_code != 0
    assert "--approve" in result.output


def test_historical_v1_snapshot_remains_readable_and_restorable(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _state_env(tmp_path, monkeypatch)
    copied = tmp_path / "snapshot" / "components" / "feedback" / "experiments.jsonl"
    copied.parent.mkdir(parents=True)
    copied.write_text('{"safe":true}\n', encoding="utf-8")
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    manifest = {
        "schema": "mq.state-snapshot.v1",
        "created_at": "2026-10-01T00:00:00Z",
        "components": [
            {
                "name": "feedback",
                "files": [
                    {
                        "path": "experiments.jsonl",
                        "size_bytes": copied.stat().st_size,
                        "sha256": digest,
                    }
                ],
            }
        ],
        "excluded": ["credentials-and-env"],
    }
    manifest_path = tmp_path / "snapshot" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = verify(tmp_path / "snapshot")
    assert report["status"] == "PASS"
    assert report["schema"] == "mq.state-snapshot.v1"

    paths["feedback"].mkdir(parents=True)
    (paths["feedback"] / "experiments.jsonl").write_text("different\n")
    result = restore(tmp_path / "snapshot")

    assert result["schema"] == "mq.state-snapshot.v1"
    assert (paths["feedback"] / "experiments.jsonl").read_text() == '{"safe":true}\n'
