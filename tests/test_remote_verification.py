"""Phase 3: explicit remote verification.

Three states, and nothing may collapse them into each other:

    not requested  ≠  attempted and failed  ≠  succeeded

A default run contacts nothing, so `not verified` is its normal state and stays
`PASS`. An explicit `--refresh` that cannot reach the remote is `UNAVAILABLE` —
never `False`, never "stale", and never a comparison nobody was able to make.

`--refresh` makes an observation fresher. It does not change how observations
are reduced: Phase 2b's semantics apply unchanged whether `origin/main` came
from disk or from the network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mq_agent.core import runtime_identity, stack_provenance

ROOT = Path(__file__).resolve().parents[1]


def _validator() -> Draft202012Validator:
    schema = json.loads(
        (ROOT / "schemas" / "stack_provenance.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, registry=runtime_identity.schema_registry())


def _remote(**overrides) -> dict:
    remote = {
        "local_origin_main": "abc1234",
        "remote_origin_main": None,
        "verification_attempted": False,
        "verified": False,
        "verified_at": None,
    }
    remote.update(overrides)
    return remote


def _component(**overrides) -> dict:
    component: dict = {
        "name": "mq-agent",
        "checkout": {"path": "/repo", "branch": "main", "head": "abc1234", "worktree_clean": True},
        "integration": {
            "head_is_main": True,
            "head_integrated_in_main": True,
            "head_pushed": True,
            "ahead": 0,
            "behind": 0,
            "diverged": False,
        },
        "remote": _remote(),
        "installed": runtime_identity.build_identity(
            version="1.28.0", commit="abc1234", install_type="editable"
        ),
        "running": None,
        "release": None,
    }
    component.update(overrides)
    return component


# --- the three states are distinct ----------------------------------------


# Without --refresh nothing was asked of the network. That is not a failed
# check, and it is not a finding.
def test_not_requested_is_not_a_finding() -> None:
    assessed = stack_provenance.assess(_component())

    assert assessed["reasons"] == []
    assert assessed["status"] == "PASS"


# With --refresh, a remote that could not be reached is an observation nobody
# could make. Not false, not stale.
def test_attempted_and_failed_is_unavailable() -> None:
    unreachable = _component(remote=_remote(verification_attempted=True))

    assessed = stack_provenance.assess(unreachable)

    assert "RTP014_REMOTE_UNAVAILABLE" in assessed["reasons"]
    assert assessed["status"] == "UNAVAILABLE"


def test_succeeded_records_what_it_saw_and_when() -> None:
    verified = _component(
        remote=_remote(
            remote_origin_main="abc1234",
            verification_attempted=True,
            verified=True,
            verified_at="2026-09-06T12:00:00+02:00",
        )
    )

    assessed = stack_provenance.assess(verified)

    assert assessed["reasons"] == []
    assert assessed["status"] == "PASS"


# The distinction has to be in the record, not inferred by whoever reads it.
# `verified: false` alone cannot say whether anyone tried.
def test_the_record_distinguishes_never_asked_from_asked_and_failed() -> None:
    never = stack_provenance.assess(_component())
    failed = stack_provenance.assess(_component(remote=_remote(verification_attempted=True)))

    assert never["remote"]["verified"] is failed["remote"]["verified"] is False
    assert never["remote"]["verification_attempted"] is False
    assert failed["remote"]["verification_attempted"] is True
    assert never["status"] != failed["status"]


# --- a verified remote that disagrees -------------------------------------


def test_a_checkout_behind_a_verified_remote_is_reported() -> None:
    behind = _component(
        remote=_remote(
            remote_origin_main="999aaaa",
            verification_attempted=True,
            verified=True,
            verified_at="2026-09-06T12:00:00+02:00",
        )
    )

    assessed = stack_provenance.assess(behind)

    assert "RTP005_CHECKOUT_BEHIND_REMOTE" in assessed["reasons"]
    assert assessed["status"] == "WARN"


# Without verification the same disagreement cannot be claimed: the local
# origin/main is simply what this machine last saw.
def test_the_same_disagreement_is_not_claimed_without_verification() -> None:
    unverified = _component(remote=_remote(remote_origin_main=None))

    assert "RTP005_CHECKOUT_BEHIND_REMOTE" not in stack_provenance.assess(unverified)["reasons"]


def test_a_local_ref_matching_a_verified_remote_is_no_finding() -> None:
    matching = _component(
        remote=_remote(
            remote_origin_main="abc1234",
            verification_attempted=True,
            verified=True,
            verified_at="2026-09-06T12:00:00+02:00",
        )
    )

    assert stack_provenance.assess(matching)["reasons"] == []


# --- refresh changes freshness, not semantics -----------------------------


# A dirty worktree is a dirty worktree whether or not the network was consulted.
@pytest.mark.parametrize("attempted", [False, True])
def test_refresh_does_not_change_how_other_findings_are_reduced(attempted) -> None:
    dirty = _component(
        checkout={"path": "/repo", "branch": "main", "head": "abc1234", "worktree_clean": False},
        remote=_remote(
            remote_origin_main="abc1234" if attempted else None,
            verification_attempted=attempted,
            verified=attempted,
            verified_at="2026-09-06T12:00:00+02:00" if attempted else None,
        ),
    )

    assessed = stack_provenance.assess(dirty)

    assert "RTP001_DIRTY_WORKTREE" in assessed["reasons"]
    assert assessed["status"] == "WARN"


# --- the contract holds the invariant -------------------------------------


def test_a_verified_remote_must_have_been_attempted() -> None:
    impossible = _component(
        remote=_remote(
            remote_origin_main="abc1234",
            verification_attempted=False,
            verified=True,
            verified_at="2026-09-06T12:00:00+02:00",
        )
    )

    record = {
        "schema": "mq.stack-provenance.v1",
        "generated_at": "2026-09-06T12:00:00+02:00",
        "remote_verified": True,
        "components": [stack_provenance.assess(impossible)],
        "summary": {"status": "PASS", "problem_count": 0, "next_action": None},
    }

    assert not _validator().is_valid(record)


def test_the_assessed_record_satisfies_the_contract() -> None:
    record = stack_provenance.build([_component()], remote_verified=False)

    _validator().validate(record)


# --- observing a remote ---------------------------------------------------


def test_observing_without_refresh_asks_nothing(tmp_path, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("the default must not touch the network")

    monkeypatch.setattr(runtime_identity, "_ls_remote", fail)

    remote = runtime_identity.observe_remote(ROOT, refresh=False)
    assert remote is not None

    assert remote["verification_attempted"] is False
    assert remote["verified"] is False
    assert remote["remote_origin_main"] is None
    assert remote["verified_at"] is None
    # The locally known ref is still reported; it just was not confirmed.
    assert remote["local_origin_main"]


def test_a_refresh_that_cannot_reach_the_remote_says_so(monkeypatch) -> None:
    monkeypatch.setattr(runtime_identity, "_ls_remote", lambda root, ref: None)

    remote = runtime_identity.observe_remote(ROOT, refresh=True)
    assert remote is not None

    assert remote["verification_attempted"] is True
    assert remote["verified"] is False
    assert remote["remote_origin_main"] is None
    assert remote["verified_at"] is None


def test_a_successful_refresh_records_the_sha_and_the_time(monkeypatch) -> None:
    monkeypatch.setattr(runtime_identity, "_ls_remote", lambda root, ref: "f" * 40)

    remote = runtime_identity.observe_remote(ROOT, refresh=True)
    assert remote is not None

    assert remote["verification_attempted"] is True
    assert remote["verified"] is True
    assert remote["remote_origin_main"] == "f" * 40
    assert remote["verified_at"] is not None


def test_a_directory_that_is_not_a_repository_observes_no_remote(tmp_path) -> None:
    assert runtime_identity.observe_remote(tmp_path, refresh=True) is None


# --- the command surface --------------------------------------------------

from typer.testing import CliRunner  # noqa: E402

from mq_agent.main import app  # noqa: E402

cli = CliRunner()


def test_the_default_command_reports_that_it_asked_nothing() -> None:
    result = cli.invoke(app, ["stack", "provenance", "--json"])

    assert result.exit_code == 0
    record = json.loads(result.output)
    assert record["remote_verified"] is False
    assert record["components"][0]["remote"]["verification_attempted"] is False


def test_refresh_marks_the_run_as_having_asked(monkeypatch) -> None:
    monkeypatch.setattr(runtime_identity, "_ls_remote", lambda root, ref: "f" * 40)

    result = cli.invoke(app, ["stack", "provenance", "--refresh", "--json"])

    assert result.exit_code == 0
    record = json.loads(result.output)
    assert record["remote_verified"] is True
    assert record["components"][0]["remote"]["verified"] is True


# Even a failed refresh must not make the command fail: provenance observes.
def test_a_failed_refresh_still_exits_zero(monkeypatch) -> None:
    monkeypatch.setattr(runtime_identity, "_ls_remote", lambda root, ref: None)

    result = cli.invoke(app, ["stack", "provenance", "--refresh"])

    assert result.exit_code == 0
    assert "RTP014_REMOTE_UNAVAILABLE" in result.output
