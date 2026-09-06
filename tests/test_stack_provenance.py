"""Phase 2b: turning observations into a status, a reason and one next action.

Three rules hold everything else up:

* `None` is not `False`. An unobserved layer never produces a reason code, a
  degraded status, or an action that assumes someone looked.
* Status is derived, never asserted. It is a deterministic reduction of the
  reason codes, which are themselves a deterministic reduction of the
  observations — so status is never a second source of truth.
* Exactly one next action, chosen by an explicit precedence. Reinstalling comes
  before restarting, because restarting a stale install starts the same code.

Provenance still decides nothing about releases or evidence. It reports facts.
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


def _component(**overrides) -> dict:
    """A component where everything was observed and everything agrees."""
    component: dict = {
        "name": "mq-agent",
        "checkout": {
            "path": "/repo",
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
        "remote": None,
        "installed": runtime_identity.build_identity(
            version="1.28.0", commit="abc1234", install_type="editable"
        ),
        "running": None,
        "running_probe": None,
        "release": {
            "declared_version": "1.28.0",
            "latest_tag": "v1.28.0",
            "tag_commit": "abc1234",
            "tag_reachable_from_head": True,
            "github_release_tag": None,
        },
    }
    component.update(overrides)
    return component


# --- everything agreeing is a pass ----------------------------------------


def test_a_component_where_everything_agrees_passes() -> None:
    assessed = stack_provenance.assess(_component())

    assert assessed["status"] == "PASS"
    assert assessed["reasons"] == []


def test_an_assessed_component_satisfies_the_contract() -> None:
    record = stack_provenance.build([_component()])

    _validator().validate(record)
    assert record["schema"] == "mq.stack-provenance.v1"
    assert record["summary"]["status"] == "PASS"
    assert record["summary"]["next_action"] is None


# --- None is not False ----------------------------------------------------


# An unobserved layer must not produce a reason, degrade the status, or suggest
# an action. Nobody looked; that is not a finding.
def test_an_unobserved_running_runtime_produces_no_finding() -> None:
    assessed = stack_provenance.assess(_component(running=None))

    assert assessed["status"] == "PASS"
    assert "RTP008_RUNNING_IDENTITY_UNKNOWN" not in assessed["reasons"]
    assert assessed["comparison"]["running_matches_installed"] is None


# A repository with no origin/main cannot say whether HEAD was pushed. That is
# an unobserved dimension, not an unpushed commit.
def test_a_missing_origin_main_does_not_become_an_unpushed_head() -> None:
    local_only = _component(
        integration={
            "head_is_main": True,
            "head_integrated_in_main": True,
            "head_pushed": None,
            "ahead": None,
            "behind": None,
            "diverged": None,
        }
    )

    assessed = stack_provenance.assess(local_only)

    assert "RTP003_LOCAL_MAIN_STALE" not in assessed["reasons"]
    assert assessed["status"] != "FAIL"


# The default command contacts no remote, so an unverified remote is the normal
# state and must not read as a problem.
def test_an_unverified_remote_is_not_a_finding() -> None:
    record = stack_provenance.build([_component()], remote_verified=False)

    assert record["summary"]["status"] == "PASS"
    assert "RTP004_REMOTE_NOT_VERIFIED" not in record["components"][0]["reasons"]


# A confirmed remote answers what GitHub holds, not what this checkout knows.
# Where `actions/checkout` leaves no `refs/remotes/origin/main`, the local side
# of the comparison was never observed, and `SHA != None` is not a disagreement.
def test_a_verified_remote_without_a_local_ref_invents_no_mismatch() -> None:
    no_tracking_ref = _component(
        remote={
            "local_origin_main": None,
            "remote_origin_main": "f" * 40,
            "verification_attempted": True,
            "verified": True,
            "verified_at": "2026-09-06T00:00:00Z",
        }
    )

    assessed = stack_provenance.assess(no_tracking_ref)

    assert "RTP005_CHECKOUT_BEHIND_REMOTE" not in assessed["reasons"]
    assert assessed["status"] == "PASS"


# The finding itself still has to fire when both sides were observed.
def test_a_verified_remote_that_differs_from_the_local_ref_is_reported() -> None:
    behind = _component(
        remote={
            "local_origin_main": "a" * 40,
            "remote_origin_main": "b" * 40,
            "verification_attempted": True,
            "verified": True,
            "verified_at": "2026-09-06T00:00:00Z",
        }
    )

    assessed = stack_provenance.assess(behind)

    assert "RTP005_CHECKOUT_BEHIND_REMOTE" in assessed["reasons"]
    assert assessed["status"] == "WARN"


@pytest.mark.parametrize(
    "layer", ["checkout", "integration", "installed", "release"]
)
def test_an_absent_layer_compares_to_nothing_and_accuses_nothing(layer) -> None:
    assessed = stack_provenance.assess(_component(**{layer: None}))

    for name, value in assessed["comparison"].items():
        assert value in (True, False, None), name
    assert assessed["status"] in ("PASS", "WARN", "UNAVAILABLE")


# --- status is derived ----------------------------------------------------


def test_status_is_a_pure_function_of_the_reason_codes() -> None:
    assert stack_provenance.status_for([]) == "PASS"
    assert stack_provenance.status_for(["RTP007_INSTALLED_CHECKOUT_MISMATCH"]) == "WARN"
    assert stack_provenance.status_for(["RTP006_INSTALLED_IDENTITY_UNKNOWN"]) == "UNAVAILABLE"
    assert stack_provenance.status_for(["RTP013_RUNTIME_IDENTITY_INVALID"]) == "FAIL"


# An incomplete picture outranks a single confirmed difference: an identity
# nobody could read may be hiding more differences than the one that was seen.
def test_an_unobservable_identity_outranks_a_mismatch() -> None:
    mixed = ["RTP007_INSTALLED_CHECKOUT_MISMATCH", "RTP006_INSTALLED_IDENTITY_UNKNOWN"]

    assert stack_provenance.status_for(mixed) == "UNAVAILABLE"


def test_every_reason_code_has_a_severity() -> None:
    """A code the reducer does not know would silently pass as no finding."""
    schema = json.loads(
        (ROOT / "schemas" / "stack_provenance.schema.json").read_text(encoding="utf-8")
    )
    for code in schema["$defs"]["reason_code"]["enum"]:
        assert code in stack_provenance.SEVERITY, code


def test_the_overall_status_is_the_worst_component_status() -> None:
    warned = _component(name="b", checkout={**_component()["checkout"], "worktree_clean": False})

    record = stack_provenance.build([_component(), warned])

    assert record["summary"]["status"] == "WARN"
    assert record["summary"]["problem_count"] == 1


# --- the findings themselves ----------------------------------------------


def test_a_dirty_worktree_is_reported() -> None:
    dirty = _component(checkout={**_component()["checkout"], "worktree_clean": False})

    assessed = stack_provenance.assess(dirty)

    assert assessed["reasons"] == ["RTP001_DIRTY_WORKTREE"]
    assert assessed["status"] == "WARN"


def test_an_installed_runtime_from_another_commit_is_reported() -> None:
    stale = _component(
        installed=runtime_identity.build_identity(
            version="1.28.0", commit="def5678", install_type="wheel"
        )
    )

    assessed = stack_provenance.assess(stale)

    assert assessed["comparison"]["installed_matches_checkout"] is False
    assert "RTP007_INSTALLED_CHECKOUT_MISMATCH" in assessed["reasons"]


def test_an_unidentifiable_installed_runtime_is_reported() -> None:
    unknown = _component(
        installed=runtime_identity.build_identity(
            version=None, commit=None, install_type="unknown"
        )
    )

    assessed = stack_provenance.assess(unknown)

    assert "RTP006_INSTALLED_IDENTITY_UNKNOWN" in assessed["reasons"]
    assert assessed["status"] == "UNAVAILABLE"


def test_a_head_outside_main_is_reported() -> None:
    unintegrated = _component(
        integration={
            "head_is_main": False,
            "head_integrated_in_main": False,
            "head_pushed": False,
            "ahead": 2,
            "behind": 0,
            "diverged": False,
        }
    )

    assessed = stack_provenance.assess(unintegrated)

    assert "RTP002_HEAD_NOT_INTEGRATED" in assessed["reasons"]


# A tag the checkout has moved past is ordinary progress between releases. If
# that alone were a finding, every repository would sit at WARN from the first
# commit after a release, and the status would stop meaning anything.
def test_a_checkout_ahead_of_its_tag_is_not_a_finding() -> None:
    after_release = _component(
        release={
            "declared_version": "1.28.0",
            "latest_tag": "v1.28.0",
            "tag_commit": "999aaaa",
            "tag_reachable_from_head": True,
            "github_release_tag": None,
        }
    )

    assessed = stack_provenance.assess(after_release)

    assert assessed["comparison"]["release_matches_checkout"] is False
    assert assessed["reasons"] == []
    assert assessed["status"] == "PASS"


# A tag that is not in this history at all is a real disagreement about which
# code the release names.
def test_a_tag_outside_this_history_is_reported() -> None:
    released_elsewhere = _component(
        release={
            "declared_version": "1.28.0",
            "latest_tag": "v1.28.0",
            "tag_commit": "999aaaa",
            "tag_reachable_from_head": False,
            "github_release_tag": None,
        }
    )

    assessed = stack_provenance.assess(released_elsewhere)

    assert assessed["comparison"]["release_matches_checkout"] is False
    assert "RTP012_RELEASE_COMMIT_MISMATCH" in assessed["reasons"]


# Unknown reachability is not a licence to accuse the tag.
def test_an_undetermined_reachability_reports_nothing() -> None:
    unknown = _component(
        release={
            "declared_version": "1.28.0",
            "latest_tag": "v1.28.0",
            "tag_commit": "999aaaa",
            "tag_reachable_from_head": None,
            "github_release_tag": None,
        }
    )

    assert "RTP012_RELEASE_COMMIT_MISMATCH" not in stack_provenance.assess(unknown)["reasons"]


def test_a_malformed_installed_identity_fails_rather_than_warns() -> None:
    assessed = stack_provenance.assess(_component(installed={"banana": 42}))

    assert "RTP013_RUNTIME_IDENTITY_INVALID" in assessed["reasons"]
    assert assessed["status"] == "FAIL"


# --- exactly one next action ----------------------------------------------


def test_a_healthy_stack_has_nothing_to_do() -> None:
    assert stack_provenance.build([_component()])["summary"]["next_action"] is None


# Restarting a process that runs a stale install starts the same stale code, so
# the reinstall has to come first even though both are true at once.
def test_reinstalling_precedes_restarting() -> None:
    both = _component(
        installed=runtime_identity.build_identity(
            version="1.28.0", commit="def5678", install_type="editable"
        ),
        running=runtime_identity.build_identity(
            version="1.28.0", commit="999aaaa", install_type="editable"
        ),
    )

    action = stack_provenance.build([both])["summary"]["next_action"]

    assert action is not None
    assert "reinstall" in action.lower()
    assert "restart" not in action.lower()


def test_a_divergence_outranks_being_behind() -> None:
    diverged = _component(
        integration={
            "head_is_main": False,
            "head_integrated_in_main": False,
            "head_pushed": False,
            "ahead": 3,
            "behind": 2,
            "diverged": True,
        }
    )

    action = stack_provenance.build([diverged])["summary"]["next_action"]

    assert action is not None
    assert "integrat" in action.lower()


# An action must never assume a check nobody ran.
def test_no_action_assumes_a_remote_that_was_never_contacted() -> None:
    behind_locally = _component(
        integration={
            "head_is_main": True,
            "head_integrated_in_main": True,
            "head_pushed": True,
            "ahead": 0,
            "behind": 4,
            "diverged": False,
        }
    )

    record = stack_provenance.build([behind_locally], remote_verified=False)
    action = record["summary"]["next_action"] or ""

    assert "RTP005_CHECKOUT_BEHIND_REMOTE" not in record["components"][0]["reasons"]
    assert "--refresh" not in action


def test_the_precedence_is_declared_once_and_covers_every_severity() -> None:
    """An action table that misses a code would silently return no action."""
    actionable = {
        code for code, severity in stack_provenance.SEVERITY.items() if severity != "PASS"
    }
    ranked = {code for code, _ in stack_provenance.NEXT_ACTIONS}

    assert ranked <= actionable
    assert len(ranked) == len(stack_provenance.NEXT_ACTIONS), "a code is ranked twice"


# --- provenance still decides nothing -------------------------------------


def test_the_record_carries_no_policy(monkeypatch) -> None:
    record = stack_provenance.build([_component()])

    serialised = json.dumps(record)
    for banned in ("blocked", "blocks_release", "may_write_evidence", "safe_to"):
        assert banned not in serialised


# --- observing this repository --------------------------------------------


def test_this_repository_can_be_observed_end_to_end() -> None:
    """What is observed depends on the machine: mq-mcp may or may not be here.

    Asserting the exact component list would encode one developer's checkout as
    the definition of an installation — the mistake this feature exists to
    catch, made in the tests instead of the code.
    """
    record = stack_provenance.observe()

    _validator().validate(record)
    names = [c["name"] for c in record["components"]]
    assert names[0] == "mq-agent"
    assert set(names) <= {"mq-agent", "mq-mcp"}
    assert record["remote_verified"] is False
    assert record["summary"]["status"] in ("PASS", "WARN", "UNAVAILABLE", "FAIL")


def test_this_runtime_never_claims_a_process_it_did_not_ask_for() -> None:
    """mq-agent is a CLI: no process of its own, and nothing asked about it."""
    component = stack_provenance.observe_component()

    assert component["running"] is None
    assert component["running_probe"] == {
        "attempted": False,
        "endpoint": None,
        "reachable": None,
    }


# --- the command surface --------------------------------------------------

from typer.testing import CliRunner  # noqa: E402

from mq_agent.main import app  # noqa: E402

cli = CliRunner()


def test_the_command_reports_this_runtime() -> None:
    result = cli.invoke(app, ["stack", "provenance"])

    assert result.exit_code == 0
    assert "mq-agent" in result.output
    assert "CHECKOUT" in result.output
    assert "INSTALLED" in result.output


def test_the_json_output_is_the_contract() -> None:
    result = cli.invoke(app, ["stack", "provenance", "--json"])

    assert result.exit_code == 0
    record = json.loads(result.output)
    _validator().validate(record)
    assert record["schema"] == "mq.stack-provenance.v1"


# Provenance observes; it does not stop work. A difference is something to know
# about, not a reason for the command to fail — the release cockpit and
# runtime_guard own their own blocking decisions.
@pytest.mark.parametrize("status", ["PASS", "WARN", "UNAVAILABLE", "FAIL"])
def test_the_command_never_blocks_on_what_it_finds(monkeypatch, status) -> None:
    record = stack_provenance.build([_component()])
    record["summary"]["status"] = status
    record["components"][0]["status"] = status
    monkeypatch.setattr("mq_agent.core.stack_provenance.observe", lambda **_: record)

    for argv in (["stack", "provenance"], ["stack", "provenance", "--json"]):
        assert cli.invoke(app, argv).exit_code == 0, argv


def test_the_human_output_names_the_reason_and_the_action(monkeypatch) -> None:
    dirty = _component(checkout={**_component()["checkout"], "worktree_clean": False})
    monkeypatch.setattr(
        "mq_agent.core.stack_provenance.observe", lambda **_: stack_provenance.build([dirty])
    )

    output = cli.invoke(app, ["stack", "provenance"]).output

    assert "RTP001_DIRTY_WORKTREE" in output
    assert "commit or stash" in output
