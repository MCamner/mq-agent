"""Phase 2: the checkout's own layers — integration and release identity.

Phase 1 answered what the running code is. This answers what the checkout it
came from looks like: how HEAD relates to the trunk, and what the repository
declares and has tagged.

Everything is local. `origin/main` here is the ref this machine already has,
never a fetch — Phase 3 adds explicit remote verification, and until then an
unverified remote is the normal state rather than staleness. Nothing is filled
in from the latest tag: a release identity only gets stronger when it can be
proven.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mq_agent.core import runtime_identity

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    (repo / "file").write_text(message, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


def _integration(root: Path) -> dict:
    """The observation, asserted present so a test can index it."""
    observed = runtime_identity.observe_integration(root)
    assert observed is not None, f"{root} should be a repository"
    return observed


def _release(root: Path) -> dict:
    observed = runtime_identity.observe_release(root)
    assert observed is not None, f"{root} should be a repository"
    return observed


@pytest.fixture()
def repo(tmp_path) -> Path:
    """A repository on main, with an `origin/main` that matches it."""
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _commit(work, "one")
    # A local origin/main, the way a cloned repo has one. Never fetched.
    _git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    return work


# --- integration ----------------------------------------------------------


def test_a_checkout_on_main_and_pushed_is_integrated(repo) -> None:
    integration = _integration(repo)

    assert integration == {
        "head_is_main": True,
        "head_integrated_in_main": True,
        "head_pushed": True,
        "ahead": 0,
        "behind": 0,
        "diverged": False,
    }


def test_a_branch_ahead_of_main_is_not_integrated(repo) -> None:
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "two")

    integration = _integration(repo)

    assert integration["head_is_main"] is False
    assert integration["head_integrated_in_main"] is False
    assert integration["head_pushed"] is False
    assert integration["ahead"] == 1
    assert integration["behind"] == 0
    assert integration["diverged"] is False


# A commit already merged into main is integrated even when HEAD is not main.
def test_a_commit_already_in_main_is_integrated_even_off_main(repo) -> None:
    first = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "two")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "-q", first)

    integration = _integration(repo)

    assert integration["head_is_main"] is False
    assert integration["head_integrated_in_main"] is True
    assert integration["head_pushed"] is True
    assert integration["behind"] == 1


def test_a_diverged_branch_says_so(repo) -> None:
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "theirs")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "ours")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "-q", "feature")

    integration = _integration(repo)

    assert integration["diverged"] is True
    assert integration["ahead"] > 0 and integration["behind"] > 0


# Without an origin/main there is nothing to compare against. Unobserved, not
# false: this is a repository that was never cloned or has no remote yet.
def test_a_repository_with_no_origin_main_reports_null_not_false(tmp_path) -> None:
    work = tmp_path / "local-only"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _commit(work, "one")

    integration = _integration(work)

    assert integration["head_is_main"] is True
    assert integration["head_integrated_in_main"] is True
    assert integration["head_pushed"] is None
    assert integration["ahead"] is None
    assert integration["behind"] is None
    assert integration["diverged"] is None


def test_a_directory_that_is_not_a_repository_observes_nothing(tmp_path) -> None:
    assert runtime_identity.observe_integration(tmp_path) is None


# --- release --------------------------------------------------------------


def test_a_tagged_checkout_reports_its_tag_and_that_tag_s_commit(repo) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "VERSION").write_text("1.28.0\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "version")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "-a", "v1.28.0", "-m", "release: v1.28.0")

    release = _release(repo)

    assert release["declared_version"] == "1.28.0"
    assert release["latest_tag"] == "v1.28.0"
    assert release["tag_commit"] == head
    # Requires the network, so Phase 2 cannot observe it.
    assert release["github_release_tag"] is None


def test_an_untagged_repository_reports_no_tag_rather_than_guessing(repo) -> None:
    release = _release(repo)

    assert release["latest_tag"] is None
    assert release["tag_commit"] is None


def test_a_repository_with_no_version_file_declares_nothing(repo) -> None:
    _git(repo, "tag", "-a", "v0.1.0", "-m", "t")

    release = _release(repo)

    assert release["declared_version"] is None
    assert release["latest_tag"] == "v0.1.0"


# main moving past its last tag is the normal state between releases, not a
# fault, and the tag is never used to fill in what HEAD is.
def test_a_checkout_ahead_of_its_latest_tag_is_not_an_error(repo) -> None:
    _git(repo, "tag", "-a", "v1.0.0", "-m", "t")
    tagged = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, "after the release")

    release = _release(repo)

    assert release["tag_commit"] == tagged
    assert release["tag_commit"] != head
    assert runtime_identity.release_matches_checkout(release, head) is False


# --- comparisons ----------------------------------------------------------


def test_a_tag_on_the_checked_out_commit_matches_it(repo) -> None:
    _git(repo, "tag", "-a", "v1.0.0", "-m", "t")
    head = _git(repo, "rev-parse", "HEAD")

    release = _release(repo)

    assert runtime_identity.release_matches_checkout(release, head) is True


@pytest.mark.parametrize("head", [None, "abc1234"])
def test_an_unobservable_side_compares_to_nothing(repo, head) -> None:
    release = _release(repo)

    assert release["tag_commit"] is None
    assert runtime_identity.release_matches_checkout(release, head) is None


def test_release_compares_against_an_installed_identity(repo) -> None:
    _git(repo, "tag", "-a", "v1.0.0", "-m", "t")
    head = _git(repo, "rev-parse", "HEAD")
    release = _release(repo)

    assert runtime_identity.release_matches_installed(release, head) is True
    assert runtime_identity.release_matches_installed(release, "def5678") is False
    assert runtime_identity.release_matches_installed(release, None) is None


def test_no_release_at_all_compares_to_nothing() -> None:
    assert runtime_identity.release_matches_checkout(None, "abc1234") is None
    assert runtime_identity.release_matches_installed(None, "abc1234") is None


# --- the layers agree with the contract -----------------------------------


def test_the_observed_layers_satisfy_the_provenance_contract(repo) -> None:
    """Each layer must drop straight into a stack-provenance record.

    Validated as a whole document rather than against the extracted component
    subschema: pulling a subschema out of the file loses the `$id` base, and
    the identity reference then resolves against nothing.
    """
    import json

    from jsonschema import Draft202012Validator

    _git(repo, "tag", "-a", "v1.0.0", "-m", "t")
    schema = json.loads((ROOT / "schemas" / "stack_provenance.schema.json").read_text())
    validator = Draft202012Validator(schema, registry=runtime_identity.schema_registry())

    head = _git(repo, "rev-parse", "HEAD")
    release = runtime_identity.observe_release(repo)
    component: dict = {
        "name": "mq-agent",
        "checkout": runtime_identity.observe_checkout(repo),
        "integration": runtime_identity.observe_integration(repo),
        "remote": None,
        "installed": runtime_identity.observe_installed(),
        "running": None,
        "release": release,
        "comparison": {
            "installed_matches_checkout": None,
            "running_matches_installed": None,
            "running_matches_checkout": None,
            "release_matches_checkout": runtime_identity.release_matches_checkout(release, head),
            "release_matches_installed": None,
        },
        "status": "PASS",
        "reasons": [],
    }

    validator.validate(
        {
            "schema": "mq.stack-provenance.v1",
            "generated_at": "2026-09-06T12:00:00+02:00",
            "remote_verified": False,
            "components": [component],
            "summary": {"status": "PASS", "problem_count": 0, "next_action": None},
        }
    )


def test_this_repository_observes_its_own_layers() -> None:
    """The real repo, not a fixture."""
    integration = _integration(ROOT)
    release = _release(ROOT)

    assert integration is not None and release is not None
    assert isinstance(integration["head_integrated_in_main"], bool)
    assert release["declared_version"] == (ROOT / "VERSION").read_text().strip()
    assert release["latest_tag"] and release["latest_tag"].startswith("v")
