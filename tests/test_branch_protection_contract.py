"""Tests for the read-only branch-protection drift check.

Every GitHub interaction is faked. The point of these tests is the comparison
logic, which is where both defect classes live.
"""

import base64
import json

import pytest
import yaml

from mq_agent.tools.branch_protection_contract import (
    GITHUB_ACTIONS_APP_ID,
    compare_check_surface,
    compare_protection,
    declared_for,
    load_contract,
    protection_entry,
    stack_protection_check,
    workflow_direct_branch_mutations,
)

APP = GITHUB_ACTIONS_APP_ID

CONTRACT = {
    "schema": "mq.branch-protection-contract.v1",
    "owner": "MCamner",
    "branch": "main",
    "defaults": {
        "strict": True,
        "enforce_admins": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_approving_reviews": None,
        "required_conversation_resolution": False,
    },
    "repos": {
        "demo": {
            "required_checks": [
                {"name": "test", "app_id": APP},
                {"name": "markdownlint", "app_id": APP},
            ]
        }
    },
}


def protection(checks, *, strict=True, admins=True, force=False, deletions=False,
               conv=False, reviews=None):
    payload = {
        "required_status_checks": {"strict": strict, "checks": checks},
        "enforce_admins": {"enabled": admins},
        "allow_force_pushes": {"enabled": force},
        "allow_deletions": {"enabled": deletions},
        "required_conversation_resolution": {"enabled": conv},
    }
    if reviews is not None:
        payload["required_pull_request_reviews"] = {"required_approving_review_count": reviews}
    return payload


