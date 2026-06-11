"""Tests for the standard mqobsidian export structure (vault_structure)."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import vault_structure as vault_structure_registered
from mq_agent.tools.vault_structure import STANDARD_DIRS, vault_structure

runner = CliRunner()

STANDARD_PATHS = [spec["path"] for spec in STANDARD_DIRS]


@pytest.fixture
def vault(tmp_path, monkeypatch) -> Path:
    """Empty vault directory, wired in as the module default."""
    root = tmp_path / "mqobsidian"
    root.mkdir()
    monkeypatch.delenv("MQ_OBSIDIAN_DIR", raising=False)
    # The package __init__ re-exports the function under the module's name,
    # so resolve the real module before patching its constant.
    module = importlib.import_module("mq_agent.tools.vault_structure")
    monkeypatch.setattr(module, "DEFAULT_VAULT_DIR", root)
    return root


def _complete(vault: Path) -> None:
    for rel in STANDARD_PATHS:
        (vault / rel).mkdir(parents=True, exist_ok=True)


class TestCheck:
    def test_empty_vault_is_incomplete(self, vault):
        data = json.loads(vault_structure())
        assert data["status"] == "INCOMPLETE"
        assert [d["path"] for d in data["dirs"]] == STANDARD_PATHS
        assert all(not d["exists"] for d in data["dirs"])

    def test_complete_vault_is_ok(self, vault):
        _complete(vault)
        data = json.loads(vault_structure())
        assert data["status"] == "OK"
        assert all(d["exists"] for d in data["dirs"])

    def test_missing_vault_is_no_vault(self, vault):
        vault.rmdir()
        data = json.loads(vault_structure(init=True))
        assert data["status"] == "NO_VAULT"
        assert not vault.exists(), "init must never create the vault itself"

    def test_check_is_read_only(self, vault):
        vault_structure()
        assert list(vault.iterdir()) == []

    def test_notes_counted_recursively(self, vault):
        _complete(vault)
        learn = vault / "memory" / "learn"
        (learn / "pattern.md").write_text("x")
        (learn / "verified").mkdir()
        (learn / "verified" / "promoted.md").write_text("x")
        data = json.loads(vault_structure())
        entry = next(d for d in data["dirs"] if d["path"] == "memory/learn")
        assert entry["notes"] == 2
        assert entry["newest"] is not None

    def test_legacy_root_dirs_reported(self, vault):
        _complete(vault)
        (vault / "reviews").mkdir()
        (vault / "reviews" / "old.md").write_text("x")
        (vault / "learn").mkdir()  # empty — should not be reported
        data = json.loads(vault_structure())
        assert data["legacy"] == [{
            "path": "reviews",
            "standard": "memory/reviews",
            "notes": 1,
            "newest": data["legacy"][0]["newest"],
        }]


class TestInit:
    def test_init_creates_dirs_with_readme(self, vault):
        data = json.loads(vault_structure(init=True))
        assert data["status"] == "OK"
        assert data["created"] == STANDARD_PATHS
        for rel in STANDARD_PATHS:
            readme = vault / rel / "README.md"
            assert readme.is_file()
            assert rel in readme.read_text()

    def test_init_is_idempotent_and_keeps_existing(self, vault):
        truth = vault / "memory" / "stack-truth"
        truth.mkdir(parents=True)
        note = truth / "2026-06-01-mq-stack-truth.md"
        note.write_text("existing")
        data = json.loads(vault_structure(init=True))
        assert "memory/stack-truth" not in data["created"]
        assert note.read_text() == "existing"
        assert not (truth / "README.md").exists(), \
            "init must not write into pre-existing dirs"
        assert json.loads(vault_structure(init=True))["created"] == []


class TestCli:
    def test_check_incomplete_exits_1(self, vault):
        result = runner.invoke(app, ["brain", "structure"])
        assert result.exit_code == 1
        assert "INCOMPLETE" in result.output
        assert "--init --approve" in result.output

    def test_check_ok_exits_0(self, vault):
        _complete(vault)
        result = runner.invoke(app, ["brain", "structure"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_init_without_approve_is_blocked(self, vault):
        result = runner.invoke(app, ["brain", "structure", "--init"])
        assert result.exit_code == 1
        assert "--approve" in result.output
        assert list(vault.iterdir()) == []

    def test_init_with_approve_creates_structure(self, vault):
        result = runner.invoke(app, ["brain", "structure", "--init", "--approve"])
        assert result.exit_code == 0
        assert "created:" in result.output
        for rel in STANDARD_PATHS:
            assert (vault / rel).is_dir()

    def test_json_output(self, vault):
        _complete(vault)
        result = runner.invoke(app, ["brain", "structure", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "OK"
        assert len(data["dirs"]) == len(STANDARD_PATHS)

    def test_missing_vault_message(self, vault):
        vault.rmdir()
        result = runner.invoke(app, ["brain", "structure"])
        assert result.exit_code == 1
        assert "Vault not found" in result.output

    def test_registered_in_tool_registry(self):
        from mq_agent.tools import TOOL_REGISTRY
        assert TOOL_REGISTRY["vault_structure"] is vault_structure
        assert vault_structure_registered is vault_structure
