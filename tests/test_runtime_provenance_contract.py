"""Phase 0 of v1.28 runtime provenance: the contracts, before anything produces them.

Nothing here instruments a runtime. These tests freeze the semantics so the
phases that follow cannot quietly redefine them:

* identity is `component + version + commit`, and a missing commit weakens it
  rather than being guessed from the latest tag;
* a comparison is `true`, `false`, or `null` — checked and matching, checked and
  differing, or not observed — and `null` is never collapsed into `false`;
* no generic `synced` / `healthy` / `current` / `aligned` boolean exists, because
  each edge of checkout → installed → running answers a different question;
* provenance reports facts and never owns a blocking decision.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mq_agent.core import runtime_identity

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "runtime_identity.schema.json"
PROVENANCE = "stack_provenance.schema.json"


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    """Validate against the registry the runtime itself uses.

    Provenance embeds runtime identity by reference, so validation needs both
    schemas registered. Phase 1 moved that helper into module code; the tests
    use it rather than keeping a second copy that could drift.
    """
    return Draft202012Validator(_schema(name), registry=runtime_identity.schema_registry())


def _identity(**overrides) -> dict:
    record = {
        "schema": "mq.runtime-identity.v1",
        "component": "mq-agent",
        "version": "1.28.0",
        "commit": "abc1234",
        "install_type": "editable",
        "identity_quality": "verified",
        "started_at": None,
    }
    record.update(overrides)
    return record


def _component(**overrides) -> dict:
    component: dict = {
        "name": "mq-agent",
        "checkout": {
            "path": "/path/to/mq-agent",
            "branch": "main",
            "head": "abc1234",
            "worktree_clean": True,
        },
        "integration": {
            "head_is_main": True,
            "head_integrated_in_main": True,
            "head_pushed": True,
            "ahead": 0,
            "behind": 0,
            "diverged": False,
        },
        "remote": {
            "local_origin_main": "abc1234",
            "remote_origin_main": None,
            "verified": False,
            "verified_at": None,
        },
        "installed": _identity(),
        "running": None,
        "release": {
            "declared_version": "1.28.0",
            "latest_tag": "v1.28.0",
            "tag_commit": "abc1234",
            "github_release_tag": None,
        },
        "comparison": {
            "installed_matches_checkout": True,
            "running_matches_installed": None,
            "running_matches_checkout": None,
            "release_matches_checkout": True,
            "release_matches_installed": True,
        },
        "status": "PASS",
        "reasons": [],
    }
    component.update(overrides)
    return component


def _provenance(**overrides) -> dict:
    record = {
        "schema": "mq.stack-provenance.v1",
        "generated_at": "2026-09-06T02:00:00+02:00",
        "remote_verified": False,
        "components": [_component()],
        "summary": {"status": "PASS", "problem_count": 0, "next_action": None},
    }
    record.update(overrides)
    return record


# --- both schemas are well formed -----------------------------------------


@pytest.mark.parametrize("name", [IDENTITY, PROVENANCE])
def test_schema_is_a_valid_draft_2020_12_schema(name) -> None:
    Draft202012Validator.check_schema(_schema(name))


@pytest.mark.parametrize("name", [IDENTITY, PROVENANCE])
def test_schema_is_closed(name) -> None:
    """A field nobody declared is a field nobody agreed on."""
    assert _schema(name)["additionalProperties"] is False


def test_the_example_records_are_valid() -> None:
    _validator(IDENTITY).validate(_identity())
    _validator(PROVENANCE).validate(_provenance())


# The existing `stack run` contract is `mq_stack_runtime.v1`. Provenance is a
# different question — which code is this? — and a name differing only in
# punctuation would be exactly the confusion this feature exists to detect.
def test_provenance_does_not_collide_with_the_stack_run_contract() -> None:
    provenance = _schema(PROVENANCE)["properties"]["schema"]["const"]
    stack_run = _schema("mq_stack_runtime.schema.json")["properties"]["schema"]["const"]

    assert provenance == "mq.stack-provenance.v1"
    assert provenance != stack_run
    assert provenance.replace(".", "_").replace("-", "_") != stack_run.replace("-", "_")


# --- runtime identity ------------------------------------------------------


def test_identity_is_component_version_and_commit() -> None:
    required = set(_schema(IDENTITY)["required"])

    assert {"schema", "component", "version", "commit", "identity_quality"} <= required


# Two builds can carry the same semver, so a version alone does not identify a
# runtime. The field stays required and nullable: absent commit is a weaker
# identity, never a missing one to be filled in from the latest tag.
def test_a_version_without_a_commit_is_partial_not_verified() -> None:
    validator = _validator(IDENTITY)

    assert validator.is_valid(_identity(commit=None, identity_quality="partial"))
    assert not validator.is_valid(_identity(commit=None, identity_quality="verified"))


def test_a_commit_makes_the_identity_verifiable() -> None:
    assert not _validator(IDENTITY).is_valid(_identity(identity_quality="partial"))


def test_an_unidentifiable_runtime_says_so_rather_than_guessing() -> None:
    unknown = _identity(
        version=None, commit=None, install_type="unknown", identity_quality="unknown"
    )

    _validator(IDENTITY).validate(unknown)


def test_install_type_covers_the_real_installation_shapes() -> None:
    allowed = set(_schema(IDENTITY)["properties"]["install_type"]["enum"])

    assert allowed == {"editable", "wheel", "pipx", "uv-tool", "pip", "unknown"}


# --- null is not false -----------------------------------------------------


# `null` means the comparison was not made; `false` means it was made and the
# two differ. A CLI with no long-lived process has no running runtime to
# compare, and reporting `false` there would invent a mismatch.
@pytest.mark.parametrize(
    "field",
    [
        "installed_matches_checkout",
        "running_matches_installed",
        "running_matches_checkout",
        "release_matches_checkout",
        "release_matches_installed",
    ],
)
def test_every_comparison_is_true_false_or_null(field) -> None:
    comparison = _schema(PROVENANCE)["$defs"]["comparison"]["properties"][field]

    assert comparison["type"] == ["boolean", "null"]


def test_a_component_with_no_running_process_compares_nothing_to_it() -> None:
    _validator(PROVENANCE).validate(_provenance())


# --- no generic green boolean ---------------------------------------------


def _property_names(node, found=None) -> set[str]:
    """Every property name the schema declares, at any depth."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for name, child in node.get("properties", {}).items():
            found.add(name)
            _property_names(child, found)
        for key, child in node.items():
            if key != "properties":
                _property_names(child, found)
    elif isinstance(node, list):
        for child in node:
            _property_names(child, found)
    return found


