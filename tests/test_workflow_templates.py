"""Tests for the three fixed workflow templates and the workflow CLI (Phase 3).

No tool execution; templates are validated and instantiated only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.workflows import SCHEMA_ID, validate_plan
from mq_agent.workflows import templates as T
from mq_agent.workflows.cli import workflow_app

runner = CliRunner()
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "workflow-plan.v1.json"
EXPECTED = {"repo-preflight", "review-and-test", "release-ready"}


# --- template inventory ----------------------------------------------------


def test_list_templates_returns_the_three_fixed_templates():
    assert set(T.list_templates()) == EXPECTED


def test_template_name_matches_filename():
    for name in T.list_templates():
        assert T.load_template(name)["template"] == name


# --- contract / safety -----------------------------------------------------


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_template_instantiates_and_validates_against_schema(name):
    jsonschema = pytest.importorskip("jsonschema")
    plan = T.instantiate(name, repo="/Users/mansys/macos-scripts", run_id="run_x")
    assert plan.schema_ == SCHEMA_ID
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(
        instance=plan.model_dump(mode="json", by_alias=True), schema=schema
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_all_template_tools_are_in_the_allowlist(name):
    raw = T.load_template(name)
    used = {s["tool"] for s in raw["steps"]}
    assert used <= T.ALLOWED_TOOLS, f"{name} uses tools outside the allowlist"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_no_template_uses_free_shell(name):
    raw = T.load_template(name)
    assert all(s["tool"] != "shell_exec" for s in raw["steps"])


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_template_has_a_clear_stop_chain(name):
    # Every step after the first depends on a prior step, so a failure stops the
    # chain (combined with the runner's stop_on_failure in Phase 4).
    plan = T.instantiate(name, repo="/tmp/x", run_id="run_x")
    ids_seen: set[str] = set()
    for i, step in enumerate(plan.steps):
        if i > 0:
            assert step.depends_on, f"{name}:{step.id} has no dependency"
        assert all(dep in ids_seen for dep in step.depends_on)
        ids_seen.add(step.id)


# --- per-template structure -----------------------------------------------


def test_repo_preflight_is_a_linear_pass_chain():
    plan = T.instantiate("repo-preflight", repo="/tmp/x", run_id="run_x")
    assert [s.tool for s in plan.steps] == [
        "run_mqlaunch_doctor",
        "run_mqlaunch_selftest",
        "run_mqlaunch_release_check",
    ]
    # release-check only runs if the prior step passed
    assert plan.steps[2].condition.value == "all_deps_passed"
    assert plan.steps[2].depends_on == ["selftest"]


def test_review_and_test_does_not_let_review_block_tests():
    plan = T.instantiate("review-and-test", repo="/tmp/x", run_id="run_x")
    tests_step = next(s for s in plan.steps if s.id == "tests")
    # tests depend on the diff, not on the (advisory) review step
    assert tests_step.depends_on == ["diff"]
    assert "review" not in tests_step.depends_on


def test_release_ready_runs_release_check_last_after_selftest():
    plan = T.instantiate("release-ready", repo="/tmp/x", run_id="run_x")
    assert plan.steps[-1].id == "release_check"
    assert plan.steps[-1].depends_on == ["selftest"]


# --- error handling --------------------------------------------------------


def test_instantiate_unknown_template_raises():
    with pytest.raises(T.TemplateError):
        T.instantiate("nope", repo="/tmp/x", run_id="run_x")


def test_instantiate_rejects_tool_outside_allowlist(monkeypatch):
    monkeypatch.setattr(
        T,
        "load_template",
        lambda name: {
            "template": "evil",
            "task": "t",
            "max_steps": 1,
            "steps": [
                {
                    "id": "s1",
                    "name": "bad",
                    "tool": "shell_exec",
                    "depends_on": [],
                    "condition": "always",
                    "approval": "none",
                }
            ],
        },
    )
    with pytest.raises(T.TemplateError):
        T.instantiate("evil", repo="/tmp/x", run_id="run_x")


# --- CLI -------------------------------------------------------------------


def test_cli_list_json():
    result = runner.invoke(workflow_app, ["list", "--json"])
    assert result.exit_code == 0
    assert set(json.loads(result.stdout)["templates"]) == EXPECTED


def test_cli_show_repo_preflight():
    result = runner.invoke(workflow_app, ["show", "repo-preflight"])
    assert result.exit_code == 0
    raw = json.loads(result.stdout)
    assert raw["template"] == "repo-preflight"
    assert len(raw["steps"]) == 3


def test_cli_show_unknown_template_exits_nonzero():
    result = runner.invoke(workflow_app, ["show", "ghost"])
    assert result.exit_code == 1


def test_cli_plan_produces_valid_plan(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))  # isolate run-id source
    result = runner.invoke(
        workflow_app, ["plan", "repo-preflight", "--repo", "/Users/mansys/macos-scripts"]
    )
    assert result.exit_code == 0
    plan = json.loads(result.stdout)
    assert plan["repo"] == "/Users/mansys/macos-scripts"
    assert plan["run_id"].startswith("run_")
    # round-trips through the contract validator
    validate_plan(plan)


def test_cli_plan_unknown_template_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    result = runner.invoke(workflow_app, ["plan", "ghost", "--repo", "/tmp/x"])
    assert result.exit_code == 1
