import pytest

from mq_agent.tools.github_branch_protection import (
    GITHUB_ACTIONS_APP_ID,
    ApprovalRequired,
    ExistingProtectionError,
    build_protection_payload,
    discover_pr_checks,
    ensure_replace_allowed,
    parse_checks,
    require_apply_approval,
)


class FakeGh:
    def __init__(self, responses):
        self.responses = responses

    def json(self, *args):
        return self.responses[args]


def test_parse_checks_trims_deduplicates_and_sorts():
    assert parse_checks("packaging, Tests,packaging, markdownlint ") == [
        "Tests",
        "markdownlint",
        "packaging",
    ]


def test_discover_pr_checks_uses_latest_pr_and_ignores_pages_jobs():
    gh = FakeGh(
        {
            (
                "pr",
                "list",
                "-R",
                "owner/repo",
                "--state",
                "all",
                "--limit",
                "1",
                "--json",
                "headRefOid",
            ): [{"headRefOid": "abc123"}],
            (
                "api",
                "repos/owner/repo/commits/abc123/check-runs",
            ): {
                "check_runs": [
                    {"name": "Tests", "app": {"slug": "github-actions"}},
                    {"name": "packaging", "app": {"slug": "github-actions"}},
                    {"name": "deploy", "app": {"slug": "github-actions"}},
                    {"name": "external", "app": {"slug": "some-app"}},
                ]
            },
        }
    )

    assert discover_pr_checks(gh, "owner/repo") == ["Tests", "packaging"]


def test_discover_pr_checks_refuses_empty_history():
    gh = FakeGh(
        {
            (
                "pr",
                "list",
                "-R",
                "owner/repo",
                "--state",
                "all",
                "--limit",
                "1",
                "--json",
                "headRefOid",
            ): []
        }
    )

    with pytest.raises(ValueError, match="pull request"):
        discover_pr_checks(gh, "owner/repo")


def test_discover_pr_checks_refuses_a_doubly_reported_context():
    # A workflow with a bare `push:` as well as `pull_request:` runs twice on
    # one SHA. Requiring a name discovered from that surface bakes in an
    # ambiguity GitHub resolves for us, invisibly.
    gh = FakeGh(
        {
            (
                "pr",
                "list",
                "-R",
                "owner/repo",
                "--state",
                "all",
                "--limit",
                "1",
                "--json",
                "headRefOid",
            ): [{"headRefOid": "abc123"}],
            (
                "api",
                "repos/owner/repo/commits/abc123/check-runs",
            ): {
                "check_runs": [
                    {"name": "Tests", "app": {"slug": "github-actions"}},
                    {"name": "markdownlint", "app": {"slug": "github-actions"}},
                    {"name": "markdownlint", "app": {"slug": "github-actions"}},
                ]
            },
        }
    )

    with pytest.raises(ValueError, match="more than once.*markdownlint"):
        discover_pr_checks(gh, "owner/repo")


def test_payload_pins_every_check_to_github_actions():
    # The deprecated `contexts` form sets app_id to null, which lets any app
    # that can post a check run satisfy the context. A read-back shows the same
    # names either way, so this is the only place the difference is visible.
    payload = build_protection_payload(["Tests", "packaging"])

    assert payload["required_status_checks"] == {
        "strict": True,
        "checks": [
            {"context": "Tests", "app_id": GITHUB_ACTIONS_APP_ID},
            {"context": "packaging", "app_id": GITHUB_ACTIONS_APP_ID},
        ],
    }
    assert "contexts" not in payload["required_status_checks"]


def test_payload_matches_the_declared_contract():
    payload = build_protection_payload(["Tests"])

    assert payload["enforce_admins"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False
    # No review requirement on single-maintainer repos: an approval nobody can
    # give blocks every PR. The status checks are the gate.
    assert payload["required_pull_request_reviews"] is None
    assert payload["required_conversation_resolution"] is False


def test_payload_sends_every_nullable_field():
    # A PUT replaces the whole protection object; anything omitted is cleared.
    payload = build_protection_payload([])
    for field in (
        "required_status_checks",
        "required_pull_request_reviews",
        "restrictions",
        "enforce_admins",
        "allow_force_pushes",
        "allow_deletions",
    ):
        assert field in payload, f"{field} would be cleared silently"
    assert payload["required_status_checks"] is None


def test_apply_requires_separate_approval_flag():
    with pytest.raises(ApprovalRequired):
        require_apply_approval(apply=True, approve=False)

    require_apply_approval(apply=True, approve=True)
    require_apply_approval(apply=False, approve=False)


def test_existing_protection_requires_explicit_replace_flag():
    with pytest.raises(ExistingProtectionError):
        ensure_replace_allowed({"protected": True}, replace_existing=False)

    ensure_replace_allowed({"protected": True}, replace_existing=True)
    ensure_replace_allowed({"protected": False}, replace_existing=False)
