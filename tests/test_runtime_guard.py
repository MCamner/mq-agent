"""A run whose code cannot be identified must not become production evidence.

`tests/conftest.py` already made this a property for the suite, and says why it
is only half the job:

    Keeping test runs out of it was a discipline — remember to set the variable
    — and a discipline is not a property. [...] A manual `docs-audit` still
    needs the variable set by hand; the suite is the half that can be enforced.

This is the other half. Observations are placed in eras by commit
(`mq_agent/tools/analysis_cohort.py`), so an observation produced by a dirty
working tree, or by a commit that is on no known branch, belongs to no era and
cannot be compared with anything. It is not weak evidence; it is unattributable
evidence, and the store has no way to tell it apart afterwards.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mq_agent.core import runtime_guard


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )


@pytest.fixture()
def integrated(tmp_path) -> Path:
    """A clean checkout whose HEAD is an ancestor of the canonical ref."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "file.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-qm", "one")
    # No network: a local ref standing in for what the remote was last seen at.
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def test_a_clean_integrated_checkout_may_record(integrated) -> None:
    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is True
    assert verdict.reason is None


def test_a_dirty_worktree_may_not_record(integrated) -> None:
    (integrated / "file.txt").write_text("edited\n", encoding="utf-8")

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is False
    assert verdict.reason == "dirty-worktree"


def test_an_untracked_file_is_also_dirt(integrated) -> None:
    # `--porcelain` reports it, and it can carry code the run imports.
    (integrated / "extra.py").write_text("x = 1\n", encoding="utf-8")

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is False
    assert verdict.reason == "dirty-worktree"


def test_a_commit_that_is_on_no_known_branch_may_not_record(integrated) -> None:
    (integrated / "file.txt").write_text("two\n", encoding="utf-8")
    _git(integrated, "commit", "-aqm", "two")

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is False
    assert verdict.reason == "unintegrated-head"


def test_a_missing_canonical_ref_is_not_a_pass(integrated) -> None:
    # Fail closed. Unable to check is not the same as checked and fine.
    _git(integrated, "update-ref", "-d", "refs/remotes/origin/main")

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is False
    assert verdict.reason == "no-canonical-ref"


def test_an_unreadable_repository_is_not_a_pass(tmp_path) -> None:
    # A directory that claims to be a repository and is not. The probe fails,
    # so the run cannot show where its code came from.
    root = tmp_path / "broken"
    (root / ".git").mkdir(parents=True)

    verdict = runtime_guard.check(root=root)

    assert verdict.allowed is False
    assert verdict.reason in {"git-probe-failed", "no-head"}


def test_an_installed_copy_outside_any_checkout_may_record(monkeypatch) -> None:
    # The released wheel is the canonical case, not the suspicious one: there is
    # no working tree to be dirty, and its code is whatever was published.
    # Refusing here would brick every installed copy of the tool.
    monkeypatch.setattr(runtime_guard, "repository_root", lambda *a, **k: None)

    verdict = runtime_guard.check()

    assert verdict.allowed is True
    assert verdict.reason is None


def test_a_directory_that_is_not_a_checkout_resolves_to_no_repository(tmp_path) -> None:
    # `.git` absent is an installed copy; the guard must not go looking further
    # up the filesystem for someone else's repository.
    assert runtime_guard.repository_root(tmp_path / "a" / "b" / "c" / "mod.py") is None


def test_the_repository_root_is_the_one_the_running_code_lives_in() -> None:
    # Not the current working directory. `mq-agent docs-audit /some/other/repo`
    # must be judged on the code that is running, never on the repo it audits.
    root = runtime_guard.repository_root()

    assert root == Path(runtime_guard.__file__).resolve().parents[2]


# --- what the guard is protecting -----------------------------------------


def test_the_default_stores_are_what_makes_a_run_worth_blocking(monkeypatch) -> None:
    monkeypatch.delenv("MQ_AGENT_ROUTE_OUTCOMES", raising=False)
    monkeypatch.delenv("MQ_AGENT_EXECUTION_OUTCOMES", raising=False)

    assert set(runtime_guard.production_stores_at_risk()) == {
        "MQ_AGENT_ROUTE_OUTCOMES",
        "MQ_AGENT_EXECUTION_OUTCOMES",
    }


def test_a_redirected_run_risks_nothing_and_is_not_blocked(monkeypatch, tmp_path) -> None:
    # This is the whole escape, and it is the same one the suite uses. Point the
    # stores somewhere else and the run cannot corrupt production evidence, so
    # there is nothing left for the guard to protect.
    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(tmp_path / "r.jsonl"))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "e.jsonl"))

    assert runtime_guard.production_stores_at_risk() == ()