# Each edge of checkout → installed → running answers a different question, and
# one boolean over all of them would answer none of them. The ban is on a field
# with that meaning, not on the English word: a description may well say
# "reinstall from the current checkout".
@pytest.mark.parametrize("banned", ["synced", "healthy", "current", "aligned", "ok"])
def test_no_generic_status_field_exists(banned) -> None:
    assert banned not in _property_names(_schema(PROVENANCE))


# --- status semantics ------------------------------------------------------


def test_status_values_are_the_four_agreed_ones() -> None:
    assert set(_schema(PROVENANCE)["$defs"]["status"]["enum"]) == {
        "PASS",
        "WARN",
        "FAIL",
        "UNAVAILABLE",
    }


def test_a_mismatch_is_a_warning_not_a_failure() -> None:
    """A stale install is a real difference, and the command still ran fine."""
    mismatch = _component(
        comparison={
            "installed_matches_checkout": False,
            "running_matches_installed": None,
            "running_matches_checkout": None,
            "release_matches_checkout": True,
            "release_matches_installed": False,
        },
        status="WARN",
        reasons=["RTP007_INSTALLED_CHECKOUT_MISMATCH"],
    )

    _validator(PROVENANCE).validate(_provenance(components=[mismatch]))


def test_an_unobserved_runtime_is_unavailable_not_a_mismatch() -> None:
    unreachable = _component(
        name="mq-mcp",
        running=None,
        status="UNAVAILABLE",
        reasons=["RTP008_RUNNING_IDENTITY_UNKNOWN"],
    )

    _validator(PROVENANCE).validate(_provenance(components=[unreachable]))


# --- reason codes are API --------------------------------------------------


def test_reason_codes_cover_every_state_the_runtime_guard_already_observes() -> None:
    """The guard reaches states the code list must be able to name."""
    codes = set(_schema(PROVENANCE)["$defs"]["reason_code"]["enum"])
    guard = (ROOT / "mq_agent" / "core" / "runtime_guard.py").read_text(encoding="utf-8")

    for reason, code in (
        ("dirty-worktree", "RTP001_DIRTY_WORKTREE"),
        ("unintegrated-head", "RTP002_HEAD_NOT_INTEGRATED"),
        ("no-head", "RTP016_CHECKOUT_HEAD_MISSING"),
        ("no-canonical-ref", "RTP017_CANONICAL_REF_MISSING"),
        ("git-probe-failed", "RTP015_GIT_PROBE_FAILED"),
    ):
        assert f'reason="{reason}"' in guard, reason
        assert code in codes, code


