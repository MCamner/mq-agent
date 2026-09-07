"""The fingerprint on an execution record is a projection, not an observation.

`runtime_guard` already observes this runtime's identity and validates it
before deciding whether the run may write evidence. If the execution writer
observed it again, the stack would have two producers of the same truth, free
to disagree — and the second one would be reading the checkout at write time,
which is the drift v1.28 exists to expose.

So the fact travels:

    guard observes and validates  →  the same fact is carried  →  projected

The projection is four fields, and it is frozen before the run starts. What the
checkout does afterwards is the checkout's business.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mq_agent.core import runtime_guard, runtime_identity
from mq_agent.tools.execution_outcome import (
    build_execution_outcome,
    project_runtime_fingerprint,
)


def _identity(**overrides: Any) -> dict[str, Any]:
    record = runtime_identity.build_identity(
        version="1.28.0",
        commit="a" * 40,
        install_type="editable",
        source_path="/repo",
        executable="/venv/bin/python",
        module="/repo/mq_agent",
    )
    record.update(overrides)
    return record


# --- exactly four fields ---------------------------------------------------


def test_the_projection_is_the_four_identity_fields() -> None:
    fingerprint = project_runtime_fingerprint(_identity())

    assert set(fingerprint) == {"component", "version", "commit", "identity_quality"}


@pytest.mark.parametrize(
    "local", ["install_type", "started_at", "executable", "module_path", "source_path"]
)
def test_no_local_detail_reaches_the_execution_record(local) -> None:
    """An execution store is not the place for paths on one operator's disk."""
    fingerprint = project_runtime_fingerprint(_identity())

    assert local not in fingerprint


@pytest.mark.parametrize(
    ("version", "commit", "quality"),
    [
        ("1.28.0", "a" * 40, "verified"),
        ("1.28.0", None, "partial"),
        (None, None, "unknown"),
    ],
)
def test_every_quality_level_projects_unchanged(version, commit, quality) -> None:
    identity = runtime_identity.build_identity(
        version=version, commit=commit, install_type="wheel"
    )
    assert identity["identity_quality"] == quality

    fingerprint = project_runtime_fingerprint(identity)

    assert fingerprint == {
        "component": "mq-agent",
        "version": version,
        "commit": commit,
        "identity_quality": quality,
    }


def test_the_projection_observes_nothing(monkeypatch) -> None:
    """A pure function of what it is given. No git, no distribution, no disk."""
    monkeypatch.setattr(
        runtime_identity,
        "observe_installed",
        lambda: pytest.fail("the projection observed the runtime"),
    )

    assert project_runtime_fingerprint(_identity())["commit"] == "a" * 40


def test_a_projected_fingerprint_satisfies_the_execution_contract() -> None:
    """Built and validated by the record's own validator, not by inspection."""
    record = build_execution_outcome(
        runtime="agent",
        task_class="task",
        result="PASS",
        exit_status="ok",
        latency_ms=1,
        runtime_fingerprint=project_runtime_fingerprint(_identity()),
    )

    assert record["runtime_fingerprint"]["identity_quality"] == "verified"


def test_an_unobserved_runtime_leaves_the_field_absent() -> None:
    """Absent means provenance was not observed. It is never written as null."""
    record = build_execution_outcome(
        runtime="agent",
        task_class="task",
        result="PASS",
        exit_status="ok",
        latency_ms=1,
        runtime_fingerprint=None,
    )

    assert "runtime_fingerprint" not in record


