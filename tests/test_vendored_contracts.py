"""The drift gate must go red when either compared document changes.

The fault this gate exists to prevent produced *falsely green* CI in both
repos: two hand-maintained copies of `mq.execution-outcome.v1` drifted in four
places, and mqobsidian's own tests validated routing records against a
hand-written inline schema missing `run_id`. Nothing failed. So these tests
mutate each side in turn and require red — a gate nobody has watched fail is
indistinguishable from no gate.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-vendored-contracts.py"
MANIFEST = ROOT / "schemas" / "vendored-contracts.json"

SPEC = importlib.util.spec_from_file_location("check_vendored_contracts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture()
def canonical(tmp_path) -> Path:
    """A canonical checkout that starts out matching the vendored copies."""
    root = tmp_path / "mqobsidian"
    for entry in _manifest()["contracts"]:
        destination = root / entry["canonical"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / entry["vendored"], destination)
    return root


def test_the_manifest_lists_both_contracts_this_repo_vendors() -> None:
    contracts = {entry["contract"] for entry in _manifest()["contracts"]}

    assert contracts == {"mq.execution-outcome.v1", "mq.model-route-outcome.v1"}


def test_matching_copies_pass(canonical) -> None:
    status, report = gate.check(canonical)

    assert status == 0, report
    assert all(line.startswith("[ok]") for line in report)


# Direction 1: canonical moved, this repo did not.
def test_a_change_to_canonical_turns_the_gate_red(canonical) -> None:
    entry = _manifest()["contracts"][0]
    path = canonical / entry["canonical"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["properties"]["model"]["description"] = "changed upstream"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    status, report = gate.check(canonical)

    assert status == 1
    assert any("[DRIFT]" in line and entry["contract"] in line for line in report)
    assert any("properties.model.description" in line for line in report)


# Direction 2: this repo moved, canonical did not.
def test_a_change_to_the_vendored_copy_turns_the_gate_red(canonical) -> None:
    entry = _manifest()["contracts"][1]
    vendored = ROOT / entry["vendored"]
    original = vendored.read_text(encoding="utf-8")
    document = json.loads(original)
    document["title"] = "edited locally"

    try:
        vendored.write_text(json.dumps(document, indent=2), encoding="utf-8")
        status, report = gate.check(canonical)
    finally:
        vendored.write_text(original, encoding="utf-8")

    assert status == 1
    assert any("title:" in line for line in report)
    assert vendored.read_text(encoding="utf-8") == original


# $id and title are contract content, not packaging metadata. The gate must not
# quietly tolerate a difference in them — that is exactly how the four existing
# execution-outcome differences survived.
def test_identity_fields_are_not_normalized_away(canonical) -> None:
    entry = _manifest()["contracts"][0]
    path = canonical / entry["canonical"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["$id"] = "https://example.invalid/schema.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    status, report = gate.check(canonical)

    assert status == 1
    assert any("$id" in line for line in report)


def test_a_missing_canonical_checkout_fails_rather_than_passing(tmp_path) -> None:
    status, report = gate.check(tmp_path / "nowhere")

    assert status == 1
    assert any("canonical checkout not found" in line for line in report)


def test_a_manifest_with_no_contracts_fails_rather_than_passing(
    canonical, tmp_path
) -> None:
    empty = tmp_path / "empty-manifest.json"
    empty.write_text(json.dumps({"contracts": []}), encoding="utf-8")

    status, report = gate.check(canonical, empty)

    assert status == 1
    assert any("vacuously" in line for line in report)


def test_the_error_names_the_file_to_fix(canonical) -> None:
    entry = _manifest()["contracts"][0]
    path = canonical / entry["canonical"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["title"] = "renamed upstream"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    _, report = gate.check(canonical)

    assert any(entry["vendored"] in line and "behind" in line for line in report)


# The runtime reads the packaged copy, so vendoring must not break the wheel.
def test_every_vendored_contract_is_force_included_in_the_wheel() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for entry in _manifest()["contracts"]:
        assert f'"{entry["vendored"]}"' in pyproject, entry["contract"]