def test_reason_codes_are_prefixed_and_named() -> None:
    for code in _schema(PROVENANCE)["$defs"]["reason_code"]["enum"]:
        number, _, name = code.partition("_")
        assert number.startswith("RTP") and number[3:].isdigit()
        assert name and name == name.upper()


def test_reason_codes_are_unique_and_documented() -> None:
    codes = _schema(PROVENANCE)["$defs"]["reason_code"]["enum"]
    documented = (ROOT / "docs" / "RUNTIME_PROVENANCE.md").read_text(encoding="utf-8")

    assert len(codes) == len(set(codes))
    for code in codes:
        assert code in documented, code


# --- provenance reports facts, never policy -------------------------------


# The blocking decision belongs to whoever acts on the signal: the release
# cockpit for a release, runtime_guard for production evidence. A field here
# saying "blocked" would move that decision into the observation.
@pytest.mark.parametrize(
    "banned", ["release_blocked", "blocked", "blocks_release", "may_write_evidence"]
)
def test_provenance_carries_no_blocking_decision(banned) -> None:
    assert banned not in _property_names(_schema(PROVENANCE))


def test_exactly_one_next_action_is_reported() -> None:
    next_action = _schema(PROVENANCE)["properties"]["summary"]["properties"]["next_action"]

    assert next_action["type"] == ["string", "null"]


# --- remote verification is opt-in ----------------------------------------


# The default command touches no network, so an unverified remote is the normal
# state and must not read as "this checkout is stale".
def test_an_unverified_remote_is_expressible_without_claiming_staleness() -> None:
    _validator(PROVENANCE).validate(_provenance(remote_verified=False))


def test_a_verified_remote_records_when_it_was_checked() -> None:
    verified = _component()
    verified["remote"] = {
        "local_origin_main": "abc1234",
        "remote_origin_main": "abc1234",
        "verified": True,
        "verified_at": "2026-09-06T02:00:00+02:00",
    }

    _validator(PROVENANCE).validate(_provenance(remote_verified=True, components=[verified]))


# --- execution outcome is untouched in phase 0 ----------------------------


def test_phase_0_does_not_change_the_execution_outcome_contract() -> None:
    execution = _schema("execution_outcome.schema.json")

    assert "runtime_identity" not in execution["properties"]
    assert "fingerprint" not in json.dumps(execution)
    assert execution["properties"]["runtime"]["enum"] == [
        "swarm",
        "executor",
        "task-runner",
        "agent",
    ]


# --- packaging -------------------------------------------------------------


# Both schemas are read at runtime, so without a force-include they vanish from
# the wheel and every installed runtime fails to load them silently.
@pytest.mark.parametrize("name", [IDENTITY, PROVENANCE])
def test_the_schema_is_force_included_in_the_wheel(name) -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert f'"schemas/{name}" = "mq_agent/schemas/{name}"' in pyproject


# --- the identity layers are really runtime identities --------------------


# The description said "an mq.runtime-identity.v1 record" while the schema
# asked only for an object, so any shape at all validated. RTP013 exists to
# name an invalid runtime identity; the contract has to be able to detect one.
@pytest.mark.parametrize("layer", ["installed", "running"])
def test_an_identity_layer_must_be_a_real_runtime_identity(layer) -> None:
    validator = _validator(PROVENANCE)

    assert not validator.is_valid(_provenance(components=[_component(**{layer: {"banana": 42}})]))
    assert not validator.is_valid(
        _provenance(components=[_component(**{layer: _identity(schema="mq.something-else.v1")})])
    )


def test_a_running_identity_is_accepted_when_it_is_well_formed() -> None:
    running = _identity(component="mq-mcp", started_at="2026-09-06T01:30:00+02:00")
    component = _component(
        name="mq-mcp",
        running=running,
        comparison={
            "installed_matches_checkout": True,
            "running_matches_installed": True,
            "running_matches_checkout": True,
            "release_matches_checkout": True,
            "release_matches_installed": True,
        },
    )

    _validator(PROVENANCE).validate(_provenance(components=[component]))


# One definition of runtime identity, embedded by reference. The reference is
# an https:// $id that resolves to nothing, so validating without the registry
# would reach for the network — which a local, network-free contract must not.
def test_identity_is_embedded_by_reference_not_duplicated() -> None:
    provenance = _schema(PROVENANCE)
    installed = provenance["properties"]["components"]["items"]["properties"]["installed"]

    assert json.dumps(installed).count("runtime_identity.schema.json") == 1
    assert "identity_quality" not in json.dumps(provenance)


