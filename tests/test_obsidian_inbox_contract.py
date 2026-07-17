from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mq_agent.memory import inbox_pipeline as ip


NOW = datetime(2026, 7, 16, tzinfo=timezone.utc)


def _write_bundle(root: Path, *, age: int = 0, drift: str | None = None,
                  path_override: str | None = None, now: datetime = NOW) -> None:
    exports = root / "exports"
    exports.mkdir()
    stamp = (now - timedelta(seconds=age)).isoformat().replace("+00:00", "Z")
    specs: dict[str, tuple[str, str, dict[str, object]]] = {
        "inbox": ("inbox-manifest.v1", "inbox.json", {"items": [{"id": "m-1", "source": "test", "state": "candidate", "first_seen": stamp, "last_seen": stamp}]}),
        "scores": ("memory-score-manifest.v1", "scores.json", {"scores": {"m-1": {"schema": "memory-score.v1", "memory_id": "m-1", "timestamp": stamp, "status": "candidate", "score": 1}}}),
        "evidence": ("memory-evidence-manifest.v1", "evidence.json", {"evidence": {"ref-1": {"ref": "ref-1", "producer": "test", "schema_id": "test.v1", "observed_at": stamp, "summary": "verified"}}}),
        "promotion-policy": (
            "promotion-policy.v1", "policy.json", {
                "weights": {"frequency": 1, "source_count": 1, "confidence": 1, "recency": 1, "usage_score": 1, "manual_boost": 0},
                "review_threshold": 1, "auto_threshold": 2, "min_supporting_factors": 2,
                "block_negative_feedback": True, "max_manifest_age_seconds": 60,
            },
        ),
    }
    surfaces = []
    for key, (schema, name, body) in specs.items():
        document: dict[str, object] = {"schema": schema, "source": "mqobsidian-export", "generated_at": stamp}
        document.update(body)
        (exports / name).write_text(json.dumps(document), encoding="utf-8")
        surfaces.append({
            "key": key,
            "schema": schema,
            "path": path_override if key == "inbox" and path_override else f"exports/{name}",
            "generated_at": stamp,
            "drift": key == drift,
        })
    index = {"schema": "truth-export-index.v1", "source": "mqobsidian-export", "generated_at": stamp, "surfaces": surfaces}
    (exports / "truth-export-index.json").write_text(json.dumps(index), encoding="utf-8")


def test_list_and_read_use_only_canonical_entrypoint(tmp_path: Path) -> None:
    _write_bundle(tmp_path)

    def clock() -> datetime:
        return NOW

    listing = ip.list_inbox_candidates(vault=tmp_path, now=clock)
    assert listing["count"] == 1 and listing["candidates"][0]["id"] == "m-1"
    found = ip.read_inbox_candidate("m-1", vault=tmp_path, now=clock)
    missing = ip.read_inbox_candidate("missing", vault=tmp_path, now=clock)
    assert found["found"] and found["candidate"]["id"] == "m-1"
    assert not missing["found"] and missing["candidate"] is None


