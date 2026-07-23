"""Tests for stack contract-check command and _contract_entry helper."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

import mq_agent.tools.stack_tools as stack_tools
from mq_agent.main import app
from mq_agent.tools.stack_tools import _contract_entry

runner = CliRunner()


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def bare_repo(tmp_path):
    """Git repo with VERSION and README — no .mq/ contract."""
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)
    (repo / "VERSION").write_text("1.0.0\n")
    (repo / "README.md").write_text("# bare\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


@pytest.fixture()
def contract_repo(bare_repo):
    """bare_repo with a valid, version-matched .mq/repo-contract.json committed."""
    mq = bare_repo / ".mq"
    mq.mkdir()
    (mq / "repo-contract.json").write_text(json.dumps({
        "repo": "test-repo",
        "role": "tester",
        "version": "1.0.0",
        "status": "active",
        "contracts": ["test.v1"],
        "next_focus": "",
    }))
    subprocess.run(["git", "add", "."], cwd=bare_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add contract"], cwd=bare_repo, capture_output=True)
    return bare_repo


# ── _contract_entry unit tests ───────────────────────────────────────────────

class TestContractEntry:
    def test_nonexistent_repo_returns_blocked(self, tmp_path):
        e = _contract_entry({"name": "ghost", "path": str(tmp_path / "nope")})
        assert e["status"] == "BLOCKED"
        assert "not found" in e["reason"]

    def test_missing_contract_returns_blocked(self, bare_repo):
        e = _contract_entry({"name": "test", "path": str(bare_repo)})
        assert e["status"] == "BLOCKED"
        assert "repo-contract.json" in e["reason"]

    def test_invalid_json_returns_blocked(self, bare_repo):
        (bare_repo / ".mq").mkdir()
        (bare_repo / ".mq" / "repo-contract.json").write_text("not-json{{{")
        e = _contract_entry({"name": "test", "path": str(bare_repo)})
        assert e["status"] == "BLOCKED"
        assert "invalid" in e["reason"].lower()

    def test_missing_required_fields_returns_blocked(self, bare_repo):
        (bare_repo / ".mq").mkdir()
        (bare_repo / ".mq" / "repo-contract.json").write_text(json.dumps({"repo": "test"}))
        e = _contract_entry({"name": "test", "path": str(bare_repo)})
        assert e["status"] == "BLOCKED"
        assert "missing fields" in e["reason"]

    def test_version_mismatch_returns_drift(self, bare_repo):
        (bare_repo / ".mq").mkdir()
        (bare_repo / ".mq" / "repo-contract.json").write_text(json.dumps({
            "repo": "test", "role": "tester", "version": "9.9.9",
            "status": "active", "contracts": [],
        }))
        e = _contract_entry({"name": "test", "path": str(bare_repo)})
        assert e["status"] == "DRIFT"
        assert "version mismatch" in e["reason"]
        assert "9.9.9" in e["reason"]
        assert "1.0.0" in e["reason"]

    def test_valid_contract_returns_ready_or_review(self, contract_repo):
        e = _contract_entry({"name": "test", "path": str(contract_repo)})
        assert e["status"] in ("READY", "REVIEW")

    @pytest.mark.parametrize("mode", ["direct", "pull_request", "manual"])
    def test_valid_release_modes_are_accepted(self, contract_repo, mode):
        contract_path = contract_repo / ".mq" / "repo-contract.json"
        contract = json.loads(contract_path.read_text())
        contract["release_mode"] = mode
        contract_path.write_text(json.dumps(contract))

        e = _contract_entry({"name": "test", "path": str(contract_repo)})

        assert e["status"] in ("READY", "REVIEW")

    def test_unknown_release_mode_returns_blocked(self, contract_repo):
        contract_path = contract_repo / ".mq" / "repo-contract.json"
        contract = json.loads(contract_path.read_text())
        contract["release_mode"] = "automatic"
        contract_path.write_text(json.dumps(contract))

        e = _contract_entry({"name": "test", "path": str(contract_repo)})

        assert e["status"] == "BLOCKED"
        assert "release_mode" in e["reason"]

    def test_clean_tree_returns_ready(self, contract_repo):
        e = _contract_entry({"name": "test", "path": str(contract_repo)})
        assert e["status"] == "READY"

    def test_dirty_tree_returns_review(self, contract_repo):
        (contract_repo / "dirty.txt").write_text("unstaged\n")
        e = _contract_entry({"name": "test", "path": str(contract_repo)})
        assert e["status"] == "REVIEW"
        assert "uncommitted" in e["reason"]

    def test_contract_dict_present_on_ready(self, contract_repo):
        e = _contract_entry({"name": "test", "path": str(contract_repo)})
        assert "contract" in e
        assert e["contract"]["repo"] == "test-repo"

    def test_schema_keys_always_present(self, contract_repo):
        e = _contract_entry({"name": "test", "path": str(contract_repo)})
        for key in ("name", "status", "reason"):
            assert key in e

    def test_no_readme_returns_blocked(self, bare_repo):
        (bare_repo / "README.md").unlink()
        e = _contract_entry({"name": "test", "path": str(bare_repo)})
        assert e["status"] == "BLOCKED"
        assert "README" in e["reason"]

    def test_no_version_returns_blocked(self, bare_repo):
        (bare_repo / "VERSION").unlink()
        e = _contract_entry({"name": "test", "path": str(bare_repo)})
        assert e["status"] == "BLOCKED"
        assert "VERSION" in e["reason"]


def test_repo_contract_schema_keeps_release_mode_closed():
    schema_path = Path(__file__).parents[1] / "schemas" / "mq_stack_repo_contract.schema.json"
    schema = json.loads(schema_path.read_text())

    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["release_mode"]["enum"] == [
        "direct",
        "pull_request",
        "manual",
    ]


def test_repo_contract_schema_accepts_pointer_contract_fields():
    schema_path = Path(__file__).parents[1] / "schemas" / "mq_stack_repo_contract.schema.json"
    schema = json.loads(schema_path.read_text())
    contract = {
        "schema": "mq-stack-repo-contract.pointer.v1",
        "repo": "macos-scripts",
        "role": "human-terminal-entrypoint",
        "version": "1.0.1",
        "status": "active",
        "canonical_contract": ".mq/context/repo-contract.json",
        "contracts": ["mq-stack-repo-contract.v1"],
        "release_mode": "pull_request",
    }

    Draft202012Validator(schema).validate(contract)


def test_stack_contract_check_includes_mqobsidian(contract_repo, monkeypatch):
    entries = [
        {"name": "mq-agent", "path": str(contract_repo), "role": "orchestrator"},
        {"name": "mqobsidian", "path": str(contract_repo), "role": "truth"},
    ]
    monkeypatch.setattr(stack_tools, "MQ_STACK_REPOS", entries)

    result = json.loads(stack_tools.stack_contract_check())

    assert [entry["name"] for entry in result["repos"]] == [
        "mq-agent",
        "mqobsidian",
    ]


# ── CLI tests ────────────────────────────────────────────────────────────────

def _ready_payload(name: str = "mq-agent") -> dict:
    return {
        "overall": "READY",
        "reasons": [],
        "repos": [{"name": name, "status": "READY", "reason": "", "contract": {}}],
        "checked_at": "2026-06-10T00:00:00+00:00",
    }


def _not_ready_payload() -> dict:
    return {
        "overall": "NOT READY",
        "reasons": ["mq-hal: missing .mq/repo-contract.json"],
        "repos": [
            {"name": "mq-agent", "status": "READY", "reason": ""},
            {"name": "mq-hal", "status": "DRIFT", "reason": "missing .mq/repo-contract.json"},
        ],
        "checked_at": "2026-06-10T00:00:00+00:00",
    }


class TestStackContractCheckCmd:
    def test_json_output_is_valid(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_ready_payload())):
            result = runner.invoke(app, ["stack", "contract-check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall" in data
        assert "repos" in data

    def test_json_exit_0_on_ready(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_ready_payload())):
            result = runner.invoke(app, ["stack", "contract-check", "--json"])
        assert result.exit_code == 0

    def test_json_exit_1_on_not_ready(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_not_ready_payload())):
            result = runner.invoke(app, ["stack", "contract-check", "--json"])
        assert result.exit_code == 1

    def test_text_contains_repo_name(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_ready_payload("mq-agent"))):
            result = runner.invoke(app, ["stack", "contract-check"])
        assert "mq-agent" in result.output

    def test_text_exit_0_on_ready(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_ready_payload())):
            result = runner.invoke(app, ["stack", "contract-check"])
        assert result.exit_code == 0
        assert "READY" in result.output

    def test_text_exit_1_on_drift(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_not_ready_payload())):
            result = runner.invoke(app, ["stack", "contract-check"])
        assert result.exit_code == 1
        assert "NOT READY" in result.output

    def test_text_shows_reason_on_failure(self):
        with patch("mq_agent.tools.stack_tools.stack_contract_check",
                   return_value=json.dumps(_not_ready_payload())):
            result = runner.invoke(app, ["stack", "contract-check"])
        assert "mq-hal" in result.output
