"""Turn provenance observations into a status, a reason and one next action.

`runtime_identity` observes. This reduces those observations — deterministically
and in one direction only:

    observation → comparison → reason code → status → next action

Three rules hold it up.

**`None` is not `False`.** An unobserved layer produces no reason code, no
degraded status, and no action that assumes someone looked. A repository with
no `origin/main` cannot say whether HEAD was pushed; that is a dimension nobody
could read, not an unpushed commit.

**Status is derived, never asserted.** It is a pure function of the reason
codes, which are a pure function of the observations. Status is therefore never
a second source of truth, and a reason code the reducer does not know would be
a silent pass — so a test requires every code in the contract to have a
severity here.

**Exactly one next action, by declared precedence.** Reinstalling comes before
restarting: restarting a process that runs a stale install starts the same
stale code again.

This module decides nothing. Whether a difference blocks a release belongs to
the release cockpit, and whether it blocks writing evidence belongs to
`runtime_guard`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import runtime_identity

SCHEMA_ID = "mq.stack-provenance.v1"

#: What each reason code does to a status. `PASS` means the code is worth
#: recording and changes nothing — an unverified remote is the normal state of
#: a command that contacts no network, not a finding against the checkout.
SEVERITY: dict[str, str] = {
    "RTP001_DIRTY_WORKTREE": "WARN",
    "RTP002_HEAD_NOT_INTEGRATED": "WARN",
    "RTP003_LOCAL_MAIN_STALE": "WARN",
    "RTP004_REMOTE_NOT_VERIFIED": "PASS",
    "RTP005_CHECKOUT_BEHIND_REMOTE": "WARN",
    "RTP006_INSTALLED_IDENTITY_UNKNOWN": "UNAVAILABLE",
    "RTP007_INSTALLED_CHECKOUT_MISMATCH": "WARN",
    "RTP008_RUNNING_IDENTITY_UNKNOWN": "UNAVAILABLE",
    "RTP009_RUNNING_INSTALLED_MISMATCH": "WARN",
    "RTP010_RUNNING_CHECKOUT_MISMATCH": "WARN",
    "RTP011_RELEASE_VERSION_MISMATCH": "WARN",
    "RTP012_RELEASE_COMMIT_MISMATCH": "WARN",
    "RTP013_RUNTIME_IDENTITY_INVALID": "FAIL",
    "RTP014_REMOTE_UNAVAILABLE": "UNAVAILABLE",
    "RTP015_GIT_PROBE_FAILED": "UNAVAILABLE",
    "RTP016_CHECKOUT_HEAD_MISSING": "UNAVAILABLE",
    "RTP017_CANONICAL_REF_MISSING": "UNAVAILABLE",
}

#: An incomplete picture outranks a single confirmed difference: an identity
#: nobody could read may be hiding more differences than the one that was seen.
_RANK = {"PASS": 0, "WARN": 1, "UNAVAILABLE": 2, "FAIL": 3}

#: Ordered by dependency, not by severity. Reinstalling precedes restarting
#: because a restart re-runs whatever is installed.
NEXT_ACTIONS: tuple[tuple[str, str], ...] = (
    ("RTP013_RUNTIME_IDENTITY_INVALID", "investigate {component}: it reported an identity that is not valid"),
    ("RTP006_INSTALLED_IDENTITY_UNKNOWN", "identify the installed {component}: its distribution metadata could not be read"),
    ("RTP007_INSTALLED_CHECKOUT_MISMATCH", "reinstall {component} from the current checkout"),
    ("RTP008_RUNNING_IDENTITY_UNKNOWN", "ask {component} to report its runtime identity"),
    ("RTP009_RUNNING_INSTALLED_MISMATCH", "restart {component}: it is running code older than what is installed"),
    ("RTP010_RUNNING_CHECKOUT_MISMATCH", "restart {component}: it is not running the checkout's code"),
    ("RTP012_RELEASE_COMMIT_MISMATCH", "check {component}: its latest tag names a different commit than the checkout"),
    ("RTP016_CHECKOUT_HEAD_MISSING", "check {component}: its checkout has no HEAD to identify"),
    ("RTP001_DIRTY_WORKTREE", "commit or stash the changes in {component}'s checkout"),
    ("RTP002_HEAD_NOT_INTEGRATED", "integrate {component}'s HEAD into main, or check out a commit that is"),
    ("RTP003_LOCAL_MAIN_STALE", "update {component}'s checkout: it is behind the main it knows about"),
    ("RTP005_CHECKOUT_BEHIND_REMOTE", "fetch {component}: the verified remote main is not the ref this checkout has"),
    ("RTP014_REMOTE_UNAVAILABLE", "retry {component} with --refresh when the remote is reachable"),
)


def status_for(reasons: list[str]) -> str:
    """The status these reason codes reduce to. Pure, and the only source."""
    worst = "PASS"
    for code in reasons:
        severity = SEVERITY.get(code, "PASS")
        if _RANK[severity] > _RANK[worst]:
            worst = severity
    return worst


def _commit_of(identity: Any) -> str | None:
    if not isinstance(identity, dict):
        return None
    commit = identity.get("commit")
    return commit if isinstance(commit, str) else None


def compare(component: dict[str, Any]) -> dict[str, bool | None]:
    """The five edges. Every one is None unless both sides were observed."""
    checkout = component.get("checkout") or {}
    release = component.get("release")
    head = checkout.get("head") if isinstance(checkout, dict) else None
    installed = _commit_of(component.get("installed"))
    running = _commit_of(component.get("running"))

    return {
        "installed_matches_checkout": runtime_identity.installed_matches_checkout(
            installed, head
        ),
        "running_matches_installed": runtime_identity.installed_matches_checkout(
            running, installed
        ),
        "running_matches_checkout": runtime_identity.installed_matches_checkout(
            running, head
        ),
        "release_matches_checkout": runtime_identity.release_matches_checkout(
            release, head
        ),
        "release_matches_installed": runtime_identity.release_matches_installed(
            release, installed
        ),
    }


def _identity_findings(identity: Any, unknown_code: str) -> list[str]:
    """What one identity layer says about itself. Absent layers say nothing."""
    if identity is None:
        return [unknown_code] if unknown_code == "RTP006_INSTALLED_IDENTITY_UNKNOWN" else []
    if not isinstance(identity, dict):
        return ["RTP013_RUNTIME_IDENTITY_INVALID"]
    if list(runtime_identity.identity_validator().iter_errors(identity)):
        return ["RTP013_RUNTIME_IDENTITY_INVALID"]
    if identity.get("identity_quality") == "unknown":
        return [unknown_code]
    return []


def findings(component: dict[str, Any], comparison: dict[str, bool | None]) -> list[str]:
    """Every reason code the observations support, and no others.

    Only `False` produces a finding. `None` is silence: nobody looked.
    """
    reasons: list[str] = []
    checkout = component.get("checkout")
    if isinstance(checkout, dict):
        if checkout.get("worktree_clean") is False:
            reasons.append("RTP001_DIRTY_WORKTREE")
        if checkout.get("head") is None:
            reasons.append("RTP016_CHECKOUT_HEAD_MISSING")

    integration = component.get("integration")
    if isinstance(integration, dict):
        if integration.get("head_integrated_in_main") is False:
            reasons.append("RTP002_HEAD_NOT_INTEGRATED")
        behind = integration.get("behind")
        if isinstance(behind, int) and behind > 0:
            reasons.append("RTP003_LOCAL_MAIN_STALE")

    # Three states, kept apart. Never asked is silence. Asked and unreachable is
    # an observation nobody could make. Confirmed and different is a finding.
    #
    # The confirmed remote is one half of the comparison; the other is a ref
    # this machine has. A checkout without `origin/main` — what `actions/checkout`
    # produces — never observed that half, and `SHA != None` is an absence, not
    # a disagreement.
    remote = component.get("remote")
    if isinstance(remote, dict) and remote.get("verification_attempted") is True:
        confirmed = remote.get("remote_origin_main")
        known_locally = remote.get("local_origin_main")
        if not remote.get("verified"):
            reasons.append("RTP014_REMOTE_UNAVAILABLE")
        elif (
            confirmed is not None
            and known_locally is not None
            and confirmed != known_locally
        ):
            reasons.append("RTP005_CHECKOUT_BEHIND_REMOTE")

    reasons += _identity_findings(
        component.get("installed"), "RTP006_INSTALLED_IDENTITY_UNKNOWN"
    )
    reasons += _identity_findings(
        component.get("running"), "RTP008_RUNNING_IDENTITY_UNKNOWN"
    )

    for field, code in (
        ("installed_matches_checkout", "RTP007_INSTALLED_CHECKOUT_MISMATCH"),
        ("running_matches_installed", "RTP009_RUNNING_INSTALLED_MISMATCH"),
        ("running_matches_checkout", "RTP010_RUNNING_CHECKOUT_MISMATCH"),
    ):
        if comparison[field] is False:
            reasons.append(code)

    # A tag the checkout has moved past is ordinary progress between releases,
    # not a finding. A tag that is not in this history at all is a genuine
    # disagreement about which code the release names.
    release = component.get("release")
    if (
        comparison["release_matches_checkout"] is False
        and isinstance(release, dict)
        and release.get("tag_reachable_from_head") is False
    ):
        reasons.append("RTP012_RELEASE_COMMIT_MISMATCH")

    # Stable and unique, in contract order.
    return sorted(set(reasons), key=lambda code: list(SEVERITY).index(code))


def assess(component: dict[str, Any]) -> dict[str, Any]:
    """One component with its comparisons, reasons and status filled in."""
    comparison = compare(component)
    reasons = findings(component, comparison)
    return {
        **component,
        "comparison": comparison,
        "reasons": reasons,
        "status": status_for(reasons),
    }


def next_action(components: list[dict[str, Any]]) -> str | None:
    """Exactly one action, or none. Never one that assumes an unmade check."""
    for code, template in NEXT_ACTIONS:
        for component in components:
            if code in component.get("reasons", []):
                return template.format(component=component.get("name", "the component"))
    return None


def build(
    components: list[dict[str, Any]], *, remote_verified: bool = False
) -> dict[str, Any]:
    """Assess every component and reduce them to one record."""
    assessed = [assess(component) for component in components]
    return {
        "schema": SCHEMA_ID,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "remote_verified": remote_verified,
        "components": assessed,
        "summary": {
            "status": status_for(
                [code for component in assessed for code in component["reasons"]]
            ),
            "problem_count": sum(1 for c in assessed if c["status"] != "PASS"),
            "next_action": next_action(assessed),
        },
    }


def observe_component(
    name: str = runtime_identity.COMPONENT, *, refresh: bool = False
) -> dict[str, Any]:
    """Observe every layer of one component. Contacts a remote only if asked."""
    return {
        "name": name,
        "checkout": runtime_identity.observe_checkout(),
        "integration": runtime_identity.observe_integration(),
        "remote": runtime_identity.observe_remote(refresh=refresh),
        "installed": runtime_identity.observe_installed(),
        # A CLI has no long-lived process. Phase 4 gives mq-mcp one to report.
        "running": None,
        "release": runtime_identity.observe_release(),
    }


def observe(*, refresh: bool = False) -> dict[str, Any]:
    """Provenance for this runtime. Read-only, and network-free unless asked.

    `refresh` makes an observation fresher; it does not change how observations
    are reduced. A finding means the same thing whether `origin/main` came from
    disk or was confirmed against the remote.
    """
    component = observe_component(refresh=refresh)
    remote = component.get("remote") or {}
    return build([component], remote_verified=bool(remote.get("verified")))
