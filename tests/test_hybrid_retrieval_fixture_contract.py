"""Contract tests for the operator-authored relevance fixture.

The fixture is the only input in the hybrid evidence chain a human writes by
hand, and it defines the relevance ground truth everything downstream is
measured against. Before it had a packaged schema, a misspelled key was simply
ignored: `expected` instead of `expected_refs` left the expected set empty, so
the case reported no recall rather than failing. That is the same silent-wrong-
conclusion class the coverage and suite-path gates exist to remove.

These tests pin the shape rules. The namespace:reference form stays a runtime
check, so it is asserted here too rather than assumed to have moved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq_agent.memory.hybrid_retrieval import _load_fixture

ROOT = Path(__file__).resolve().parents[1]


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid() -> dict:
    return {
        "schema": "mq.hybrid-retrieval-fixture.v1",
        "expected_refs": ["notebook:abc"],
        "contradicted_refs": [],
        "stale_refs": [],
    }


def test_valid_fixture_is_accepted(tmp_path: Path) -> None:
    fixture, sha = _load_fixture(_write(tmp_path, _valid()))

    assert fixture is not None
    assert fixture["expected_refs"] == ["notebook:abc"]
    assert len(sha or "") == 64


def test_misspelled_expected_refs_is_rejected(tmp_path: Path) -> None:
    """The defect this contract exists for.

    Two faults at once: an unknown property and a missing required one. Either
    alone would be enough; together they make the mistake unmistakable.
    """
    payload = _valid()
    payload["expected"] = payload.pop("expected_refs")

    with pytest.raises(Exception) as exc:
        _load_fixture(_write(tmp_path, payload))

    assert "expected" in str(exc.value)


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    payload = _valid()
    payload["notes"] = "why these refs were chosen"

    with pytest.raises(Exception):
        _load_fixture(_write(tmp_path, payload))


@pytest.mark.parametrize(
    "field", ["expected_refs", "contradicted_refs", "stale_refs"]
)
def test_missing_required_array_is_rejected(tmp_path: Path, field: str) -> None:
    payload = _valid()
    payload.pop(field)

    with pytest.raises(Exception) as exc:
        _load_fixture(_write(tmp_path, payload))

    assert field in str(exc.value)


@pytest.mark.parametrize(
    "field", ["expected_refs", "contradicted_refs", "stale_refs"]
)
def test_duplicate_refs_are_rejected(tmp_path: Path, field: str) -> None:
    payload = _valid()
    payload[field] = ["notebook:abc", "notebook:abc"]

    with pytest.raises(Exception):
        _load_fixture(_write(tmp_path, payload))


def test_wrong_schema_id_is_rejected(tmp_path: Path) -> None:
    payload = _valid()
    payload["schema"] = "mq.hybrid-retrieval-fixture.v2"

    with pytest.raises(ValueError, match="fixture schema must be"):
        _load_fixture(_write(tmp_path, payload))


def test_namespace_form_is_still_enforced_at_runtime(tmp_path: Path) -> None:
    """The schema takes shape, the loader keeps semantics.

    `minLength: 1` matches how sibling schemas constrain refs, so a ref without
    a namespace separator is contract-valid and must still be refused on load.
    Removing the runtime check because a schema now exists would widen what is
    accepted.
    """
    payload = _valid()
    payload["expected_refs"] = ["no-namespace-separator"]

    with pytest.raises(ValueError, match="namespace:reference"):
        _load_fixture(_write(tmp_path, payload))


def test_schema_is_packaged_into_the_wheel() -> None:
    """An unpackaged schema turns every fixture-backed run into a crash.

    validate_contract resolves the file at runtime, so a schema missing from
    force-include raises FileNotFoundError once installed -- worse than the
    silent typo this change removes.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "schemas/hybrid_retrieval_fixture.schema.json" in pyproject
