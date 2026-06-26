"""Persistence tests for workflow runs (Phase 2).

All tests use an injected tmp ``base_dir`` so state never lands in a real home
directory or in the repo. No tool execution.
"""
from __future__ import annotations

import json

import pytest

from mq_agent.workflows import (
    SCHEMA_ID,
    StepStatus,
    WorkflowStateError,
    WorkflowStatus,
    default_workflows_dir,
    new_run,
    validate_plan,
)
from mq_agent.workflows.storage import WorkflowStore


def _plan(run_id="run_20260626_001", *, steps=None, status="planned"):
    return validate_plan(
        {
            "schema": SCHEMA_ID,
            "run_id": run_id,
            "template": "repo-preflight",
            "task": "Verify repository readiness",
            "repo": "/Users/mansys/macos-scripts",
            "status": status,
            "current_step": None,
            "max_steps": 6,
            "max_replans": 0,
            "steps": steps
            if steps is not None
            else [
                {
                    "id": "s1",
                    "name": "Doctor",
                    "tool": "run_mqlaunch_doctor",
                    "args": {},
                    "depends_on": [],
                    "condition": "always",
                    "approval": "none",
                    "status": "pending",
                    "attempt": 0,
                    "result": None,
                    "error": None,
                }
            ],
        }
    )


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(base_dir=tmp_path / "workflows")


# --- save / load round-trip ------------------------------------------------


def test_save_and_load_round_trip(store):
    run = new_run(_plan())
    store.save_run(run)
    loaded = store.load_run(run.run_id)
    assert loaded.run_id == run.run_id
    assert loaded.status is WorkflowStatus.PLANNED
    assert loaded.plan.steps[0].id == "s1"


def test_save_writes_inside_base_dir_only(store, tmp_path):
    run = new_run(_plan())
    store.save_run(run)
    run_file = store.dir / f"{run.run_id}.json"
    assert run_file.exists()
    assert str(run_file).startswith(str(tmp_path))


def test_save_leaves_no_temp_files(store):
    store.save_run(new_run(_plan()))
    leftovers = [p.name for p in store.dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_updated_at_advances_on_save(store):
    run = new_run(_plan())
    before = run.updated_at
    store.save_run(run)
    assert run.updated_at >= before


# --- corruption ------------------------------------------------------------


def test_corrupt_json_raises_clear_error(store):
    store.dir.mkdir(parents=True, exist_ok=True)
    (store.dir / "run_20260626_001.json").write_text("{not valid json")
    with pytest.raises(WorkflowStateError) as exc:
        store.load_run("run_20260626_001")
    assert "corrupt" in str(exc.value).lower()


def test_missing_run_raises_clear_error(store):
    with pytest.raises(WorkflowStateError):
        store.load_run("run_does_not_exist")


def test_list_skips_corrupt_files(store):
    store.save_run(new_run(_plan(run_id="run_20260626_001")))
    store.dir.joinpath("run_20260626_002.json").write_text("garbage")
    runs = store.list_runs()
    assert [r.run_id for r in runs] == ["run_20260626_001"]


# --- ids / no-overwrite ----------------------------------------------------


def test_two_run_ids_do_not_overwrite(store):
    store.save_run(new_run(_plan(run_id="run_20260626_001")))
    store.save_run(new_run(_plan(run_id="run_20260626_002")))
    assert {r.run_id for r in store.list_runs()} == {
        "run_20260626_001",
        "run_20260626_002",
    }


def test_generate_run_id_increments_after_save(store):
    import datetime as dt

    now = dt.datetime(2026, 6, 26, tzinfo=dt.timezone.utc)
    first = store.generate_run_id(now=now)
    assert first == "run_20260626_001"
    store.save_run(new_run(_plan(run_id=first)))
    second = store.generate_run_id(now=now)
    assert second == "run_20260626_002"


# --- latest ----------------------------------------------------------------


def test_latest_run_points_to_last_saved(store):
    store.save_run(new_run(_plan(run_id="run_20260626_001")))
    store.save_run(new_run(_plan(run_id="run_20260626_002")))
    latest = store.latest_run()
    assert latest is not None
    assert latest.run_id == "run_20260626_002"


def test_latest_run_none_when_empty(store):
    assert store.latest_run() is None


# --- cancel ----------------------------------------------------------------


def test_cancel_run_persists_cancelled_state(store):
    store.save_run(new_run(_plan(status="running")))
    cancelled = store.cancel_run("run_20260626_001")
    assert cancelled.status is WorkflowStatus.CANCELLED
    assert store.load_run("run_20260626_001").status is WorkflowStatus.CANCELLED


# --- secrets never persisted ----------------------------------------------


def test_secrets_sanitized_before_persist(store):
    steps = [
        {
            "id": "s1",
            "name": "Doctor",
            "tool": "run_mqlaunch_doctor",
            "args": {},
            "depends_on": [],
            "condition": "always",
            "approval": "none",
            "status": "passed",
            "attempt": 1,
            "result": {"summary": "ok", "api_key": "sk-LEAK"},
            "error": None,
        }
    ]
    run = new_run(_plan(steps=steps))
    store.save_run(run)
    raw = (store.dir / "run_20260626_001.json").read_text()
    assert "sk-LEAK" not in raw
    assert "***redacted***" in raw


# --- dead-process reconciliation on load -----------------------------------


def test_dead_process_run_reconciled_on_load(store):
    steps = [
        {
            "id": "s1",
            "name": "Doctor",
            "tool": "run_mqlaunch_doctor",
            "args": {},
            "depends_on": [],
            "condition": "always",
            "approval": "none",
            "status": "running",
            "attempt": 1,
            "result": None,
            "error": None,
        }
    ]
    run = new_run(_plan(steps=steps, status="running"))
    run.pid = 2**31 - 1  # dead pid
    store.save_run(run)
    loaded = store.load_run(run.run_id)
    assert loaded.status is WorkflowStatus.PAUSED
    assert loaded.plan.steps[0].status is StepStatus.PENDING


# --- default dir (no repo / Git) -------------------------------------------


def test_default_dir_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    d = default_workflows_dir()
    assert d == tmp_path / "xdg" / "mq-agent" / "workflows"


def test_default_dir_is_outside_any_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    d = default_workflows_dir()
    # Lives under the user state dir, never inside a project/Git working tree.
    assert d.parts[-3:] == ("state", "mq-agent", "workflows")
    assert ".git" not in d.parts


# --- full lifecycle (Definition of Done) -----------------------------------


def test_full_lifecycle_create_save_load_pause_resume_cancel(store):
    import os

    from mq_agent.workflows import cancel, pause, resume

    # create — running, owned by this (live) process so load doesn't reconcile
    run = new_run(_plan(status="running", steps=[
        {
            "id": "s1", "name": "Doctor", "tool": "run_mqlaunch_doctor",
            "args": {}, "depends_on": [], "condition": "always",
            "approval": "none", "status": "running", "attempt": 0,
            "result": None, "error": None,
        }
    ]))
    run.pid = os.getpid()
    # save -> load
    store.save_run(run)
    run = store.load_run(run.run_id)
    assert run.status is WorkflowStatus.RUNNING
    # pause
    pause(run)
    store.save_run(run)
    assert store.load_run(run.run_id).status is WorkflowStatus.PAUSED
    # resume
    resume(run)
    store.save_run(run)
    assert store.load_run(run.run_id).status is WorkflowStatus.RUNNING
    # cancel
    cancel(run)
    store.save_run(run)
    assert store.load_run(run.run_id).status is WorkflowStatus.CANCELLED
