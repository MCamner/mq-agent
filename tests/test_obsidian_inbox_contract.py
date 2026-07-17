from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mq_agent.memory import inbox_pipeline as ip


NOW = datetime(2026, 7, 16, tzinfo=timezone.utc)


def _write_bundle(root: Path, *, age: int = 0, drift: str | None = None,
                  path_override: str | None = None) -> None:
    exports = root / "exports"
    exports.mkdir()
    stamp = (NOW - timedelta(seconds=age)).isoformat().replace("+00:00", "Z")
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
