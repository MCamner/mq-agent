"""CLI-level tests for mq-agent memory commands — no OpenAI calls, no real upload."""
import json

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


# ── memory status ──────────────────────────────────────────────────────────

def test_memory_status_runs(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "status", str(tmp_path)])
    assert result.exit_code == 0
    assert "canonical" in result.output


def test_memory_status_json(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_test")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "status", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ready"
    assert data["enabled"] is True
    assert data["vector_store_id"] == "vs_test"


def test_memory_status_json_without_env_reports_canonical(monkeypatch, tmp_path):
    from mq_agent.memory.semantic import CANONICAL_VECTOR_STORE_ID

    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "status", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["enabled"] is True
    assert data["vector_store_id"] == CANONICAL_VECTOR_STORE_ID
    assert data["vector_store_source"] == "canonical"


# ── memory build dry-run ───────────────────────────────────────────────────

def test_memory_build_dry_run_is_default(tmp_path):
    result = runner.invoke(app, ["memory", "build", str(tmp_path)])
    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert "Would run" in result.output


def test_memory_build_dry_run_explicit(tmp_path):
    result = runner.invoke(app, ["memory", "build", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Would run" in result.output


def test_memory_build_no_dry_run_calls_build(monkeypatch, tmp_path):
    import subprocess
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr("mq_agent.memory.semantic.subprocess.run", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "build", str(tmp_path), "--no-dry-run"])
    assert result.exit_code == 0
    assert "built" in result.output.lower()


def test_memory_build_no_dry_run_failure(monkeypatch, tmp_path):
    import subprocess
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
    monkeypatch.setattr("mq_agent.memory.semantic.subprocess.run", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "build", str(tmp_path), "--no-dry-run"])
    assert result.exit_code != 0


# ── memory refresh approval gate ───────────────────────────────────────────

def test_memory_refresh_requires_approve(tmp_path):
    result = runner.invoke(app, ["memory", "refresh", str(tmp_path)])
    assert result.exit_code == 1
    assert "approve" in result.output.lower()


def test_memory_refresh_with_approve(monkeypatch, tmp_path):
    import subprocess
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="uploaded", stderr="")
    monkeypatch.setattr("mq_agent.memory.semantic.subprocess.run", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "refresh", str(tmp_path), "--approve"])
    assert result.exit_code == 0
    assert "refreshed" in result.output.lower()


def test_memory_refresh_approve_propagates_failure(monkeypatch, tmp_path):
    import subprocess
    fake = subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="upload failed")
    monkeypatch.setattr("mq_agent.memory.semantic.subprocess.run", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "refresh", str(tmp_path), "--approve"])
    assert result.exit_code != 0


# ── memory doctor ──────────────────────────────────────────────────────────

def test_memory_doctor_names_the_canonical_store_without_env(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path)])
    assert result.exit_code == 0
    # The operator must be able to see *which* memory answered, not just that one did.
    assert sem.CANONICAL_VECTOR_STORE_ID in result.output
    assert "canonical" in result.output


def test_memory_doctor_healthy(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_abc")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path)])
    assert result.exit_code == 0
    assert "vs_abc" in result.output


def test_memory_doctor_shows_fix_for_missing_repo_signal(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_abc")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: False)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path)])
    assert result.exit_code == 1
    assert "repo-signal" in result.output
    assert "uv pip install" in result.output


def test_memory_doctor_json_healthy(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_xyz")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["healthy"] is True
    assert all(item["ok"] for item in data["items"])


def test_memory_doctor_json_unhealthy(monkeypatch, tmp_path):
    """repo-signal, not the store, is now the only thing that can be missing."""
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: False)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path), "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["healthy"] is False
    failing = [i for i in data["items"] if not i["ok"]]
    assert [i["label"] for i in failing] == ["repo-signal"]


def test_memory_doctor_json_reports_the_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_override")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    store = next(i for i in data["items"] if i["label"] == "vector store")
    assert "vs_override" in store["detail"]
    assert sem.CANONICAL_VECTOR_STORE_ID not in store["detail"]
