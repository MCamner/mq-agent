from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.release_cockpit import (
    ReleaseEvidence,
    _stack_preflight_status,
    build_release_cockpit,
    resolve_release_state,
)


def _evidence(**overrides) -> ReleaseEvidence:
    # Annotated so **values keeps its per-field types at the call site; an
    # inferred dict[str, object] makes every keyword argument a type error.
    values: dict[str, Any] = {
        "repo": "mq-agent",
        "path": "/repo",
        "path_exists": True,
        "current_version": "1.24.1",
        "target_version": None,
        "latest_tag": "v1.24.1",
        "latest_tag_type": "tag",
        "latest_tag_target": "abc",
        "head_commit": "abc",
        "origin_main_commit": "abc",
        "branch": "main",
        "clean": True,
        "synced_main": True,
        "release_mode": "pull_request",
        "release_check": "READY",
        "contract_check": "READY",
        "stack_preflight": "UP-TO-DATE",
        "main_ci": "PASS",
        "pull_request": None,
        "github_release": {"published": True, "url": "https://example/release"},
        "unavailable": [],
        "check_evidence": {
            "release": {"blockers": []},
            "contract": {"reason": ""},
            "stack_preflight": {"blockers": []},
            "main_ci": {},
        },
    }
    values.update(overrides)
    return ReleaseEvidence(**values)


def test_idle_requires_no_target_and_aligned_current_release():
    assert resolve_release_state(_evidence()).state == "IDLE"


def test_idle_refuses_version_and_tag_drift():
    result = resolve_release_state(_evidence(latest_tag="v1.23.0"))
    assert result.state == "BLOCKED"
    assert result.blockers[0]["code"] == "VERSION_TAG_MISMATCH"


def test_preflight_ready_requires_target():
    result = resolve_release_state(_evidence(
        target_version="1.25.0",
        stack_preflight="READY",
        github_release={"published": False, "url": None},
    ))
    assert result.state == "PREFLIGHT_READY"


def test_release_state_progression_and_precedence():
    target = {
        "target_version": "1.25.0",
        "stack_preflight": "READY",
        "github_release": {"published": False, "url": None},
    }
    prepared = _evidence(**target, pull_request={
        "number": 12, "url": "https://example/pr/12", "state": "OPEN",
        "review_decision": "REVIEW_REQUIRED", "ci": "PENDING",
        "merge_commit": None,
    })
    assert resolve_release_state(prepared).state == "PREPARED_PR"

    green = _evidence(**target, pull_request={
        "number": 12, "url": "https://example/pr/12", "state": "OPEN",
        "review_decision": "APPROVED", "ci": "PASS", "merge_commit": None,
    })
    assert resolve_release_state(green).state == "PR_GREEN"

    merged = _evidence(**target, current_version="1.25.0", pull_request={
        "number": 12, "url": "https://example/pr/12", "state": "MERGED",
        "review_decision": "APPROVED", "ci": "PASS", "merge_commit": "def",
    })
    assert resolve_release_state(merged).state == "MERGED"

    drifted_merge = _evidence(**target, pull_request=merged.pull_request)
    assert resolve_release_state(drifted_merge).blockers[0]["code"] == "TARGET_VERSION_MISMATCH"

    finalized = _evidence(
        **target,
        current_version="1.25.0",
        latest_tag="v1.25.0",
        latest_tag_target="def",
        pull_request={
            "number": 12, "url": "https://example/pr/12", "state": "MERGED",
            "review_decision": "APPROVED", "ci": "PASS", "merge_commit": "def",
        },
    )
    assert resolve_release_state(finalized).state == "FINALIZED"

    published = _evidence(
        **{**finalized.__dict__, "github_release": {
            "published": True, "url": "https://example/release",
        }}
    )
    assert resolve_release_state(published).state == "PUBLISHED"
    assert resolve_release_state(published, audited=True).state == "AUDITED"


def test_blocked_has_highest_precedence_and_one_action():
    result = resolve_release_state(_evidence(
        target_version="1.25.0", clean=False, stack_preflight="BLOCKED",
    ))
    assert result.state == "BLOCKED"
    assert result.blockers[0]["code"] == "DIRTY_TREE"
    assert result.next_action["label"] == "Clean the working tree"


def test_failed_ci_and_missing_repo_are_bounded_blockers():
    ci = resolve_release_state(_evidence(main_ci="FAIL", target_version="1.25.0"))
    assert ci.blockers[0]["code"] == "CI_FAILED"
    missing = resolve_release_state(_evidence(path_exists=False))
    assert missing.blockers[0]["code"] == "REPO_MISSING"