@pytest.mark.parametrize("age,allowed", [(59, True), (60, True), (61, False)])
def test_freshness_boundary(tmp_path: Path, age: int, allowed: bool) -> None:
    _write_bundle(tmp_path, age=age)
    if allowed:
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)
    else:
        with pytest.raises(ip.ExportContractError, match="stale"):
            ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_drifted_surface_fails_closed(tmp_path: Path) -> None:
    _write_bundle(tmp_path, drift="scores")
    with pytest.raises(ip.ExportContractError, match="drifted"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


@pytest.mark.parametrize("unsafe", ["/tmp/inbox.json", "../inbox.json"])
def test_unsafe_surface_path_is_rejected(tmp_path: Path, unsafe: str) -> None:
    _write_bundle(tmp_path, path_override=unsafe)
    with pytest.raises(ip.ExportContractError, match="absolute|escapes"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_schema_mismatch_is_rejected(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "scores.json"
    payload = json.loads(path.read_text())
    payload["schema"] = "memory-score-manifest.v2"
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="schema mismatch"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_missing_required_index_field_is_rejected(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "truth-export-index.json"
    payload = json.loads(path.read_text())
    del payload["source"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="source"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_missing_required_surface_field_is_rejected(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "inbox.json"
    payload = json.loads(path.read_text())
    del payload["items"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="items"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


@pytest.mark.parametrize("age,allowed", [(59, True), (60, True), (61, False)])
def test_index_freshness_boundary(tmp_path: Path, age: int, allowed: bool) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "truth-export-index.json"
    payload = json.loads(path.read_text())
    payload["generated_at"] = (NOW - timedelta(seconds=age)).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(payload))
    if allowed:
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)
    else:
        with pytest.raises(ip.ExportContractError, match="index"):
            ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_malformed_nested_inbox_item_is_rejected(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "inbox.json"
    payload = json.loads(path.read_text())
    del payload["items"][0]["state"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="inbox item"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_malformed_index_entry_and_unknown_field_are_rejected(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "truth-export-index.json"
    payload = json.loads(path.read_text())
    payload["surfaces"][0]["private_path"] = "no"
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="unknown fields"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


@pytest.mark.parametrize("name,field,match", [("scores.json", "timestamp", "score"), ("evidence.json", "summary", "evidence")])
def test_malformed_nested_score_and_evidence_are_rejected(tmp_path: Path, name: str, field: str, match: str) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / name
    payload = json.loads(path.read_text())
    records = payload["scores"] if "scores" in payload else payload["evidence"]
    del next(iter(records.values()))[field]
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match=match):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


@pytest.mark.parametrize("field,value", [("review_threshold", True), ("auto_threshold", -1)])
def test_invalid_policy_numbers_are_rejected(tmp_path: Path, field: str, value: object) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "policy.json"
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="policy"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


def test_future_dated_surface_is_rejected(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "exports" / "inbox.json"
    payload = json.loads(path.read_text())
    payload["generated_at"] = "2026-07-16T00:00:01Z"
    path.write_text(json.dumps(payload))
    with pytest.raises(ip.ExportContractError, match="future-dated"):
        ip.load_canonical_exports(vault=tmp_path, now=lambda: NOW)


# --- ranking contract (v1.22 Task 7) ----------------------------------------

_RANK_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "inbox_promotion_orchestration.v1.json"


def _rank_schema() -> dict:
    return json.loads(_RANK_SCHEMA.read_text(encoding="utf-8"))


def test_ranking_schema_is_a_valid_2020_12_schema() -> None:
    Draft202012Validator.check_schema(_rank_schema())


def test_real_ranking_output_validates_against_the_schema(tmp_path: Path) -> None:
    """Meta-validating the schema proves nothing about the producer. Validate
    what the producer actually emits, from a real bundle on disk."""
    _write_bundle(tmp_path)
    ranking = ip.rank_inbox(vault=tmp_path, now=lambda: NOW)
    Draft202012Validator(_rank_schema()).validate(ranking)
    assert ranking["schema"] == ip.RANKING_SCHEMA
    assert ranking["counts"]["review-needed"] + ranking["counts"]["inbox"] \
        + ranking["counts"]["auto-promotable"] == len(ranking["candidates"])


def test_ranking_fails_closed_on_a_drifted_surface(tmp_path: Path) -> None:
    """Ranking must inherit discovery's fail-closed behaviour, not bypass it."""
    _write_bundle(tmp_path, drift="scores")
    with pytest.raises(ip.ExportContractError, match="drifted"):
        ip.rank_inbox(vault=tmp_path, now=lambda: NOW)


def test_ranking_fails_closed_on_a_stale_bundle(tmp_path: Path) -> None:
    _write_bundle(tmp_path, age=61)
    with pytest.raises(ip.ExportContractError, match="stale"):
        ip.rank_inbox(vault=tmp_path, now=lambda: NOW)


# --- obsidian inbox CLI (v1.22 Task 10) -------------------------------------
#
# The surface mqlaunch delegates to. Two rules carry the weight: --json is the
# only machine-readable contract, and a mutation never writes without --confirm.

from typer.testing import CliRunner  # noqa: E402

from mq_agent.main import app  # noqa: E402

_cli = CliRunner()
_MUTATIONS = ("promote", "reject", "defer", "rollback", "deprecate")


def _bundle_env(tmp_path: Path, monkeypatch) -> None:
    # The CLI has no injected clock, so the bundle must be fresh against real time.
    _write_bundle(tmp_path, now=datetime.now(timezone.utc))
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(tmp_path))


def test_inbox_list_json_is_machine_readable(tmp_path: Path, monkeypatch) -> None:
    _bundle_env(tmp_path, monkeypatch)
    result = _cli.invoke(app, ["obsidian", "inbox", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema"] == "inbox-candidate-list.v1"
    assert payload["count"] == 1


def test_inbox_read_json_reports_found_and_missing(tmp_path: Path, monkeypatch) -> None:
    _bundle_env(tmp_path, monkeypatch)
    found = json.loads(_cli.invoke(app, ["obsidian", "inbox", "read", "m-1", "--json"]).stdout)
    assert found["found"] is True and found["candidate"]["id"] == "m-1"

    result = _cli.invoke(app, ["obsidian", "inbox", "read", "nope", "--json"])
    assert json.loads(result.stdout)["found"] is False
    assert result.exit_code == 1, "a missing candidate is not a success"


def test_inbox_rank_json_validates_against_the_contract(tmp_path: Path, monkeypatch) -> None:
    _bundle_env(tmp_path, monkeypatch)
    result = _cli.invoke(app, ["obsidian", "inbox", "rank", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    Draft202012Validator(_rank_schema()).validate(payload)


def test_json_output_carries_nothing_but_json(tmp_path: Path, monkeypatch) -> None:
    """mqlaunch pipes this. A banner would corrupt the contract."""
    _bundle_env(tmp_path, monkeypatch)
    for argv in (["obsidian", "inbox", "list", "--json"], ["obsidian", "inbox", "rank", "--json"]):
        out = _cli.invoke(app, argv).stdout
        json.loads(out)  # raises if anything else was printed


def test_stale_bundle_fails_closed_through_the_cli(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path, age=99999, now=datetime.now(timezone.utc))
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(tmp_path))
    result = _cli.invoke(app, ["obsidian", "inbox", "list", "--json"])
    assert result.exit_code == 1
    assert "stale" in result.stdout + str(result.exception or "")


def test_every_mutation_previews_without_confirm(tmp_path: Path, monkeypatch) -> None:
    for verb in _MUTATIONS:
        calls: list[list[str]] = []

        def fake(vault, args):
            calls.append(args)
            return 0, '{"ok": true, "mode": "preview"}', ""

        monkeypatch.setattr("mq_agent.memory.inbox_pipeline.run_mqobsidian_cli", fake)
        result = _cli.invoke(app, ["obsidian", verb, "m-1", "--reason", "r", "--vault", str(tmp_path)])
        assert result.exit_code == 0, f"{verb}: {result.output}"
        assert calls and "--apply" not in calls[0], f"{verb} wrote without --confirm"


def test_every_mutation_applies_only_with_confirm(tmp_path: Path, monkeypatch) -> None:
    for verb in _MUTATIONS:
        calls: list[list[str]] = []

        def fake(vault, args):
            calls.append(args)
            return 0, '{"ok": true, "mode": "applied"}', ""

        monkeypatch.setattr("mq_agent.memory.inbox_pipeline.run_mqobsidian_cli", fake)
        result = _cli.invoke(
            app, ["obsidian", verb, "m-1", "--reason", "r", "--confirm", "--vault", str(tmp_path)]
        )
        assert result.exit_code == 0, f"{verb}: {result.output}"
        assert "--apply" in calls[0], f"{verb} ignored --confirm"


def test_promote_forwards_evidence_refs(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake(vault, args):
        calls.append(args)
        return 0, '{"ok": true}', ""

    monkeypatch.setattr("mq_agent.memory.inbox_pipeline.run_mqobsidian_cli", fake)
    _cli.invoke(app, ["obsidian", "promote", "m-1", "--reason", "r",
                      "--evidence", "observation:o1", "--evidence", "observation:o2",
                      "--vault", str(tmp_path)])
    assert calls[0].count("--evidence") == 2


def test_mutation_failure_propagates_exit_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mq_agent.memory.inbox_pipeline.run_mqobsidian_cli",
        lambda vault, args: (1, '{"ok": false, "error": "illegal transition"}', ""),
    )
    result = _cli.invoke(app, ["obsidian", "promote", "m-1", "--reason", "r",
                              "--vault", str(tmp_path)])
    assert result.exit_code == 1
    assert "illegal transition" in result.stdout


def test_reason_is_required_by_every_mutation(tmp_path: Path) -> None:
    for verb in _MUTATIONS:
        result = _cli.invoke(app, ["obsidian", verb, "m-1", "--vault", str(tmp_path)])
        assert result.exit_code != 0, f"{verb} accepted a transition with no reason"


def test_existing_memory_commands_still_exist() -> None:
    """Task 10 adds a surface; it must not move the one mqlaunch already uses."""
    for name in ("inbox-cochange", "review-status", "promote-from-review", "resolve-supersede"):
        assert _cli.invoke(app, ["memory", name, "--help"]).exit_code == 0, name
