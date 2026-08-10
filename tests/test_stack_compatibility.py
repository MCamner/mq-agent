"""Contract and inventory tests for the stack compatibility gate.

Phase 0 (contract) and Phase 1 (repository inventory) of
`mq.stack-compatibility.v1`.

These tests build synthetic repositories in tmp_path rather than reading the
developer's sibling checkouts, so they behave identically in CI where those
repos do not exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from mq_agent.tools.stack_compatibility import (
    COMPATIBILITY_SCHEMA,
    _is_bounded,
    build_report,
    stack_compatibility,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "mq_stack_compatibility.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _make_repo(
    root: Path,
    name: str,
    *,
    version: str = "1.0.0",
    declared: str | None = "mcp>=1.27.1,<2",
    locked: str | None = "1.27.1",
    contract: bool = True,
    nested: bool = False,
    optional_extra: bool = False,
) -> dict[str, str]:
    """Create a synthetic repo and return an MQ_STACK_REPOS-style entry."""
    repo = root / name
    package_dir = repo / name if nested else repo
    package_dir.mkdir(parents=True, exist_ok=True)

    (repo / "VERSION").write_text(f"{version}\n", encoding="utf-8")

    if contract:
        (repo / ".mq").mkdir(exist_ok=True)
        (repo / ".mq" / "repo-contract.json").write_text(
            json.dumps({"repo": name, "role": "test", "version": version}),
            encoding="utf-8",
        )

    if declared is not None:
        if optional_extra:
            body = (
                "[project]\nname = 'x'\nversion = '1'\n"
                f"[project.optional-dependencies]\nmcp = ['{declared}']\n"
            )
        else:
            body = (
                "[project]\nname = 'x'\nversion = '1'\n"
                f"dependencies = ['{declared}']\n"
            )
        (package_dir / "pyproject.toml").write_text(body, encoding="utf-8")

    if locked is not None:
        (package_dir / "uv.lock").write_text(
            f'version = 1\n\n[[package]]\nname = "mcp"\nversion = "{locked}"\n',
            encoding="utf-8",
        )

    return {"name": name, "path": str(repo), "role": "test"}


def _report(entries: list[dict[str, str]]) -> dict[str, Any]:
    return build_report(repos=entries, slice_only=False)


# ── Phase 0: contract ──────────────────────────────────────────────────────


def test_schema_file_is_valid(validator: Draft202012Validator) -> None:
    assert SCHEMA_PATH.is_file()
    assert validator.schema["title"] == COMPATIBILITY_SCHEMA


def test_report_validates_against_schema(tmp_path, validator) -> None:
    entries = [_make_repo(tmp_path, "repo-a")]
    errors = list(validator.iter_errors(_report(entries)))
    assert not errors, [e.message for e in errors]


def test_schema_is_versioned() -> None:
    assert _report([])["schema"] == "mq.stack-compatibility.v1"


def test_unknown_status_is_rejected(tmp_path, validator) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    report["status"] = "MAYBE"
    assert list(validator.iter_errors(report)), "unknown status must be rejected"


def test_unknown_finding_code_is_rejected(tmp_path, validator) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    report["findings"].append(
        {
            "code": "MQC999_INVENTED",
            "severity": "FAIL",
            "repo": "repo-a",
            "message": "x",
            "blocks_release": True,
        }
    )
    assert list(validator.iter_errors(report)), "unknown code must be rejected"


def test_incomplete_evidence_is_rejected(tmp_path, validator) -> None:
    """Provenance without an observed value is not evidence."""
    report = _report([_make_repo(tmp_path, "repo-a")])
    report["findings"].append(
        {
            "code": "MQC005_DECLARED_RANGE_UNBOUNDED",
            "severity": "WARN",
            "repo": "repo-a",
            "message": "x",
            "blocks_release": False,
            "evidence": [{"repo": "repo-a", "file": "pyproject.toml", "field": "d"}],
        }
    )
    assert list(validator.iter_errors(report)), "evidence must require observed"


def test_dependency_without_sources_is_rejected(tmp_path, validator) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    report["components"][0]["dependencies"].append(
        {"name": "x", "declared": ">=1", "locked": "1.0", "sources": []}
    )
    assert list(validator.iter_errors(report)), "sources must be non-empty"


def test_unexpected_top_level_field_is_rejected(tmp_path, validator) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    report["surprise"] = True
    assert list(validator.iter_errors(report))


def test_missing_required_field_is_rejected(tmp_path, validator) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    del report["next_action"]
    assert list(validator.iter_errors(report))


def test_findings_never_carry_pass_severity(tmp_path, validator) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    report["findings"].append(
        {
            "code": "MQC005_DECLARED_RANGE_UNBOUNDED",
            "severity": "PASS",
            "repo": "repo-a",
            "message": "x",
            "blocks_release": False,
        }
    )
    assert list(validator.iter_errors(report))


def test_pass_report_has_empty_next_action(tmp_path) -> None:
    report = _report([_make_repo(tmp_path, "repo-a")])
    assert report["status"] == "PASS"
    assert report["next_action"] == ""


def test_only_fail_findings_block_release(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "unbounded", declared="mcp>=1.0"),
        _make_repo(tmp_path, "drifted", declared="mcp>=1.27.1,<2", locked="2.1.0"),
    ]
    findings = _report(entries)["findings"]
    for finding in findings:
        assert finding["blocks_release"] is (finding["severity"] == "FAIL")


# ── Phase 1: repository inventory ──────────────────────────────────────────


def test_declared_and_locked_are_reported(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", declared="mcp>=1.27.1,<2", locked="1.27.1")]
    dep = _report(entries)["components"][0]["dependencies"][0]
    assert dep["name"] == "mcp"
    assert dep["locked"] == "1.27.1"
    assert "1.27.1" in dep["declared"]
    assert dep["bounded"] is True


def test_nested_package_layout_is_discovered(tmp_path) -> None:
    """mq-mcp nests its package one level down; a root-only search misses it."""
    entries = [_make_repo(tmp_path, "nested-repo", nested=True)]
    component = _report(entries)["components"][0]
    assert component["dependencies"], "nested pyproject.toml was not discovered"
    assert component["dependencies"][0]["locked"] == "1.27.1"


def test_optional_dependency_extra_is_discovered(tmp_path) -> None:
    """mq-image-analyze declares mcp under an optional extra, not a hard dep."""
    entries = [_make_repo(tmp_path, "repo-a", declared="mcp>=1.0,<2", optional_extra=True)]
    dep = _report(entries)["components"][0]["dependencies"][0]
    assert dep["sources"][0]["field"] == "project.optional-dependencies.mcp"


def test_missing_repo_is_unavailable_not_incompatible(tmp_path) -> None:
    entries = [{"name": "ghost", "path": str(tmp_path / "nope"), "role": "test"}]
    report = _report(entries)
    assert report["status"] == "UNAVAILABLE"
    assert report["components"][0]["status"] == "UNAVAILABLE"
    codes = [f["code"] for f in report["findings"]]
    assert "MQC001_REPO_NOT_FOUND" in codes
    assert all(not f["blocks_release"] for f in report["findings"])


def test_missing_contract_is_reported(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", contract=False)]
    report = _report(entries)
    assert "MQC002_CONTRACT_MISSING" in [f["code"] for f in report["findings"]]
    assert report["components"][0]["contract_present"] is False


def test_invalid_contract_json_is_reported(tmp_path) -> None:
    entry = _make_repo(tmp_path, "repo-a")
    (Path(entry["path"]) / ".mq" / "repo-contract.json").write_text("{not json", encoding="utf-8")
    report = _report([entry])
    assert "MQC003_CONTRACT_INVALID" in [f["code"] for f in report["findings"]]


def test_missing_dependency_source_is_unavailable(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", declared=None, locked=None)]
    report = _report(entries)
    assert report["components"][0]["status"] == "UNAVAILABLE"
    assert "MQC004_DEPENDENCY_SOURCE_MISSING" in [f["code"] for f in report["findings"]]


def test_unbounded_range_warns(tmp_path) -> None:
    """The real failure mode: mcp>=1.0 let MCP 2.x install against FastMCP 1.x."""
    entries = [_make_repo(tmp_path, "repo-a", declared="mcp>=1.0")]
    report = _report(entries)
    assert report["status"] == "WARN"
    assert "MQC005_DECLARED_RANGE_UNBOUNDED" in [f["code"] for f in report["findings"]]
    assert report["components"][0]["dependencies"][0]["bounded"] is False


def test_locked_outside_declared_range_fails(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", declared="mcp>=1.27.1,<2", locked="2.1.0")]
    report = _report(entries)
    assert report["status"] == "FAIL"
    finding = next(f for f in report["findings"] if f["code"] == "MQC006_LOCKED_OUTSIDE_DECLARED")
    assert finding["blocks_release"] is True
    assert finding["evidence"], "a FAIL must carry evidence"


def test_constraints_file_supplies_locked_version(tmp_path) -> None:
    entry = _make_repo(tmp_path, "repo-a", locked=None)
    (Path(entry["path"]) / "constraints.txt").write_text(
        "# pinned\nmcp==1.27.1\n", encoding="utf-8"
    )
    dep = _report([entry])["components"][0]["dependencies"][0]
    assert dep["locked"] == "1.27.1"


def test_provenance_is_repo_relative(tmp_path) -> None:
    """Absolute or home paths must never reach the report."""
    entries = [_make_repo(tmp_path, "repo-a", nested=True)]
    for component in _report(entries)["components"]:
        for dep in component["dependencies"]:
            for source in dep["sources"]:
                assert not source["file"].startswith("/")
                assert "~" not in source["file"]
                assert str(tmp_path) not in source["file"]


def test_untracked_dependency_is_omitted(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", declared="requests>=2", locked=None)]
    assert _report(entries)["components"][0]["dependencies"] == []


def test_worst_status_wins_across_components(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "good"),
        _make_repo(tmp_path, "bad", declared="mcp>=1.27.1,<2", locked="3.0.0"),
    ]
    assert _report(entries)["status"] == "FAIL"


def test_report_is_read_only(tmp_path) -> None:
    """The gate must not touch dependencies, lockfiles or working trees."""
    entry = _make_repo(tmp_path, "repo-a", nested=True)
    repo = Path(entry["path"])
    before = {
        path: path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }

    _report([entry])

    after = {
        path: path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }
    assert before == after, "the compatibility check modified the working tree"


def test_json_output_matches_report(tmp_path) -> None:
    """Human and JSON surfaces must carry identical semantics."""
    entries = [_make_repo(tmp_path, "repo-a", declared="mcp>=1.0")]
    parsed = json.loads(stack_compatibility(repos=entries, slice_only=False))
    built = build_report(repos=entries, slice_only=False)
    parsed.pop("checked_at")
    built.pop("checked_at")
    assert parsed == built


def test_report_is_deterministic_apart_from_timestamp(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a"), _make_repo(tmp_path, "repo-b")]
    first, second = _report(entries), _report(entries)
    first.pop("checked_at")
    second.pop("checked_at")
    assert first == second


def test_slice_defaults_to_the_two_mcp_repos() -> None:
    """The first vertical slice is mq-mcp and mq-image-analyze, by name."""
    names = [c["repo"] for c in build_report(slice_only=True)["components"]]
    assert names == ["mq-mcp", "mq-image-analyze"]


def test_no_hardcoded_private_paths_in_source() -> None:
    source = (REPO_ROOT / "mq_agent" / "tools" / "stack_compatibility.py").read_text(
        encoding="utf-8"
    )
    assert "/Users/" not in source
    assert "/home/" not in source


@pytest.mark.parametrize(
    "spec,expected",
    [
        (">=1.27.1,<2", True),
        (">=1.0,<2", True),
        (">=1.0", False),
        (">=1.0,<3", False),
        ("==1.27.1", True),
        ("~=1.27.1", True),
        (None, False),
        ("not a spec", False),
    ],
)
def test_bounded_detection(spec: str | None, expected: bool) -> None:
    assert _is_bounded(spec) is expected
