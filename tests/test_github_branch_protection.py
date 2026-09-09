import pytest

from mq_agent.tools.github_branch_protection import (
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


def test_discover_pr_checks_uses_latest_merged_pr_and_ignores_pages_jobs():
    gh = FakeGh(
        {
            (
                "pr",
                "list",
                "-R",
                "owner/repo",
                "--state",
                "merged",
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
                "merged",
                "--limit",
                "1",
                "--json",
                "headRefOid",
            ): []
        }
    )

    with pytest.raises(ValueError, match="merged pull request"):
        discover_pr_checks(gh, "owner/repo")


def test_payload_requires_pr_checks_current_base_and_blocks_destructive_pushes():
    payload = build_protection_payload(["Tests", "packaging"])

    assert payload["required_status_checks"] == {
        "strict": True,
        "contexts": ["Tests", "packaging"],
    }
    assert payload["enforce_admins"] is True
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 0
    assert payload["required_conversation_resolution"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


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
