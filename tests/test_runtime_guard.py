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