def test_turning_telemetry_off_still_leaves_the_route_store_exposed(
    monkeypatch, tmp_path
) -> None:
    # MQ_AGENT_TELEMETRY only silences execution outcomes. A routed run would
    # still append to the operator's route store, so it is still at risk.
    monkeypatch.setenv("MQ_AGENT_TELEMETRY", "off")
    monkeypatch.delenv("MQ_AGENT_ROUTE_OUTCOMES", raising=False)
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "e.jsonl"))

    assert runtime_guard.production_stores_at_risk() == ("MQ_AGENT_ROUTE_OUTCOMES",)


# --- the entrypoints ------------------------------------------------------
#
# Same shape as the missing API key in #255: a condition that means the run must
# not happen is checked before the record opens, so a refused run leaves no
# trace of an execution that never started.

from typer.testing import CliRunner  # noqa: E402

from mq_agent.main import app  # noqa: E402

cli = CliRunner()

ENTRYPOINTS = [
    (["docs-audit", "."], "mq_agent.agents.docs_agent.DocsAgent.audit"),
    (["audit", "."], "mq_agent.agents.audit_agent.AuditAgent.run"),
    (["release-check", "."], "mq_agent.agents.release_agent.ReleaseAgent.run_check"),
    (["fix-ci", "."], "mq_agent.agents.ci_agent.CIAgent.diagnose"),
    (["signal", "."], "mq_agent.agents.signal_agent.SignalAgent.run"),
    (["swarm", "audit", "."], "mq_agent.core.swarm.SwarmRunner.run"),
]


@pytest.fixture()
def blocked(monkeypatch):
    """A runtime that may not record, with the production stores exposed."""
    monkeypatch.setattr(
        runtime_guard, "production_stores_at_risk", lambda *a, **k: ("MQ_AGENT_ROUTE_OUTCOMES",)
    )
    monkeypatch.setattr(
        runtime_guard,
        "check",
        lambda *a, **k: runtime_guard.Verdict(
            allowed=False, reason="dirty-worktree", detail="3 uncommitted change(s)"
        ),
    )
    monkeypatch.setattr("mq_agent.tools.signal_tools.signal_available", lambda: True)


@pytest.mark.parametrize(("argv", "never_called"), ENTRYPOINTS)
def test_an_unverifiable_runtime_never_starts_the_run(
    blocked, monkeypatch, argv, never_called
) -> None:
    def _must_not_run(*args, **kwargs):
        raise AssertionError("the run started from an unverifiable runtime")

    monkeypatch.setattr(never_called, _must_not_run)

    result = cli.invoke(app, argv)

    assert result.exit_code == 1
    assert "dirty-worktree" in result.output or "uncommitted" in result.output


@pytest.mark.parametrize(("argv", "never_called"), ENTRYPOINTS)
def test_a_run_that_risks_no_production_evidence_is_not_blocked(
    monkeypatch, argv, never_called
) -> None:
    # The stores are redirected — the suite's own fixture does it — so the guard
    # has nothing to protect and must stay out of the way even from a dirty tree.
    monkeypatch.setattr(
        runtime_guard,
        "check",
        lambda *a, **k: runtime_guard.Verdict(allowed=False, reason="dirty-worktree"),
    )
    reached = {}

    def _record(*args, **kwargs):
        reached["ran"] = True
        raise RuntimeError("far enough")

    monkeypatch.setattr("mq_agent.main._client", lambda: None)
    monkeypatch.setattr(never_called, _record)

    cli.invoke(app, argv)

    assert reached.get("ran") is True


# --- can this process say what it is? --------------------------------------
#
# Not a comparison. The obvious gate — refuse when the installed commit differs
# from the checkout's — turns out to be unreachable here, and the module
# docstring says why: an editable install reads its commit from the same tree
# as the checkout, and a wheel has no checkout to differ from. Gating on it
# would be a check that can never fire.
#
# What remains is narrower and does happen: a runtime that cannot express an
# internally valid identity has no business writing evidence about itself.
# Absence of knowledge is allowed; contradiction is not.


@pytest.mark.parametrize("quality", ["verified", "partial", "unknown"])
def test_any_honest_identity_may_record(integrated, monkeypatch, quality) -> None:
    """A wheel carries no commit and says so. That is an answer, not a fault."""
    from mq_agent.core import runtime_identity

    record = runtime_identity.build_identity(
        version=None if quality == "unknown" else "1.28.0",
        commit="a" * 40 if quality == "verified" else None,
        install_type="unknown",
    )
    monkeypatch.setattr(runtime_identity, "observe_installed", lambda: record)

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is True


def test_a_self_identity_that_fails_its_own_contract_may_not_record(
    integrated, monkeypatch
) -> None:
    from mq_agent.core import runtime_identity

    monkeypatch.setattr(runtime_identity, "observe_installed", lambda: {"banana": 42})

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is False
    assert verdict.reason == "identity-invalid"


