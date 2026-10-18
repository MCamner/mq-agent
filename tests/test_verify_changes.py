"""Real Git/child-process tests for bounded, change-specific verification."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.verify_changes import check_receipt, verify


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    git(tmp_path, "config", "user.name", "Fixture")
    (tmp_path / ".mq").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/a.py").write_text("value = 1\n")
    (tmp_path / "tests/check.sh").write_text("#!/bin/bash\nexit 0\n")
    config = {"schema": "mq.verification-config.v1", "checks": [
        {"id": "unit", "runner": "bash", "targets": ["tests/check.sh"],
         "paths": ["src/*", "tests/*", ".mq/verification.json"], "timeout_seconds": 2}
    ]}
    (tmp_path / ".mq/verification.json").write_text(json.dumps(config))
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "fixture")
    return tmp_path


def change(repo: Path) -> None:
    (repo / "src/a.py").write_text("value = 2\n")


def test_select_run_and_validate_receipt(repo):
    change(repo)
    plan = verify(repo, plan_only=True)
    assert plan["status"] == "PLAN"
    assert [c["id"] for c in plan["checks"]] == ["unit"]
    assert check_receipt(repo)["status"] == "MISSING"
    result = verify(repo)
    assert result["status"] == "PASS"
    assert result["checks"][0]["exit_code"] == 0
    assert check_receipt(repo)["status"] == "PASS"
    (repo / "src/a.py").write_text("value = 3\n")
    assert check_receipt(repo)["status"] == "STALE"


def test_staged_untracked_deleted_and_renamed_files(repo):
    git(repo, "mv", "src/a.py", "src/b.py")
    (repo / "src/new.py").write_text("new = True\n")
    result = verify(repo, plan_only=True)
    assert set(result["changed_files"]) == {"src/a.py", "src/b.py", "src/new.py"}


def test_unknown_file_never_passes(repo):
    change(repo)
    (repo / "unknown.txt").write_text("uncovered")
    result = verify(repo)
    assert result["status"] == "INCOMPLETE"
    assert result["uncovered_files"] == ["unknown.txt"]
    assert check_receipt(repo)["status"] == "INCOMPLETE"


def test_failed_check_never_passes(repo):
    change(repo)
    (repo / "tests/check.sh").write_text("exit 9\n")
    result = verify(repo)
    assert result["status"] == "FAIL"
    assert result["checks"][0]["exit_code"] == 9
    assert check_receipt(repo)["status"] == "FAIL"


def test_timeout_kills_check(repo):
    change(repo)
    (repo / "tests/check.sh").write_text("sleep 20\n")
    config_path = repo / ".mq/verification.json"
    config = json.loads(config_path.read_text())
    config["checks"][0]["timeout_seconds"] = 1
    config_path.write_text(json.dumps(config))
    result = verify(repo)
    assert result["status"] == "FAIL"
    assert result["checks"][0]["status"] == "TIMEOUT"


def test_changes_during_execution_make_receipt_stale(repo):
    change(repo)
    (repo / "tests/check.sh").write_text("printf changed > src/a.py\n")
    assert verify(repo)["status"] == "STALE"
    assert check_receipt(repo)["status"] == "STALE"


def test_unchanged_test_and_index_changes_invalidate_receipt(repo):
    change(repo)
    assert verify(repo)["status"] == "PASS"
    git(repo, "add", "src/a.py")
    assert check_receipt(repo)["status"] == "STALE"
    assert verify(repo)["status"] == "PASS"
    (repo / "tests/check.sh").write_text("exit 1\n")
    assert check_receipt(repo)["status"] == "STALE"


def test_base_revision_checks_committed_changes(repo):
    change(repo)
    git(repo, "commit", "-qam", "change")
    assert verify(repo)["status"] == "NO_CHANGES"
    assert verify(repo, base="HEAD~1")["status"] == "PASS"
    assert check_receipt(repo, base="HEAD~1")["status"] == "PASS"
    assert check_receipt(repo)["status"] == "STALE"


def test_output_is_not_stored_in_receipt(repo):
    change(repo)
    (repo / "tests/check.sh").write_text("echo PRIVATE-STDOUT; echo PRIVATE-STDERR >&2\n")
    result = verify(repo)
    assert result["status"] == "PASS"
    assert "PRIVATE-" not in json.dumps(result)
    assert "PRIVATE-" not in json.dumps(check_receipt(repo))


@pytest.mark.parametrize("runner,targets", [("shell", ["echo bad"]), ("bash", ["../outside.sh"]), ("pytest", ["-c"] )])
def test_rejects_unapproved_runners_and_escaping_targets(repo, runner, targets):
    p = repo / ".mq/verification.json"
    config = json.loads(p.read_text())
    config["checks"][0].update(runner=runner, targets=targets)
    p.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        verify(repo)


def test_cli_json_and_exit_status(repo):
    from mq_agent.main import app
    change(repo)
    runner = CliRunner()
    result = runner.invoke(app, ["verify-changes", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "PASS"
    (repo / "tests/check.sh").write_text("exit 3\n")
    result = runner.invoke(app, ["verify-changes", str(repo), "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "FAIL"
    result = runner.invoke(app, ["verify-changes", str(repo), "--base", "absent", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_receipt_checksum_detects_corruption(repo):
    change(repo)
    verify(repo)
    receipt = repo / ".git/mq-verification/receipt.json"
    data = json.loads(receipt.read_text())
    data["checks"][0]["exit_code"] = 42
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="checksum"):
        check_receipt(repo)


def test_external_symlink_is_recorded_but_not_followed(repo, tmp_path):
    outside = repo.parent / (repo.name + "-external")
    outside.write_text("external dependency")
    (repo / "src/link").symlink_to(outside)
    assert verify(repo)["status"] == "PASS"
    outside.write_text("contents outside receipt scope")
    assert check_receipt(repo)["status"] == "PASS"


def test_plan_rejects_multiple_scripts_for_bash_syntax(repo):
    p = repo / ".mq/verification.json"
    config = json.loads(p.read_text())
    config["checks"][0].update(runner="bash-syntax", targets=["tests/check.sh", "src/a.py"])
    p.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="one script"):
        verify(repo, plan_only=True)


def test_linked_worktree_gets_its_own_receipt(repo, tmp_path):
    linked = repo.parent / (repo.name + "-linked")
    git(repo, "worktree", "add", "--detach", str(linked))
    change(repo)
    assert verify(repo)["status"] == "PASS"
    assert check_receipt(linked)["status"] == "MISSING"
    change(linked)
    assert verify(linked)["status"] == "PASS"
    assert check_receipt(repo)["status"] == "PASS"


def test_plan_validates_unselected_targets_before_running_any_check(repo):
    config_path = repo / ".mq/verification.json"
    config = json.loads(config_path.read_text())
    config["checks"].append({"id": "missing", "runner": "bash",
        "targets": ["tests/missing.sh"], "paths": ["elsewhere/*"], "timeout_seconds": 2})
    config_path.write_text(json.dumps(config))
    # Even a clean tree must reject the broken, unselected rule.
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "broken rule")
    with pytest.raises(ValueError, match="missing"):
        verify(repo, plan_only=True)
    assert check_receipt(repo)["status"] == "MISSING"


def test_script_target_must_be_a_file(repo):
    config_path = repo / ".mq/verification.json"
    config = json.loads(config_path.read_text())
    config["checks"][0]["targets"] = ["tests"]
    config_path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="file"):
        verify(repo, plan_only=True)


def declare_runtime(repo):
    config_path = repo / ".mq/verification.json"
    config = json.loads(config_path.read_text())
    config["runtime_data"] = [{"path": "history.json", "reason": "Runtime review history; inspect separately."}]
    config_path.write_text(json.dumps(config))
    (repo / "history.json").write_text("[]\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "runtime declaration")


def test_runtime_is_explicit_and_never_counts_as_verified_code(repo):
    declare_runtime(repo)
    change(repo)
    (repo / "history.json").write_text('[{"event": "review"}]\n')
    result = verify(repo)
    assert result["code_status"] == "PASS"
    assert result["status"] == "INCOMPLETE"
    assert result["uncovered_files"] == []
    assert result["runtime_data"] == [{"path": "history.json", "reason": "Runtime review history; inspect separately.", "status": "NOT_VERIFIED"}]
    assert check_receipt(repo)["status"] == "INCOMPLETE"
    (repo / "history.json").write_text("[]\n")
    stale = check_receipt(repo)
    assert stale["status"] == stale["code_status"] == "STALE"


def test_runtime_only_does_not_run_code_checks_even_with_broad_rule(repo):
    declare_runtime(repo)
    p = repo / ".mq/verification.json"
    config = json.loads(p.read_text())
    config["checks"][0]["paths"] = ["*"]
    p.write_text(json.dumps(config))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "broad rule")
    (repo / "history.json").write_text("[1]\n")
    result = verify(repo)
    assert result["checks"] == []
    assert result["code_status"] == "NO_CHANGES"
    assert result["status"] == "INCOMPLETE"
    assert len(result["runtime_data"]) == 1


@pytest.mark.parametrize("entry", [
    {"path": "*.json", "reason": "too broad"},
    {"path": "../outside", "reason": "outside"},
    {"path": "history.json", "reason": ""},
    {"path": "history.json"},
])
def test_runtime_declaration_requires_an_exact_path_and_reason(repo, entry):
    p = repo / ".mq/verification.json"
    config = json.loads(p.read_text())
    config["runtime_data"] = [entry]
    p.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        verify(repo, plan_only=True)


def test_runtime_and_code_results_are_visible_in_human_cli(repo):
    from mq_agent.main import app
    declare_runtime(repo)
    change(repo)
    (repo / "history.json").write_text("[1]\n")
    result = CliRunner().invoke(app, ["verify-changes", str(repo)])
    assert result.exit_code == 1
    assert "Code verification: PASS" in result.stdout
    assert "RUNTIME DATA (NOT_VERIFIED): history.json" in result.stdout


def test_code_failure_takes_priority_over_pending_runtime(repo):
    declare_runtime(repo)
    (repo / "history.json").write_text("[1]\n")
    (repo / "tests/check.sh").write_text("exit 7\n")
    result = verify(repo)
    assert result["status"] == result["code_status"] == "FAIL"
    assert result["runtime_data"][0]["status"] == "NOT_VERIFIED"


def test_missing_rule_blocks_otherwise_selected_checks(repo):
    change(repo)
    (repo / "tests/check.sh").write_text("touch executed-marker\n")
    p = repo / ".mq/verification.json"
    config = json.loads(p.read_text())
    config["checks"].append({"id": "missing", "runner": "bash", "targets": ["missing.sh"],
                             "paths": ["elsewhere/*"], "timeout_seconds": 2})
    p.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="missing"):
        verify(repo)
    assert not (repo / "executed-marker").exists()
