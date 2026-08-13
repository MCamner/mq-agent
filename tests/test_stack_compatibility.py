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
    _ranges_overlap,
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
    compat: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Create a synthetic repo and return an MQ_STACK_REPOS-style entry.

    `compat` is the optional `compatibility` block. Passing None models a repo
    that has not yet declared its boundary — the normal state during rollout.
    """
    repo = root / name
    package_dir = repo / name if nested else repo
    package_dir.mkdir(parents=True, exist_ok=True)

    (repo / "VERSION").write_text(f"{version}\n", encoding="utf-8")

    if contract:
        contract_body: dict[str, Any] = {
            "repo": name,
            "role": "test",
            "version": version,
        }
        if compat is not None:
            contract_body["compatibility"] = compat
        (repo / ".mq").mkdir(exist_ok=True)
        (repo / ".mq" / "repo-contract.json").write_text(
            json.dumps(contract_body), encoding="utf-8"
        )

    if declared is not None:
        if optional_extra:
            pyproject_body = (
                "[project]\nname = 'x'\nversion = '1'\n"
                f"[project.optional-dependencies]\nmcp = ['{declared}']\n"
            )
        else:
            pyproject_body = (
                "[project]\nname = 'x'\nversion = '1'\n"
                f"dependencies = ['{declared}']\n"
            )
        (package_dir / "pyproject.toml").write_text(
            pyproject_body, encoding="utf-8"
        )

    if locked is not None:
        (package_dir / "uv.lock").write_text(
            f'version = 1\n\n[[package]]\nname = "mcp"\nversion = "{locked}"\n',
            encoding="utf-8",
        )

    return {"name": name, "path": str(repo), "role": "test"}


def _report(entries: list[dict[str, str]]) -> dict[str, Any]:
    return build_report(repos=entries, slice_only=False)


# A repo that has fully declared its boundary, matching its pyproject.toml.
DECLARED_MCP_1X: dict[str, Any] = {
    "protocols": {"mcp_api": "1.x-fastmcp"},
    "dependencies": {"mcp": ">=1.27.1,<2"},
}


# ── Phase 0: contract ──────────────────────────────────────────────────────


def test_schema_file_is_valid(validator: Draft202012Validator) -> None:
    # The fixture already ran check_schema; a JSON Schema may legally be a
    # bare boolean, so read the title from the file rather than indexing
    # validator.schema.
    assert SCHEMA_PATH.is_file()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["title"] == COMPATIBILITY_SCHEMA
    assert validator.schema is not None


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
    report = _report([_make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X)])
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


# ── Phase 2: declared compatibility ────────────────────────────────────────


def test_repo_contract_schema_accepts_compatibility_block() -> None:
    """Extending the contract must not break existing consumers."""
    schema = json.loads(
        (REPO_ROOT / "schemas" / "mq_stack_repo_contract.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    base = {
        "repo": "mq-mcp",
        "role": "runtime",
        "version": "2.0.2",
        "status": "active",
        "contracts": ["x.v1"],
    }

    # The pre-existing shape stays valid.
    assert not list(validator.iter_errors(base))

    # And the new optional block is accepted.
    extended = dict(base, compatibility={
        "protocols": {"mcp_api": "1.x-fastmcp"},
        "dependencies": {"mcp": ">=1.27.1,<2"},
        "produces": ["mq-mcp.tools.v1"],
        "consumes": ["mq.feedback.v1"],
    })
    assert not list(validator.iter_errors(extended))


def test_repo_contract_schema_rejects_unknown_compatibility_key() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas" / "mq_stack_repo_contract.schema.json").read_text(
            encoding="utf-8"
        )
    )
    contract = {
        "repo": "x", "role": "r", "version": "1.0.0", "status": "active",
        "contracts": [], "compatibility": {"nonsense": {}},
    }
    assert list(Draft202012Validator(schema).iter_errors(contract))


def test_missing_metadata_warns_but_does_not_block(tmp_path) -> None:
    """Absent metadata must stay explicit and non-blocking during rollout."""
    report = _report([_make_repo(tmp_path, "repo-a", compat=None)])
    assert report["status"] == "WARN"
    finding = next(
        f for f in report["findings"]
        if f["code"] == "MQC009_COMPATIBILITY_METADATA_MISSING"
    )
    assert finding["blocks_release"] is False
    assert report["components"][0]["compatibility_declared"] is False


def test_declared_boundary_matching_pyproject_passes(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X)]
    report = _report(entries)
    assert report["status"] == "PASS"
    assert report["components"][0]["compatibility_declared"] is True
    assert report["components"][0]["protocols"] == {"mcp_api": "1.x-fastmcp"}


def test_declared_boundary_order_does_not_matter(tmp_path) -> None:
    """'<2,>=1.27.1' and '>=1.27.1,<2' describe the same boundary."""
    entries = [
        _make_repo(
            tmp_path, "repo-a",
            declared="mcp<2,>=1.27.1",
            compat={"dependencies": {"mcp": ">=1.27.1,<2"}},
        )
    ]
    assert _report(entries)["status"] == "PASS"


def test_inconsistent_metadata_fails(tmp_path) -> None:
    """Metadata that contradicts pyproject.toml is a hard failure."""
    entries = [
        _make_repo(
            tmp_path, "repo-a",
            declared="mcp>=1.0,<3",
            compat={"dependencies": {"mcp": ">=1.27.1,<2"}},
        )
    ]
    report = _report(entries)
    assert report["status"] == "FAIL"
    finding = next(
        f for f in report["findings"]
        if f["code"] == "MQC011_DECLARED_DEPENDENCY_MISMATCH"
    )
    assert finding["blocks_release"] is True


def test_missing_and_inconsistent_metadata_are_distinct(tmp_path) -> None:
    """The two states must not collapse into one code."""
    missing = _report([_make_repo(tmp_path, "a", compat=None)])
    inconsistent = _report([
        _make_repo(tmp_path, "b", declared="mcp>=1.0,<3",
                   compat={"dependencies": {"mcp": ">=1.27.1,<2"}})
    ])
    assert [f["code"] for f in missing["findings"]] == [
        "MQC009_COMPATIBILITY_METADATA_MISSING"
    ]
    assert "MQC011_DECLARED_DEPENDENCY_MISMATCH" in [
        f["code"] for f in inconsistent["findings"]
    ]
    assert missing["status"] == "WARN"
    assert inconsistent["status"] == "FAIL"


def test_open_range_contradicting_protocol_fails(tmp_path) -> None:
    """The exact regression: a 1.x FastMCP contract that still allows MCP 2.x."""
    entries = [
        _make_repo(
            tmp_path, "repo-a",
            declared="mcp>=1.0",
            compat={
                "protocols": {"mcp_api": "1.x-fastmcp"},
                "dependencies": {"mcp": ">=1.0"},
            },
        )
    ]
    report = _report(entries)
    assert report["status"] == "FAIL"
    codes = [f["code"] for f in report["findings"]]
    assert "MQC012_PROTOCOL_CONTRADICTS_RANGE" in codes
    finding = next(f for f in report["findings"] if f["code"] == "MQC012_PROTOCOL_CONTRADICTS_RANGE")
    assert finding["blocks_release"] is True


def test_bounded_range_matching_protocol_passes(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X)]
    codes = [f["code"] for f in _report(entries)["findings"]]
    assert "MQC012_PROTOCOL_CONTRADICTS_RANGE" not in codes


def test_produces_and_consumes_are_reported(tmp_path) -> None:
    entries = [
        _make_repo(
            tmp_path, "repo-a",
            compat=dict(DECLARED_MCP_1X, produces=["mq-mcp.tools.v1"],
                        consumes=["mq.feedback.v1"]),
        )
    ]
    component = _report(entries)["components"][0]
    assert component["produces"] == ["mq-mcp.tools.v1"]
    assert component["consumes"] == ["mq.feedback.v1"]


def test_phase2_report_still_validates(tmp_path, validator) -> None:
    entries = [
        _make_repo(tmp_path, "ok", compat=DECLARED_MCP_1X),
        _make_repo(tmp_path, "missing", compat=None),
        _make_repo(tmp_path, "bad", declared="mcp>=1.0",
                   compat={"protocols": {"mcp_api": "1.x-fastmcp"},
                           "dependencies": {"mcp": ">=1.0"}}),
    ]
    errors = list(validator.iter_errors(_report(entries)))
    assert not errors, [e.message for e in errors]


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


def test_dependency_declared_with_no_version_at_all_is_reported(tmp_path) -> None:
    # `dependencies = ['mcp']` is the most exposed declaration there is: it
    # admits every future major. Reading it as "not declared" made the repo
    # disappear from the report entirely — the exact shape of the incident this
    # gate exists to catch.
    entry = _make_repo(
        tmp_path,
        "repo-a",
        declared="mcp",
        compat={"protocols": {"mcp_api": "1.x-fastmcp"}},
    )
    report = _report([entry])

    dependency = report["components"][0]["dependencies"][0]
    assert dependency["name"] == "mcp"
    assert dependency["declared"] == ""
    assert dependency["bounded"] is False

    codes = [f["code"] for f in report["findings"]]
    assert "MQC005_DECLARED_RANGE_UNBOUNDED" in codes
    assert "MQC012_PROTOCOL_CONTRADICTS_RANGE" in codes
    assert report["status"] == "FAIL"


# ── Phase 3: stack relationships and overlap ───────────────────────────────

# Two repos on the same protocol track, both bounded to MCP 1.x.
MCP_2X: dict[str, Any] = {
    "protocols": {"mcp_api": "2.x-mcp"},
    "dependencies": {"mcp": ">=2,<3"},
}


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (">=1.27.1,<2", ">=1.27.1,<2", True),
        (">=1.27.1,<2", ">=1.30,<2", True),
        (">=1.27.1,<2", ">=2,<3", False),
        ("==1.27.1", "==1.28.0", False),
        ("==1.27.1", ">=1.0,<2", True),
        (">=1.0", ">=2,<3", True),
        # Upper bounds alone: everything below the bound satisfies both.
        ("<2", "<2", True),
        ("<2", "<3", True),
        ("<2", ">=2", False),
        ("!=2.0.0", "<1.5", True),
        (None, ">=1.0,<2", None),
        ("not a spec", ">=1.0,<2", None),
    ],
)
def test_range_overlap_detection(
    left: str | None, right: str | None, expected: bool | None
) -> None:
    assert _ranges_overlap(left, right) is expected


def test_shared_dependency_produces_a_relationship(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(tmp_path, "repo-b", compat=DECLARED_MCP_1X),
    ]
    report = _report(entries)
    relationships = [r for r in report["relationships"] if r["subject"] == "mcp"]
    assert len(relationships) == 1
    relationship = relationships[0]
    assert {relationship["producer"], relationship["consumer"]} == {"repo-a", "repo-b"}
    assert relationship["overlap"] is True
    assert relationship["status"] == "PASS"


def test_single_repo_has_no_relationships(tmp_path) -> None:
    entries = [_make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X)]
    assert _report(entries)["relationships"] == []


def test_disjoint_ranges_fail(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=2,<3", locked="2.0.0", compat=MCP_2X
        ),
    ]
    report = _report(entries)
    assert report["status"] == "FAIL"
    finding = next(
        f for f in report["findings"] if f["code"] == "MQC007_DECLARED_RANGES_DISJOINT"
    )
    assert finding["blocks_release"] is True
    relationship = next(r for r in report["relationships"] if r["subject"] == "mcp")
    assert relationship["overlap"] is False
    assert relationship["status"] == "FAIL"


def test_disjoint_ranges_name_both_repos_and_observed_values(tmp_path) -> None:
    """A relationship is evidence, not just a verdict."""
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=2,<3", locked="2.0.0", compat=MCP_2X
        ),
    ]
    report = _report(entries)
    # packaging normalises specifier order, so assert against what the report
    # actually observed rather than how the fixture spelled it.
    declared = {
        c["repo"]: c["dependencies"][0]["declared"] for c in report["components"]
    }
    finding = next(
        f for f in report["findings"] if f["code"] == "MQC007_DECLARED_RANGES_DISJOINT"
    )
    assert declared["repo-a"] in finding["message"]
    assert declared["repo-b"] in finding["message"]
    repos = {e["repo"] for e in finding["evidence"]}
    assert repos == {"repo-a", "repo-b"}

    relationship = next(r for r in report["relationships"] if r["subject"] == "mcp")
    assert declared["repo-a"] in relationship["detail"]
    assert declared["repo-b"] in relationship["detail"]


def test_parallel_protocol_tracks_are_flagged(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=2,<3", locked="2.0.0", compat=MCP_2X
        ),
    ]
    finding = next(
        f
        for f in _report(entries)["findings"]
        if f["code"] == "MQC008_PROTOCOL_TRACK_MISMATCH"
    )
    assert "1.x-fastmcp" in finding["message"]
    assert "2.x-mcp" in finding["message"]


def test_same_protocol_track_raises_no_mismatch(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(tmp_path, "repo-b", compat=DECLARED_MCP_1X),
    ]
    codes = [f["code"] for f in _report(entries)["findings"]]
    assert "MQC008_PROTOCOL_TRACK_MISMATCH" not in codes
    assert "MQC007_DECLARED_RANGES_DISJOINT" not in codes


def test_protocol_mismatch_on_a_runtime_path_blocks_release(tmp_path) -> None:
    """Different tracks warn; different tracks wired together fail."""
    producer = dict(DECLARED_MCP_1X, produces=["mq-mcp.tools.v1"])
    consumer = dict(MCP_2X, consumes=["mq-mcp.tools.v1"])
    entries = [
        _make_repo(tmp_path, "repo-a", compat=producer),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=2,<3", locked="2.0.0", compat=consumer
        ),
    ]
    report = _report(entries)
    finding = next(
        f
        for f in report["findings"]
        if f["code"] == "MQC008_PROTOCOL_TRACK_MISMATCH"
    )
    assert finding["severity"] == "FAIL"
    assert finding["blocks_release"] is True


def test_protocol_mismatch_without_a_runtime_path_only_warns(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=2,<3", locked="2.0.0", compat=MCP_2X
        ),
    ]
    finding = next(
        f
        for f in _report(entries)["findings"]
        if f["code"] == "MQC008_PROTOCOL_TRACK_MISMATCH"
    )
    assert finding["severity"] == "WARN"
    assert finding["blocks_release"] is False


def test_matched_contract_becomes_a_relationship(tmp_path) -> None:
    producer = dict(DECLARED_MCP_1X, produces=["mq-mcp.tools.v1"])
    consumer = dict(DECLARED_MCP_1X, consumes=["mq-mcp.tools.v1"])
    entries = [
        _make_repo(tmp_path, "producer", compat=producer),
        _make_repo(tmp_path, "consumer", compat=consumer),
    ]
    report = _report(entries)
    relationship = next(
        r for r in report["relationships"] if r["subject"] == "mq-mcp.tools.v1"
    )
    assert relationship["producer"] == "producer"
    assert relationship["consumer"] == "consumer"
    assert relationship["status"] == "PASS"
    assert relationship["overlap"] is None


def test_consumer_without_a_producer_is_flagged(tmp_path) -> None:
    entries = [
        _make_repo(
            tmp_path, "consumer",
            compat=dict(DECLARED_MCP_1X, consumes=["mq-mcp.tools.v1"]),
        ),
        _make_repo(tmp_path, "bystander", compat=DECLARED_MCP_1X),
    ]
    report = _report(entries)
    finding = next(
        f
        for f in report["findings"]
        if f["code"] == "MQC013_CONTRACT_UNPRODUCED"
    )
    assert finding["repo"] == "consumer"
    assert "mq-mcp.tools.v1" in finding["message"]
    assert finding["blocks_release"] is False
    # A relationship needs two parties; an unproduced contract is a finding
    # against the consumer, not a half-populated edge.
    subjects = [r["subject"] for r in report["relationships"]]
    assert "mq-mcp.tools.v1" not in subjects


def test_unavailable_repo_creates_no_relationships(tmp_path) -> None:
    """A missing repo is unknown, not incompatible."""
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        {"name": "gone", "path": str(tmp_path / "gone"), "role": "test"},
    ]
    report = _report(entries)
    assert report["relationships"] == []
    codes = [f["code"] for f in report["findings"]]
    assert "MQC007_DECLARED_RANGES_DISJOINT" not in codes


def test_relationships_are_deterministic(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-b", compat=DECLARED_MCP_1X),
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(tmp_path, "repo-c", compat=DECLARED_MCP_1X),
    ]
    first = _report(entries)["relationships"]
    second = _report(entries)["relationships"]
    assert first == second
    assert [(r["producer"], r["consumer"]) for r in first] == sorted(
        (r["producer"], r["consumer"]) for r in first
    )


def test_phase3_report_validates_against_schema(tmp_path, validator) -> None:
    producer = dict(DECLARED_MCP_1X, produces=["mq-mcp.tools.v1"])
    consumer = dict(MCP_2X, consumes=["mq-mcp.tools.v1", "nobody.produces.this"])
    entries = [
        _make_repo(tmp_path, "repo-a", compat=producer),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=2,<3", locked="2.0.0", compat=consumer
        ),
        _make_repo(tmp_path, "repo-c", compat=None),
    ]
    report = _report(entries)
    errors = list(validator.iter_errors(report))
    assert not errors, [e.message for e in errors]
    assert report["relationships"], "expected relationships to be populated"


def test_identical_upper_bounds_do_not_fail(tmp_path) -> None:
    """Regression: two repos declaring the same range are not disjoint."""
    entries = [
        _make_repo(tmp_path, "repo-a", declared="mcp<2", compat=None),
        _make_repo(tmp_path, "repo-b", declared="mcp<2", compat=None),
    ]
    report = _report(entries)
    codes = [f["code"] for f in report["findings"]]
    assert "MQC007_DECLARED_RANGES_DISJOINT" not in codes
    relationship = next(r for r in report["relationships"] if r["subject"] == "mcp")
    assert relationship["overlap"] is True


def test_unproduced_contract_is_not_claimed_from_a_partial_view(tmp_path) -> None:
    """Unknown is not incompatible: a repo we could not read may produce it."""
    entries = [
        _make_repo(
            tmp_path, "consumer",
            compat=dict(DECLARED_MCP_1X, consumes=["mq-mcp.tools.v1"]),
        ),
        {"name": "gone", "path": str(tmp_path / "gone"), "role": "test"},
    ]
    codes = [f["code"] for f in _report(entries)["findings"]]
    assert "MQC013_CONTRACT_UNPRODUCED" not in codes


def test_self_produced_contract_is_not_flagged(tmp_path) -> None:
    both = dict(
        DECLARED_MCP_1X,
        produces=["mq-mcp.tools.v1"],
        consumes=["mq-mcp.tools.v1"],
    )
    entries = [
        _make_repo(tmp_path, "repo-a", compat=both),
        _make_repo(tmp_path, "repo-b", compat=DECLARED_MCP_1X),
    ]
    codes = [f["code"] for f in _report(entries)["findings"]]
    assert "MQC013_CONTRACT_UNPRODUCED" not in codes


def test_relationship_status_reflects_a_protocol_mismatch(tmp_path) -> None:
    """A pair that raises a blocking finding must not render as PASS."""
    producer = dict(DECLARED_MCP_1X, produces=["mq-mcp.tools.v1"])
    consumer = dict(MCP_2X, consumes=["mq-mcp.tools.v1"])
    entries = [
        _make_repo(tmp_path, "repo-a", compat=producer),
        _make_repo(
            tmp_path, "repo-b", declared="mcp>=1.5,<3", locked="2.0.0", compat=consumer
        ),
    ]
    report = _report(entries)
    relationship = next(r for r in report["relationships"] if r["subject"] == "mcp")
    assert relationship["overlap"] is True, "ranges do overlap; the tracks do not"
    assert relationship["status"] == "FAIL"


def test_protocol_tracks_compare_without_a_shared_dependency_row(tmp_path) -> None:
    """Parallel tracks are visible even when one repo pins nothing itself."""
    entries = [
        _make_repo(tmp_path, "repo-a", compat=DECLARED_MCP_1X),
        _make_repo(
            tmp_path, "repo-b", declared="requests>=2,<3", locked=None, compat=MCP_2X
        ),
    ]
    codes = [f["code"] for f in _report(entries)["findings"]]
    assert "MQC008_PROTOCOL_TRACK_MISMATCH" in codes


def test_relationships_survive_a_repo_without_metadata(tmp_path) -> None:
    """Rollout state: one repo declares nothing and must not break the pass."""
    entries = [
        _make_repo(tmp_path, "declared", compat=DECLARED_MCP_1X),
        _make_repo(tmp_path, "undeclared", compat=None),
    ]
    report = _report(entries)
    relationship = next(r for r in report["relationships"] if r["subject"] == "mcp")
    assert relationship["overlap"] is True
    assert relationship["status"] == "PASS"


# ── Phase 5: CLI surface ───────────────────────────────────────────────────


def _cli(report: dict[str, Any], *args: str):
    """Invoke the CLI against a fixed report and return the result."""
    from typer.testing import CliRunner

    import mq_agent.tools.stack_compatibility as module
    from mq_agent.main import app

    runner = CliRunner()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "stack_compatibility", lambda **kwargs: json.dumps(report))
        return runner.invoke(app, ["stack", "compatibility", *args])


def _fixed(status: str) -> dict[str, Any]:
    return {
        "schema": COMPATIBILITY_SCHEMA,
        "status": status,
        "mode": "static",
        "components": [],
        "relationships": [],
        "findings": [],
        "next_action": "",
        "checked_at": "2026-08-13T00:00:00+00:00",
    }


@pytest.mark.parametrize(
    "status,expected",
    [("PASS", 0), ("SKIPPED", 0), ("WARN", 0), ("FAIL", 2), ("UNAVAILABLE", 3)],
)
def test_exit_codes_follow_the_report_status(status: str, expected: int) -> None:
    assert _cli(_fixed(status), "--json").exit_code == expected


@pytest.mark.parametrize(
    "status,expected",
    [("PASS", 0), ("WARN", 1), ("FAIL", 2), ("UNAVAILABLE", 3)],
)
def test_strict_mode_makes_warnings_fail(status: str, expected: int) -> None:
    assert _cli(_fixed(status), "--strict", "--json").exit_code == expected


@pytest.mark.parametrize("status", ["PASS", "WARN", "FAIL", "UNAVAILABLE"])
def test_human_and_json_output_carry_the_same_verdict(status: str) -> None:
    human = _cli(_fixed(status))
    machine = _cli(_fixed(status), "--json")

    assert human.exit_code == machine.exit_code
    assert status in human.stdout
    assert json.loads(machine.stdout)["status"] == status


def test_interruption_exits_130() -> None:
    from typer.testing import CliRunner

    import mq_agent.tools.stack_compatibility as module
    from mq_agent.main import app

    def _interrupt(**kwargs):
        raise KeyboardInterrupt

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "stack_compatibility", _interrupt)
        result = CliRunner().invoke(app, ["stack", "compatibility"])

    assert result.exit_code == 130
