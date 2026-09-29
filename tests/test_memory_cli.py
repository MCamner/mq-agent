"""CLI-level tests for mq-agent memory commands — no OpenAI calls, no real upload."""
import json

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()


# ── memory status ──────────────────────────────────────────────────────────

def test_memory_status_runs(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    result = runner.invoke(app, ["memory", "status", str(tmp_path)])
    assert result.exit_code == 0
    # No override is a normal state: the canonical store answers and says so.
    assert "canonical" in result.output


def test_memory_status_json(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_test")
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "status", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "degraded"
    assert data["enabled"] is False
    assert data["configured"] is True
    assert data["reachable"] is None
    assert data["freshness"] == "unknown"
    assert data["vector_store_id"] == "vs_test"


def test_memory_status_json_without_an_override(monkeypatch, tmp_path):
    from mq_agent.memory.semantic import CANONICAL_VECTOR_STORE_ID

    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    result = runner.invoke(app, ["memory", "status", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
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


def test_memory_build_no_dry_run_uses_refresh_safety(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import mq_agent.memory.semantic as sem

    seen = {}
    fake = SimpleNamespace(
        returncode=0,
        stdout="uploaded",
        stderr="",
        error="",
        uploaded=True,
    )

    def _refresh(path, *, cleanup_stale=False):
        seen["cleanup_stale"] = cleanup_stale
        return fake

    monkeypatch.setattr(sem, "refresh", _refresh)
    result = runner.invoke(app, ["memory", "build", str(tmp_path), "--no-dry-run"])

    assert result.exit_code == 0
    assert seen["cleanup_stale"] is False
    assert "built" in result.output.lower()


def test_memory_build_no_dry_run_propagates_refresh_failure(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import mq_agent.memory.semantic as sem

    fake = SimpleNamespace(
        returncode=2,
        stdout="",
        stderr="",
        error="replacement requires cleanup",
        uploaded=False,
    )
    monkeypatch.setattr(sem, "refresh", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "build", str(tmp_path), "--no-dry-run"])

    assert result.exit_code != 0


# ── memory refresh approval gate ───────────────────────────────────────────

def test_memory_refresh_requires_approve(tmp_path):
    result = runner.invoke(app, ["memory", "refresh", str(tmp_path)])
    assert result.exit_code == 1
    assert "approve" in result.output.lower()


def test_memory_refresh_with_approve(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import mq_agent.memory.semantic as sem

    fake = SimpleNamespace(
        returncode=0,
        stdout="uploaded",
        stderr="",
        detached=(),
        error="",
        postcondition_status="PASS",
        uploaded=True,
    )
    monkeypatch.setattr(sem, "refresh", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "refresh", str(tmp_path), "--approve"])
    assert result.exit_code == 0
    assert "refreshed" in result.output.lower()


def test_memory_refresh_approve_propagates_failure(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import mq_agent.memory.semantic as sem

    fake = SimpleNamespace(
        returncode=2,
        stdout="",
        stderr="upload failed",
        detached=(),
        error="replacement requires cleanup",
        postcondition_status="FAIL",
        uploaded=False,
    )
    monkeypatch.setattr(sem, "refresh", lambda *a, **kw: fake)
    result = runner.invoke(app, ["memory", "refresh", str(tmp_path), "--approve"])
    assert result.exit_code != 0


def test_memory_refresh_cleanup_flag_is_explicit(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import mq_agent.memory.semantic as sem

    seen = {}
    fake = SimpleNamespace(
        returncode=0,
        stdout="uploaded",
        stderr="",
        detached=("vs:file_old",),
        error="",
        postcondition_status="PASS",
        uploaded=True,
    )

    def _refresh(path, *, cleanup_stale=False):
        seen["cleanup_stale"] = cleanup_stale
        return fake

    monkeypatch.setattr(sem, "refresh", _refresh)
    result = runner.invoke(
        app,
        ["memory", "refresh", str(tmp_path), "--approve", "--cleanup-stale"],
    )
    assert result.exit_code == 0
    assert seen["cleanup_stale"] is True
    assert "Detached 1" in result.output


# ── memory doctor ──────────────────────────────────────────────────────────

def test_memory_doctor_does_not_fail_on_a_missing_override(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path)])
    assert result.exit_code == 0
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
    """A real fault still fails; the vector store is no longer one of them."""
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    import mq_agent.memory.semantic as sem
    monkeypatch.setattr(sem, "repo_signal_available", lambda: False)
    result = runner.invoke(app, ["memory", "doctor", str(tmp_path), "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["healthy"] is False
    failing = [i for i in data["items"] if not i["ok"]]
    assert any(i["label"] == "repo-signal" for i in failing)
    assert all(i["label"] != "vector store" for i in failing)