def test_an_unreadable_identity_is_not_permission(integrated, monkeypatch) -> None:
    """A broken observation is not a reason to take down the run it was
    protecting — and not permission either. The question went unanswered."""
    from mq_agent.core import runtime_identity

    def _explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(runtime_identity, "observe_installed", _explode)

    verdict = runtime_guard.check(root=integrated)

    assert verdict.allowed is False
    assert verdict.reason == "identity-unreadable"


def test_the_identity_question_is_asked_of_a_runtime_with_no_checkout(
    monkeypatch,
) -> None:
    """A released wheel has no working tree, and still has to be able to say
    what it is."""
    from mq_agent.core import runtime_identity

    monkeypatch.setattr(runtime_guard, "repository_root", lambda *a, **k: None)
    monkeypatch.setattr(runtime_identity, "observe_installed", lambda: {"banana": 42})

    verdict = runtime_guard.check()

    assert verdict.allowed is False
    assert verdict.reason == "identity-invalid"


def test_the_guard_gates_on_no_comparison_between_layers() -> None:
    """Neither absent gate may come back by accident.

    Two decisions, one mechanism, and two different reasons. `RTP007` is not
    gated on because the signal is unreachable for mq-agent, so the gate could
    never legitimately fire. `RTP010` is reachable and a gate would fire — but
    the dependency cone is empty, so every refusal would be unrelated to the
    execution being protected. Both are recorded in
    `docs/RUNTIME_PROVENANCE.md`.

    Read as names the code actually references, not as words in the file — the
    docstring explains at length why these are not gated on here, and a text
    search would fail on the very explanation that keeps them out.

    String constants count, and prose does not. A comparison is a dict keyed by
    these names, so the realistic way either gate returns is
    `component["comparison"]["running_matches_checkout"]` — an exact key, which
    an attribute-and-name scan reads straight past. Docstrings are excluded so
    the explanation stays sayable.
    """
    import ast

    tree = ast.parse(Path(runtime_guard.__file__).read_text(encoding="utf-8"))
    prose = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    referenced = (
        {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        | {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in prose
        }
    )

    assert "installed_matches_checkout" not in referenced
    assert "running_matches_checkout" not in referenced
    assert "observe_mq_mcp" not in referenced
    assert "compare" not in referenced


# --- a revision the contract cannot express is absent, not coerced ---------


@pytest.mark.parametrize(
    ("vcs", "revision"),
    [
        # The one that slipped through: seven characters, all valid hex, and
        # not a commit. A pattern cannot tell it from an abbreviated SHA — only
        # the recorded system can, so the system is what gets checked. The
        # earlier test missed this by picking a revision too short to match.
        ("svn", "1234567"),
        ("svn", "deadbee"),
        ("svn", "4721"),
        ("bzr", "abcdef1"),
        ("hg", "a" * 40),
        (None, "abcdef1"),
        ("", "abcdef1"),
    ],
)
def test_only_git_records_a_commit_this_contract_can_carry(vcs, revision) -> None:
    from mq_agent.core import runtime_identity

    assert (
        runtime_identity.direct_url_commit(
            {"url": "x", "vcs_info": {"vcs": vcs, "commit_id": revision}}
        )
        is None
    )


@pytest.mark.parametrize("revision", ["not-a-sha", "ABCDEF1", "r99", "", "abcdef", "g" * 8])
def test_a_git_revision_that_is_not_an_object_name_is_absent(revision) -> None:
    from mq_agent.core import runtime_identity

    assert (
        runtime_identity.direct_url_commit(
            {"url": "x", "vcs_info": {"vcs": "git", "commit_id": revision}}
        )
        is None
    )


@pytest.mark.parametrize("revision", ["abcdef1", "a" * 40, "0123456789abcdef"])
def test_a_git_object_name_passes_through_unchanged(revision) -> None:
    """A rule that only ever says no is not a rule."""
    from mq_agent.core import runtime_identity

    assert (
        runtime_identity.direct_url_commit(
            {"url": "x", "vcs_info": {"vcs": "git", "commit_id": revision}}
        )
        == revision
    )


def test_an_exact_match_means_exact(monkeypatch) -> None:
    """`$` also matches before a trailing newline, so `match` was not exact."""
    from mq_agent.core import runtime_identity

    assert runtime_identity.usable_commit("abcdef1\n") is None
    assert runtime_identity.usable_commit(" abcdef1") is None
    assert runtime_identity.usable_commit("abcdef1") == "abcdef1"


def test_a_subversion_install_is_partial_rather_than_invalid() -> None:
    from mq_agent.core import runtime_identity

    identity = runtime_identity.build_identity(
        version="1.28.0",
        commit=runtime_identity.direct_url_commit(
            {"url": "x", "vcs_info": {"vcs": "svn", "commit_id": "1234567"}}
        ),
        install_type="unknown",
    )

    runtime_identity.identity_validator().validate(identity)
    assert identity["identity_quality"] == "partial"
    assert identity["commit"] is None
