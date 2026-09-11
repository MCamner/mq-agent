"""mq-agent's memory has a name, and every surface says where that name came from.

The identity used to live only in gitignored `.env` files. With none present
`memory status` reported `missing-vector-store`, so mq-agent had no memory at
all, while the macos-scripts shell consumers silently fell back to a *different*
store. Which memory answered depended on untracked files on the machine.

The contract these tests fix:

    OPENAI_VECTOR_STORE_ID set  ->  explicit override
    unset / whitespace          ->  canonical store
    status / doctor / JSON      ->  always show which of the two applied

Resolution reads the process environment and nothing else — no `.env`
discovery, no shell-out — so the answer cannot change with the directory the
command happens to run in.
"""

import json
import subprocess

from typer.testing import CliRunner

import mq_agent.memory.semantic as sem
from mq_agent.main import app
from mq_agent.memory.semantic import (
    CANONICAL_VECTOR_STORE_ID,
    resolve_vector_store_id,
    status,
)

runner = CliRunner()


# --- the resolution contract ----------------------------------------------


def test_an_explicit_id_wins_and_is_named_as_explicit(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_explicit")
    assert resolve_vector_store_id() == ("vs_explicit", "OPENAI_VECTOR_STORE_ID")


def test_no_environment_falls_back_to_the_canonical_store(monkeypatch):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    assert resolve_vector_store_id() == (CANONICAL_VECTOR_STORE_ID, "canonical")


def test_an_empty_or_whitespace_value_is_not_an_override(monkeypatch):
    for value in ("", "   ", "\t\n"):
        monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", value)
        assert resolve_vector_store_id() == (CANONICAL_VECTOR_STORE_ID, "canonical")


def test_surrounding_whitespace_does_not_change_an_explicit_id(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "  vs_explicit  ")
    assert resolve_vector_store_id() == ("vs_explicit", "OPENAI_VECTOR_STORE_ID")


def test_the_canonical_id_is_a_declared_constant():
    """Declared in the repository, not recovered from the machine."""
    assert CANONICAL_VECTOR_STORE_ID.startswith("vs_")
    assert CANONICAL_VECTOR_STORE_ID.strip() == CANONICAL_VECTOR_STORE_ID
    assert len(CANONICAL_VECTOR_STORE_ID) > len("vs_")


# --- what resolution must not do ------------------------------------------


def test_a_dotenv_file_in_the_working_directory_is_ignored(monkeypatch, tmp_path):
    """Identity must not depend on which directory the command ran in."""
    (tmp_path / ".env").write_text(
        "OPENAI_VECTOR_STORE_ID=vs_from_a_dotenv_file\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)

    assert resolve_vector_store_id() == (CANONICAL_VECTOR_STORE_ID, "canonical")


def test_resolution_runs_no_subprocess(monkeypatch):
    """A login shell is slow, can hang, and can print text that reads as a value."""
    def _forbidden(*args, **kwargs):
        raise AssertionError("config resolution must not shell out")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(subprocess, "check_output", _forbidden)
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)

    resolve_vector_store_id()


def test_resolution_reads_only_the_one_variable(monkeypatch):
    """A neighbouring repo's variable is not this repo's configuration."""
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setenv("MQ_REPO_VECTOR_STORE_ID", "vs_macos_scripts")
    monkeypatch.setenv("MQ_TERMINAL_GUIDE_VECTOR_STORE_ID", "vs_terminal_guide")

    store_id, source = resolve_vector_store_id()
    assert store_id == CANONICAL_VECTOR_STORE_ID
    assert source == "canonical"


# --- status ---------------------------------------------------------------


def test_status_always_has_an_id_and_a_source(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    state = status(tmp_path)
    assert state.vector_store_id == CANONICAL_VECTOR_STORE_ID
    assert state.vector_store_source == "canonical"
    assert state.status == "ready"
    assert state.enabled is True


def test_status_no_longer_reports_a_missing_store(monkeypatch, tmp_path):
    """mq-agent is never without a memory, so the state cannot occur."""
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: False)

    state = status(tmp_path)
    assert state.status == "missing-repo-signal"
    assert "missing-vector-store" != state.status


def test_status_json_names_the_source(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    result = runner.invoke(app, ["memory", "status", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["vector_store_id"] == CANONICAL_VECTOR_STORE_ID
    assert data["vector_store_source"] == "canonical"


def test_status_json_names_an_explicit_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_explicit")
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    result = runner.invoke(app, ["memory", "status", str(tmp_path), "--json"])
    data = json.loads(result.output)
    assert data["vector_store_id"] == "vs_explicit"
    assert data["vector_store_source"] == "OPENAI_VECTOR_STORE_ID"


def test_status_screen_shows_the_source(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    result = runner.invoke(app, ["memory", "status", str(tmp_path)])
    assert result.exit_code == 0
    assert "canonical" in result.output


# --- doctor ---------------------------------------------------------------


def test_doctor_is_healthy_without_the_environment_variable(monkeypatch, tmp_path):
    """An unset override is a normal state, not a fault to be fixed."""
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    result = runner.invoke(app, ["memory", "doctor", str(tmp_path)])
    assert result.exit_code == 0
    assert "canonical" in result.output


def test_doctor_json_names_the_source(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    result = runner.invoke(app, ["memory", "doctor", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    store = next(i for i in data["items"] if i["label"] == "vector store")
    assert store["ok"] is True
    assert CANONICAL_VECTOR_STORE_ID in store["detail"]
    assert "canonical" in store["detail"]


def test_doctor_json_names_an_explicit_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_explicit")
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)

    result = runner.invoke(app, ["memory", "doctor", str(tmp_path), "--json"])
    data = json.loads(result.output)
    store = next(i for i in data["items"] if i["label"] == "vector store")
    assert "vs_explicit" in store["detail"]
    assert "OPENAI_VECTOR_STORE_ID" in store["detail"]
