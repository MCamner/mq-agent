"""Selection invariants; contract snapshots are test-only, never runtime fallbacks."""

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.skills.route import route_skills


@pytest.fixture
def env(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(Path(__file__).parent / "fixtures/skill_selection", vault)
    (vault / ".mq").mkdir(exist_ok=True)
    vocabulary = {
        "schema": "skill-selection-vocabulary.v1",
        "intents": {
            "implement": ["implement", "bygg"],
            "review": ["review", "audit", "granska"],
            "fix": ["fix"],
            "release": ["release"],
        },
        "domains": {"repo": ["repo", "repot"], "ci": ["ci"], "release": ["release"]},
        "risks": {"secret_exposure": ["secret"], "repo_write": ["implement"]},
        "max_selected_skills": 5,
        "max_optional_skills": 3,
    }
    (vault / ".mq/skill-selection-vocabulary.json").write_text(json.dumps(vocabulary))
    repo = tmp_path / "sample"
    repo.mkdir()
    return repo, vault


def skill(
    repo,
    name,
    *,
    targets=("codex", "claude"),
    discovered=("codex", "claude"),
    **overrides,
):
    p = repo / "skills" / name
    p.mkdir(parents=True)
    (p / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test skill\n---\n")
    profile = dict(
        schema="mq.skill-profile.v1",
        skill=name,
        status="active",
        supported_targets=list(targets),
        scope=["repo"],
        intents=["implement"],
        domains=["repo"],
        risks=[],
        required_for=[],
        supersedes=[],
        description="Test skill",
    )
    profile.update(overrides)
    (p / "skill-profile.json").write_text(json.dumps(profile))
    for target in discovered:
        d = repo / (".agents" if target == "codex" else ".claude") / "skills" / name
        d.parent.mkdir(parents=True, exist_ok=True)
        d.symlink_to(p, target_is_directory=True)
    return p


def run(env, task="implement repo", target="codex"):
    repo, vault = env
    result = route_skills(task, repo, target=target, vault=vault)
    schema = json.loads((vault / "schemas/mq.skill-route.v1.json").read_text())
    Draft202012Validator(schema).validate(result)
    return result


@pytest.mark.parametrize(
    "task,expected",
    [
        ("bygg funktionen", "implement"),
        ("granska repot", "review"),
        ("fix failing CI", "fix"),
        ("prepare release", "release"),
    ],
)
def test_profile(env, task, expected):
    assert expected in run(env, task)["profile"]["intents"]


def test_selection_and_determinism(env):
    skill(env[0], "repo-aware")
    result = run(env)
    assert result["selection_state"] == "complete"
    assert [s["skill"] for s in result["selected"]] == ["repo-aware"]
    assert run(env) == result


def test_audit_supersedes_generic_but_not_for_implementation(env):
    skill(env[0], "repo-aware", intents=["implement", "review"])
    skill(env[0], "repo-audit", intents=["review"], supersedes=["repo-aware"])
    assert [s["skill"] for s in run(env, "audit repo")["selected"]] == ["repo-audit"]
    assert [s["skill"] for s in run(env)["selected"]] == ["repo-aware"]


def test_required_missing_for_both_is_partial(env):
    skill(env[0], "safe", discovered=["codex"], required_for=["secret_exposure"])
    result = run(env, "secret", "both")
    assert result["selection_state"] == "partial"
    assert result["missing_required"] == [{"skill": "safe", "targets": ["claude"]}]
    assert result["selected"][0]["requirement"] == "required"


def test_declared_support_is_not_discovery(env):
    skill(env[0], "safe", discovered=[], required_for=["secret_exposure"])
    result = run(env, "secret")
    assert result["selection_state"] == "partial"
    assert not result["selected"]
    assert any(r["code"] == "SKS004_SKILL_NOT_DISCOVERABLE" for r in result["reasons"])


def test_required_unsupported(env):
    skill(env[0], "safe", targets=["claude"], required_for=["secret_exposure"])
    result = run(env, "secret")
    assert result["selection_state"] == "partial"
    assert any(r["code"] == "SKS009_TARGET_UNSUPPORTED" for r in result["reasons"])


def test_budget_and_required_are_not_optional(env):
    for i in reversed(range(10)):
        skill(env[0], f"skill-{i}")
    assert [s["skill"] for s in run(env)["selected"]] == [
        "skill-0",
        "skill-1",
        "skill-2",
    ]
    for i in range(6):
        skill(env[0], f"safe-{i}", required_for=["secret_exposure"])
    result = run(env, "implement repo secret")
    assert len(result["selected"]) == 6
    assert all(s["requirement"] == "required" for s in result["selected"])
    assert any(
        r["code"] == "SKS007_SELECTION_BUDGET_APPLIED" for r in result["reasons"]
    )


def test_required_cannot_be_superseded(env):
    skill(env[0], "safe", required_for=["secret_exposure"])
    skill(env[0], "replacement", supersedes=["safe"])
    assert "safe" in [s["skill"] for s in run(env, "implement repo secret")["selected"]]


def test_empty_is_not_invalid(env):
    assert run(env, "hello")["selection_state"] == "empty"
    (env[1] / ".mq/skill-selection-vocabulary.json").unlink()
    result = run(env)
    assert result["selection_state"] == "invalid"
    assert result["reasons"][0]["code"] == "SKS001_VOCABULARY_UNAVAILABLE"


@pytest.mark.parametrize(
    "change", ["unknown", "malformed", "missing-skill", "unknown-supersedes"]
)
def test_invalid_profile(env, change):
    p = skill(env[0], "bad")
    if change == "missing-skill":
        (p / "SKILL.md").unlink()
    else:
        data = json.loads((p / "skill-profile.json").read_text())
        if change == "unknown":
            data["risks"] = ["invented"]
        elif change == "unknown-supersedes":
            data["supersedes"] = ["missing"]
        else:
            data["supported_targets"] = "codex"
        (p / "skill-profile.json").write_text(json.dumps(data))
    assert run(env)["selection_state"] == "invalid"


def test_term_boundaries(env):
    assert not run(env, "precise civic device")["profile"]["domains"]


def test_cli_and_explain(env):
    from mq_agent.main import app

    skill(env[0], "repo-aware")
    args = [
        "skills",
        "route",
        "implement repo",
        "--repo",
        str(env[0]),
        "--vault",
        str(env[1]),
    ]
    result = CliRunner().invoke(app, args + ["--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == run(env)
    result = CliRunner().invoke(app, args + ["--explain"])
    assert result.exit_code == 0
    assert "repo-aware" in result.output and "implement" in result.output


def test_supersession_chain_keeps_only_live_superseders(env):
    skill(env[0], "a")
    skill(env[0], "b", supersedes=["a"])
    skill(env[0], "c", supersedes=["b"])
    assert [s["skill"] for s in run(env)["selected"]] == ["a", "c"]


def test_supersession_cycle_is_invalid(env):
    skill(env[0], "a", supersedes=["b"])
    skill(env[0], "b", supersedes=["a"])
    assert run(env)["selection_state"] == "invalid"


def test_optional_both_can_serve_one_target(env):
    skill(env[0], "one", discovered=["codex"])
    result = run(env, target="both")
    assert result["selection_state"] == "complete"
    assert result["selected"][0]["discoverable_targets"] == ["codex"]


def test_profile_copy_mismatch_is_invalid(env):
    skill(env[0], "one")
    copy = env[0] / ".claude/skills/one"
    copy.unlink()
    shutil.copytree(env[0] / "skills/one", copy)
    p = copy / "skill-profile.json"
    data = json.loads(p.read_text())
    data["description"] = "Different profile"
    p.write_text(json.dumps(data))
    assert run(env)["selection_state"] == "invalid"


def test_missing_and_malformed_vocabulary(env):
    p = env[1] / ".mq/skill-selection-vocabulary.json"
    p.write_text("{")
    assert run(env)["reasons"][0]["code"] == "SKS002_VOCABULARY_INVALID"
    p.write_text("{}")
    assert run(env)["selection_state"] == "invalid"


def test_context_pack_renders_without_new_machine_fields(env):
    from mq_agent.tools.context_pack import build_task_pack

    skill(env[0], "repo-aware")
    (env[1] / ".mq/context-selection-vocabulary.json").write_text(
        json.dumps(
            dict(
                schema="context-selection-vocabulary.v1",
                source_heavy_hints=["fix"],
                source_heavy_suppress=[],
                max_codegraph_queries=5,
            )
        )
    )
    result = build_task_pack(
        "implement repo", repo="sample", repos_root=env[0].parent, vault=env[1]
    )
    assert "## Selected skills" in result["content"]
    assert "`repo-aware`" in result["content"]
    assert "selected_skills" not in result and "skill_route" not in result
    assert set(result) == {
        "task",
        "target",
        "repo",
        "relevant_repos",
        "cards",
        "card_metadata",
        "exclusions",
        "codegraph_applied",
        "codegraph_queries",
        "line_count",
        "content",
    }


def test_description_does_not_make_skill_required(env):
    skill(
        env[0],
        "optional",
        description="Required for secret exposure",
        risks=["secret_exposure"],
    )
    assert run(env, "secret")["selected"][0]["requirement"] == "recommended"


def test_cli_partial_exit_and_inventory_profile(env):
    from mq_agent.main import app

    skill(env[0], "safe", discovered=[], required_for=["secret_exposure"])
    common = ["--repo", str(env[0]), "--vault", str(env[1]), "--json"]
    runner = CliRunner()
    result = runner.invoke(app, ["skills", "route", "secret", *common])
    assert result.exit_code == 1
    assert json.loads(result.output)["selection_state"] == "partial"
    result = runner.invoke(app, ["skills", "inventory", *common])
    assert result.exit_code == 0
    assert json.loads(result.output)["entries"][0]["discoverable_targets"] == []
    result = runner.invoke(app, ["skills", "profile", "fix CI", *common])
    assert result.exit_code == 0
    assert json.loads(result.output)["domains"] == ["ci"]


def test_explicit_repos_root_wins_over_current_checkout(env, monkeypatch):
    from mq_agent.skills.inventory import resolve_repo

    root, _ = env
    current = root.parent / "other"
    (current / ".mq").mkdir(parents=True)
    (current / ".mq/repo-contract.json").write_text(json.dumps({"repo": "sample"}))
    monkeypatch.chdir(current)
    assert resolve_repo("sample", root.parent) == root


def test_worktree_uses_declared_repository_name(env):
    root, _ = env
    (root / ".mq").mkdir()
    (root / ".mq/repo-contract.json").write_text(json.dumps({"repo": "declared-repo"}))
    assert run(env)["repo"] == "declared-repo"


def test_published_golden_route_and_explanation_are_one_decision():
    from mq_agent.skills.render import render_route

    repo = Path(__file__).resolve().parents[1]
    vault = repo / "tests/fixtures/skill_selection"
    expected = json.loads((vault / "golden-route.json").read_text())
    first_explain: list[dict] = []
    second_explain: list[dict] = []
    first = route_skills(expected["task"], repo, vault=vault, explain=first_explain)
    second = route_skills(expected["task"], repo, vault=vault, explain=second_explain)
    assert first == second == expected
    assert first_explain == second_explain
    assert {e["skill"] for e in first_explain if e["decision"] == "selected"} == {
        s["skill"] for s in first["selected"]
    }
    assert render_route(first, first_explain) == render_route(second, second_explain)