# --- unknown means unknown ------------------------------------------------


# `verified` and `partial` were constrained; `unknown` was not, so a record
# could carry a version and a commit while claiming it identified nothing.
def test_an_unknown_identity_carries_no_version_or_commit() -> None:
    validator = _validator(IDENTITY)

    assert not validator.is_valid(_identity(identity_quality="unknown"))
    assert not validator.is_valid(_identity(commit=None, identity_quality="unknown"))
    assert validator.is_valid(
        _identity(version=None, commit=None, identity_quality="unknown")
    )


# Knowing how something was installed is not the same as knowing what it is:
# a pipx install can be perfectly identifiable as pipx and still carry no
# version metadata.
def test_an_unknown_identity_may_still_know_how_it_was_installed() -> None:
    unknown_but_pipx = _identity(
        version=None, commit=None, install_type="pipx", identity_quality="unknown"
    )

    _validator(IDENTITY).validate(unknown_but_pipx)


# --- null semantics are enforced, not just documented ---------------------


# "null is not false" has to be impossible to break, not merely written down.
# A comparison against a layer that was never observed is null; false would
# claim someone looked and found a difference.
def test_an_unobserved_running_runtime_compares_to_nothing() -> None:
    validator = _validator(PROVENANCE)
    broken = _component(running=None)
    broken["comparison"]["running_matches_installed"] = False

    assert not validator.is_valid(_provenance(components=[broken]))


def test_an_absent_checkout_compares_to_nothing() -> None:
    validator = _validator(PROVENANCE)
    wheel = _component(checkout=None, integration=None)
    wheel["comparison"] = {
        "installed_matches_checkout": None,
        "running_matches_installed": None,
        "running_matches_checkout": None,
        "release_matches_checkout": None,
        "release_matches_installed": True,
    }

    validator.validate(_provenance(components=[wheel]))

    wheel["comparison"]["installed_matches_checkout"] = True
    assert not validator.is_valid(_provenance(components=[wheel]))


def test_an_absent_release_compares_to_nothing() -> None:
    validator = _validator(PROVENANCE)
    unreleased = _component(release=None)
    unreleased["comparison"]["release_matches_checkout"] = None
    unreleased["comparison"]["release_matches_installed"] = None

    validator.validate(_provenance(components=[unreleased]))

    unreleased["comparison"]["release_matches_checkout"] = False
    assert not validator.is_valid(_provenance(components=[unreleased]))


# --- a verified remote carries its evidence -------------------------------


def test_a_verified_remote_must_say_what_it_saw_and_when() -> None:
    validator = _validator(PROVENANCE)
    component = _component()
    component["remote"] = {
        "local_origin_main": "abc1234",
        "remote_origin_main": None,
        "verified": True,
        "verified_at": None,
    }

    assert not validator.is_valid(_provenance(remote_verified=True, components=[component]))


# A component cannot have been verified against a remote in a run that
# contacted none. The converse does not hold: --refresh may reach the network
# and still fail to verify one repo.
def test_a_verified_component_implies_the_run_contacted_a_remote() -> None:
    verified = _component()
    verified["remote"] = {
        "local_origin_main": "abc1234",
        "remote_origin_main": "abc1234",
        "verified": True,
        "verified_at": "2026-09-06T02:00:00+02:00",
    }

    assert not _validator(PROVENANCE).is_valid(
        _provenance(remote_verified=False, components=[verified])
    )


def test_a_refreshed_run_may_still_fail_to_verify_a_component() -> None:
    unreachable = _component(
        status="UNAVAILABLE", reasons=["RTP014_REMOTE_UNAVAILABLE"]
    )

    _validator(PROVENANCE).validate(
        _provenance(remote_verified=True, components=[unreachable])
    )


# The reference is relative, so the registry resolves it from the two files on
# disk. An absolute `https://` ref would send a validator that forgot the
# registry to the network; a relative one fails closed instead. Consumers must
# still supply the registry — Phase 1 moves `_registry()` into module code.
def test_the_identity_reference_is_relative_so_it_resolves_locally() -> None:
    provenance = _schema(PROVENANCE)
    installed = provenance["properties"]["components"]["items"]["properties"]["installed"]
    ref = next(o["$ref"] for o in installed["oneOf"] if "$ref" in o)

    assert ref == IDENTITY
    assert not ref.startswith(("http://", "https://"))