# --- the guard carries the fact it established -----------------------------


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    (root / "f").write_text("one\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "one")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def test_an_allowed_verdict_carries_the_identity_it_validated(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(runtime_identity, "observe_installed", _identity)

    verdict = runtime_guard.check(root=_repository(tmp_path))

    assert verdict.allowed is True
    assert verdict.identity == _identity()


def test_a_runtime_with_no_checkout_carries_it_too(monkeypatch) -> None:
    """The released wheel still knows what it is, and still says so."""
    monkeypatch.setattr(runtime_identity, "observe_installed", _identity)
    monkeypatch.setattr(runtime_guard, "repository_root", lambda *a, **k: None)

    verdict = runtime_guard.check()

    assert verdict.allowed is True
    assert verdict.identity is not None


def test_a_refusal_carries_no_identity(tmp_path, monkeypatch) -> None:
    """Nothing runs, so there is nothing to attribute."""
    monkeypatch.setattr(runtime_identity, "observe_installed", _identity)
    root = _repository(tmp_path)
    (root / "f").write_text("edited\n", encoding="utf-8")

    verdict = runtime_guard.check(root=root)

    assert verdict.allowed is False
    assert verdict.identity is None


def test_the_runtime_is_observed_once_per_execution(tmp_path, monkeypatch) -> None:
    """Two observations of the same truth are free to disagree."""
    calls = 0

    def _counted() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _identity()

    monkeypatch.setattr(runtime_identity, "observe_installed", _counted)

    verdict = runtime_guard.check(root=_repository(tmp_path))
    assert verdict.identity is not None
    project_runtime_fingerprint(verdict.identity)

    assert calls == 1


# --- frozen before the run, not read at write time -------------------------


def test_the_fingerprint_does_not_follow_a_moving_checkout(tmp_path, monkeypatch) -> None:
    """The record names the code that started the run.

    Projecting at write time would read whatever the checkout had become by
    then — a record attributing an execution to code that never produced it,
    which is precisely what the fingerprint exists to prevent.
    """
    root = _repository(tmp_path)
    started_from = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()

    def _from_checkout() -> dict[str, Any]:
        return runtime_identity.build_identity(
            version="1.28.0",
            commit=runtime_identity.checkout_head(root),
            install_type="editable",
        )

    monkeypatch.setattr(runtime_identity, "observe_installed", _from_checkout)

    verdict = runtime_guard.check(root=root)
    assert verdict.identity is not None
    fingerprint = project_runtime_fingerprint(verdict.identity)
    assert fingerprint["commit"] == started_from

    # The checkout moves while the run is still going.
    (root / "later").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "two"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
        ).stdout.strip()
        != started_from
    )

    record = build_execution_outcome(
        runtime="agent",
        task_class="task",
        result="PASS",
        exit_status="ok",
        latency_ms=1,
        runtime_fingerprint=fingerprint,
    )

    assert record["runtime_fingerprint"]["commit"] == started_from


# --- the escape stays an escape --------------------------------------------


def test_redirected_stores_are_still_not_guarded(monkeypatch, tmp_path) -> None:
    """Point the evidence somewhere scratch and the production policy does not
    apply — the suite's own escape, unchanged by any of this.

    No identity is established there, so the record carries no fingerprint.
    That is consistent rather than convenient: attribution comes from the
    guard, and a run the guard never judged has nothing to attribute. Absence
    already means "not observed", which is exactly what happened.
    """
    from mq_agent import main

    monkeypatch.setenv("MQ_AGENT_ROUTE_OUTCOMES", str(tmp_path / "route.jsonl"))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "exec.jsonl"))
    monkeypatch.setattr(
        runtime_guard,
        "check",
        lambda *a, **k: pytest.fail("the guard ran for a redirected store"),
    )

    assert main._require_recordable_runtime() is None


# --- end to end ------------------------------------------------------------


def test_a_real_run_records_the_runtime_that_produced_it(tmp_path, monkeypatch) -> None:
    """Drive an entrypoint and read what it wrote.

    The suite redirects both evidence stores, so `production_stores_at_risk()`
    is empty and the guard does not run — which is the escape working, and why
    a scratch record carries no fingerprint. Attribution comes from the guard,
    so a run the guard never judged has none to carry, and the field is absent
    rather than invented.

    To exercise the guarded path without writing to the operator's store, the
    run is told its evidence is production while the file still points at
    `tmp_path`.
    """
    store = tmp_path / "exec.jsonl"
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(store))
    monkeypatch.setenv("MQ_AGENT_TELEMETRY", "on")
    monkeypatch.setattr(
        runtime_guard, "production_stores_at_risk", lambda *a, **k: ("MQ_AGENT_EXECUTION_OUTCOMES",)
    )
    monkeypatch.setattr(runtime_guard, "check", lambda *a, **k: runtime_guard.Verdict(
        allowed=True, identity=_identity()
    ))

    from mq_agent.main import app

    result = CliRunner().invoke(app, ["docs-audit", str(tmp_path), "--json"])
    assert result.exit_code in (0, 1), result.output

    records = [json.loads(line) for line in store.read_text().splitlines() if line]
    assert records, "the run wrote no execution record"
    fingerprint = records[-1].get("runtime_fingerprint")

    assert fingerprint is not None, "a guarded run recorded no runtime"
    assert fingerprint["component"] == "mq-agent"
    assert set(fingerprint) == {"component", "version", "commit", "identity_quality"}