class FakeGh:
    """Returns a canned response per argument tuple; raises for anything else."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def json(self, *args):
        self.calls.append(args)
        value = self.responses.get(args)
        if value is None:
            raise RuntimeError(f"unexpected call: {args}")
        if isinstance(value, Exception):
            raise value
        return value


# ── the contract file itself ───────────────────────────────────────────────


def test_shipped_contract_loads_and_pins_every_check():
    contract = load_contract()
    assert contract["schema"] == "mq.branch-protection-contract.v1"
    assert contract["repos"], "the shipped contract declares no repos"
    for name, repo in contract["repos"].items():
        for check in repo["required_checks"]:
            assert check["app_id"] == APP, f"{name}: {check['name']} is not app-pinned"


def test_shipped_contract_gives_every_exclusion_a_reason():
    # An exclusion without a reason is how a required check quietly goes
    # missing: someone removes it and nobody can say why it was ever out.
    for name, repo in load_contract()["repos"].items():
        for excluded in repo.get("excluded_checks", []):
            assert excluded.get("reason"), f"{name}: {excluded['name']} is excluded with no reason"


def test_load_contract_rejects_a_foreign_schema(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({**CONTRACT, "schema": "something.else"}))
    with pytest.raises(ValueError, match="expected schema"):
        load_contract(path)


def test_load_contract_rejects_a_repo_with_no_required_checks(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({**CONTRACT, "repos": {"demo": {"required_checks": []}}}))
    with pytest.raises(ValueError, match="no required_checks"):
        load_contract(path)


def test_declared_for_merges_the_stack_defaults():
    declared = declared_for(CONTRACT, "demo")
    assert declared["strict"] is True
    assert declared["enforce_admins"] is True
    assert [c["name"] for c in declared["required_checks"]] == ["test", "markdownlint"]


# ── PROTECTION_DRIFT ───────────────────────────────────────────────────────


def test_matching_protection_reports_nothing():
    declared = declared_for(CONTRACT, "demo")
    actual = protection([
        {"context": "test", "app_id": APP},
        {"context": "markdownlint", "app_id": APP},
    ])
    assert compare_protection(declared, actual) == []


def test_an_unpinned_check_is_drift_even_though_the_name_matches():
    # This is what the deprecated `contexts[]` PUT form does: the names look
    # right and app_id is silently null, so any app may satisfy the context.
    declared = declared_for(CONTRACT, "demo")
    actual = protection([
        {"context": "test", "app_id": None},
        {"context": "markdownlint", "app_id": APP},
    ])
    problems = compare_protection(declared, actual)
    assert problems == ["required check 'test' is not pinned to app 15368: any app may satisfy it"]


def test_a_missing_and_an_extra_check_are_both_reported():
    declared = declared_for(CONTRACT, "demo")
    actual = protection([
        {"context": "test", "app_id": APP},
        {"context": "surprise", "app_id": APP},
    ])
    assert compare_protection(declared, actual) == [
        "required check 'markdownlint' is not enforced",
        "'surprise' is enforced but not in the contract",
    ]


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"strict": False}, "strict is False, contract says True"),
        ({"admins": False}, "enforce_admins is False, contract says True"),
        ({"force": True}, "allow_force_pushes is True, contract says False"),
        ({"deletions": True}, "allow_deletions is True, contract says False"),
        ({"conv": True}, "required_conversation_resolution is True, contract says False"),
        # Present-requiring-zero is a different state from absent, and only the
        # second is what "no review requirement" means.
        ({"reviews": 0}, "required approving reviews is 0, contract says None"),
    ],
)
def test_each_relaxed_setting_is_drift(kwargs, expected):
    declared = declared_for(CONTRACT, "demo")
    actual = protection(
        [{"context": "test", "app_id": APP}, {"context": "markdownlint", "app_id": APP}],
        **kwargs,
    )
    assert expected in compare_protection(declared, actual)


# ── CHECK_SURFACE_DRIFT ────────────────────────────────────────────────────


def test_one_run_per_required_context_is_clean():
    declared = declared_for(CONTRACT, "demo")
    runs = [
        {"name": "test", "app": {"id": APP}},
        {"name": "markdownlint", "app": {"id": APP}},
        {"name": "something-else", "app": {"id": 4242}},
    ]
    assert compare_check_surface(declared, runs) == []


def test_a_context_reported_twice_is_drift():
    # A workflow carrying a bare `push:` as well as `pull_request:` runs twice
    # on one SHA. Required checks match on the name and ignore the event, so
    # which run satisfies the requirement is undefined.
    declared = declared_for(CONTRACT, "demo")
    runs = [{"name": "test"}, {"name": "markdownlint"}, {"name": "markdownlint"}]
    assert compare_check_surface(declared, runs) == [
        "context 'markdownlint' was reported 2 times on one commit "
        "(a workflow fires on both push and pull_request)"
    ]


def test_a_required_context_the_pr_never_reports_is_drift():
    # The silent killer: the PR waits forever with nothing to show why.
    declared = declared_for(CONTRACT, "demo")
    assert compare_check_surface(declared, [{"name": "test"}]) == [
        "required context 'markdownlint' was not reported by the sampled pull request"
    ]


def test_an_unclassified_actions_context_is_drift():
    # A gate nobody decided about: it runs on every PR, it can go red, and it
    # blocks nothing. That is how a real check quietly becomes decorative.
    declared = declared_for(CONTRACT, "demo")
    runs = [
        {"name": "test", "app": {"id": APP}},
        {"name": "markdownlint", "app": {"id": APP}},
        {"name": "parity", "app": {"id": APP}},
    ]
    assert compare_check_surface(declared, runs) == [
        "context 'parity' runs on pull requests but the contract neither "
        "requires nor excludes it: it can go red without blocking anything"
    ]


def test_an_excluded_context_is_classified_and_therefore_silent():
    declared = dict(declared_for(CONTRACT, "demo"))
    declared["excluded_checks"] = [{"name": "parity", "reason": "informational"}]
    runs = [
        {"name": "test", "app": {"id": APP}},
        {"name": "markdownlint", "app": {"id": APP}},
        {"name": "parity", "app": {"id": APP}},
    ]
    assert compare_check_surface(declared, runs) == []


def test_a_third_party_check_is_not_ours_to_classify():
    # An external integration posting a check run is not a gate this contract
    # governs, and demanding a decision about it would be noise.
    declared = declared_for(CONTRACT, "demo")
    runs = [
        {"name": "test", "app": {"id": APP}},
        {"name": "markdownlint", "app": {"id": APP}},
        {"name": "some-saas-scanner", "app": {"id": 99999}},
    ]
    assert compare_check_surface(declared, runs) == []


def test_every_reported_actions_context_in_the_shipped_contract_is_classified():
    # The rule the contract states about itself: required or excluded, no
    # third bucket. This is a structural check on the file, not on GitHub.
    contract = load_contract()
    for name, repo in contract["repos"].items():
        required = {c["name"] for c in repo["required_checks"]}
        excluded = {c["name"] for c in repo.get("excluded_checks", [])}
        overlap = required & excluded
        assert not overlap, f"{name}: {sorted(overlap)} is both required and excluded"


def test_a_matrix_context_is_matched_by_its_full_display_name():
    declared = {"required_checks": [{"name": "test (3.11)", "app_id": APP}]}
    assert compare_check_surface(declared, [{"name": "test (3.11)"}]) == []
    # A bare job name matches nothing, which is exactly why it must not be
    # declared that way.
    assert compare_check_surface({"required_checks": [{"name": "test", "app_id": APP}]},
                                 [{"name": "test (3.11)"}, {"name": "test (3.12)"}]) == [
        "required context 'test' was not reported by the sampled pull request"
    ]


# ── WORKFLOW_MUTATION_RISK ────────────────────────────────────────────────


def test_push_to_main_auto_commit_action_is_a_mutation_risk():
    workflow = """