def test_unavailable_checks_never_resolve_green():
    result = resolve_release_state(_evidence(unavailable=["github"], target_version="1.25.0"))
    assert result.state == "BLOCKED"
    assert any(item["code"] == "EVIDENCE_UNAVAILABLE" for item in result.blockers)


def test_published_target_treats_expected_release_plan_refusals_as_up_to_date(monkeypatch):
    monkeypatch.setattr(
        "mq_agent.tools.release_cockpit._collect_stack_release_plan",
        lambda repo_name, path, target: {
            "current_version": "1.25.0",
            "last_tag": "v1.25.0",
            "go": False,
            "blockers": [
                "no unreleased commits since v1.25.0",
                "target version v1.25.0 is already tagged",
            ],
        },
    )
    status, evidence = _stack_preflight_status("mq-agent", Path("/repo"), "1.25.0")
    assert status == "UP-TO-DATE"
    assert evidence["blockers"]


def test_cockpit_payload_validates_against_schema():
    payload = build_release_cockpit(_evidence(), command="status")
    schema = json.loads(Path("schemas/mq_release_cockpit.schema.json").read_text())
    Draft202012Validator(schema).validate(payload)
    assert payload["schema"] == "mq_release_cockpit.v1"
    assert len([payload["next_action"]]) == 1


def test_ship_status_json_cli(monkeypatch):
    payload = build_release_cockpit(_evidence(), command="status")
    monkeypatch.setattr(
        "mq_agent.tools.release_cockpit.release_cockpit", lambda **kwargs: payload,
    )
    result = CliRunner().invoke(app, ["ship", "status", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["state"] == "IDLE"


def test_ship_audit_exits_nonzero_when_not_audited(monkeypatch):
    payload = build_release_cockpit(
        _evidence(target_version="1.25.0", clean=False), command="audit", audited=True,
    )
    monkeypatch.setattr(
        "mq_agent.tools.release_cockpit.release_cockpit", lambda **kwargs: payload,
    )
    result = CliRunner().invoke(app, ["ship", "audit", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["state"] == "BLOCKED"


# ── Phase 6: compatibility enforcement ─────────────────────────────────────

BLOCKING_COMPATIBILITY: dict[str, Any] = {
    "status": "FAIL",
    "stack_status": "FAIL",
    "blocking": [
        {
            "code": "MQC007_DECLARED_RANGES_DISJOINT",
            "message": "mq-agent declares mcp '<2,>=1.27.1' and mq-mcp declares '<3,>=2'",
        }
    ],
}


def test_compatibility_failure_blocks_the_release():
    result = resolve_release_state(_evidence(compatibility=BLOCKING_COMPATIBILITY))

    assert result.state == "BLOCKED"
    assert [b["code"] for b in result.blockers] == ["COMPATIBILITY_BLOCKED"]
    assert "MQC007_DECLARED_RANGES_DISJOINT" in result.blockers[0]["message"]


def test_compatibility_blocker_points_at_the_compatibility_command():
    result = resolve_release_state(_evidence(compatibility=BLOCKING_COMPATIBILITY))

    assert result.next_action["command"] == "mq-agent stack compatibility --all --json"
    assert result.next_action["requires_human"] is False


@pytest.mark.parametrize("status", ["WARN", "UNAVAILABLE", "PASS"])
def test_only_blocking_findings_stop_a_release(status: str):
    """Unknown is not incompatible: a check that said nothing blocks nothing."""
    result = resolve_release_state(
        _evidence(compatibility={"status": status, "blocking": []})
    )
    assert result.state == "IDLE"


def test_compatibility_status_is_reported_as_evidence():
    payload = build_release_cockpit(
        _evidence(compatibility=BLOCKING_COMPATIBILITY), command="status"
    )
    assert payload["checks"]["compatibility"] == "FAIL"
    evidence = payload["checks"]["evidence"]["compatibility"]
    assert evidence["blocking"] == BLOCKING_COMPATIBILITY["blocking"]
    assert evidence["stack_status"] == "FAIL"


def test_a_stack_failure_elsewhere_is_not_this_repos_verdict():
    """checks.compatibility sits beside repo-scoped checks, so it must be
    repo-scoped: FAIL here alongside an empty blocker list is unreadable."""
    payload = build_release_cockpit(
        _evidence(compatibility={"status": "WARN", "stack_status": "FAIL", "blocking": []}),
        command="status",
    )
    assert payload["checks"]["compatibility"] == "WARN"
    assert payload["checks"]["evidence"]["compatibility"]["stack_status"] == "FAIL"
    assert payload["blockers"] == []
    assert payload["state"] != "BLOCKED"
