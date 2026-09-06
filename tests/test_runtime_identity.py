"""Phase 1: can mq-agent prove which code mq-agent itself is running?

Identity comes from the imported module, its distribution metadata and the
checkout that module lives in — never from the working directory. `mq-agent
docs-audit /some/other/repo` must be judged on the code doing the auditing, the
same rule `runtime_guard.repository_root()` already follows.

Nothing here reaches the network, aggregates a stack, or looks at a release.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from mq_agent.core import runtime_identity

ROOT = Path(__file__).resolve().parents[1]


def _identity(**overrides) -> dict:
    record = runtime_identity.observe_installed()
    record.update(overrides)
    return record


# --- the offline registry now lives in module code ------------------------


# Phase 0 kept this helper in the tests. Provenance embeds runtime identity by
# reference, and the reference resolves from the packaged schemas rather than
# the network — a validator without the registry raises instead of fetching.
def test_the_registry_resolves_both_schemas_without_the_network() -> None:
    validator = runtime_identity.identity_validator()

    validator.validate(_identity())
    with pytest.raises(ValidationError):
        validator.validate({"schema": "mq.runtime-identity.v1"})


def test_the_registry_is_built_from_the_packaged_schemas() -> None:
    registry = runtime_identity.schema_registry()

    for name in ("runtime_identity.schema.json", "stack_provenance.schema.json"):
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert registry.get(schema["$id"]) is not None, name


# --- self identity --------------------------------------------------------


def test_mq_agent_identifies_itself_against_its_own_contract() -> None:
    identity = runtime_identity.observe_installed()

    runtime_identity.identity_validator().validate(identity)
    assert identity["schema"] == "mq.runtime-identity.v1"
    assert identity["component"] == "mq-agent"


def test_the_module_path_is_the_imported_package_not_the_working_directory(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    identity = runtime_identity.observe_installed()

    assert Path(identity["module_path"]).name == "mq_agent"
    assert Path(identity["module_path"]).is_dir()
    assert tmp_path not in Path(identity["module_path"]).parents


# Running inside another repository must not make that repository the runtime's
# source. This is the case runtime_guard's docstring calls out.
def test_another_checkout_is_never_mistaken_for_the_runtime_source(
    tmp_path, monkeypatch
) -> None:
    other = tmp_path / "some-other-repo"
    (other / ".git").mkdir(parents=True)
    monkeypatch.chdir(other)

    identity = runtime_identity.observe_installed()
    checkout = runtime_identity.observe_checkout()

    assert identity["source_path"] != str(other)
    if checkout is not None:
        assert checkout["path"] != str(other)


# --- install type is proven, never guessed --------------------------------


# PEP 610 records how a distribution was installed. An editable install says so
# explicitly, and the url names the checkout it points at.
def test_an_editable_install_is_proven_by_its_direct_url() -> None:
    install_type, source_path = runtime_identity.install_source(
        {"url": "file:///path/to/mq-agent", "dir_info": {"editable": True}}
    )

    assert install_type == "editable"
    assert source_path == "/path/to/mq-agent"


def test_a_wheel_install_is_proven_by_its_archive_url() -> None:
    install_type, source_path = runtime_identity.install_source(
        {"url": "file:///tmp/mq_agent-1.28.0-py3-none-any.whl", "archive_info": {}}
    )

    assert install_type == "wheel"
    assert source_path is None


# A distribution installed from an index carries no direct_url.json. That
# absence does not distinguish pip from pipx from uv tool, so claiming any of
# them would be a guess dressed as a fact.
def test_an_unprovable_install_is_unknown_rather_than_assumed() -> None:
    assert runtime_identity.install_source(None) == ("unknown", None)
    assert runtime_identity.install_source({"url": "file:///x", "dir_info": {}})[0] == "wheel"


def test_a_non_editable_directory_install_is_not_called_editable() -> None:
    install_type, _ = runtime_identity.install_source(
        {"url": "file:///path/to/mq-agent", "dir_info": {"editable": False}}
    )

    assert install_type != "editable"


# --- identity quality -----------------------------------------------------


def test_a_version_and_a_commit_make_a_verified_identity() -> None:
    assert runtime_identity.identity_quality("1.28.0", "abc1234") == "verified"


# A wheel built without commit metadata is a weaker identity, not a broken one.
def test_a_wheel_without_commit_metadata_is_partial() -> None:
    assert runtime_identity.identity_quality("1.28.0", None) == "partial"


def test_a_runtime_with_no_version_at_all_is_unknown() -> None:
    assert runtime_identity.identity_quality(None, None) == "unknown"


# The quality a record claims has to survive its own contract.
@pytest.mark.parametrize(
    ("version", "commit"), [("1.28.0", "abc1234"), ("1.28.0", None), (None, None)]
)
def test_every_quality_level_produces_a_contract_valid_record(version, commit) -> None:
    record = runtime_identity.build_identity(
        version=version, commit=commit, install_type="wheel"
    )

    runtime_identity.identity_validator().validate(record)
    assert record["identity_quality"] == runtime_identity.identity_quality(version, commit)


# --- comparison -----------------------------------------------------------


def test_the_same_commit_matches() -> None:
    assert runtime_identity.installed_matches_checkout("abc1234", "abc1234") is True


# Two builds can carry the same semver, so the version is not what is compared.
def test_the_same_version_at_a_different_commit_does_not_match() -> None:
    assert runtime_identity.installed_matches_checkout("abc1234", "def5678") is False


# null is not false: with nothing to compare against, no comparison was made.
@pytest.mark.parametrize(
    ("installed", "checkout"), [(None, "abc1234"), ("abc1234", None), (None, None)]
)
def test_an_unobserved_side_compares_to_nothing(installed, checkout) -> None:
    assert runtime_identity.installed_matches_checkout(installed, checkout) is None


def test_a_short_commit_matches_the_long_one_it_abbreviates() -> None:
    """Git reports both forms; they are the same commit."""
    assert runtime_identity.installed_matches_checkout(
        "abc1234", "abc1234def5678901234567890123456789012ab"
    ) is True


# --- checkout observation -------------------------------------------------


def test_the_checkout_is_this_repository_when_running_from_it() -> None:
    checkout = runtime_identity.observe_checkout()

    assert checkout is not None, "the test suite runs from an editable checkout"
    assert Path(checkout["path"]) == ROOT
    assert checkout["head"] and len(checkout["head"]) >= 7
    assert isinstance(checkout["worktree_clean"], bool)


def test_a_runtime_with_no_checkout_observes_none(monkeypatch) -> None:
    """An installed wheel has no working tree; that is the canonical case."""
    monkeypatch.setattr(runtime_identity, "repository_root", lambda: None)

    assert runtime_identity.observe_checkout() is None


def test_a_checkout_that_is_not_a_repository_observes_none(tmp_path) -> None:
    assert runtime_identity.observe_checkout(root=tmp_path) is None


# --- the wheel case, without building one ---------------------------------


# Verified for real against a built wheel installed into a clean environment:
# install_type wheel, commit null, quality partial, checkout None, comparison
# None. This reproduces that shape from injected metadata so the suite covers
# it without a build.
def test_an_installed_wheel_identifies_itself_without_a_checkout(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_identity,
        "_direct_url",
        lambda: {"url": "file:///tmp/mq_agent-1.28.0-py3-none-any.whl", "archive_info": {}},
    )
    monkeypatch.setattr(runtime_identity, "repository_root", lambda: None)

    identity = runtime_identity.observe_installed()
    checkout = runtime_identity.observe_checkout()

    runtime_identity.identity_validator().validate(identity)
    assert identity["install_type"] == "wheel"
    assert identity["commit"] is None
    assert identity["source_path"] is None
    assert identity["identity_quality"] == "partial"
    assert checkout is None
    assert runtime_identity.installed_matches_checkout(identity["commit"], None) is None


# The editable install points at checkout B. Standing in checkout A — a real
# repository, not an empty directory — must not make A the runtime's source.
def test_standing_in_another_repository_does_not_change_the_identity(
    tmp_path, monkeypatch
) -> None:
    import subprocess

    other = tmp_path / "checkout-a"
    other.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=other, check=True)
    (other / "f").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=other, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a"],
        cwd=other,
        check=True,
    )
    from_repo = runtime_identity.observe_checkout()

    monkeypatch.chdir(other)
    from_elsewhere = runtime_identity.observe_checkout()

    assert from_elsewhere == from_repo
    assert from_elsewhere is not None
    assert Path(from_elsewhere["path"]) == ROOT


# An unidentifiable runtime says so: no version, no commit, no guess.
def test_a_runtime_without_distribution_metadata_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr(runtime_identity, "package_version", lambda: None)
    monkeypatch.setattr(runtime_identity, "_direct_url", lambda: None)

    identity = runtime_identity.observe_installed()

    runtime_identity.identity_validator().validate(identity)
    assert identity["identity_quality"] == "unknown"
    assert identity["version"] is None and identity["commit"] is None
    assert identity["install_type"] == "unknown"