on:
  push:
    branches: [main]
jobs:
  examples:
    steps:
      - uses: stefanzweifel/git-auto-commit-action@v5
"""
    problems = workflow_direct_branch_mutations(workflow, branch="main")
    assert problems == [
        "job 'examples' step 1 uses direct commit action "
        "'stefanzweifel/git-auto-commit-action@v5'"
    ]


def test_push_to_main_shell_git_push_is_a_mutation_risk():
    workflow = """
on:
  push:
    branches: [main]
jobs:
  update:
    steps:
      - run: |
          git add generated/
          git commit -m update
          git push
"""
    problems = workflow_direct_branch_mutations(workflow, branch="main")
    assert problems == [
        "job 'update' step 1 runs git push from a push-to-main workflow"
    ]


def test_create_pull_request_action_is_not_a_direct_main_mutation():
    workflow = """
on:
  push:
    branches: [main]
jobs:
  examples:
    steps:
      - uses: peter-evans/create-pull-request@v7
        with:
          branch: automation/generated-examples
"""
    assert workflow_direct_branch_mutations(workflow, branch="main") == []


def test_direct_commit_action_on_non_main_push_is_outside_main_guard():
    workflow = """
on:
  push:
    branches: [generated]
jobs:
  update:
    steps:
      - uses: stefanzweifel/git-auto-commit-action@v5
"""
    assert workflow_direct_branch_mutations(workflow, branch="main") == []


# ── the whole entry, across all three layers ───────────────────────────────


def runs_response(names):
    return {"check_runs": [{"name": n} for n in names]}


def gh_for(protection_value, pulls=None, runs=None):
    responses = {
        ("api", "repos/MCamner/demo/branches/main/protection"): protection_value,
        ("api", "repos/MCamner/demo/contents/.github/workflows?ref=main"): [],
        ("pr", "list", "-R", "MCamner/demo", "--state", "all", "--limit", "1",
         "--json", "headRefOid"): pulls if pulls is not None else [{"headRefOid": "deadbeef"}],
    }
    if runs is not None:
        responses[("api", "repos/MCamner/demo/commits/deadbeef/check-runs?per_page=100")] = runs
    return FakeGh(responses)


def test_unprotected_branch_is_missing():
    gh = gh_for(RuntimeError("Branch not protected (HTTP 404)"))
    entry = protection_entry(gh, CONTRACT, "demo")
    assert entry["status"] == "MISSING"
    assert "not protected" in entry["reasons"][0]


def test_everything_agreeing_is_a_pass():
    gh = gh_for(
        protection([{"context": "test", "app_id": APP}, {"context": "markdownlint", "app_id": APP}]),
        runs=runs_response(["test", "markdownlint"]),
    )
    entry = protection_entry(gh, CONTRACT, "demo")
    assert entry["status"] == "PASS"
    assert entry["sampled_commit"] == "deadbeef"
    assert entry["reasons"] == []


def test_protection_drift_short_circuits_before_sampling_a_pr():
    # No point reading a PR's check runs when protection is already wrong, and
    # the fake would raise if it were asked.
    gh = gh_for(protection([{"context": "test", "app_id": None},
                            {"context": "markdownlint", "app_id": APP}]))
    entry = protection_entry(gh, CONTRACT, "demo")
    assert entry["status"] == "PROTECTION_DRIFT"
    assert ("api", "repos/MCamner/demo/commits/deadbeef/check-runs?per_page=100") not in gh.calls


def test_direct_main_mutation_short_circuits_before_sampling_pr():
    actual = protection([
        {"context": "test", "app_id": APP},
        {"context": "markdownlint", "app_id": APP},
    ])
    workflow = """
on:
  push:
    branches: [main]
jobs:
  mutate:
    steps:
      - uses: stefanzweifel/git-auto-commit-action@v5
"""
    encoded = base64.b64encode(workflow.encode()).decode()
    gh = FakeGh({
        ("api", "repos/MCamner/demo/branches/main/protection"): actual,
        ("api", "repos/MCamner/demo/contents/.github/workflows?ref=main"): [
            {
                "type": "file",
                "path": ".github/workflows/examples.yml",
            }
        ],
        (
            "api",
            "repos/MCamner/demo/contents/.github/workflows/examples.yml?ref=main",
        ): {"content": encoded},
    })

    entry = protection_entry(gh, CONTRACT, "demo")
    assert entry["status"] == "WORKFLOW_MUTATION_RISK"
    assert "git-auto-commit-action" in entry["reasons"][0]
    assert not any(call and call[0] == "pr" for call in gh.calls)


def test_matching_protection_with_a_moved_check_surface_is_surface_drift():
    gh = gh_for(
        protection([{"context": "test", "app_id": APP}, {"context": "markdownlint", "app_id": APP}]),
        runs=runs_response(["test", "markdownlint", "markdownlint"]),
    )
    entry = protection_entry(gh, CONTRACT, "demo")
    assert entry["status"] == "CHECK_SURFACE_DRIFT"
    assert "reported 2 times" in entry["reasons"][0]


def test_a_repo_with_no_pull_requests_is_blocked_not_passed():
    gh = gh_for(
        protection([{"context": "test", "app_id": APP}, {"context": "markdownlint", "app_id": APP}]),
        pulls=[],
    )
    entry = protection_entry(gh, CONTRACT, "demo")
    assert entry["status"] == "BLOCKED"
    assert "no pull request" in entry["reasons"][0]


def test_the_check_never_writes(tmp_path):
    # The whole contract: this command must not be able to change anything.
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(CONTRACT))
    gh = gh_for(
        protection([{"context": "test", "app_id": APP}, {"context": "markdownlint", "app_id": APP}]),
        runs=runs_response(["test", "markdownlint"]),
    )
    raw = stack_protection_check(gh=gh, contract_path=path)
    assert json.loads(raw)["overall"] == "PASS"
    for call in gh.calls:
        assert "--method" not in call and "-X" not in call
        assert not any(str(a).upper() in ("PUT", "POST", "PATCH", "DELETE") for a in call)


def test_unknown_repo_names_the_known_ones(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(CONTRACT))
    with pytest.raises(ValueError, match="known: demo"):
        stack_protection_check(gh=FakeGh({}), contract_path=path, only="nope")
